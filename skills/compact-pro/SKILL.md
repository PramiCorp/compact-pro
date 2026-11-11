---
name: compact-pro
description: >
  Deep compaction for Claude Code. At a safe point (no half-done change, nothing running, no open
  question), it writes the session's state to docs/handoff/HANDOFF.md and backs up the full transcript next
  to it as slim, searchable, secret-masked JSONL. Then it clears the session, so the next one starts from a
  ~2k-token handoff instead of a 25k-45k-token compact summary. It refuses to clear mid-task unless given
  "force". Use when the user types /compact-pro or asks for Compact Pro, a deep compact, or a handoff and clear,
  or with args "auto" when a "[compact-pro auto]" hook line asks for it.
---

# /compact-pro

Built-in `/compact` keeps a long summary plus re-attached files and skills inside the conversation, often
25k-45k tokens. `/compact-pro` keeps only a short handoff file. Everything else is kept outside the context, in
a transcript backup that costs nothing until you search it. A SessionStart hook loads the handoff and the
user's last words into every new or cleared session.

Paths below: `SKILL_DIR` is the base directory Claude Code shows when this skill loads. `PROJECT` is the
project root, the folder holding the code, `docs/` and `CLAUDE.md` (walk up from a subfolder). The handoff
folder is `PROJECT/docs/handoff` unless `COMPACT_PRO_DIR` sets another path relative to the project.

Run every step in order without asking questions. The user typed one command and expects it done. Never run
`/compact-pro` on your own initiative. Only suggest it in one line, at a safe point. The one exception is auto
mode, below.

## Auto mode (args `auto`)

Opt-in: the user sets `COMPACT_PRO_AUTO=1`. Then the UserPromptSubmit hook adds a `[compact-pro auto]` line
once the context is large, and you invoke this skill yourself with args `auto` as the last step of a turn,
after the user's request is done and before your closing message. Everything below applies, with these
differences:

- **Strict gate, silent skip.** If any check in step 0 fails, stop at once and say nothing about it: no
  "finishing first", no partial steps 2–5, never `force`. The hook asks again on the next prompt.
- **Desktop app only.** If `mcp__ccd_session_mgmt__clear_session` isn't available (terminal or IDE), stop
  silently.
- **Short italic note.** In step 6, instead of the three report lines and the summary, end your closing
  message with this note in italics, filling in the numbers from `report.py`:

  *Compact Pro has been applied automatically to keep this session efficient (context Xk → ~Yk tokens). Our
  conversation is fully saved and nothing has been lost; you can refer to anything we discussed at any time.
  If the chat appears cleared, that is expected: we continue exactly where we left off.*
- **The user's request comes first.** Your closing message still answers what the user asked, in full; the
  italic note goes at its end. The next session gets that answer back through "Where we left off".

## 0. Gate: is this a safe point to clear?

Clearing loses everything that lives only in the conversation: what was tried, exact error text, which edits
landed, and what "that one" means. The handoff keeps conclusions, not working state. So clear only at a
**boundary**, when the work in hand is finished, or stopped and written down. Check each item against what
you actually know about this session.

**All of these must be true:**

| # | Check | Why |
|---|---|---|
| 1 | No half-applied change. Every edit of the current task is in, and the project builds and passes its checks, or the failing state is understood and written down exactly (file, line, error, next fix). | Otherwise the next session can't tell which edits landed. |
| 2 | Nothing running: no background command, subagent, workflow or side session still working or awaited. | Its results would arrive in a session that doesn't know why it was started. |
| 3 | Not waiting on the user: no open question, approval, choice or plan awaiting a yes. | The question and its options would vanish. |
| 4 | No live interactive state: no browser flow half done, no device or app test mid-way, no setup half done. | Those steps can't be resumed from a summary. |
| 5 | No live debugging thread whose evidence (logs, repro steps, values) is only in the conversation. | Hypotheses and evidence are exactly what summaries lose. |
| 6 | No pending references: the user isn't iterating on recent output ("bigger", "the second one", "like before"). | Pointing words lose what they point at. |
| 7 | Corrections and preferences the user just gave are saved (memory, CLAUDE.md or the decision log). | They would otherwise be forgotten. |

**Good moments:** a feature or fix was just finished, verified and recorded; you're switching to unrelated
work; a research phase ended and its conclusions are written down; a long autonomous job is about to start
from a written plan; the context is long and full of finished work.

**Bad moments:** mid-feature, mid-refactor or with a red build; during debugging; while a build, test, agent
or device check runs; right after asking the user something; mid UI iteration; during a multi-step browser
or device task; right after an unsaved correction.

**A short session** is not worth clearing, though it does no harm: say so in one line and go ahead.

**If any check fails, do not clear.** Act without asking:

- **A safe point is close** (a few steps: finish the edit and build, wait for the running check, save the
  correction). Say "Finishing X first, then Compact Pro" in one line, get to the safe point, then continue
  with step 1.
- **A safe point is not close.** In two lines, say why clearing now would lose work and exactly when it
  becomes safe ("after the build passes", "once you pick A or B"). Still do steps 2–5, which are all
  harmless and make the handoff and backup current, but don't clear. Then carry on with the work.
- **`/compact-pro force`** clears anyway, for example when the context is about to run out. Before that,
  write an extra-detailed **In progress** section: every file touched and whether its edit is complete,
  the exact last error, running jobs and how to check them, the next three actions, and any open question
  word for word.

## 1. Tidy up

Finish anything trivially finishable. Make sure nothing unsaved is left in an editor or temp file that only
this conversation knows about.

## 2. Record what lasts

- New feedback on how the user wants you to work goes to memory or `CLAUDE.md`, as the project does it.
- New design or product decisions go to the project's decision log, if it keeps one.
- After code changes, refresh any code index the project uses.

## 3. Write `HANDOFF.md` from scratch

First run step 4's backup command once. It copies the current `HANDOFF.md` into `history/` before you
replace it. Then read the current `HANDOFF.md`, keep what is still true, and rewrite the whole file. Never
append. Aim for 80–150 lines, about 2,000 tokens, and never over 7 KB: the session-start hook fits everything
into 9.5 KB, and a longer handoff is cut there. Write plain sentences with exact names, and date anything
time-bound. Use these sections:

- `# <Project> — handoff (<date time>)`, then one line: "From session <id>. Exact history: the session_*.jsonl
  backups in this folder; earlier handoffs in history/."
- **Project in one paragraph.** What it is, the stack, where the source lives, and how it is built, run and
  tested (devices, addresses and accounts in use, never their passwords).
- **Rules that always apply.** Standing instructions and safety rules, word for word where the user gave
  them word for word.
- **Where things stand.** What changed recently and what was verified, with file paths.
- **In progress / next step.** The exact next action if work stopped mid-way.
- **Pending and dates.** Follow-ups, deadlines, reservations, tickets and replies awaited.
- **Key files and tools.** One line each.
- **Look things up.** `python "SKILL_DIR/scripts/search.py" "PROJECT" word1 word2`, then `--show FILE:LINE`;
  `--asks` lists what the user typed.

Never put passwords, keys, tokens or other credentials in the handoff, even ones seen in the session. The
user's last messages and your last replies are added word for word at session start by the hook, so don't
copy them.

## 4. Back up the transcript

```bash
python "SKILL_DIR/scripts/backup.py" "PROJECT" <session id>
```

Run it again here, after the handoff is written, so the backup holds the whole session. Use the session id when you know it: the transcript's file name. The desktop app's `get_session("self")` reports
it with a `local_` prefix that isn't part of the file name, so omit it if unsure. Without it, the
script takes the transcript being written right now. Check that it printed the backup name, entry count and
masked count. The script keeps all text, drops images and the app's duplicate copies, masks secrets, saves
the previous handoff in `history/`, and adds a `.gitignore` that keeps backups out of git. If the project
keeps a code index that scans `docs/`, exclude `docs/handoff/*.jsonl` from it.

## 5. Check the next session's start

```bash
python "SKILL_DIR/scripts/session_start.py"
```

Run it from PROJECT. It must print the new handoff and a "Where we left off" block.

## 6. Report and clear

Measure the savings, the way `/compact` reports what it freed:

```bash
python "SKILL_DIR/scripts/report.py" "PROJECT" <session id>
```

It prints three lines, all from the transcripts' real token counts:
- the context before and after;
- what `/compact` would have left, based on the median of this project's measured compactions;
- how many fewer tokens every later turn carries.

In auto mode, show only the italic note described under "Auto mode". Otherwise show those three lines to the
user word for word, then say in one or two lines what was saved: the handoff,
and the backup's name and size. Say that the session clears now. Then, as the very last action:

- **Claude desktop app:** call `mcp__ccd_session_mgmt__clear_session` with `session_id: "self"`. Load it
  with ToolSearch (`select:mcp__ccd_session_mgmt__clear_session`) if it is deferred. The clear happens when
  this turn ends.
- **Terminal (CLI) or IDE:** no tool can clear the session there, so finish with "Type `/clear` to start
  fresh". The hook loads the handoff into the cleared session.

## In every later session

When something isn't in the handoff, or isn't clear, search the backups before guessing, asking the user or
re-reading big files:

```bash
python "SKILL_DIR/scripts/search.py" "PROJECT" word1 word2    # ALL words; --any for ANY
python "SKILL_DIR/scripts/search.py" "PROJECT" --show FILE:LINE
python "SKILL_DIR/scripts/search.py" "PROJECT" --around FILE:LINE 4
python "SKILL_DIR/scripts/search.py" "PROJECT" --asks 20
python "SKILL_DIR/scripts/search.py" "PROJECT" --list
```

A search costs a few hundred tokens. Asking again or redoing work costs far more.
