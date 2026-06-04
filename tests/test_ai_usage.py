#!/usr/bin/env python3
"""SwiftBar AI usage provider tests."""
import importlib.util
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODULE_PATH = os.path.join(_HERE, os.pardir, "swiftbar", "ai-usage.60s.py")
_spec = importlib.util.spec_from_file_location("ai_usage", _MODULE_PATH)
ai_usage = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ai_usage)


class AntigravityProviderTest(unittest.TestCase):
    def _accounts_file(self, payload):
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        return path

    def test_antigravity_provider_reports_active_local_rate_limit_windows(self):
        reset_ms = 1_800_000_000_000
        path = self._accounts_file({
            "accounts": [{
                "email": "user@example.com",
                "rateLimitResetTimes": {
                    "claude": reset_ms,
                    "gemini-antigravity": reset_ms + 60_000,
                    "gemini-cli": reset_ms + 120_000,
                },
            }]
        })
        try:
            rec = ai_usage.provider_antigravity(accounts_path=path, now_ms=reset_ms - 300_000)
        finally:
            os.remove(path)

        self.assertTrue(rec["ok"])
        self.assertEqual(rec["short"], "AG")
        self.assertEqual(rec["plan"], "1 acct")
        self.assertEqual(
            [(w["label"], w["pct"], w["reset"]) for w in rec["windows"]],
            [("Claude", 100.0, reset_ms / 1000), ("Gemini", 100.0, (reset_ms + 60_000) / 1000)],
        )

    def test_antigravity_provider_prefers_usage_command_output_as_available_quota(self):
        usage_text = """
        └ Model Quota

          Gemini 3.5 Flash (Medium)
          ███████████ ███████████ 92%
          Quota available

          Gemini 3.1 Pro (Low)
          ███████████ ███████████ 75%
          Quota available
        """

        rec = ai_usage.provider_antigravity(accounts_path="/no/such/file.json", usage_text=usage_text)

        self.assertTrue(rec["ok"])
        self.assertEqual(rec["plan"], "agy /usage")
        self.assertEqual(
            [(w["label"], w["pct"], w["kind"]) for w in rec["windows"]],
            [
                ("Gemini 3.5 Flash (Medium)", 92.0, "available"),
                ("Gemini 3.1 Pro (Low)", 75.0, "available"),
            ],
        )

    def test_antigravity_usage_windows_carry_refresh_countdown_as_reset(self):
        usage_text = """
        └ Model Quota

          Gemini 3.5 Flash (Medium)
          ███████████ ███████████ 80%
          80% remaining · Refreshes in 2h 46m

          Claude Opus 4.6 (Thinking)
          ███████████ ███████████ 100%
          Quota available
        """
        now_ms = 1_000_000_000_000

        rec = ai_usage.provider_antigravity(
            accounts_path="/no/such/file.json", now_ms=now_ms, usage_text=usage_text
        )

        windows = {w["label"]: w for w in rec["windows"]}
        self.assertAlmostEqual(
            windows["Gemini 3.5 Flash (Medium)"]["reset"],
            now_ms / 1000 + 2 * 3600 + 46 * 60,
        )
        # A full window ("Quota available") has no countdown -> no reset key.
        self.assertNotIn("reset", windows["Claude Opus 4.6 (Thinking)"])

    def test_antigravity_provider_ignores_expired_limits_and_marks_account_ready(self):
        path = self._accounts_file({
            "accounts": [{"email": "user@example.com", "rateLimitResetTimes": {"claude": 1000}}]
        })
        try:
            rec = ai_usage.provider_antigravity(accounts_path=path, now_ms=2000)
        finally:
            os.remove(path)

        self.assertTrue(rec["ok"])
        self.assertEqual(rec["windows"], [])
        self.assertEqual(rec["status"], "ready")

    def test_dropdown_uses_provider_specific_window_labels(self):
        rec = {
            "name": "Antigravity", "short": "AG", "icon": "gravity", "ok": True,
            "plan": "1 acct", "status": "limited", "five_hour": None, "seven_day": None,
            "windows": [{"label": "Claude", "pct": 100.0, "reset": 1_800_000_000}],
        }
        buf = io.StringIO()
        with redirect_stdout(buf):
            ai_usage._print_dropdown([rec])

        out = buf.getvalue()
        self.assertIn("Antigravity  ·  1 acct", out)
        self.assertIn("Claude  ██████████   100%", out)

    def test_dropdown_omits_reset_for_usage_command_windows(self):
        rec = {
            "name": "Antigravity", "short": "AG", "icon": "gravity", "ok": True,
            "plan": "agy /usage", "status": "usage", "five_hour": None, "seven_day": None,
            "windows": [{"label": "Gemini 3.5 Flash (Medium)", "pct": 92.0, "kind": "available"}],
        }
        buf = io.StringIO()
        with redirect_stdout(buf):
            ai_usage._print_dropdown([rec])

        out = buf.getvalue()
        self.assertIn("Gemini 3.5 Flash (Medium)  █████████░    92% available", out)
        self.assertNotIn("⟳", out)


class ClockFormatTest(unittest.TestCase):
    """`_clock` mirrors the native app: date only when the reset is not today."""

    def _epoch(self, *args):
        from datetime import datetime
        return datetime(*args, tzinfo=ai_usage._LOCAL_TZ).timestamp()

    def test_same_local_day_shows_time_only(self):
        from datetime import datetime
        reset = self._epoch(2027, 1, 15, 16, 0)
        now = datetime(2027, 1, 15, 9, 0, tzinfo=ai_usage._LOCAL_TZ)
        self.assertEqual(ai_usage._clock(reset, now=now), "16:00")

    def test_other_local_day_includes_date(self):
        from datetime import datetime
        reset = self._epoch(2027, 1, 15, 16, 0)
        now = datetime(2027, 1, 10, 9, 0, tzinfo=ai_usage._LOCAL_TZ)
        self.assertEqual(ai_usage._clock(reset, now=now), "01/15 16:00")


class ExpiringUnusedTest(unittest.TestCase):
    """SwiftBar mirrors the native `RemainingQuotaPresenter` expiring-unused logic:
    a window with lots of quota left AND an imminent reset is "use it or lose it"."""

    def test_window_duration_parses_label(self):
        self.assertEqual(ai_usage._window_duration("5h"), 5 * 3600)
        self.assertEqual(ai_usage._window_duration("7d"), 7 * 86400)
        self.assertEqual(ai_usage._window_duration("2w"), 2 * 604800)
        self.assertEqual(ai_usage._window_duration("1m"), 2_592_000)
        # case-insensitive, tolerant of an interior space
        self.assertEqual(ai_usage._window_duration("7D"), 7 * 86400)
        self.assertEqual(ai_usage._window_duration("5 h"), 5 * 3600)
        # unparseable labels yield None (Antigravity model names, free-form, empty)
        for bad in ("Gemini 3.5 Flash (Medium)", "Requests", "", "abc"):
            self.assertIsNone(ai_usage._window_duration(bad))

    def test_is_expiring_unused_matches_native_logic(self):
        now = 1_800_000_000

        def w(label, used, reset_in):
            return {"label": label, "pct": float(used), "reset": now + reset_in}

        # 5h window, 55% remaining (used 45%), reset in 30 min -> within 45-min tail -> True
        self.assertTrue(ai_usage._is_expiring_unused(w("5h", 45, 30 * 60), now=now))
        # 5h window, same quota, reset in 2 h -> outside the 15% tail -> False
        self.assertFalse(ai_usage._is_expiring_unused(w("5h", 45, 2 * 3600), now=now))
        # 7d window, 55% remaining, reset in 20 h -> within ~25.2 h tail -> True
        self.assertTrue(ai_usage._is_expiring_unused(w("7d", 45, 20 * 3600), now=now))
        # remaining 30% (< 40 threshold) -> False
        self.assertFalse(ai_usage._is_expiring_unused(w("5h", 70, 10 * 60), now=now))
        # boundary: exactly 40% remaining (used 60) -> True (>=)
        self.assertTrue(ai_usage._is_expiring_unused(w("5h", 60, 10 * 60), now=now))
        # boundary: reset exactly at duration*0.15 (5h -> 2700s) -> True (<=)
        self.assertTrue(ai_usage._is_expiring_unused(w("5h", 45, 2700), now=now))
        # reset already passed -> False
        self.assertFalse(ai_usage._is_expiring_unused(w("5h", 45, -600), now=now))
        # no reset key -> False
        self.assertFalse(ai_usage._is_expiring_unused({"label": "5h", "pct": 45.0}, now=now))
        # available kind, parseable label, high remaining, imminent reset -> True
        self.assertTrue(ai_usage._is_expiring_unused(
            {"label": "5h", "pct": 55.0, "kind": "available", "reset": now + 20 * 60}, now=now))
        # unparseable label (Antigravity model name) -> False
        self.assertFalse(ai_usage._is_expiring_unused(
            {"label": "Gemini 3.5 Flash (Medium)", "pct": 40.0, "kind": "available", "reset": now + 60},
            now=now))

    def test_dropdown_marks_expiring_unused_window(self):
        from datetime import datetime, timezone
        now_ts = datetime.now(timezone.utc).timestamp()
        rec = {
            "name": "Claude Code", "short": "CC", "icon": "spark", "ok": True,
            "plan": "Pro", "status": "limited", "five_hour": None, "seven_day": None,
            "windows": [{"label": "5h", "pct": 45.0, "reset": now_ts + 1800}],
        }
        buf = io.StringIO()
        with redirect_stdout(buf):
            ai_usage._print_dropdown([rec])
        out = buf.getvalue()
        self.assertIn("即將重置", out)
        self.assertIn(ai_usage.EXPIRING_COLOR, out)

    def test_dropdown_omits_marker_when_not_expiring(self):
        from datetime import datetime, timezone
        now_ts = datetime.now(timezone.utc).timestamp()
        rec = {
            "name": "Claude Code", "short": "CC", "icon": "spark", "ok": True,
            "plan": "Pro", "status": "limited", "five_hour": None, "seven_day": None,
            # reset 4 h away for a 5h window -> well outside the 15% tail
            "windows": [{"label": "5h", "pct": 45.0, "reset": now_ts + 4 * 3600}],
        }
        buf = io.StringIO()
        with redirect_stdout(buf):
            ai_usage._print_dropdown([rec])
        out = buf.getvalue()
        self.assertNotIn("即將重置", out)


if __name__ == "__main__":
    unittest.main()
