# Changelog

## 1.2.0 — 2026-11-11

- Auto mode (opt-in, `COMPACT_PRO_AUTO=1`, desktop app): past `COMPACT_PRO_AUTO_AT` (default 200k tokens),
  Claude runs Compact Pro by itself at the end of a turn instead of suggesting it. Same safe-point gate; when
  it isn't a safe point it skips silently and tries again on the next prompt. It ends the reply with a short italic note: the
  conversation is saved, nothing is lost, and a cleared-looking chat is expected.

## 1.1.2 — 2026-11-11

- The session-start text stays under Claude Code's 10,000-character hook limit (budget 9,500 bytes). Above it,
  Claude Code showed only a 2 KB preview, so most of the handoff never reached the new session. "Where we left off"
  now shrinks to fit, and a handoff too long on its own is cut at a line with a pointer to the file.

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
