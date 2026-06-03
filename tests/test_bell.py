#!/usr/bin/env python3
"""bell 元件測試：notify.sh 行為 + bell-setup 設定合併。純標準庫。"""
import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_BELL_DIR = os.path.join(_HERE, os.pardir, "bell")
_NOTIFY = os.path.join(_BELL_DIR, "notify.sh")
_SETUP = os.path.join(_BELL_DIR, "bell-setup")
# 腳本名含連字號且無副檔名，需明確傳入 SourceFileLoader，
# 否則 spec_from_file_location 在 Python 3.14 回傳 None。
_setup_loader = importlib.machinery.SourceFileLoader("bell_setup", _SETUP)
_spec = importlib.util.spec_from_file_location("bell_setup", _SETUP, loader=_setup_loader)
bell_setup = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bell_setup)


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


class ClaudeStopHookTest(unittest.TestCase):
    CMD = "/abs/bell/notify.sh claude"

    def test_apply_adds_stop_hook_to_empty(self):
        out = bell_setup.apply_stop_hook({}, self.CMD)
        self.assertEqual(
            out["hooks"]["Stop"],
            [{"hooks": [{"type": "command", "command": self.CMD}]}],
        )

    def test_apply_preserves_existing_keys_and_other_hooks(self):
        data = {"model": "opus", "hooks": {"Stop": [
            {"hooks": [{"type": "command", "command": "other"}]}]}}
        out = bell_setup.apply_stop_hook(data, self.CMD)
        self.assertEqual(out["model"], "opus")
        cmds = [h["command"] for m in out["hooks"]["Stop"] for h in m["hooks"]]
        self.assertEqual(cmds, ["other", self.CMD])

    def test_apply_is_idempotent(self):
        once = bell_setup.apply_stop_hook({}, self.CMD)
        twice = bell_setup.apply_stop_hook(once, self.CMD)
        self.assertEqual(once, twice)

    def test_apply_does_not_mutate_input(self):
        data = {"hooks": {"Stop": []}}
        bell_setup.apply_stop_hook(data, self.CMD)
        self.assertEqual(data, {"hooks": {"Stop": []}})

    def test_remove_drops_only_our_matcher(self):
        data = bell_setup.apply_stop_hook(
            {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "other"}]}]}},
            self.CMD)
        out, removed = bell_setup.remove_stop_hook(data, self.CMD)
        self.assertTrue(removed)
        cmds = [h["command"] for m in out["hooks"]["Stop"] for h in m["hooks"]]
        self.assertEqual(cmds, ["other"])

    def test_remove_returns_false_when_absent(self):
        out, removed = bell_setup.remove_stop_hook({}, self.CMD)
        self.assertFalse(removed)
        self.assertEqual(out, {})


class CodexNotifyTest(unittest.TestCase):
    ARGS = ["/abs/bell/notify.sh", "codex"]

    def test_detect_toplevel_notify_present(self):
        self.assertTrue(bell_setup.codex_has_toplevel_notify(
            'model = "o3"\nnotify = ["x"]\n[tools]\n'))

    def test_notify_inside_table_is_not_toplevel(self):
        self.assertFalse(bell_setup.codex_has_toplevel_notify(
            '[some]\nnotify = ["x"]\n'))

    def test_apply_prepends_when_absent(self):
        text = '[mcp_servers.foo]\ncommand = "x"\n'
        out, changed = bell_setup.apply_codex_notify(text, self.ARGS)
        self.assertTrue(changed)
        self.assertTrue(out.startswith(bell_setup.MARKER))
        self.assertIn('notify = ["/abs/bell/notify.sh", "codex"]', out)
        self.assertIn('[mcp_servers.foo]', out)  # 原內容保留
        # notify 必須在第一個 table 之前
        self.assertLess(out.index("notify ="), out.index("[mcp_servers.foo]"))

    def test_apply_noop_when_present(self):
        text = 'notify = ["existing"]\n[t]\n'
        out, changed = bell_setup.apply_codex_notify(text, self.ARGS)
        self.assertFalse(changed)
        self.assertEqual(out, text)

    def test_remove_strips_our_block_only(self):
        text = '[mcp_servers.foo]\ncommand = "x"\n'
        applied, _ = bell_setup.apply_codex_notify(text, self.ARGS)
        out, removed = bell_setup.remove_codex_notify(applied)
        self.assertTrue(removed)
        self.assertNotIn("notify =", out)
        self.assertIn('[mcp_servers.foo]', out)

    def test_remove_noop_without_marker(self):
        out, removed = bell_setup.remove_codex_notify('notify = ["hand"]\n')
        self.assertFalse(removed)
        self.assertEqual(out, 'notify = ["hand"]\n')

    def test_apply_remove_round_trip_newline_prefixed(self):
        text = '\n[tools]\nfoo = 1\n'
        applied, _ = bell_setup.apply_codex_notify(text, self.ARGS)
        out, removed = bell_setup.remove_codex_notify(applied)
        self.assertTrue(removed)
        self.assertEqual(out, text)


class GhosttyBellTest(unittest.TestCase):
    def test_apply_appends_when_absent(self):
        out, changed = bell_setup.apply_ghostty_bell("font-size = 14\n")
        self.assertTrue(changed)
        self.assertIn("bell-features = title,attention", out)
        self.assertIn("font-size = 14", out)
        self.assertTrue(out.endswith("\n"))

    def test_apply_adds_trailing_newline_when_missing(self):
        out, changed = bell_setup.apply_ghostty_bell("font-size = 14")  # 無結尾換行
        self.assertTrue(changed)
        self.assertIn("font-size = 14\n", out)
        self.assertIn("bell-features = title,attention", out)

    def test_apply_noop_when_bell_features_present(self):
        text = "bell-features = no-audio\n"
        out, changed = bell_setup.apply_ghostty_bell(text)
        self.assertFalse(changed)
        self.assertEqual(out, text)

    def test_remove_strips_our_block(self):
        applied, _ = bell_setup.apply_ghostty_bell("font-size = 14\n")
        out, removed = bell_setup.remove_ghostty_bell(applied)
        self.assertTrue(removed)
        self.assertNotIn("bell-features", out)
        self.assertIn("font-size = 14", out)

    def test_remove_noop_for_hand_written(self):
        out, removed = bell_setup.remove_ghostty_bell("bell-features = audio\n")
        self.assertFalse(removed)
        self.assertEqual(out, "bell-features = audio\n")


class BellSetupIoTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.claude = os.path.join(self.dir, "settings.json")
        self.codex = os.path.join(self.dir, "config.toml")
        self.ghostty = os.path.join(self.dir, "ghostty.config")
        self.cmd = "/abs/bell/notify.sh claude"
        self.codex_args = ["/abs/bell/notify.sh", "codex"]

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _write(self, path, text):
        with open(path, "w") as f:
            f.write(text)

    def test_install_creates_and_backs_up(self):
        self._write(self.claude, '{"model":"opus"}')
        self._write(self.codex, '[t]\n')
        self._write(self.ghostty, 'font-size = 14\n')
        results = bell_setup.run_install(
            self.claude, self.cmd, self.codex, self.codex_args, self.ghostty)
        with open(self.claude) as f:
            data = json.load(f)
        cmds = [h["command"] for m in data["hooks"]["Stop"] for h in m["hooks"]]
        self.assertIn(self.cmd, cmds)
        for base in (self.claude, self.codex, self.ghostty):
            self.assertTrue(any(f.startswith(os.path.basename(base) + ".bak.")
                                for f in os.listdir(self.dir)))
        self.assertEqual(len(results), 3)

    def test_install_is_idempotent_no_second_change(self):
        self._write(self.claude, "{}")
        self._write(self.codex, "")
        self._write(self.ghostty, "")
        bell_setup.run_install(self.claude, self.cmd, self.codex,
                               self.codex_args, self.ghostty)
        with open(self.ghostty) as f:
            before = f.read()
        bell_setup.run_install(self.claude, self.cmd, self.codex,
                               self.codex_args, self.ghostty)
        with open(self.ghostty) as f:
            self.assertEqual(f.read(), before)

    def test_install_isolates_write_failure(self):
        # Claude 路徑指向一個目錄 → 寫入必失敗，但 Codex/Ghostty 仍須照常套用
        claude_as_dir = os.path.join(self.dir, "settings.json")
        os.mkdir(claude_as_dir)
        self._write(self.codex, "")
        self._write(self.ghostty, "")
        results = bell_setup.run_install(
            claude_as_dir, self.cmd, self.codex, self.codex_args, self.ghostty)
        by_target = {r["target"]: r["status"] for r in results}
        self.assertEqual(by_target[claude_as_dir], "error")
        self.assertEqual(by_target[self.codex], "ok")
        self.assertEqual(by_target[self.ghostty], "ok")

    def test_install_aborts_claude_on_invalid_json(self):
        self._write(self.claude, "{ not json")
        self._write(self.codex, "")
        self._write(self.ghostty, "")
        results = bell_setup.run_install(self.claude, self.cmd, self.codex,
                                         self.codex_args, self.ghostty)
        with open(self.claude) as f:
            self.assertEqual(f.read(), "{ not json")
        claude_res = [r for r in results if r["target"] == self.claude][0]
        self.assertEqual(claude_res["status"], "error")

    def test_uninstall_restores(self):
        self._write(self.claude, "{}")
        self._write(self.codex, "")
        self._write(self.ghostty, "")
        bell_setup.run_install(self.claude, self.cmd, self.codex,
                               self.codex_args, self.ghostty)
        bell_setup.run_uninstall(self.claude, self.cmd, self.codex, self.ghostty)
        with open(self.claude) as f:
            self.assertNotIn("Stop", json.load(f).get("hooks", {}))
        with open(self.codex) as f:
            self.assertNotIn("notify", f.read())
        with open(self.ghostty) as f:
            self.assertNotIn("bell-features", f.read())


if __name__ == "__main__":
    unittest.main()
