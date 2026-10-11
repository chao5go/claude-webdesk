# Contributing

A useful contribution starts with a concrete remote-development workflow: what you were trying to do, where it broke, and the smallest change that helps.

1. Fork the repo and create a focused branch.
2. Use Node.js 22+ and Python 3.10+. Run `npm ci && npm run build`.
3. Run `npm run check`, `npm test` and `npm run test:python`.
4. For UI/process changes, run `npx playwright install chromium && npm run test:browser`.
5. Include what changed and how you verified it. Use synthetic fixtures, never real transcripts or credentials.

`npm run demo` gives you an isolated workspace without calling a model. `npm run test:package` tests the installed npm artifact. Python builds use `uv build --out-dir python-dist`; see CI for installed wheel/source tests.

Good first contributions: English interface localization, accessible upload cancellation, history pagination, and documentation verified on macOS. Discuss architecture changes in an issue first. Do not add permission bypasses or multi-user claims without a complete threat model and tests.

Bug reports should include OS, Node/Python/Claude/Webdesk versions, expected vs actual behavior, and a sanitized reproduction. Never attach `~/.claude` wholesale or paste access tokens.
