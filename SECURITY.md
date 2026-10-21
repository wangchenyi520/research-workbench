# Security Policy

## Supported versions

This project is in alpha. Security fixes are applied to the latest `main` only.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting:

1. Open the repository's **Security** tab.
2. Choose **Report a vulnerability**.
3. Include the affected version, reproduction steps, and impact.

Do **not** open a public issue containing API keys, personal data, database
dumps, screenshots with private information, or full logs. If you accidentally
publish a key, revoke it at the provider immediately (DeepSeek, Zotero, etc.)
and rewrite the Git history before making the repository public again.

## Local data and secrets

- `backend/data/` is gitignored. It contains the SQLite database, images,
  attachments, PDFs, audio, logs, and backups.
- API keys are encrypted with Windows DPAPI and stored in the local SQLite
  database. On non-Windows systems the app falls back to plaintext storage; do
  not use it on a shared machine without an alternative secret store.
- The backend binds to `127.0.0.1` by default. Do not expose it on `0.0.0.0`
  or a public reverse proxy without authentication, TLS, and a review of the
  API surface.

## Known dependency advisories

`npm audit` currently reports moderate advisories in the Vite/esbuild dev
server, KaTeX, and React Router. Fixing them requires major-version upgrades
(Vite 8, KaTeX 0.19, React Router 7), which are tracked in the roadmap. The app
serves only local, user-authored notes and does not render untrusted remote
content by default; the development server is not exposed to the network.

## Scope

This policy covers the application code in this repository. It does not cover
third-party services (DeepSeek, Zotero, OpenAlex) or data that you choose to
send to them.
