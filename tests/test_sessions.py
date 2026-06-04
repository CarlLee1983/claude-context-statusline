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
dashboard = _load("sessions_dashboard", "dashboard.py")
ghostty = _load("sessions_ghostty", "ghostty.py")


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

    def test_apply_adds_all_events(self):
        out = setup.apply_claude_hooks({}, self.CMD)
        for ev in setup.CLAUDE_EVENTS:
            self.assertEqual(out["hooks"][ev],
                             [{"hooks": [{"type": "command", "command": self.CMD}]}])
        self.assertEqual(setup.CLAUDE_EVENTS,
                         ["SessionStart", "UserPromptSubmit", "Stop", "Notification", "SessionEnd"])

    def test_sessionend_is_registered(self):
        out = setup.apply_claude_hooks({}, self.CMD)
        self.assertIn("SessionEnd", out["hooks"])

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
        self.assertTrue(new.endswith("\n"))

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

    def test_foreign_bell_path_without_marker_untouched(self):
        # 使用者自己的 notify 剛好路徑含 bell/notify.sh，但沒有 bell marker → 不可動
        text = 'notify = ["/my/projects/bell/notify.sh"]\n'
        new, changed = setup.apply_codex_dispatch(text, self.ARGS)
        self.assertFalse(changed)
        self.assertEqual(new, text)

    def test_bell_notify_with_foreign_marker_untouched(self):
        # 前一行是別的工具 marker（非 bell 完整 marker）→ 不可動
        text = ('# added by claude-context-statusline other/install.sh\n'
                'notify = ["/abs/bell/notify.sh", "codex"]\n')
        new, changed = setup.apply_codex_dispatch(text, self.ARGS)
        self.assertFalse(changed)
        self.assertEqual(new, text)

    def test_upgrade_then_remove_round_trip(self):
        original = ('# added by claude-context-statusline bell/install.sh\n'
                    'notify = ["/abs/bell/notify.sh", "codex"]\n\nmodel = "x"\n')
        upgraded, c1 = setup.apply_codex_dispatch(original, self.ARGS)
        self.assertTrue(c1)
        removed, c2 = setup.remove_codex_dispatch(upgraded)
        self.assertTrue(c2)
        self.assertNotIn("sessions/notify.sh", removed)
        self.assertIn('model = "x"', removed)


class OrchestrationTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.claude = os.path.join(self.root, "settings.json")
        self.codex = os.path.join(self.root, "config.toml")
        self.cmd = "/abs/sessions/track.sh claude"
        self.codex_args = ["/abs/sessions/notify.sh", "codex"]

    def test_install_then_uninstall_round_trip(self):
        r1 = setup.run_install(self.claude, self.cmd, self.codex, self.codex_args)
        self.assertTrue(all(x["status"] in ("ok", "skipped") for x in r1), r1)
        with open(self.claude, encoding="utf-8") as f:
            data = json.load(f)
        for ev in setup.CLAUDE_EVENTS:
            self.assertIn(ev, data["hooks"])
        with open(self.codex, encoding="utf-8") as f:
            self.assertIn("sessions/notify.sh", f.read())

        setup.run_uninstall(self.claude, self.cmd, self.codex)
        with open(self.claude, encoding="utf-8") as f:
            self.assertEqual(json.load(f).get("hooks", {}), {})
        with open(self.codex, encoding="utf-8") as f:
            self.assertNotIn("sessions/notify.sh", f.read())

    def test_bad_claude_json_aborts_that_target_only(self):
        with open(self.claude, "w") as f:
            f.write("{ not json")
        results = setup.run_install(self.claude, self.cmd, self.codex, self.codex_args)
        statuses = {r["target"]: r["status"] for r in results}
        self.assertEqual(statuses[self.claude], "error")
        self.assertEqual(statuses[self.codex], "ok")  # Codex 不受 Claude 失敗影響


class DashboardLogicTest(unittest.TestCase):
    def test_sort_waiting_first_then_running_then_idle(self):
        recs = [{"status": "idle", "updated_at": 5},
                {"status": "waiting", "updated_at": 1},
                {"status": "running", "updated_at": 9}]
        ordered = sorted(recs, key=dashboard.sort_key)
        self.assertEqual([r["status"] for r in ordered],
                         ["waiting", "running", "idle"])

    def test_is_stale_threshold(self):
        self.assertTrue(dashboard.is_stale({"updated_at": 0}, now=2000, threshold=1800))
        self.assertFalse(dashboard.is_stale({"updated_at": 1500}, now=2000, threshold=1800))

    def test_humanize(self):
        self.assertEqual(dashboard.humanize(45), "45s")
        self.assertEqual(dashboard.humanize(120), "2m")
        self.assertEqual(dashboard.humanize(7200), "2h")

    def test_format_row_contains_basename_and_status(self):
        row = dashboard.format_row(
            {"status": "waiting", "cli": "claude", "cwd": "/Users/x/proj", "updated_at": 90},
            now=100)
        self.assertIn("waiting", row)
        self.assertIn("proj", row)
        self.assertIn("claude", row)

    def test_load_records_skips_bad_files(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        with open(os.path.join(d, "good.json"), "w") as f:
            json.dump({"status": "idle", "cwd": "/p", "updated_at": 1}, f)
        with open(os.path.join(d, "bad.json"), "w") as f:
            f.write("NOT JSON")
        with open(os.path.join(d, "ignore.txt"), "w") as f:
            f.write("x")
        recs = dashboard.load_records(d)
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["cwd"], "/p")

    def test_load_records_coerces_bad_updated_at(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        with open(os.path.join(d, "bad_ts.json"), "w") as f:
            json.dump({"status": "idle", "cwd": "/p", "updated_at": "not-a-number"}, f)
        recs = dashboard.load_records(d)
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["updated_at"], 0.0)
        # downstream pure fns must not raise on the coerced record
        dashboard.is_stale(recs[0], now=100)
        dashboard.sort_key(recs[0])
        dashboard.format_row(recs[0], now=100)

    def test_load_records_missing_dir_returns_empty(self):
        self.assertEqual(dashboard.load_records("/no/such/dir"), [])


class PickTerminalTest(unittest.TestCase):
    def test_single_cwd_match_returns_id(self):
        terms = [{"id": "A", "cwd": "/a/b/proj", "title": "anything"}]
        rec = {"cwd": "/a/b/proj", "cli": "claude"}
        self.assertEqual(ghostty.pick_terminal(rec, terms), "A")

    def test_prefers_cli_like_title_over_shell(self):
        terms = [
            {"id": "SH", "cwd": "/a/b/proj", "title": "…/a/b/proj"},
            {"id": "CLI", "cwd": "/a/b/proj", "title": "⠂ Review task"},
            {"id": "DEV", "cwd": "/a/b/proj", "title": "proj"},
        ]
        rec = {"cwd": "/a/b/proj", "cli": "claude"}
        self.assertEqual(ghostty.pick_terminal(rec, terms), "CLI")

    def test_all_shell_like_returns_first_match(self):
        terms = [
            {"id": "SH1", "cwd": "/a/b/proj", "title": "…/a/b/proj"},
            {"id": "SH2", "cwd": "/a/b/proj", "title": "admin@host: ~"},
        ]
        rec = {"cwd": "/a/b/proj", "cli": "claude"}
        self.assertEqual(ghostty.pick_terminal(rec, terms), "SH1")

    def test_trailing_slash_normalized(self):
        terms = [{"id": "A", "cwd": "/a/b/proj/", "title": "x"}]
        rec = {"cwd": "/a/b/proj", "cli": "claude"}
        self.assertEqual(ghostty.pick_terminal(rec, terms), "A")

    def test_no_match_returns_none(self):
        terms = [{"id": "A", "cwd": "/other", "title": "x"}]
        rec = {"cwd": "/a/b/proj", "cli": "claude"}
        self.assertIsNone(ghostty.pick_terminal(rec, terms))

    def test_bad_input_returns_none(self):
        self.assertIsNone(ghostty.pick_terminal(None, []))
        self.assertIsNone(ghostty.pick_terminal({"cli": "claude"}, []))
        self.assertIsNone(ghostty.pick_terminal({"cwd": ""}, [{"id": "A", "cwd": "", "title": "x"}]))
        self.assertIsNone(ghostty.pick_terminal({"cwd": "/a/b/proj"}, None))


class AntigravityTrackTest(unittest.TestCase):
    def test_event_to_status(self):
        self.assertEqual(track.antigravity_event_to_status("PostToolUse"), "running")
        self.assertEqual(track.antigravity_event_to_status("Stop"), "idle")
        self.assertIsNone(track.antigravity_event_to_status("PreToolUse"))
        self.assertIsNone(track.antigravity_event_to_status(""))

    def test_derive_id_from_cwd(self):
        self.assertEqual(track.derive_antigravity_id("/Users/x/p"), "antigravity:/Users/x/p")

    def test_fields_prefers_conversation_id(self):
        data = {"conversationId": "conv-1",
                "workspacePaths": ["/Users/x/p"],
                "transcriptPath": "/t.jsonl"}
        sid, cwd, tp = track.antigravity_fields(data)
        self.assertEqual(sid, "conv-1")
        self.assertEqual(cwd, "/Users/x/p")
        self.assertEqual(tp, "/t.jsonl")

    def test_fields_falls_back_to_cwd_derived_id(self):
        data = {"workspacePaths": ["/Users/x/p"]}
        sid, cwd, tp = track.antigravity_fields(data)
        self.assertEqual(sid, "antigravity:/Users/x/p")
        self.assertEqual(cwd, "/Users/x/p")
        self.assertIsNone(tp)

    def test_fields_empty_workspacepaths(self):
        sid, cwd, tp = track.antigravity_fields({"conversationId": "c"})
        self.assertEqual(sid, "c")
        self.assertEqual(cwd, "")
        self.assertIsNone(tp)


class AntigravityHandlerTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)

    def _records(self):
        out = []
        for n in os.listdir(self.dir):
            if n.endswith(".json"):
                with open(os.path.join(self.dir, n), encoding="utf-8") as f:
                    out.append(json.load(f))
        return out

    def test_posttooluse_writes_running(self):
        payload = json.dumps({"conversationId": "c1", "workspacePaths": ["/p"]})
        track._handle_antigravity(self.dir, "PostToolUse", payload, now=100)
        recs = self._records()
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["cli"], "antigravity")
        self.assertEqual(recs[0]["status"], "running")
        self.assertEqual(recs[0]["cwd"], "/p")
        self.assertEqual(recs[0]["session_id"], "c1")

    def test_stop_writes_idle(self):
        payload = json.dumps({"conversationId": "c1", "workspacePaths": ["/p"]})
        track._handle_antigravity(self.dir, "Stop", payload, now=100)
        self.assertEqual(self._records()[0]["status"], "idle")

    def test_unknown_event_ignored(self):
        payload = json.dumps({"conversationId": "c1", "workspacePaths": ["/p"]})
        track._handle_antigravity(self.dir, "PreToolUse", payload, now=100)
        self.assertEqual(self._records(), [])

    def test_no_identity_ignored(self):
        track._handle_antigravity(self.dir, "Stop", json.dumps({}), now=100)
        self.assertEqual(self._records(), [])

    def test_writes_transcript_path_when_present(self):
        payload = json.dumps({
            "conversationId": "c1",
            "workspacePaths": ["/p"],
            "transcriptPath": "/t.jsonl",
        })
        track._handle_antigravity(self.dir, "Stop", payload, now=100)
        self.assertEqual(self._records()[0].get("transcript_path"), "/t.jsonl")

    def test_main_dispatches_antigravity(self):
        payload = json.dumps({"conversationId": "c9", "workspacePaths": ["/q"]})
        track.main(argv=["antigravity", "Stop"], stdin=io.StringIO(payload),
                   env={"AI_SESSIONS_DIR": self.dir}, now=200)
        recs = self._records()
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["session_id"], "c9")
        self.assertEqual(recs[0]["status"], "idle")


class AntigravitySetupTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.plugin_dir = os.path.join(self.root, "plugins", "ai-sessions")
        self.track = "/abs/sessions/track.sh"

    def test_plugin_files_content(self):
        files = setup.antigravity_plugin_files(self.track)
        self.assertIn("plugin.json", files)
        self.assertIn("hooks.json", files)
        self.assertIn('"name": "ai-sessions"', files["plugin.json"])
        hooks = json.loads(files["hooks.json"])["hooks"]
        self.assertEqual(hooks["PostToolUse"][0]["hooks"][0]["command"],
                         "/abs/sessions/track.sh antigravity PostToolUse")
        self.assertEqual(hooks["Stop"][0]["hooks"][0]["command"],
                         "/abs/sessions/track.sh antigravity Stop")

    def test_apply_creates_then_idempotent_then_remove(self):
        r1 = setup._apply_antigravity(self.plugin_dir, self.track)
        self.assertEqual(r1["status"], "ok")
        self.assertTrue(os.path.exists(os.path.join(self.plugin_dir, "plugin.json")))
        self.assertTrue(os.path.exists(os.path.join(self.plugin_dir, "hooks.json")))
        r2 = setup._apply_antigravity(self.plugin_dir, self.track)
        self.assertEqual(r2["status"], "skipped")
        r3 = setup._remove_antigravity(self.plugin_dir)
        self.assertEqual(r3["status"], "ok")
        self.assertFalse(os.path.exists(self.plugin_dir))
        r4 = setup._remove_antigravity(self.plugin_dir)
        self.assertEqual(r4["status"], "skipped")

    def test_run_install_includes_antigravity_when_dir_given(self):
        claude = os.path.join(self.root, "settings.json")
        codex = os.path.join(self.root, "config.toml")
        results = setup.run_install(claude, "/t/track.sh claude", codex,
                                    ["/t/notify.sh", "codex"],
                                    agy_plugin_dir=self.plugin_dir,
                                    track_path="/t/track.sh")
        self.assertEqual(len(results), 3)
        self.assertTrue(os.path.exists(os.path.join(self.plugin_dir, "hooks.json")))
        results_u = setup.run_uninstall(claude, "/t/track.sh claude", codex,
                                        agy_plugin_dir=self.plugin_dir)
        self.assertEqual(len(results_u), 3)
        self.assertFalse(os.path.exists(self.plugin_dir))

    def test_run_install_without_agy_gives_two_results(self):
        claude = os.path.join(self.root, "settings.json")
        codex = os.path.join(self.root, "config.toml")
        results = setup.run_install(claude, "/t/track.sh claude", codex,
                                    ["/t/notify.sh", "codex"])
        self.assertEqual(len(results), 2)

    def test_paths_resolves_gemini_dir(self):
        claude, codex, agy = setup._paths({"GEMINI_CONFIG_DIR": "/g"})
        self.assertEqual(agy, "/g/plugins/ai-sessions")
