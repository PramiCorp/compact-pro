"""compact-pro tests. Standard library only:  python -m unittest discover -s tests -v"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "compact-pro" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import backup  # noqa: E402
import nudge  # noqa: E402
import report  # noqa: E402
import search  # noqa: E402
import session_start  # noqa: E402


def entry(role, content, ts="2026-01-01T10:00:00Z", **extra):
    return {"type": role, "timestamp": ts, "uuid": "u", "message": {"role": role, "content": content}, **extra}


def write_transcript(path: Path, entries) -> Path:
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")
    return path


class MaskTests(unittest.TestCase):
    def test_masks_real_secrets(self):
        cases = {
            "rtsp://root:Secr3t@10.0.0.2:554/live": "rtsp://root:***@10.0.0.2:554/live",
            'val password = "hunter22"': 'val password = "***"',
            '{"api_key": "abc123xyz"}': '{"api_key": "***"}',
            "GET /x?user=a&pass=xyz9 HTTP": "GET /x?user=a&pass=*** HTTP",
            "Authorization: Bearer eyJhbGciOi": "Authorization: Bearer ***",
            "key sk-ant-api03-abcdefghijklmnopqrstuvwxyz": "key sk-ant-api03-ab***",
        }
        for raw, want in cases.items():
            self.assertEqual(backup.mask(raw)[0], want, raw)

    def test_leaves_non_secrets(self):
        for raw in ['password="false"', "rtsp://$user:$pass@$host", 'password: "******"', "the password field"]:
            self.assertEqual(backup.mask(raw), (raw, 0), raw)


class SlimTests(unittest.TestCase):
    def test_images_dropped_and_file_writes_kept_exactly(self):
        node = {"content": [
            {"type": "image", "source": {"type": "base64", "data": "AAAA"}},
            {"type": "tool_use", "name": "Write", "input": {"content": 'password = "fixture1"'}},
            {"type": "text", "text": 'password = "real1"'},
        ]}
        counter = [0]
        out = backup.slim(node, counter)["content"]
        self.assertEqual(out[0], {"type": "text", "text": "[image removed]"})
        self.assertIn("fixture1", out[1]["input"]["content"])
        self.assertEqual(out[2]["text"], 'password = "***"')
        self.assertEqual(counter[0], 1)


class Workspace(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = Path(self.tmp.name) / "proj"
        (self.project / "docs" / "handoff").mkdir(parents=True)
        (self.project / "docs" / "handoff" / "HANDOFF.md").write_text("# Proj handoff\nNext: ship it.\n", encoding="utf-8")
        self.transcript = write_transcript(Path(self.tmp.name) / "abcdef12-0000.jsonl", [
            entry("user", "Please add the export button"),
            entry("assistant", [{"type": "text", "text": "Added the export button in Toolbar.kt."}],
                  ts="2026-01-01T10:05:00Z", toolUseResult={"huge": "x" * 5000}),
            entry("user", "Tool loaded."),
            entry("user", "<command-name>/compact-pro</command-name>"),
            entry("assistant", [{"type": "text", "text": "Saved the handoff; clearing now."}], ts="2026-01-01T10:09:00Z"),
        ])

    def tearDown(self):
        self.tmp.cleanup()

    def run_main(self, module, argv, stdin=""):
        out = io.StringIO()
        with mock.patch.object(sys, "argv", ["x", *argv]), mock.patch.object(sys, "stdin", io.StringIO(stdin)), redirect_stdout(out):
            module.main()
        return out.getvalue()

    def test_backup_search_and_session_start(self):
        result = backup.backup(self.project, self.transcript)
        self.assertIn("session_2026-01-01_abcdef12.jsonl", result)
        folder = self.project / "docs" / "handoff"
        saved = (folder / "session_2026-01-01_abcdef12.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("toolUseResult", saved)
        self.assertTrue((folder / ".gitignore").exists())
        self.assertEqual(len(list((folder / "history").glob("HANDOFF_*.md"))), 1)

        hits = self.run_main(search, [str(self.project), "export", "button"])
        self.assertIn("Toolbar.kt", hits)
        asks = self.run_main(search, [str(self.project), "--asks"])
        self.assertIn("export button", asks)
        self.assertNotIn("Tool loaded", asks)

        start = self.run_main(session_start, [], stdin=json.dumps({"cwd": str(self.project)}))
        self.assertIn("Next: ship it.", start)
        self.assertIn("Please add the export button", start)
        self.assertIn("Added the export button", start)       # the real last reply...
        self.assertNotIn("clearing now", start)               # ...not the /compact-pro turn's reply

        compact = self.run_main(session_start, ["--compact"], stdin=json.dumps({"cwd": str(self.project)}))
        self.assertIn("backed up word for word", compact)
        self.assertNotIn("Next: ship it.", compact)

    def test_hooks_silent_without_handoff(self):
        other = Path(self.tmp.name) / "other"
        other.mkdir()
        self.assertEqual(self.run_main(session_start, [], stdin=json.dumps({"cwd": str(other)})), "")
        self.assertEqual(self.run_main(backup, ["--hook"], stdin=json.dumps(
            {"cwd": str(other), "transcript_path": str(self.transcript)})), "")
        self.assertFalse((other / "docs").exists())

    def test_nudge_once_per_step(self):
        big = write_transcript(Path(self.tmp.name) / "big.jsonl", [
            {"type": "assistant", "message": {"role": "assistant", "content": [],
                                              "usage": {"input_tokens": 5, "cache_read_input_tokens": 150_000}}}])
        payload = json.dumps({"cwd": str(self.project), "session_id": "s1", "transcript_path": str(big)})
        with mock.patch.object(nudge, "STATE", Path(self.tmp.name) / "state.json"):
            first = self.run_main(nudge, [], stdin=payload)
            second = self.run_main(nudge, [], stdin=payload)
        self.assertIn("about 150k tokens", first)
        self.assertEqual(second, "")


    def test_report_compares_with_compact(self):
        folder = Path(self.tmp.name) / "transcripts"
        folder.mkdir()
        usage = lambda n: {"type": "assistant", "message": {"role": "assistant", "content": [], "usage": {"input_tokens": 0, "cache_read_input_tokens": n}}}
        write_transcript(folder / "old.jsonl", [usage(100_000), usage(300_000),
                                                {"type": "user", "isCompactSummary": True, "message": {"role": "user", "content": "summary"}},
                                                usage(130_000)])
        current = write_transcript(folder / "cur.jsonl", [usage(100_000), usage(400_000)])
        backup.backup(self.project, self.transcript)
        out = self.run_main(report, [str(self.project), str(current)])
        self.assertIn("context 400k", out)
        self.assertIn("carries ~30k, median of 1 measured", out)   # 130k after compact - 100k baseline
        self.assertIn("/compact would have left ~130k", out)


if __name__ == "__main__":
    unittest.main()
