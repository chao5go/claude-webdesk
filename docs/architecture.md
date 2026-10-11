# Architecture and API

`bin/cli.js` validates configuration and starts the Node HTTP server. `src/tasks.js` spawns Claude with an argument array (no shell), passes the prompt via stdin, manages one process group, and persists task snapshots. `src/protocol.js` interprets stream-json in both the browser and server: text deltas, assistant messages, session IDs, result metrics, errors and permission denials. Nested agent text is excluded from the structured answer; raw output preserves received data.

`src/history.js` scans only top-level `projects/<project>/<UUID>.jsonl` transcripts. The full history plugin uses the adapted Python library from the author's local Claude history viewer, invoked per request with serialized operations. No standalone Python HTTP server is started. Plugins run trusted code in the same service; they are not sandboxed.

The file plugin is rooted at startup `cwd`, independent of the task directory. It checks path components, real paths and symlinks, limits streamed uploads and serves downloads as attachments. This protects HTTP path handling; a local process with the same OS permissions remains trusted and can modify files. It is not a security boundary against a hostile local user racing filesystem operations.

## Authenticated API

Send `Authorization: Bearer <access-token>` or use the HttpOnly login cookie. Cookie-authenticated writes require a matching Origin. All `/api/*` (except login) and `/plugins/*` routes require authentication. The app shell and its bundled static resources are public.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| POST | `/api/login` | `{token}` → session cookie |
| POST | `/api/logout` | Revoke cookie |
| GET | `/api/config` | Public runtime configuration; never the token |
| GET | `/api/plugins` | Installed tool manifest |
| GET/POST | `/api/tasks` | List/start tasks |
| GET | `/api/tasks/:id` | Full task snapshot |
| GET | `/api/tasks/:id/events?after=N` | SSE replay/reconnect; also accepts Last-Event-ID |
| POST | `/api/tasks/:id/stop` | `{signal:"SIGINT"}` |
| GET | `/api/sessions` | Native session summaries |
| GET | `/api/sessions/:id` | Conversation messages |
| GET | `/api/sessions/:id/export` | JSON download |
| GET | `/api/files?path=relative` | Directory listing, up to 1,000 entries |
| POST | `/api/files/upload?name=filename` | Raw bytes, max 25 MiB |
| GET | `/api/files/download?path=relative` | Attachment download |

Task body:

```json
{
  "prompt": "Review the authentication flow",
  "cwd": "/srv/project",
  "model": "sonnet",
  "effort": "high",
  "permissionMode": "plan",
  "maxBudgetUsd": 1.0,
  "contextPaths": [],
  "resumeId": "",
  "forkSession": false
}
```

Omitted settings use defaults. Prompt limit: 50,000 characters. Up to eight absolute additional directories. Budget must be a finite positive number ≤1,000; empty UI value means no cap. Fork requires a resume ID. Resuming through the HTTP API resolves the original session directory server-side and validates it.

The full history API lives under `/api/plugins/claude-history/api/sessions`; export/delete/merge POSTs additionally require the `X-CSRF-Token` returned by its list endpoint. Exports are downloads, deletion moves files to a recoverable trash directory, and merge only writes a handoff document—it never invokes a model.

## Limits

SSE events and raw/structured output are bounded per task. The task store and native session scans are not yet indexed or paginated. A crash can lose the last checkpoint interval. On restart, unfinished tasks become interrupted; they are not silently rerun. Native history is an internal CLI storage format and can change; fixture tests do not guarantee forward compatibility.
