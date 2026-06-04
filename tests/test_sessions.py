#!/usr/bin/env python3
"""sessions 元件測試：track 事件映射 + setup 設定合併 + dashboard 純邏輯。純標準庫。"""
import importlib.machinery
import importlib.util
import io
import json
import os
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
        cwd = self.dir
        old = os.getcwd()
        os.chdir(cwd)
        try:
            track.main(["codex", payload], env=self.env, now=10)
        finally:
            os.chdir(old)
        rec = self._read(track.derive_codex_id(cwd))
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
