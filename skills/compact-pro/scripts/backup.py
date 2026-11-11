"""Back up a Claude Code session transcript into <project>/docs/handoff/ as slim, searchable JSONL.

  python backup.py <project_dir> [session_id | path/to/transcript.jsonl]
  python backup.py --hook      PreCompact / SessionEnd hook: reads the hook's JSON on stdin and acts only in
                               projects that already have docs/handoff/HANDOFF.md

Claude Code keeps transcripts in ~/.claude/projects/<project>/<session>.jsonl and deletes them after about
30 days, so these backups are the lasting record. What is kept and dropped:
  kept     every user message, assistant reply, tool call and tool result, word for word, with timestamps
  dropped  embedded images (-> "[image removed]") and the app's display copies of the same data
           (toolUseResult, snapshots, rendering metadata). In practice 75-85% smaller.
  masked   secret values: passwords in links (rtsp://user:***@host), key = "value" passwords/tokens,
           ?password= query values, Authorization headers, well-known API key shapes. Booleans and
           placeholders are left alone. Text of tool calls that write project files is kept exactly,
           because it is in the project already.
Re-running for the same session rewrites its backup (atomically). The previous HANDOFF.md is copied to
history/ first, so a handoff rewrite can always be undone. A .gitignore keeps the backups out of git.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import HANDOFF_FILE, find_project, handoff_folder, read_hook_input, utf8_stdout  # noqa: E402

KEEP = ("type", "timestamp", "uuid", "message", "summary", "isCompactSummary")
VERBATIM_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
NOT_SECRETS = {"true", "false", "null", "none", "", "***", "string", "text", "password"}
GITIGNORE = "# compact-pro: transcript backups can hold private conversation; keep them out of git\nsession_*.jsonl\n*.tmp\n"

# Each pattern has three groups: kept prefix, the secret (masked), kept suffix.
SECRETS = [
    re.compile(r"([a-z][a-z0-9+.-]*://[^:/\s@\"']+:)([^@\s\"'/]+)(@)", re.I),
    re.compile(r"((?:pass(?:word|wd)?|pwd|secret|token|api[_-]?key|access[_-]?key)\"?\s*[:=]\s*\")([^\"\n]{1,200})(\")", re.I),
    re.compile(r"([?&](?:pass(?:word)?|pwd|token|key)=)([^&\s\"']+)()", re.I),
    re.compile(r"(Authorization\"?\s*[:=]\s*\"?\s*(?:Basic|Bearer|Digest)\s+)([^\s\"]+)()", re.I),
    re.compile(r"\b(sk-ant-[A-Za-z0-9_-]{8})([A-Za-z0-9_-]+)()"),
    re.compile(r"\b(sk-[A-Za-z0-9]{6})([A-Za-z0-9_-]{20,})()"),
    re.compile(r"\b(AIza[0-9A-Za-z_-]{6})([0-9A-Za-z_-]{20,})()"),
    re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{6})([A-Za-z0-9]{20,})()"),
    re.compile(r"\b(github_pat_[A-Za-z0-9]{6})([A-Za-z0-9_]{20,})()"),
    re.compile(r"\b(xox[abpr]-[A-Za-z0-9]{4})([A-Za-z0-9-]{10,})()"),
    re.compile(r"\b(AKIA[0-9A-Z]{4})([0-9A-Z]{12})()"),
]


def mask(text: str) -> tuple[str, int]:
    count = 0

    def sub(m: re.Match) -> str:
        nonlocal count
        value = m.group(2)
        if value.strip().lower() in NOT_SECRETS or value.startswith("$") or set(value) <= {"*", "•"}:
            return m.group(0)
        count += 1
        return f"{m.group(1)}***{m.group(3)}"

    for pattern in SECRETS:
        text = pattern.sub(sub, text)
    return text, count


def slim(node, counter: list, verbatim: bool = False):
    if isinstance(node, dict):
        if node.get("type") == "image" and isinstance(node.get("source"), dict):
            return {"type": "text", "text": "[image removed]"}
        exact = verbatim or (node.get("type") == "tool_use" and node.get("name") in VERBATIM_TOOLS)
        return {k: slim(v, counter, exact) for k, v in node.items()}
    if isinstance(node, list):
        return [slim(v, counter, verbatim) for v in node]
    if isinstance(node, str) and not verbatim:
        text, n = mask(node)
        counter[0] += n
        return text
    return node


def transcripts_folder(project: Path) -> Path:
    return Path.home() / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(project))


def find_transcript(project: Path, hint: str | None) -> Path:
    if hint and hint.endswith(".jsonl") and Path(hint).is_file():
        return Path(hint)
    folder = transcripts_folder(project)
    if hint and (folder / f"{hint}.jsonl").is_file():
        return folder / f"{hint}.jsonl"
    candidates = sorted(folder.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        candidates = sorted((Path.home() / ".claude" / "projects").glob("*/*.jsonl"),
                            key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        sys.exit("compact-pro: no transcript found")
    return candidates[0]  # the running session is the one being written right now


def backup(project: Path, src: Path) -> str:
    out_dir = handoff_folder(project)
    out_dir.mkdir(parents=True, exist_ok=True)
    if not (out_dir / ".gitignore").exists():
        (out_dir / ".gitignore").write_text(GITIGNORE, encoding="utf-8")
    handoff = out_dir / HANDOFF_FILE
    if handoff.exists():
        history = out_dir / "history"
        history.mkdir(exist_ok=True)
        stamp = datetime.fromtimestamp(handoff.stat().st_mtime).strftime("%Y-%m-%d_%H%M")
        if not (history / f"HANDOFF_{stamp}.md").exists():
            shutil.copy2(handoff, history / f"HANDOFF_{stamp}.md")
    first_ts, lines, masked = None, [], 0
    with src.open(encoding="utf-8", errors="replace") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError:
                continue
            first_ts = first_ts or entry.get("timestamp")
            kept = {k: entry[k] for k in KEEP if k in entry}
            if "message" in kept or "summary" in kept:
                counter = [0]
                lines.append(json.dumps(slim(kept, counter), ensure_ascii=False))
                masked += counter[0]
    day = (first_ts or datetime.now().isoformat())[:10]
    out = out_dir / f"session_{day}_{src.stem[:8]}.jsonl"
    tmp = out.with_suffix(".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp.replace(out)
    return (f"{out.relative_to(project).as_posix()}  ({len(lines)} entries, {src.stat().st_size / 1e6:.1f} MB -> "
            f"{out.stat().st_size / 1e6:.1f} MB, {masked} secret(s) masked, session {src.stem})")


def main() -> None:
    utf8_stdout()
    if sys.argv[1:2] == ["--hook"]:
        data = read_hook_input()
        project = find_project(data.get("cwd"))
        src = data.get("transcript_path")
        if project and src and Path(src).is_file():
            print(backup(project, Path(src)))
        return
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    project = Path(sys.argv[1]).resolve()
    hint = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] not in ("", "self") else None
    print(backup(project, find_transcript(project, hint)))


if __name__ == "__main__":
    main()
