"""SessionStart hook: give a new or cleared session its starting point.

  (no args)   startup / clear: the project's HANDOFF.md, then "Where we left off" (the user's last messages
              and the final replies of the last two turns, word for word, from the newest backup), then how
              to search the backups. About 1.5k-3k tokens in total.
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

LAST_ASKS = 6
ASK_CHARS = 500
REPLY_CHARS = 2500
LAST_REPLIES = 2


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
    replies = [(t[2], t[1]) for t in turns if not t[0] and t[1]][-LAST_REPLIES:]
    return asks[-LAST_ASKS:], replies


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
    print("[compact-pro] Starting point for this session:\n")
    print(handoff.read_text(encoding="utf-8").rstrip())
    age = (datetime.now() - datetime.fromtimestamp(handoff.stat().st_mtime)).days
    if age >= 3:
        print(f"\n(This handoff is {age} days old: check anything time-bound before relying on it.)")
    if not backups:
        return
    asks, replies = left_off(backups[0])
    print(f"\n## Where we left off (word for word, from {backups[0].name})")
    if asks:
        print("The user's last messages, oldest first:")
        for when, ask in asks:
            ask = re.sub(r"\s+", " ", ask)
            stamp = f"[{when}] " if when else ""
            print(f"- {stamp}{ask[:ASK_CHARS]}{' …' if len(ask) > ASK_CHARS else ''}")
    for when, reply in replies:
        cut = " …(cut; search the backup for the rest)" if len(reply) > REPLY_CHARS else ""
        print(f"\nYour reply [{when}]:\n{reply[:REPLY_CHARS]}{cut}")
    print(f"\nIf the user's next message refers to any of this (\"yes\", \"do it\", \"the second one\"), it means the "
          f"above. Whenever something is missing or unclear, search the backups at once, before guessing or "
          f"asking: {how}. Backups: {', '.join(b.name for b in backups[:5])}.")


if __name__ == "__main__":
    main()
