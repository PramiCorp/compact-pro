"""SessionStart hook: give a new or cleared session its starting point.

  (no args)   startup / clear: the project's HANDOFF.md, then "Where we left off" (the user's last messages
              and the final replies of the last two turns, word for word, from the newest backup), then how
              to search the backups. At most 9,500 bytes (about 2.4k tokens): "Where we left off" shrinks to
              fit, and an oversized handoff is cut with a pointer to the file.
  --compact   after the built-in /compact: the PreCompact hook has just backed up the session, so only point
              at that backup. The handoff is not printed, because it may be older than this session.
Prints nothing in projects without a handoff.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _common import HANDOFF_DIR, HANDOFF_FILE, find_project, handoff_folder, read_hook_input, text_of, utf8_stdout  # noqa: E402
from search import clean_ask, newest_first  # noqa: E402

# Claude Code shows hook output over 10,000 characters only as a 2 KB preview plus a file path, so the
# rest of the handoff never reaches the session. Stay under it, in bytes, with room to spare.
BUDGET = 9_500
# "Where we left off" shrinks to the first level that fits: (asks, chars per ask, replies, chars per reply).
LEFT_OFF_LEVELS = [(6, 500, 2, 2500), (6, 300, 2, 1500), (5, 300, 1, 1500), (4, 250, 1, 900), (3, 200, 1, 500),
                   (2, 150, 1, 250)]


def is_compact_pro(raw: str) -> bool:
    return bool(re.search(r"<command-name>/?[\w:-]*compact-pro</command-name>|^/[\w:-]*compact-pro\b", raw.strip()))


def left_off(backup: Path):
    """The user's last asks and the final reply of each of the last turns. The /compact-pro turn itself is
    skipped: its reply only says what was saved."""
    asks, turns = [], []  # turns: [is_compact_pro_turn, final_text, time]
    with backup.open(encoding="utf-8") as f:
        for raw in f:
            entry = json.loads(raw)
            msg = entry.get("message") or {}
            if entry.get("isCompactSummary"):
                continue
            when = entry.get("timestamp", "")[:16].replace("T", " ")
            if msg.get("role") == "user":
                full = text_of(msg.get("content"))
                if is_compact_pro(full):
                    turns.append([True, "", when])
                    continue
                ask = "" if "<task-notification>" in full else clean_ask(full)
                if ask and (not asks or asks[-1][1] != ask):
                    asks.append((when, ask))
                    turns.append([False, "", when])
            elif msg.get("role") == "assistant" and turns:
                text = text_of(msg.get("content")).strip()
                if text:
                    turns[-1][1], turns[-1][2] = text, when
    n_asks, _, n_replies, _ = LEFT_OFF_LEVELS[0]
    replies = [(t[2], t[1]) for t in turns if not t[0] and t[1]][-n_replies:]
    return asks[-n_asks:], replies


def main() -> None:
    utf8_stdout()
    hook = read_hook_input() if not sys.stdin.isatty() else {}
    project = find_project(hook.get("cwd"))
    if not project:
        return
    folder = handoff_folder(project)
    backups = newest_first(folder)
    how = (f'python "{(HERE / "search.py").as_posix()}" "{project.as_posix()}" word1 word2  '
           f"(then --show FILE:LINE, --around FILE:LINE, --asks, --list)")
    if "--compact" in sys.argv:
        if backups:
            print(f"[compact-pro] This session was backed up word for word to {HANDOFF_DIR}/{backups[0].name} just "
                  f"before it was compacted. If the summary lacks a detail (exact error, value, file, what the user "
                  f"said), search the backup before guessing or asking: {how}")
        return
    handoff = folder / HANDOFF_FILE
    head = "[compact-pro] Starting point for this session:\n\n" + handoff.read_text(encoding="utf-8").rstrip()
    age = (datetime.now() - datetime.fromtimestamp(handoff.stat().st_mtime)).days
    if age >= 3:
        head += f"\n\n(This handoff is {age} days old: check anything time-bound before relying on it.)"
    if not backups:
        print(fit(head, BUDGET, handoff))
        return
    foot = (f"\n\nIf the user's next message refers to any of this (\"yes\", \"do it\", \"the second one\"), it means "
            f"the above. Whenever something is missing or unclear, search the backups at once, before guessing or "
            f"asking: {how}. Backups: {', '.join(b.name for b in backups[:5])}.")
    head = fit(head, BUDGET - size(foot), handoff)
    room = BUDGET - size(head) - size(foot)
    asks, replies = left_off(backups[0])
    middle = ""
    for limits in LEFT_OFF_LEVELS:
        middle = left_off_text(backups[0].name, asks, replies, *limits)
        if size(middle) <= room:
            break
    else:
        middle = ""
    print(head + middle + foot)


def size(text: str) -> int:
    """Bytes as the hook writes them: Windows turns every newline into two."""
    return len(text.encode("utf-8")) + text.count("\n")


def fit(text: str, budget: int, handoff: Path) -> str:
    """Cut the handoff at a line break so it fits, and say where the rest is."""
    if size(text) <= budget:
        return text
    note = f"\n…(handoff cut to fit the session-start limit; read the rest now: {handoff.as_posix()})"
    room, kept = budget - size(note), []
    for line in text.split("\n"):
        room -= size(line) + 2
        if room < 0:
            break
        kept.append(line)
    return "\n".join(kept) + note


def left_off_text(name, asks, replies, n_asks, ask_chars, n_replies, reply_chars) -> str:
    out = [f"\n\n## Where we left off (word for word, from {name})"]
    if asks[-n_asks:]:
        out.append("The user's last messages, oldest first:")
        for when, ask in asks[-n_asks:]:
            ask = re.sub(r"\s+", " ", ask)
            stamp = f"[{when}] " if when else ""
            out.append(f"- {stamp}{ask[:ask_chars]}{' …' if len(ask) > ask_chars else ''}")
    for when, reply in replies[-n_replies:]:
        cut = " …(cut; search the backup for the rest)" if len(reply) > reply_chars else ""
        out.append(f"\nYour reply [{when}]:\n{reply[:reply_chars]}{cut}")
    return "\n".join(out)


if __name__ == "__main__":
    main()
