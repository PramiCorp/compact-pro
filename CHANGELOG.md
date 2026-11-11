# Changelog

## 1.1.1 — 2026-11-11

- The skill backs up before rewriting the handoff, so `history/` always gets the previous handoff, not the new one.

## 1.1.0 — 2026-11-11

- Savings report after every run (`scripts/report.py`). It is measured from the transcripts' real token counts:
  - the context before and after;
  - what `/compact` would have left, from the median of this project's measured compactions;
  - the tokens saved on every later turn.

## 1.0.0 — 2026-11-11

First release.

- `/compact-pro`:
  - safety gate (7 checks; finishes a near step or defers; `force` override)
  - handoff rewrite
  - transcript backup
  - clear (desktop app) or a `/clear` prompt (CLI)
- Transcript backups:
  - all text kept; images and app duplicates dropped (about 80% smaller)
  - secrets masked; placeholders and booleans kept
  - atomic writes; previous handoffs kept in `history/`; automatic `.gitignore`
- `search.py`: all/any words, `--show`, `--around`, `--asks`, `--list`, `--who`.
- Hooks (all dormant until a project has a handoff):
  - SessionStart loads the handoff, your last messages and the last replies, verbatim
  - PreCompact and SessionEnd back up the transcript
  - long-context reminder
- Plugin and marketplace manifests, a manual installer with uninstall, and stdlib-only tests on 3 operating systems.
