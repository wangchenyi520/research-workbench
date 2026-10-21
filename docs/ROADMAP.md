# Roadmap

This is a living list, not a promise. Priorities are chosen by the maintainer
and by issues with clear reproduction steps.

## Near term (0.2)

- [ ] Add backend tests for task scheduling, reminders, backup/restore, and
      Zotero sync parsing.
- [ ] Add a one-command development script and a seed/demo database so new
      contributors can see the UI without personal data.
- [ ] Package a Windows installer (PyInstaller or MSIX) that bundles the
      backend, frontend build, and WebView2 bootstrap.
- [ ] Improve first-run onboarding: detect missing dependencies, show a
      checklist, and explain optional AI/Zotero setup.
- [ ] Add import/export for tasks and notes (Markdown/CSV/JSON).
- [ ] Make the reminder scheduler resilient to sleep/resume and timezone
      changes.

## Mid term (0.3)

- [ ] Cross-platform desktop shell: replace DPAPI with the OS keychain,
      provide tray/notification fallbacks, and test on macOS/Linux.
- [ ] Optional end-to-end encrypted sync between devices (local-first,
      conflict-aware, no mandatory cloud account).
- [ ] Plugin API for custom dashboard cards and data sources.
- [ ] Better literature workflow: annotation import, citation graph, and
      reading queue.
- [ ] Accessibility and keyboard-only navigation pass.

## Longer term

- [ ] Mobile capture companion (quick add, voice notes, paper saving) that
      syncs through the optional encrypted layer.
- [ ] Multi-user/lab mode with explicit permissions, only if it can be done
      without weakening the local-first default.
- [ ] Public benchmark of AI-assisted planning quality against a manual
      baseline.

## Non-goals

- A hosted SaaS with mandatory accounts.
- Telemetry, ads, or selling user data.
- Social feeds or gamified leaderboards.
- Replacing Zotero, Obsidian, or a full calendar; the workbench integrates
  with them rather than locking data in.

## How to influence the roadmap

Open an issue with the problem you are trying to solve, not only the feature
you want. Include your workflow, the current workaround, and what would make
the biggest difference. Small, well-scoped PRs are easier to review than large
rewrites.
