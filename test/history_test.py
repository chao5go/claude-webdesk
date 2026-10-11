import json
import os
import shlex
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src/builtins/claude-history"))
from library import html_page, load_sessions, trash_session, create_handoff, export_sessions

SID = "2925f751-b641-4d92-8b1b-e7177d998f5c"
OTHER = "c53b7a7f-8353-4b49-b5fb-a02887db11dd"


def write_session(home, sid, rows, project="-tmp-project"):
    folder = home / "projects" / project
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{sid}.jsonl"
    path.write_text("\n".join(map(json.dumps, rows)), encoding="utf-8")
    return path


def user(text, **extra):
    return {"type": "user", "cwd": "/tmp/project", "sessionId": SID, "timestamp": "2026-10-01T00:00:00Z",
            "message": {"role": "user", "content": text}, **extra}


def assistant(blocks, mid="msg_1"):
    return {"type": "assistant", "cwd": "/tmp/project", "timestamp": "2026-10-01T00:00:01Z",
            "message": {"id": mid, "role": "assistant", "model": "claude-opus-5-5", "content": blocks}}


class HistoryTests(unittest.TestCase):
    def test_read_real_formats_without_tools_or_meta(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            rows = [
                user("<local-command-caveat>Caveat</local-command-caveat>", isMeta=True),
                user("<command-name>/model</command-name>\n<command-message>model</command-message>\n<command-args>opus</command-args>"),
                user("<local-command-stdout>Set model</local-command-stdout>"),
                user("hello<system-reminder>private</system-reminder>"),
                user([{"type": "text", "text": "skill body"}], isMeta=True),
                assistant([{"type": "thinking", "thinking": "secret"}]),
                assistant([{"type": "text", "text": "world"}]),
                assistant([{"type": "tool_use", "name": "Bash", "input": {}}]),
                user([{"type": "tool_result", "content": "private output"}]),
                assistant([{"type": "text", "text": "part 1"}], mid="msg_2"),
                assistant([{"type": "text", "text": "part 2"}], mid="msg_2"),
                {**assistant([{"type": "text", "text": "subagent"}], mid="msg_3"), "isSidechain": True},
                {"type": "ai-title", "aiTitle": "自动标题", "sessionId": SID},
            ]
            path = write_session(home, SID, rows)
            path.write_text(path.read_text() + '\n{"incomplete":')
            (home / "projects" / "-tmp-project" / SID / "subagents").mkdir(parents=True)
            write_session(home, OTHER, [user("sub")], project=f"-tmp-project/{SID}/subagents")
            data = load_sessions(home)
            self.assertEqual(len(data["sessions"]), 1)
            s = data["sessions"][0]
            self.assertEqual(s["title"], "自动标题")
            self.assertEqual([m["text"] for m in s["messages"]], ["/model opus", "hello", "world", "part 1\n\npart 2"])
            self.assertEqual(s["model"], "claude-opus-5-5")
            self.assertEqual(s["command"], "cd /tmp/project && claude --resume " + SID)

    def test_custom_title_wins_and_cwd_is_quoted(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            rows = [{**user("hi"), "cwd": "/tmp/it's here"},
                    {"type": "ai-title", "aiTitle": "auto"}, {"type": "custom-title", "customTitle": "mine"}]
            write_session(home, SID, rows)
            s = load_sessions(home)["sessions"][0]
            self.assertEqual(s["title"], "mine")
            argv = shlex.split(s["command"])
            self.assertEqual(argv[:2], ["cd", "/tmp/it's here"])

    def test_delete_moves_transcript_and_sidecar_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            target = write_session(home, SID, [user("bye")])
            data = target.read_text()
            sidecar = target.with_suffix("") / "subagents"
            sidecar.mkdir(parents=True)
            other = write_session(home, OTHER, [user("keep")])
            result = trash_session(home, SID)
            self.assertFalse(target.exists())
            self.assertFalse(sidecar.exists())
            moved = Path(result["trash"]) / "projects" / "-tmp-project"
            self.assertEqual((moved / f"{SID}.jsonl").read_text(), data)
            self.assertTrue((moved / SID / "subagents").is_dir())
            self.assertTrue(other.exists())
            self.assertEqual(len(load_sessions(home)["sessions"]), 1)
            with self.assertRaises(FileNotFoundError):
                trash_session(home, SID)
            with self.assertRaises(ValueError):
                trash_session(home, "../other")

    def test_delete_rejects_running_session_and_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            target = write_session(home, SID, [user("x")])
            (home / "sessions").mkdir()
            (home / "sessions" / "1.json").write_text(json.dumps({"pid": os.getpid(), "sessionId": SID}))
            with self.assertRaises(RuntimeError):
                trash_session(home, SID)
            (home / "sessions" / "1.json").unlink()
            with target.open("a"):
                with self.assertRaises(RuntimeError):
                    trash_session(home, SID)
            self.assertTrue(target.exists())
            outside = home / "outside.jsonl"
            target.rename(outside)
            target.symlink_to(outside)
            with self.assertRaises(FileNotFoundError):
                trash_session(home, SID)
            self.assertTrue(outside.exists())

    def test_merge_preserves_sources_and_quotes_command(self):
        with tempfile.TemporaryDirectory(prefix="history's ") as directory:
            home = Path(directory)
            ids = [SID, OTHER]
            before = {}
            for i, sid in enumerate(ids):
                text = f"任务 {i}\n```\n$(touch /tmp/should-not-run)\n```\n" + "长文本" * 5000
                p = write_session(home, sid, [{**user(text), "timestamp": f"2026-10-0{i+1}T00:00:00Z"}])
                before[p] = p.read_bytes()
            result = create_handoff(home, list(reversed(ids)), "继续 ETL 增量开发")
            contents = Path(result["file"]).read_text()
            self.assertEqual(result["sessions"], 2)
            self.assertIn("继续 ETL 增量开发", contents)
            self.assertIn("长文本" * 5000, contents)
            self.assertLess(contents.index(ids[0]), contents.index(ids[1]))
            self.assertEqual(Path(result["file"]).stat().st_mode & 0o777, 0o600)
            argv = shlex.split(result["command"])
            self.assertEqual(argv[0], "claude")
            self.assertEqual(len(argv), 2)
            self.assertIn(str(home), argv[1])
            for p, data in before.items():
                self.assertEqual(p.read_bytes(), data)
            for invalid in ([SID], [SID, SID], [SID, "../unsafe"], None):
                with self.assertRaises(ValueError):
                    create_handoff(home, invalid)

    def test_export_formats_all_or_selected(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            write_session(home, SID, [user("第一段 ``` 代码")])
            write_session(home, OTHER, [user("第二段")])
            body, name, mime = export_sessions(home, [], "json")
            self.assertTrue(name.endswith(".json"))
            self.assertEqual(len(json.loads(body)["sessions"]), 2)
            body, name, _ = export_sessions(home, [OTHER], "md")
            self.assertIn("第二段", body.decode())
            self.assertNotIn("第一段", body.decode())
            body, _, mime = export_sessions(home, None, "html")
            self.assertIn('"exported": true', body.decode())
            self.assertTrue(mime.startswith("text/html"))
            with self.assertRaises(ValueError):
                export_sessions(home, [], "exe")
            with self.assertRaises(ValueError):
                export_sessions(home, ["../x"], "md")

    def test_export_cannot_break_out_of_script(self):
        attack = '</script><img src=x onerror="alert(1)">'
        result = html_page({"sessions": [{"title": attack}]}).decode()
        self.assertNotIn(attack, result)
        self.assertIn(r"</script>", result)


if __name__ == "__main__":
    unittest.main()
