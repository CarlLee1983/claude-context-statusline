#!/usr/bin/env python3
"""sessions 元件測試：track 事件映射 + setup 設定合併 + dashboard 純邏輯。純標準庫。"""
import importlib.machinery
import importlib.util
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_DIR = os.path.join(_HERE, os.pardir, "sessions")


def _load(modname, filename):
    path = os.path.join(_DIR, filename)
    loader = importlib.machinery.SourceFileLoader(modname, path)
    spec = importlib.util.spec_from_file_location(modname, path, loader=loader)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


track = _load("sessions_track", "sessions-track")
setup = _load("sessions_setup", "sessions-setup")


class EventToStatusTest(unittest.TestCase):
    def test_known_events_map_to_status(self):
        self.assertEqual(track.event_to_status("UserPromptSubmit"), "running")
        self.assertEqual(track.event_to_status("Notification"), "waiting")
        self.assertEqual(track.event_to_status("Stop"), "idle")
        self.assertEqual(track.event_to_status("SessionStart"), "idle")

    def test_unknown_event_returns_none(self):
        self.assertIsNone(track.event_to_status("PreToolUse"))
        self.assertIsNone(track.event_to_status("SessionEnd"))

    def test_sanitize_id_replaces_unsafe_chars(self):
        self.assertEqual(track.sanitize_id("codex:/a/b c"), "codex__a_b_c")
        self.assertEqual(track.sanitize_id("abc-123_.OK"), "abc-123_.OK")
        self.assertEqual(track.sanitize_id(""), "unknown")

    def test_derive_codex_id_from_cwd(self):
        self.assertEqual(track.derive_codex_id("/Users/x/p"), "codex:/Users/x/p")

    def test_merge_record_preserves_started_at(self):
        old = {"started_at": 100, "status": "running", "session_id": "s"}
        new = track.merge_record(old, {"status": "idle"}, now=200)
        self.assertEqual(new["started_at"], 100)
        self.assertEqual(new["updated_at"], 200)
        self.assertEqual(new["status"], "idle")
        self.assertEqual(old["status"], "running")  # 不改輸入

    def test_merge_record_sets_started_when_new(self):
        new = track.merge_record(None, {"status": "running"}, now=50)
        self.assertEqual(new["started_at"], 50)
        self.assertEqual(new["updated_at"], 50)


class TrackMainTest(unittest.TestCase):
    def setUp(self):
        self.dir = os.path.realpath(tempfile.mkdtemp())
        self.env = {"AI_SESSIONS_DIR": self.dir}
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)

    def _read(self, session_id):
        path = os.path.join(self.dir, track.sanitize_id(session_id) + ".json")
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def test_claude_userpromptsubmit_writes_running(self):
        payload = json.dumps({"hook_event_name": "UserPromptSubmit",
                              "session_id": "abc", "cwd": "/p"})
        track.main(["claude"], stdin=io.StringIO(payload), env=self.env, now=10)
        rec = self._read("abc")
        self.assertEqual(rec["status"], "running")
        self.assertEqual(rec["cli"], "claude")
        self.assertEqual(rec["cwd"], "/p")
        self.assertEqual(rec["session_id"], "abc")

    def test_claude_notification_writes_waiting(self):
        payload = json.dumps({"hook_event_name": "Notification", "session_id": "abc"})
        track.main(["claude"], stdin=io.StringIO(payload), env=self.env, now=10)
        self.assertEqual(self._read("abc")["status"], "waiting")

    def test_claude_sessionend_deletes_file(self):
        track.main(["claude"], stdin=io.StringIO(json.dumps(
            {"hook_event_name": "Stop", "session_id": "abc", "cwd": "/p"})),
            env=self.env, now=10)
        track.main(["claude"], stdin=io.StringIO(json.dumps(
            {"hook_event_name": "SessionEnd", "session_id": "abc"})),
            env=self.env, now=20)
        self.assertFalse(os.path.exists(os.path.join(self.dir, "abc.json")))

    def test_claude_unknown_event_writes_nothing(self):
        track.main(["claude"], stdin=io.StringIO(json.dumps(
            {"hook_event_name": "PreToolUse", "session_id": "abc"})),
            env=self.env, now=10)
        self.assertEqual(os.listdir(self.dir), [])

    def test_codex_agent_turn_complete_writes_idle(self):
        payload = json.dumps({"type": "agent-turn-complete", "last-assistant-message": "hi"})
        track.main(["codex", payload], env=self.env, now=10, cwd=self.dir)
        rec = self._read(track.derive_codex_id(self.dir))
        self.assertEqual(rec["status"], "idle")
        self.assertEqual(rec["cli"], "codex")

    def test_codex_other_event_writes_nothing(self):
        track.main(["codex", json.dumps({"type": "task-started"})], env=self.env, now=10)
        self.assertEqual(os.listdir(self.dir), [])

    def test_started_at_preserved_across_updates(self):
        for ev, t in [("UserPromptSubmit", 10), ("Stop", 30)]:
            track.main(["claude"], stdin=io.StringIO(json.dumps(
                {"hook_event_name": ev, "session_id": "abc", "cwd": "/p"})),
                env=self.env, now=t)
        rec = self._read("abc")
        self.assertEqual(rec["started_at"], 10)
        self.assertEqual(rec["updated_at"], 30)
        self.assertEqual(rec["status"], "idle")


class TrackShTest(unittest.TestCase):
    TRACK = os.path.join(_DIR, "track.sh")

    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def _run(self, args, stdin=b""):
        return subprocess.run(["/bin/sh", self.TRACK, *args], input=stdin,
                              env={**os.environ, "AI_SESSIONS_DIR": self.dir},
                              capture_output=True, timeout=10)

    def test_claude_stop_writes_record_and_exits_zero(self):
        payload = json.dumps({"hook_event_name": "Stop", "session_id": "s1", "cwd": "/p"})
        proc = self._run(["claude"], stdin=payload.encode())
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(os.path.exists(os.path.join(self.dir, "s1.json")))

    def test_bad_stdin_does_not_error(self):
        proc = self._run(["claude"], stdin=b"NOT JSON")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stderr, b"")
        self.assertEqual(os.listdir(self.dir), [])

    def test_no_args_does_not_error(self):
        proc = self._run([])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stderr, b"")


class NotifyShTest(unittest.TestCase):
    NOTIFY = os.path.join(_DIR, "notify.sh")

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        fd, self.tty = tempfile.mkstemp(suffix=".tty")
        os.close(fd)
        self.addCleanup(os.remove, self.tty)

    def _run(self, payload):
        return subprocess.run(
            ["/bin/sh", self.NOTIFY, "codex", payload],
            env={**os.environ, "AI_SESSIONS_DIR": self.dir, "BELL_TTY": self.tty},
            capture_output=True, timeout=10)

    def test_codex_complete_fans_out_to_bell_and_state(self):
        proc = self._run('{"type":"agent-turn-complete","last-assistant-message":"hi"}')
        self.assertEqual(proc.returncode, 0, proc.stderr)
        with open(self.tty, "rb") as f:
            self.assertIn(b"\a", f.read())           # bell concern
        self.assertEqual(len(os.listdir(self.dir)), 1)  # sessions concern

    def test_non_complete_event_exits_zero_no_state(self):
        proc = self._run('{"type":"task-started"}')
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(os.listdir(self.dir), [])


class ClaudeHooksTest(unittest.TestCase):
    CMD = "/abs/sessions/track.sh claude"

    def test_apply_adds_all_four_events(self):
        out = setup.apply_claude_hooks({}, self.CMD)
        for ev in setup.CLAUDE_EVENTS:
            self.assertEqual(out["hooks"][ev],
                             [{"hooks": [{"type": "command", "command": self.CMD}]}])
        self.assertEqual(setup.CLAUDE_EVENTS,
                         ["SessionStart", "UserPromptSubmit", "Stop", "Notification"])

    def test_apply_is_idempotent(self):
        once = setup.apply_claude_hooks({}, self.CMD)
        twice = setup.apply_claude_hooks(once, self.CMD)
        self.assertEqual(once, twice)

    def test_apply_preserves_existing_unrelated_hook(self):
        data = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "other"}]}]}}
        out = setup.apply_claude_hooks(data, self.CMD)
        cmds = [h["command"] for m in out["hooks"]["Stop"] for h in m["hooks"]]
        self.assertIn("other", cmds)
        self.assertIn(self.CMD, cmds)

    def test_remove_drops_only_our_command(self):
        data = setup.apply_claude_hooks(
            {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "other"}]}]}},
            self.CMD)
        out, changed = setup.remove_claude_hooks(data, self.CMD)
        self.assertTrue(changed)
        cmds = [h["command"] for m in out["hooks"]["Stop"] for h in m["hooks"]]
        self.assertEqual(cmds, ["other"])
        self.assertNotIn("UserPromptSubmit", out["hooks"])

    def test_remove_when_absent_reports_false(self):
        _out, changed = setup.remove_claude_hooks({}, self.CMD)
        self.assertFalse(changed)


class CodexDispatchTest(unittest.TestCase):
    ARGS = ["/abs/sessions/notify.sh", "codex"]
    NOTIFY = 'notify = ["/abs/sessions/notify.sh", "codex"]'

    def test_no_notify_prepends_block(self):
        new, changed = setup.apply_codex_dispatch("model = \"x\"\n", self.ARGS)
        self.assertTrue(changed)
        self.assertTrue(new.startswith(setup.MARKER))
        self.assertIn(self.NOTIFY, new)
        self.assertIn('model = "x"', new)

    def test_upgrades_bell_notify(self):
        text = ('# added by claude-context-statusline bell/install.sh\n'
                'notify = ["/abs/bell/notify.sh", "codex"]\n\nmodel = "x"\n')
        new, changed = setup.apply_codex_dispatch(text, self.ARGS)
        self.assertTrue(changed)
        self.assertIn("sessions/notify.sh", new)
        self.assertNotIn("bell/notify.sh", new)
        self.assertIn(setup.MARKER, new)

    def test_idempotent_when_already_ours(self):
        text = f"{setup.MARKER}\n{self.NOTIFY}\n"
        new, changed = setup.apply_codex_dispatch(text, self.ARGS)
        self.assertFalse(changed)

    def test_foreign_notify_left_untouched(self):
        text = 'notify = ["/my/own/script"]\n'
        new, changed = setup.apply_codex_dispatch(text, self.ARGS)
        self.assertFalse(changed)
        self.assertEqual(new, text)

    def test_remove_our_dispatch(self):
        text = f"{setup.MARKER}\n{self.NOTIFY}\n\nmodel = \"x\"\n"
        new, changed = setup.remove_codex_dispatch(text)
        self.assertTrue(changed)
        self.assertNotIn("sessions/notify.sh", new)
        self.assertNotIn(setup.MARKER, new)
        self.assertIn('model = "x"', new)

    def test_remove_when_absent(self):
        new, changed = setup.remove_codex_dispatch('model = "x"\n')
        self.assertFalse(changed)
