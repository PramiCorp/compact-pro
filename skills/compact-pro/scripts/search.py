"""Search compact-pro's transcript backups (<project>/docs/handoff/session_*.jsonl) for a few hundred tokens.

  python search.py <project> word [word ...]          entries containing ALL the words (any case), newest first
  python search.py <project> --show FILE:LINE         one entry in full
  python search.py <project> --around FILE:LINE [N]   N entries either side of a hit, one line each (default 4)
  python search.py <project> --asks [N]               what the user typed in the newest backup (default last 40)
  python search.py <project> --list                   every backup: time span, size, first and last ask
  options  --any  (ANY word, not ALL)   --who user|assistant|tool|result   --max N (default 25)   --file PART
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import handoff_folder, one_line, utf8_stdout  # noqa: E402

NOISE = ("The user sent a new message while you were working:",)
HARNESS_LINES = {"tool loaded.", "continue", "[request interrupted by user]"}


def texts(entry: dict):
    """(who, text) pieces of one entry: user/assistant text, tool calls, tool results, summaries."""
    msg = entry.get("message") or {}
    role = msg.get("role") or entry.get("type", "?")
    content = msg.get("content")
    if isinstance(content, str):
        yield role, content
    for block in content if isinstance(content, list) else []:
        if not isinstance(block, dict):
            continue
        kind = block.get("type")
        if kind == "text":
            yield role, block.get("text", "")
        elif kind == "tool_use":
            yield f"tool:{block.get('name', '?')}", json.dumps(block.get("input", {}), ensure_ascii=False)
        elif kind == "tool_result":
            c = block.get("content")
            if isinstance(c, list):
                c = "\n".join(x.get("text", "") for x in c if isinstance(x, dict))
            yield "result", str(c or "")
    if entry.get("summary"):
        yield "summary", entry["summary"]


def clean_ask(text: str) -> str:
    """What the user actually typed: no system/hook blocks, no harness wrappers."""
    text = re.sub(r"<([a-z_-]+)>.*?</\1>", "", text, flags=re.S)
    for n in NOISE:
        text = text.replace(n, "")
    text = text.split("This is how Claude Code surfaces messages the user sends mid-turn")[0].strip()
    if text.lower() in HARNESS_LINES or text.startswith("[SYSTEM NOTIFICATION"):
        return ""
    return text


def user_ask(entry: dict) -> str:
    msg = entry.get("message") or {}
    if msg.get("role") != "user" or entry.get("isCompactSummary"):
        return ""
    content = msg.get("content")
    raw = content if isinstance(content, str) else " ".join(
        b.get("text", "") for b in content or [] if isinstance(b, dict) and b.get("type") == "text")
    return "" if "<task-notification>" in raw else clean_ask(raw)


def newest_first(folder: Path, only: str = "") -> list:
    """Backups ordered by when their session last ran (the last entry's time), newest first."""
    def last_time(p: Path) -> str:
        with p.open("rb") as f:
            f.seek(max(0, p.stat().st_size - 200_000))
            for raw in reversed(f.read().splitlines()):
                m = re.search(rb'"timestamp": "([^"]+)"', raw)
                if m:
                    return m.group(1).decode()
        return ""
    return sorted((p for p in folder.glob("session_*.jsonl") if only in p.name), key=last_time, reverse=True)


def main() -> None:
    utf8_stdout()
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    folder = handoff_folder(Path(args.pop(0)))
    opts = {"max": 25, "file": "", "show": None, "around": None, "asks": 0, "any": False, "who": "", "list": False}
    words = []
    while args:
        a = args.pop(0)
        if a in ("--max", "--file", "--who", "--show"):
            opts[a[2:]] = int(args.pop(0)) if a == "--max" else args.pop(0)
        elif a == "--around":
            opts["around"] = (args.pop(0), int(args.pop(0)) if args and args[0].isdigit() else 4)
        elif a == "--asks":
            opts["asks"] = int(args.pop(0)) if args and args[0].isdigit() else 40
        elif a in ("--any", "--list"):
            opts[a[2:]] = True
        else:
            words.append(a)

    if opts["show"] or opts["around"]:
        ref = opts["show"] or opts["around"][0]
        name, line = ref.strip().rsplit(":", 1)
        lines = (folder / Path(name).name).read_text(encoding="utf-8").splitlines()
        n = int(line)
        if opts["show"]:
            entry = json.loads(lines[n - 1])
            print(entry.get("timestamp", ""))
            for who, t in texts(entry):
                print(f"[{who}]\n{t[:8000]}{' …(cut)' if len(t) > 8000 else ''}")
            return
        span = opts["around"][1]
        for i in range(max(1, n - span), min(len(lines), n + span) + 1):
            entry = json.loads(lines[i - 1])
            for who, t in texts(entry):
                if t.strip():
                    mark = ">>" if i == n else "  "
                    print(f"{mark} {Path(name).name}:{i} {entry.get('timestamp', '')[11:16]} [{who}] {one_line(t, 200)}")
                    break
        return

    files = newest_first(folder, opts["file"])
    if not files:
        sys.exit(f"No backups in {folder}")

    if opts["list"]:
        for p in files:
            lines = p.read_text(encoding="utf-8").splitlines()
            span = [json.loads(lines[i]).get("timestamp", "")[:16] for i in (0, -1)]
            asks = [a for a in (user_ask(json.loads(l)) for l in lines) if a]
            print(f"{p.name}  {span[0]} -> {span[1]}  {len(lines)} entries, {p.stat().st_size / 1e6:.1f} MB")
            if asks:
                print(f"   first ask: {one_line(asks[0], 150)}\n   last ask:  {one_line(asks[-1], 150)}")
        return

    if opts["asks"]:
        rows, prev = [], None
        for n, raw in enumerate(files[0].read_text(encoding="utf-8").splitlines(), 1):
            entry = json.loads(raw)
            ask = user_ask(entry)
            if ask and ask != prev:
                rows.append(f"{files[0].name}:{n} {entry.get('timestamp', '')[:16]} {one_line(ask)}")
                prev = ask
        print("\n".join(rows[-opts["asks"]:]))
        return

    if not words:
        sys.exit("Give words to search for, or --show / --around / --asks / --list")
    pats = [re.compile(re.escape(w), re.I) for w in words]
    hit = (lambda s: any(p.search(s) for p in pats)) if opts["any"] else (lambda s: all(p.search(s) for p in pats))
    count = 0
    for path in files:
        with path.open(encoding="utf-8") as f:
            for n, raw in enumerate(f, 1):
                if not hit(raw):
                    continue
                entry = json.loads(raw)
                for who, t in texts(entry):
                    if opts["who"] and not who.startswith(opts["who"]):
                        continue
                    if hit(t):
                        m = next(p.search(t) for p in pats if p.search(t))
                        start = max(0, m.start() - 120)
                        print(f"{path.name}:{n} {entry.get('timestamp', '')[:16]} [{who}] {one_line(t[start:m.end() + 180], 320)}")
                        count += 1
                        break
                if count >= opts["max"]:
                    print(f"… stopped at {opts['max']} hits (--max N for more, or add words)")
                    return
    if count == 0:
        print("No match in " + ", ".join(p.name for p in files))


if __name__ == "__main__":
    main()
