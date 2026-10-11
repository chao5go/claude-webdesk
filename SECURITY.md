# Security

Claude Webdesk is for one trusted user. Token holders can run Claude Code and access project/session data with the service account's permissions. Claude permission modes and workspace path checks are not OS sandboxing. Local plugins are executable trusted code.

Use loopback + SSH or HTTPS. Keep configuration, tokens, histories and exports private. There is no multi-tenant isolation or automatic data retention. Native Claude hooks/settings remain active. File-sharing filters reduce accidental exposure but are not a general secret scanner; review the directory you share.

Report vulnerabilities through GitHub private vulnerability reporting when available. Do not put exploit details, tokens or private transcripts into a public issue. Supported release line: 0.1.x. No guaranteed security response SLA.
