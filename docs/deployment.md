# Deployment

Use the same OS user that runs and authenticates Claude Code. Webdesk does not copy or manage Claude credentials.

## SSH tunnel

On the server:

```bash
claude-webdesk --cwd /srv/my-project --workspace-root /srv
```

On your computer:

```bash
ssh -N -L 8090:127.0.0.1:8090 user@server
```

Open `http://127.0.0.1:8090`. Enter the startup token. A browser tab can close while a task keeps running. Service shutdown interrupts tasks.

## HTTPS with Caddy

Use a hostname you control. Keep Webdesk listening on loopback:

```bash
claude-webdesk --cwd /srv/my-project --origin https://desk.example.com --secure-cookie
```

Caddyfile:

```caddyfile
desk.example.com {
    reverse_proxy 127.0.0.1:8090 {
        flush_interval -1
    }
}
```

Set proxy timeouts long enough for SSE streams and uploads. Preserve the original Host header and forward the Origin header unchanged. Host and configured origin are checked; rewritten hosts will cause 403 responses. Webdesk does not trust X-Forwarded-For, so failed login attempts behind a proxy share the proxy address's rate limit.

Do not mount at a subpath: the frontend uses root-relative URLs. Use a dedicated hostname/port. A 25 MiB upload cap also applies behind proxies; slow uploads must finish within the server's 30-second request timeout in this release. Use remote-fileshare for larger/slow transfers.

## User systemd service

Install the npm package globally, then adapt [the service example](../contrib/claude-webdesk.service) to your Node/CLI paths and project. The environment file should contain:

```text
CLAUDE_WEBDESK_TOKEN=replace-with-a-random-32-byte-token
```

Protect it with `chmod 600`. With the service installed in `~/.config/systemd/user/claude-webdesk.service`:

```bash
systemctl --user daemon-reload
systemctl --user enable --now claude-webdesk
journalctl --user -u claude-webdesk
```

A user service needs the appropriate PATH to locate Node and Claude. Configure it explicitly in the unit. User lingering, if desired, is a separate OS administration choice.

## Data and backups

- Web tasks: `~/.local/share/claude-webdesk/*.json`; atomically written, active tasks checkpoint about once per second.
- Native sessions/config: `$CLAUDE_CONFIG_DIR` or `~/.claude`.
- Uploaded files: `<startup cwd>/webdesk-uploads/`.
- Recoverable session deletions: `<claude-home>/history-trash/<batch>/projects/...`. Restore by moving the original relative paths into `<claude-home>/projects/` while the session is inactive. No restore button yet.
- Handoffs: `<claude-home>/history-handoffs/`.
- Plugins: `~/.config/claude-webdesk/plugins/`.

Stop the service before making a consistent backup. Logs, raw tool output, exports and handoffs may contain private project data. No retention/cleanup scheduler is included. Do not make the home directory your shared project root. This app is intended for one trusted user, not shared-host tenant isolation.

## Troubleshooting

- **CLI not found / unsupported flags:** run `claude-webdesk doctor`; pass `--claude-bin /absolute/path/to/claude` if necessary. Log in using Claude CLI itself.
- **History plugin unavailable:** install Python 3.10+ or set `pluginOptions.claude-history.pythonBin` in configuration. Basic history and tasks use Node only.
- **Resume rejected:** the original project must still exist and be inside the configured workspace root.
- **Tool denied:** inspect the displayed permission denials and your Claude configuration. Noninteractive web tasks cannot answer approval prompts.
- **Upload is outside the selected task directory:** files always live under the startup root. Start Webdesk in that project or add the upload directory as task context.
