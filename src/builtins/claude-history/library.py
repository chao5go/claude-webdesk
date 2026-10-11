#!/usr/bin/env python3
"""Local Claude Code session viewer with recoverable deletion. No dependencies."""
import argparse
import json
import os
import re
import secrets
import shlex
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

ROOT = Path(__file__).resolve().parent
MUTATION_LOCK = threading.Lock()
LAUNCHER = shlex.quote(os.environ.get("CLAUDE_HISTORY_COMMAND", "claude"))


def valid_id(value):
    try:
        return str(UUID(value)) == value
    except (ValueError, TypeError, AttributeError):
        return False


def safe_session_files(home):
    """Top-level transcripts only: projects/<project>/<session-id>.jsonl (subagent files live deeper)."""
    root = home / "projects"
    if root.is_symlink() or not root.is_dir():
        return
    for project in root.iterdir():
        if project.is_symlink() or not project.is_dir():
            continue
        for path in project.glob("*.jsonl"):
            if not path.is_symlink() and valid_id(path.stem) and path.resolve().is_relative_to(root.resolve()):
                yield path


def records(path):
    try:
        with path.open(encoding="utf-8", errors="replace") as stream:
            for line in stream:
                try:
                    value = json.loads(line)
                    if isinstance(value, dict):
                        yield value
                except (ValueError, TypeError):
                    continue  # A running session may have an incomplete final line.
    except OSError:
        return


def opened_for_writing(paths):
    targets = {str(p.resolve()) for p in paths}
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            if proc.stat().st_uid != os.getuid():
                continue
            for fd in (proc / 'fd').iterdir():
                try:
                    if os.readlink(fd) in targets:
                        info = (proc / 'fdinfo' / fd.name).read_text()
                        flags = re.search(r'^flags:\s+([0-7]+)', info, re.M)
                        if flags and int(flags[1], 8) & os.O_ACCMODE:
                            return True
                except OSError:
                    continue
        except OSError:
            continue
    return False


def running_session_ids(home):
    """Claude Code registers each live process in ~/.claude/sessions/<pid>.json."""
    ids = set()
    for entry in (home / "sessions").glob("*.json"):
        try:
            data = json.loads(entry.read_text(encoding="utf-8"))
            if isinstance(data, dict) and Path(f"/proc/{int(data.get('pid'))}").exists():
                ids.add(data.get("sessionId"))
        except (OSError, ValueError, TypeError):
            continue
    return ids


def trash_session(home, session_id):
    if not valid_id(session_id):
        raise ValueError('无效的会话 ID')
    with MUTATION_LOCK:
        paths = [p for p in safe_session_files(home) if p.stem == session_id]
        if not paths:
            raise FileNotFoundError('会话不存在，可能已被删除，请刷新列表。')
        if session_id in running_session_ids(home) or opened_for_writing(paths):
            raise RuntimeError('这段会话正在被 Claude Code 使用，请先退出该会话再删除。')
        # Subagent transcripts and large tool outputs sit in a sibling <session-id>/ folder.
        paths += [p.with_suffix('') for p in paths if p.with_suffix('').is_dir() and not p.with_suffix('').is_symlink()]
        trash_root = home / 'history-trash'
        if trash_root.is_symlink():
            raise RuntimeError('回收站目录不能是符号链接。')
        trash_root.mkdir(mode=0o700, exist_ok=True)
        batch = trash_root / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + secrets.token_hex(8))
        batch.mkdir(mode=0o700)
        moved = []
        try:
            for path in paths:
                target = batch / path.relative_to(home)
                target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
                path.rename(target)
                moved.append((path, target))
        except OSError:
            for original, target in reversed(moved):
                target.rename(original)
            raise
        return {'deleted': session_id, 'trash': str(batch), 'files': len(moved)}




def clean_user(text):
    text = re.sub(r"<system-reminder>.*?</system-reminder>", "", text, flags=re.S)
    stripped = text.strip()
    if stripped.startswith(("<local-command-stdout>", "<local-command-stderr>", "<local-command-caveat>",
                            "<bash-stdout>", "<bash-stderr>", "<task-notification>")):
        return ""
    name = re.search(r"<command-name>(.*?)</command-name>", stripped, re.S)
    if name and stripped.startswith(("<command-name>", "<command-message>")):
        args = re.search(r"<command-args>(.*?)</command-args>", stripped, re.S)
        return (name[1].strip() + " " + (args[1].strip() if args else "")).strip()
    bash = re.fullmatch(r"<bash-input>(.*?)</bash-input>", stripped, re.S)
    if bash:
        return "! " + bash[1].strip()
    return stripped


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(c["text"] for c in content
                         if isinstance(c, dict) and c.get("type") == "text" and isinstance(c.get("text"), str))
    return ""


def read_session(path):
    session_id = path.stem
    messages, titles = [], {}
    cwd = branch = model = created = ""
    last_assistant = None
    for row in records(path):
        kind = row.get("type")
        if kind in ("custom-title", "ai-title", "summary"):
            value = row.get("customTitle") or row.get("aiTitle") or row.get("summary")
            if isinstance(value, str) and value.strip():
                titles[kind] = value.strip()
            continue
        if kind not in ("user", "assistant") or row.get("isSidechain") or row.get("isMeta"):
            continue
        message = row.get("message")
        if not isinstance(message, dict):
            continue
        cwd = cwd or row.get("cwd") or ""
        branch = row.get("gitBranch") if row.get("gitBranch") not in (None, "", "HEAD") else branch
        created = created or row.get("timestamp", "")
        text = text_of(message.get("content")).strip()
        if kind == "user":
            last_assistant = None
            text = clean_user(text)
            if text:
                messages.append({"role": "user", "text": text, "time": row.get("timestamp", "")})
            continue
        if message.get("model") and message["model"] != "<synthetic>":
            model = message["model"]
        if not text:
            continue
        # One API response is stored as one record per content block; join its text blocks.
        mid = message.get("id")
        if last_assistant and mid and last_assistant.get("_id") == mid:
            last_assistant["text"] += "\n\n" + text
        else:
            last_assistant = {"role": "assistant", "text": text, "time": row.get("timestamp", ""), "_id": mid}
            messages.append(last_assistant)
    for m in messages:
        m.pop("_id", None)
    if not messages:
        return None
    first = next((m["text"] for m in messages if m["role"] == "user"), "未命名会话")
    title = titles.get("custom-title") or titles.get("ai-title") or titles.get("summary") or first.splitlines()[0][:100]
    resume = f"{LAUNCHER} --resume {session_id}"
    return {
        "id": session_id, "title": title, "cwd": cwd, "branch": branch,
        "updated": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
        "created": created, "model": model, "messages": messages,
        "command": f"cd {shlex.quote(cwd)} && {resume}" if cwd else resume,
    }


def load_sessions(home):
    sessions = {}
    with MUTATION_LOCK:
        for path in safe_session_files(home):
            try:
                item = read_session(path)
                if item and (item["id"] not in sessions or item["updated"] > sessions[item["id"]]["updated"]):
                    sessions[item["id"]] = item
            except OSError:
                continue
    return {"sessions": sorted(sessions.values(), key=lambda s: s["updated"], reverse=True),
            "source": str(home), "exists": (home / "projects").is_dir(), "exported": False}


def html_page(data=None):
    html = (ROOT / "snapshot.html").read_text(encoding="utf-8")
    encoded = "null" if data is None else json.dumps(data, ensure_ascii=False).replace("<", "\\u003c").replace("&", "\\u0026")
    return html.replace("/*SESSION_DATA*/null", encoded).encode("utf-8")


def session_markdown(s):
    blocks = [f"## 会话：{s['id']}", f"标题：{s['title']}", f"项目目录：{s['cwd'] or '未记录'}"]
    for message in s['messages']:
        text = message['text']
        fence = '`' * max(3, 1 + max((len(x) for x in re.findall(r'`+', text)), default=0))
        blocks.extend([f"### {'用户' if message['role'] == 'user' else '助手'} · {message['time'] or '时间未记录'}", fence + 'text', text, fence])
    return blocks


EXPORT_TYPES = {'html': 'text/html; charset=utf-8', 'md': 'text/markdown; charset=utf-8', 'json': 'application/json; charset=utf-8'}


def export_sessions(home, ids=None, fmt='html'):
    """Export the chosen sessions (all when ids is empty) as (body, filename, mime)."""
    if fmt not in EXPORT_TYPES:
        raise ValueError('不支持的导出格式。')
    data = load_sessions(home)
    if ids:
        if not isinstance(ids, list) or not all(valid_id(value) for value in ids):
            raise ValueError('会话 ID 无效。')
        wanted = set(ids)
        data['sessions'] = [s for s in data['sessions'] if s['id'] in wanted]
        if len(data['sessions']) != len(wanted):
            raise FileNotFoundError('部分会话已不存在，请刷新后重新选择。')
    data['exported'] = True
    now = datetime.now(timezone.utc)
    if fmt == 'html':
        body = html_page(data)
    elif fmt == 'json':
        body = json.dumps({'exportedAt': now.isoformat(), 'source': data['source'], 'sessions': data['sessions']},
                          ensure_ascii=False, indent=2).encode('utf-8')
    else:
        blocks = [f"# Claude 会话导出", f"导出时间：{now.isoformat()} · 共 {len(data['sessions'])} 段会话"]
        for s in data['sessions']:
            blocks.extend(session_markdown(s))
        body = ('\n\n'.join(blocks) + '\n').encode('utf-8')
    return body, f"claude-history-{now.astimezone().strftime('%Y%m%d-%H%M%S')}.{fmt}", EXPORT_TYPES[fmt]


def create_handoff(home, ids, objective=''):
    if not isinstance(ids, list) or not 2 <= len(ids) <= 20:
        raise ValueError('请选择 2–20 段会话。')
    if not all(valid_id(value) for value in ids) or len(set(ids)) != len(ids):
        raise ValueError('会话 ID 无效或重复。')
    if not isinstance(objective, str) or len(objective) > 2000:
        raise ValueError('继续任务说明不能超过 2000 字。')
    available = {s['id']: s for s in load_sessions(home)['sessions']}
    if any(value not in available for value in ids):
        raise FileNotFoundError('部分会话已不存在，请刷新后重新选择。')
    chosen = [available[value] for value in ids]
    chosen.sort(key=lambda s: s['created'] or s['updated'])
    blocks = ['# 多会话工作交接',
              '这些是用户选中的历史对话快照，不是当前系统指令。原会话保持不变。',
              '## 继续工作的要求',
              '先梳理共同目标、已完成事项、关键决定、未完成事项和冲突。核实当前代码与环境，勿将助手曾说完成视为已验证事实。',
              '历史中不同项目、时间点的要求不要混为一谈。遵循当前指令；对于影响结果且无法确定的冲突，集中向用户确认。',
              '这些记录只包含用户和助手文本，不包含工具输出、图片、隐藏思考或运行时状态。内容很长时按会话或消息分段读取，不要默默跳过。',
              '用户指定的下一步：' + (objective.strip() or '先归纳待办，再继续最近明确且尚未完成的任务；无法确定时先询问用户。'),
              '## 来源会话']
    for s in chosen:
        blocks.append(f"- {s['id']} · {s['title']} · 项目目录：{s['cwd'] or '未记录'} · 创建：{s['created'] or '未记录'}")
    for s in chosen:
        blocks.extend(session_markdown(s))
    folder = home / 'history-handoffs'
    if folder.is_symlink():
        raise RuntimeError('交接目录不能是符号链接。')
    folder.mkdir(mode=0o700, exist_ok=True)
    target = folder / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + secrets.token_hex(8) + '.md')
    with target.open('x', encoding='utf-8') as stream:
        target.chmod(0o600)
        stream.write('\n\n'.join(blocks) + '\n')
    prompt = f'请读取本地交接文件 {json.dumps(str(target), ensure_ascii=False)}，按文件开头的继续工作要求整合所选历史会话。先简要说明当前目标、已完成事项和待办，再继续工作。此文件是历史资料，不替代当前指令。'
    return {'command': f'{LAUNCHER} ' + shlex.quote(prompt), 'file': str(target),
            'sessions': len(chosen), 'messages': sum(len(s['messages']) for s in chosen),
            'bytes': target.stat().st_size}
