"""UserPromptSubmit hook: when the context gets long, add one line asking Claude to suggest /compact-pro at
the next safe point. It never compacts or clears anything itself.

The size is the real one: the last reply's input + cache-read + cache-write tokens from the transcript. It
speaks once per COMPACT_PRO_NUDGE_STEP tokens (default 40k) of growth past COMPACT_PRO_NUDGE_AT (default
120k), and only in projects that have a handoff.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import find_project, read_hook_input  # noqa: E402

START = int(os.environ.get("COMPACT_PRO_NUDGE_AT", "120000"))
STEP = int(os.environ.get("COMPACT_PRO_NUDGE_STEP", "40000"))
STATE = Path(os.environ.get("COMPACT_PRO_STATE", Path(tempfile.gettempdir()) / "compact-pro-nudge.json"))


def context_tokens(transcript: Path) -> int:
    with transcript.open("rb") as f:
        f.seek(max(0, transcript.stat().st_size - 1_500_000))
        tail = f.read().splitlines()
    for raw in reversed(tail):
        if b'"usage"' not in raw:
            continue
        try:
            usage = json.loads(raw).get("message", {}).get("usage") or {}
        except Exception:
            continue
        total = sum(usage.get(k, 0) for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
        if total:
            return total
    return 0


def main() -> None:
    if START <= 0:
        return
    data = read_hook_input()
    path = Path(data.get("transcript_path") or "")
    if not path.is_file() or not find_project(data.get("cwd")):
        return
    tokens = context_tokens(path)
    if tokens < START:
        return
    level = (tokens - START) // STEP
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        state = {}
    session = data.get("session_id") or path.stem
    if state.get(session, -1) >= level:
        return
    state = dict(list(state.items())[-50:])
    state[session] = level
    try:
        STATE.write_text(json.dumps(state), encoding="utf-8")
    except Exception:
        pass
    print(f"[compact-pro] This session's context is about {tokens // 1000}k tokens. Keep working on the user's "
          f"request. When the current task is finished and verified, nothing is running and no question is open, "
          f"suggest /compact-pro in one line. Never suggest it mid-task.")


if __name__ == "__main__":
    main()
