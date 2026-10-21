# Changelog

## 0.1.0 — 2026-10-21

First public release.

- Local-first FastAPI + SQLite backend with a React + Vite frontend.
- Today dashboard, tasks, goals, notes, literature, reviews, reports, search,
  tags, study log, attendance, reminders, Pomodoro, and job-prep pages.
- Optional DeepSeek integration for summaries, planning, tagging, and chat.
- Optional Zotero online-API sync and OpenAlex daily-paper discovery.
- Optional local speech-to-text through faster-whisper.
- Desktop shell (pywebview + pystray) with floating checklist, Pomodoro, and
  four always-on-top desktop pills.
- API keys encrypted with Windows DPAPI; all user data stored locally.
- GitHub Actions: backend compile/tests on Windows, frontend build on Ubuntu.
- Sanitized local paths and removed personal data from the public tree.

Known limitations:

- Windows-first; Linux and macOS need platform-specific implementations for
  DPAPI, tray, notifications, and always-on-top widgets.
- Single-user, single-machine; no sync.
- Alpha API and database schema; migrations are additive but not yet frozen.
