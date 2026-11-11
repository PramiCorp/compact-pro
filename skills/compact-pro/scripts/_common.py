"""Shared settings and helpers for compact-pro's scripts. Standard library only (Python 3.8+)."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

# Where a project keeps its handoff and backups, relative to the project root.
HANDOFF_DIR = os.environ.get("COMPACT_PRO_DIR", "docs/handoff")
HANDOFF_FILE = "HANDOFF.md"


def utf8_stdout() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to a legacy code page
    except Exception:
        pass


def handoff_folder(project: Path) -> Path:
    return project / HANDOFF_DIR


def find_project(start: str | os.PathLike | None) -> Path | None:
    """The nearest folder (start or a parent) that has a handoff. Hooks only act in such projects, so
    compact-pro stays dormant until /compact-pro has been used there once."""
    here = Path(start or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()).resolve()
    for p in [here, *here.parents]:
        if (handoff_folder(p) / HANDOFF_FILE).exists():
            return p
    return None


def read_hook_input() -> dict:
    try:
        return json.load(sys.stdin)
    except Exception:
        return {}


def text_of(content) -> str:
    """The plain text of a message's content (string or list of blocks)."""
    if isinstance(content, str):
        return content
    return "\n".join(b.get("text", "") for b in content or [] if isinstance(b, dict) and b.get("type") == "text")


def one_line(text: str, limit: int = 240) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit] + (" …" if len(text) > limit else "")
