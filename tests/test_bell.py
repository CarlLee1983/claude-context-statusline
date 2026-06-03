#!/usr/bin/env python3
"""bell 元件測試：notify.sh 行為 + bell-setup 設定合併。純標準庫。"""
import importlib.util
import os
import subprocess
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_BELL_DIR = os.path.join(_HERE, os.pardir, "bell")
_NOTIFY = os.path.join(_BELL_DIR, "notify.sh")


class NotifyShTest(unittest.TestCase):
    def _run(self, *args, payload_tty=None):
        """跑 notify.sh，BELL_TTY 指到暫存檔；回傳該檔內容（bytes）。"""
        fd, tty = tempfile.mkstemp(suffix=".tty")
        os.close(fd)
        env = {**os.environ, "BELL_TTY": payload_tty if payload_tty else tty}
        try:
            proc = subprocess.run(
                ["/bin/sh", _NOTIFY, *args], env=env,
                capture_output=True, timeout=10,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            with open(tty, "rb") as f:
                return f.read()
        finally:
            os.remove(tty)

    def test_claude_source_always_emits_bell(self):
        self.assertIn(b"\a", self._run("claude"))

    def test_codex_turn_complete_emits_bell(self):
        payload = '{"type":"agent-turn-complete","last-assistant-message":"hi"}'
        self.assertIn(b"\a", self._run("codex", payload))

    def test_codex_other_event_is_silent(self):
        payload = '{"type":"task-started"}'
        self.assertEqual(b"", self._run("codex", payload))

    def test_unwritable_tty_does_not_error(self):
        # 不可寫的目標仍須 exit 0、不噴錯
        proc = subprocess.run(
            ["/bin/sh", _NOTIFY, "claude"],
            env={**os.environ, "BELL_TTY": "/nonexistent-dir/nope"},
            capture_output=True, timeout=10,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()
