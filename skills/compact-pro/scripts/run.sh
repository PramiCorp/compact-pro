#!/bin/sh
# Runs one of compact-pro's Python scripts with the first Python 3.8+ that actually works.
# (On Windows `python3` is often a Microsoft Store stub that only prints an install hint, so each
# candidate is tested before use.) Hook failures must never block Claude Code: on any problem exit 0.
here=$(cd "$(dirname "$0")" && pwd)
script="$1"; shift
for py in python3 python py; do
  if command -v "$py" >/dev/null 2>&1 && "$py" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' >/dev/null 2>&1; then
    exec "$py" "$here/$script" "$@"
  fi
done
echo "compact-pro: Python 3.8+ not found; hook skipped" >&2
exit 0
