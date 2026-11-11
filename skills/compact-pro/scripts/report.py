"""Token report for /compact-pro: how much it saved, and how that compares with the built-in /compact.

  python report.py <project> [session_id | transcript.jsonl]

Every number is measured from Claude Code's own transcripts (the `usage` block of each reply), not guessed:
  before      the context size of the session's last reply (input + cache read + cache write)
  baseline    the fixed overhead every session carries (system prompt, tools, skills, CLAUDE.md, memory):
              the smallest first-reply context among this project's recent sessions
  carry/pro   what /compact-pro brings into the next session: the session-start text, at ~4 chars per token
  carry/cmp   what the built-in /compact brings: the median measured over this project's past compactions
              (first reply after a compact minus the baseline); 30k when none have been recorded yet
"""
from __future__ import annotations

import io
import json
import re
import statistics
import sys
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _common import utf8_stdout  # noqa: E402

DEFAULT_COMPACT_CARRY = 30_000
RECENT = 12


def total(usage: dict) -> int:
    return sum(usage.get(k, 0) for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))


def scan(path: Path):
    """(first reply's context, last reply's context, [context of the first reply after each compaction])."""
    first = last = None
    after_compact, pending = [], False
    with path.open(encoding="utf-8", errors="replace") as f:
        for raw in f:
            if '"isCompactSummary": true' in raw or '"isCompactSummary":true' in raw:
                pending = True
                continue
            if '"usage"' not in raw:
                continue
            try:
                usage = (json.loads(raw).get("message") or {}).get("usage") or {}
            except json.JSONDecodeError:
                continue
            t = total(usage)
            if not t:
                continue
            first = first if first is not None else t
            last = t
            if pending:
                after_compact.append(t)
                pending = False
    return first, last, after_compact


def start_text_tokens(project: Path) -> int:
    import session_start
    out = io.StringIO()
    argv, stdin = sys.argv, sys.stdin
    try:
        sys.argv, sys.stdin = ["session_start.py"], io.StringIO(json.dumps({"cwd": str(project)}))
        with redirect_stdout(out):
            session_start.main()
    finally:
        sys.argv, sys.stdin = argv, stdin
    return len(out.getvalue()) // 4


def k(n: float) -> str:
    return f"{n / 1000:.1f}k" if n < 10_000 else f"{round(n / 1000)}k"


def main() -> None:
    utf8_stdout()
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    project = Path(sys.argv[1]).resolve()
    import backup
    hint = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] not in ("", "self") else None
    current = backup.find_transcript(project, hint)
    folder = current.parent
    recent = sorted(folder.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[:RECENT]

    firsts, after = [], []
    before = None
    for p in recent:
        first, last, ac = scan(p)
        if p == current:
            before = last
        if first:
            firsts.append(first)
        after += ac
    if not before:
        sys.exit("compact-pro report: no token usage found in this session's transcript")
    baseline = min(firsts) if firsts else 0
    carries = [a - baseline for a in after if a > baseline]
    compact_carry = int(statistics.median(carries)) if carries else DEFAULT_COMPACT_CARRY
    measured = f"median of {len(carries)} measured /compact runs here" if carries else "typical value; none measured here yet"
    pro_carry = start_text_tokens(project)

    pro_after = baseline + pro_carry
    compact_after = baseline + compact_carry
    saved_pro = before - pro_after
    saved_cmp = before - compact_after
    per_turn = compact_carry - pro_carry
    share = per_turn / compact_carry * 100 if compact_carry else 0

    print(f"Compact Pro: context {k(before)} -> ~{k(pro_after)} tokens (saved ~{k(saved_pro)}).")
    print(f"/compact would have left ~{k(compact_after)} (saved ~{k(saved_cmp)}; it carries ~{k(compact_carry)}, {measured}).")
    print(f"Compact Pro carries ~{k(pro_carry)} instead: ~{k(per_turn)} fewer tokens on every following turn "
          f"({share:.0f}% less than /compact). Fixed overhead in both: ~{k(baseline)}.")


if __name__ == "__main__":
    main()
