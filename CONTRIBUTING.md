# Contributing

Thanks for taking a look. This is an alpha, single-maintainer project, but
issues and pull requests are welcome.

## Development setup

```bat
git clone https://github.com/wangchenyi520/research-workbench.git
cd research-workbench
setup.bat
```

Manual setup is documented in [`docs/SETUP.md`](docs/SETUP.md).

## Before opening a pull request

- Keep the change focused. One feature or fix per PR.
- Do not commit `backend/data/`, `.env`, databases, logs, API keys, personal
  screenshots, or downloaded papers.
- Run the checks:

```bat
.venv\Scripts\python.exe -m pytest
python -m compileall -q backend\app
cd frontend
npm run build
```

- Update the README or docs when behavior or setup changes.
- Add a screenshot or a short recording for UI changes when possible.

## Code style

- Python: standard library style, type hints where they clarify interfaces,
  small functions, no new heavy dependencies without a reason.
- React: function components and hooks, keep data fetching in `src/api.js` or
  the page that owns the data, reuse existing components and CSS classes.
- UI copy is currently Chinese; keep new user-facing strings consistent with
  the existing pages.
- Prefer local-first behavior. Any new network call must be optional, documented
  in `docs/PRIVACY.md`, and easy to disable.

## Adding a feature

A typical feature touches:

1. `backend/app/models.py` (if persistence is needed)
2. `backend/app/schemas.py`
3. a router in `backend/app/routers/`
4. a service in `backend/app/services/` for non-trivial logic
5. a page or component in `frontend/src/`
6. a route in `frontend/src/App.jsx`
7. tests and docs

Database changes must be additive and handled by `backend/app/migrate.py` so
existing local databases keep working.

## Commit messages

Use short imperative messages, for example:

```
add weekly review export
fix reminder timezone handling
docs: clarify Zotero API setup
```

## Reporting bugs

Use the issue template and include:

- what you expected and what happened;
- steps to reproduce;
- Windows version, Python version, Node version;
- relevant log lines **with secrets and personal data removed**.

For security issues, follow [`SECURITY.md`](SECURITY.md) instead of opening a
public issue.
