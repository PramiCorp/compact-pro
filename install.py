"""Install compact-pro without the plugin system: copy the skill to ~/.claude/skills/compact-pro and add its
hooks to ~/.claude/settings.json (with a backup of that file first). Safe to run again: it updates in place.

  python install.py              install or update
  python install.py --uninstall  remove the skill and its hooks (your handoffs and backups are not touched)

Prefer the plugin route when you can:  /plugin marketplace add PramiCorp/compact-pro  then  /plugin install compact-pro@prami
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

SRC = Path(__file__).resolve().parent / "skills" / "compact-pro"
DEST = Path.home() / ".claude" / "skills" / "compact-pro"
SETTINGS = Path.home() / ".claude" / "settings.json"
MARK = "compact-pro/scripts/run.sh"


def hooks_for(run: str) -> dict:
    cmd = lambda args, t: {"type": "command", "command": f'sh "{run}" {args}', "timeout": t}  # noqa: E731
    return {
        "SessionStart": [{"matcher": "startup|clear", "hooks": [cmd("session_start.py", 15)]},
                         {"matcher": "compact", "hooks": [cmd("session_start.py --compact", 15)]}],
        "PreCompact": [{"hooks": [cmd("backup.py --hook", 120)]}],
        "SessionEnd": [{"hooks": [cmd("backup.py --hook", 120)]}],
        "UserPromptSubmit": [{"hooks": [cmd("nudge.py", 10)]}],
    }


def load_settings() -> dict:
    if not SETTINGS.exists():
        return {}
    data = json.loads(SETTINGS.read_text(encoding="utf-8"))
    backup = SETTINGS.with_name(f"settings.json.bak-{datetime.now():%Y%m%d-%H%M%S}")
    shutil.copy2(SETTINGS, backup)
    print(f"Backed up settings to {backup}")
    return data


def strip_ours(settings: dict) -> None:
    for event, entries in list(settings.get("hooks", {}).items()):
        kept = []
        for entry in entries:
            entry["hooks"] = [h for h in entry.get("hooks", []) if MARK not in h.get("command", "")]
            if entry["hooks"]:
                kept.append(entry)
        if kept:
            settings["hooks"][event] = kept
        else:
            del settings["hooks"][event]


def main() -> None:
    settings = load_settings()
    strip_ours(settings)
    if "--uninstall" in sys.argv:
        shutil.rmtree(DEST, ignore_errors=True)
        SETTINGS.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")
        print("compact-pro removed. Handoffs and backups in your projects were left as they are.")
        return
    if DEST.exists():
        shutil.rmtree(DEST)
    shutil.copytree(SRC, DEST, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    run = (DEST / "scripts" / "run.sh").as_posix()
    hooks = settings.setdefault("hooks", {})
    for event, entries in hooks_for(run).items():
        hooks.setdefault(event, []).extend(entries)
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"compact-pro installed to {DEST}\nHooks added to {SETTINGS}\nRestart Claude Code, then type /compact-pro at a safe point.")


if __name__ == "__main__":
    main()
