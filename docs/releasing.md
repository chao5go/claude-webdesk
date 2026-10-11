# Releasing

Both registries share the version in `package.json`. Python's build hook bundles the prebuilt Node runtime into its wheel and source distribution. No npm download is required when starting a Python installation.

CI runs syntax, server/protocol/file/history tests, Chromium browser flows, npm installed-package tests, and Python wheel/source installed-package tests on Node 22 and 24.

A push of a `v*` tag invokes the Release workflow: verify the tag equals `package.json`, run checks, build/test packages, publish npm (with provenance) and PyPI, wait for registry processing, verify public versions/latest tag and artifact digests, test public installs, then create a GitHub release with artifacts. Main-branch pushes only run CI. Configure repository Actions secrets `NPM_TOKEN` and `PYPI_TOKEN` with the minimum publishing scope. Tokens are never committed.

```bash
# After reviewing changes and updating CHANGELOG.md
npm version patch --no-git-tag-version
npm ci
npm run check && npm run build && npm test && npm run test:python
npm run test:browser && npm run test:package
git add package.json package-lock.json CHANGELOG.md
git commit -m "Release next patch"
git tag -a v0.1.1 -m "Claude Webdesk 0.1.1"
git push origin main v0.1.1
```

Use the actual new version in the tag. Publish only after CI is green. npm/PyPI versions are immutable: a partial publication is recovered by verifying the existing registry artifact, publishing only missing artifacts and creating the missing GitHub release. npm can report success while a new package is still in staging (`0.0.0-stage`). The verifier waits up to 20 minutes without uploading again. Run `scripts/verify-published.py` with the original release artifacts if you need to recheck visibility. Do not blindly rerun the full publication job or delete/reuse a public version. Normal feature commits never automatically bump or publish a package.
