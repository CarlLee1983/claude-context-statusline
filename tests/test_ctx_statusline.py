#!/usr/bin/env python3
"""ctx-statusline.py 的單元測試（純標準庫 unittest）。

Unit tests for ctx-statusline.py (pure-stdlib unittest, no third-party deps).

執行 / Run:  python3 -m unittest discover -s tests
"""
import importlib.util
import calendar
import io
import json
import os
import re
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

# 腳本名含連字號，無法用一般 import，改用 importlib 依路徑載入。
# The script name has a hyphen, so load it by path with importlib.
_HERE = os.path.dirname(os.path.abspath(__file__))
_MODULE_PATH = os.path.join(_HERE, os.pardir, "ctx-statusline.py")
_spec = importlib.util.spec_from_file_location("ctx_statusline", _MODULE_PATH)
ctx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ctx)


def _record(input_tokens=0, cache_read=0, cache_creation=0, sidechain=False):
    rec = {
        "message": {
            "usage": {
                "input_tokens": input_tokens,
                "cache_read_input_tokens": cache_read,
                "cache_creation_input_tokens": cache_creation,
            }
        }
    }
    if sidechain:
        rec["isSidechain"] = True
    return json.dumps(rec)


def _write_transcript(lines):
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


class ContextLimitTest(unittest.TestCase):
    def test_default_limit(self):
        self.assertEqual(ctx.context_limit("claude-opus-4-8"), 200_000)

    def test_million_window(self):
        self.assertEqual(ctx.context_limit("claude-opus-4-8[1m]"), 1_000_000)

    def test_fable_5_uses_million_window(self):
        self.assertEqual(ctx.context_limit("fable-5"), 1_000_000)
        self.assertEqual(ctx.context_limit("Claude Fable 5"), 1_000_000)

    def test_case_insensitive(self):
        self.assertEqual(ctx.context_limit("MODEL-1M"), 1_000_000)

    def test_none_and_empty(self):
        self.assertEqual(ctx.context_limit(None), 200_000)
        self.assertEqual(ctx.context_limit(""), 200_000)


class HumanizeTest(unittest.TestCase):
    def test_below_thousand(self):
        self.assertEqual(ctx.humanize(0), "0")
        self.assertEqual(ctx.humanize(999), "999")

    def test_thousands(self):
        self.assertEqual(ctx.humanize(72_000), "72k")
        self.assertEqual(ctx.humanize(1_500), "2k")  # rounds

    def test_millions(self):
        self.assertEqual(ctx.humanize(1_000_000), "1m")
        self.assertEqual(ctx.humanize(1_500_000), "1.5m")


class UsedTokensTest(unittest.TestCase):
    def test_missing_path(self):
        self.assertEqual(ctx.used_tokens(None), 0)
        self.assertEqual(ctx.used_tokens("/no/such/file.jsonl"), 0)

    def test_sums_usage_fields(self):
        path = _write_transcript([_record(100, 200, 50)])
        try:
            self.assertEqual(ctx.used_tokens(path), 350)
        finally:
            os.remove(path)

    def test_uses_last_record(self):
        path = _write_transcript([_record(100), _record(900)])
        try:
            self.assertEqual(ctx.used_tokens(path), 900)
        finally:
            os.remove(path)

    def test_skips_sidechain(self):
        path = _write_transcript([_record(500), _record(999, sidechain=True)])
        try:
            self.assertEqual(ctx.used_tokens(path), 500)
        finally:
            os.remove(path)

    def test_skips_blank_and_invalid_lines(self):
        path = _write_transcript(["", "not json", _record(123)])
        try:
            self.assertEqual(ctx.used_tokens(path), 123)
        finally:
            os.remove(path)

    def test_negative_and_garbage_usage_count_zero(self):
        path = _write_transcript([_record(-5000)])
        bad = _write_transcript([json.dumps(
            {"message": {"usage": {"input_tokens": "x", "cache_read_input_tokens": 7}}})])
        try:
            self.assertEqual(ctx.used_tokens(path), 0)
            self.assertEqual(ctx.used_tokens(bad), 7)
        finally:
            os.remove(path)
            os.remove(bad)

    def test_no_usage_returns_zero(self):
        path = _write_transcript([json.dumps({"message": {"role": "user"}})])
        try:
            self.assertEqual(ctx.used_tokens(path), 0)
        finally:
            os.remove(path)

    def test_large_file_tail_scan(self):
        # 用大量填充行把最後一筆 usage 推到 TAIL_BYTES 視窗內仍可讀到。
        # Pad with many lines and confirm the trailing-tail scan still finds it.
        padding = [json.dumps({"noise": "x" * 100}) for _ in range(50_000)]
        path = _write_transcript(padding + [_record(4242)])
        try:
            self.assertTrue(os.path.getsize(path) > ctx.TAIL_BYTES)
            self.assertEqual(ctx.used_tokens(path), 4242)
        finally:
            os.remove(path)

    def test_large_file_fallback_full_scan(self):
        # 早期一筆真 usage + 之後全是 sidechain 噪音超過 TAIL_BYTES，需整檔回掃。
        # Real usage early, then sidechain noise beyond TAIL_BYTES -> full rescan.
        noise = [_record(111, sidechain=True) for _ in range(60_000)]
        path = _write_transcript([_record(777)] + noise)
        try:
            self.assertTrue(os.path.getsize(path) > ctx.TAIL_BYTES)
            self.assertEqual(ctx.used_tokens(path), 777)
        finally:
            os.remove(path)


_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _plain(text):
    """去掉 ANSI SGR 序列，只留可見文字。 Strip ANSI SGR sequences."""
    return _ANSI.sub("", text)


class _TruecolorMixin:
    """把 COLORTERM 固定成 truecolor，測試後還原。

    Pin COLORTERM=truecolor for the test and restore it afterwards.
    """

    colorterm = "truecolor"

    def setUp(self):
        super().setUp()
        patcher = mock.patch.dict(os.environ)
        patcher.start()
        self.addCleanup(patcher.stop)
        if self.colorterm is None:
            os.environ.pop("COLORTERM", None)
        else:
            os.environ["COLORTERM"] = self.colorterm


FULL_PAYLOAD = {
    "model": {"id": "claude-opus-5-5", "display_name": "Opus 5.5"},
    "transcript_path": "/nonexistent/transcript.jsonl",
    "context_window": {
        "total_input_tokens": 229005,
        "total_output_tokens": 139,
        "context_window_size": 1000000,
        "used_percentage": 23,
        "remaining_percentage": 77,
        "current_usage": {
            "input_tokens": 5,
            "cache_read_input_tokens": 200_000,
            "cache_creation_input_tokens": 29_000,
            "output_tokens": 139,
        },
    },
    "rate_limits": {
        "five_hour": {"used_percentage": 11, "resets_at": 1793091600},
        "seven_day": {"used_percentage": 14, "resets_at": 1793383200},
    },
}


class ResolveLimitTest(unittest.TestCase):
    def test_payload_size_overrides_heuristic(self):
        cw = {"context_window_size": 1_000_000}
        self.assertEqual(ctx.resolve_limit(cw, "claude-opus-5-5"), 1_000_000)

    def test_fallback_when_missing_or_garbage(self):
        for cw in (None, {}, {"context_window_size": 0}, {"context_window_size": -5},
                   {"context_window_size": "1000000"}, {"context_window_size": True},
                   {"context_window_size": 1.5}, "x"):
            self.assertEqual(ctx.resolve_limit(cw, "claude-opus-4-8"), 200_000)
            self.assertEqual(ctx.resolve_limit(cw, "fable-5"), 1_000_000)


class ResolveUsedTest(unittest.TestCase):
    def test_current_usage_beats_transcript(self):
        path = _write_transcript([_record(999)])
        try:
            cw = {"current_usage": {"input_tokens": 1, "cache_read_input_tokens": 2,
                                    "cache_creation_input_tokens": 3}}
            self.assertEqual(ctx.resolve_used(cw, path, 200_000), 6)
        finally:
            os.remove(path)

    def test_garbage_fields_count_zero(self):
        cw = {"current_usage": {"input_tokens": "x", "cache_read_input_tokens": None,
                                "cache_creation_input_tokens": 7}}
        self.assertEqual(ctx.resolve_used(cw, None, 200_000), 7)

    def test_fallback_to_transcript(self):
        path = _write_transcript([_record(1234)])
        try:
            for cw in (None, {}, {"current_usage": "bad"}, {"current_usage": None}):
                self.assertEqual(ctx.resolve_used(cw, path, 200_000), 1234)
        finally:
            os.remove(path)

    def test_used_percentage_when_no_current_usage(self):
        self.assertEqual(ctx.resolve_used({"used_percentage": 25}, None, 200_000), 50_000)

    def test_current_usage_wins_over_used_percentage(self):
        cw = {"used_percentage": 99, "current_usage": {"input_tokens": 1_000}}
        self.assertEqual(ctx.resolve_used(cw, None, 200_000), 1_000)

    def test_negative_fields_count_zero(self):
        cw = {"current_usage": {"input_tokens": -5_000, "cache_read_input_tokens": 3}}
        self.assertEqual(ctx.resolve_used(cw, None, 200_000), 3)

    def test_overflow_inputs_clamped_to_limit(self):
        self.assertEqual(
            ctx.resolve_used({"used_percentage": 1e308}, None, 200_000), 200_000)
        self.assertEqual(
            ctx.resolve_used({"used_percentage": 10 ** 400}, None, 200_000), 200_000)
        cw = {"current_usage": {"input_tokens": 10 ** 400}}
        self.assertEqual(ctx.resolve_used(cw, None, 200_000), 200_000)

    def test_negative_overflow_used_percentage_is_zero(self):
        self.assertEqual(
            ctx.resolve_used({"used_percentage": -1e308}, None, 1000), 0)
        self.assertEqual(
            ctx.resolve_used({"used_percentage": -(10 ** 400)}, None, 1000), 0)

    def test_transcript_usage_clamped_to_limit(self):
        path = _write_transcript([_record(10 ** 6)])
        try:
            self.assertEqual(ctx.resolve_used(None, path, 1000), 1000)
        finally:
            os.remove(path)

    def test_used_percentage_clamped(self):
        self.assertEqual(ctx.resolve_used({"used_percentage": 500}, None, 1000), 1000)
        self.assertEqual(ctx.resolve_used({"used_percentage": -5}, None, 1000), 0)

    def test_used_percentage_ignored_when_not_number(self):
        self.assertEqual(ctx.resolve_used({"used_percentage": "25"}, None, 200_000), 0)
        self.assertEqual(ctx.resolve_used({"used_percentage": True}, None, 200_000), 0)


class ColorDepthTest(_TruecolorMixin, unittest.TestCase):
    def test_truecolor_and_24bit_use_24bit_sgr(self):
        for value in ("truecolor", "24bit", "TrueColor"):
            os.environ["COLORTERM"] = value
            self.assertEqual(ctx.fg((1, 2, 3)), "\033[38;2;1;2;3m")
            self.assertEqual(ctx.bg((1, 2, 3)), "\033[48;2;1;2;3m")

    def test_other_values_use_256(self):
        for value in (None, "", "yes"):
            if value is None:
                os.environ.pop("COLORTERM", None)
            else:
                os.environ["COLORTERM"] = value
            self.assertTrue(ctx.fg((232, 141, 103)).startswith("\033[38;5;"))
            self.assertTrue(ctx.bg((232, 141, 103)).startswith("\033[48;5;"))

    def test_nearest_256_index(self):
        self.assertEqual(ctx.nearest_256((255, 255, 255)), 231)
        self.assertEqual(ctx.nearest_256((0, 0, 0)), 16)
        self.assertEqual(ctx.nearest_256((255, 0, 0)), 196)
        # 近灰色走灰階斜坡 232..255 / near-grays use the grayscale ramp
        self.assertTrue(232 <= ctx.nearest_256((70, 70, 80)) <= 255)
        for rgb, index in ((ctx.TRACK_RGB, 239), (ctx.OPUS_RGB, 173),
                           (ctx.SONNET_RGB, 74), (ctx.FABLE_RGB, 141),
                           (ctx.NEUTRAL_RGB, 247)):
            self.assertEqual(ctx.nearest_256(rgb), index)


class ModelPillTest(_TruecolorMixin, unittest.TestCase):
    def test_family_colors(self):
        for name, rgb in (("Fable 5", ctx.FABLE_RGB), ("Opus 5.5", ctx.OPUS_RGB),
                          ("Sonnet 5.5", ctx.SONNET_RGB), ("Haiku 5.5", ctx.HAIKU_RGB)):
            pill = ctx.model_pill("", name)
            self.assertIn(ctx.bg(rgb), pill)
            self.assertIn(ctx.fg(ctx.INK_RGB), pill)
            self.assertIn(ctx.BOLD, pill)
            self.assertEqual(_plain(pill), " " + name + " ")

    def test_family_detected_from_id_case_insensitively(self):
        self.assertIn(ctx.bg(ctx.OPUS_RGB), ctx.model_pill("CLAUDE-OPUS-5-5", "Custom"))
        self.assertIn(ctx.bg(ctx.SONNET_RGB), ctx.model_pill("claude-sonnet-5-5", "x"))

    def test_unknown_family_is_neutral_gray(self):
        self.assertIn(ctx.bg(ctx.NEUTRAL_RGB), ctx.model_pill("gpt-x", "Mystery"))

    def test_effort_inside_pill_keeps_background(self):
        pill = ctx.model_pill("claude-opus-5-5", "Opus 5.5", "medium")
        self.assertEqual(_plain(pill), " Opus 5.5 \u00b7 medium ")
        self.assertEqual(pill, (
            ctx.bg(ctx.OPUS_RGB) + ctx.fg(ctx.INK_RGB) + ctx.BOLD
            + " Opus 5.5" + ctx.UNBOLD + " \u00b7 medium " + ctx.RESET))
        # 名稱與 effort 之間只關粗體（SGR 22），不 reset，底色得以延續
        # Only bold is turned off between name and effort; no reset, so the
        # background persists.
        self.assertEqual(ctx.UNBOLD, "\033[22m")
        between = pill.split("Opus 5.5")[1].split("medium")[0]
        self.assertNotIn(ctx.RESET, between)

    def test_effort_absent_leaves_pill_unchanged(self):
        self.assertEqual(ctx.model_pill("claude-opus-5-5", "Opus 5.5", ""),
                         ctx.model_pill("claude-opus-5-5", "Opus 5.5"))
        self.assertNotIn(ctx.UNBOLD, ctx.model_pill("claude-opus-5-5", "Opus 5.5"))

    def test_effort_shown_on_unknown_family(self):
        pill = ctx.model_pill("gpt-x", "Mystery", "xhigh")
        self.assertIn(ctx.bg(ctx.NEUTRAL_RGB), pill)
        self.assertEqual(_plain(pill), " Mystery \u00b7 xhigh ")

    def test_effort_displayed_as_given(self):
        self.assertEqual(_plain(ctx.model_pill("", "M", "weird-Level")),
                         " M \u00b7 weird-Level ")

    def test_effort_without_model_name_has_no_pill(self):
        self.assertEqual(ctx.model_pill("claude-opus-5-5", "", "medium"), "")

    def test_empty_name_has_no_pill(self):
        self.assertEqual(ctx.model_pill("claude-opus-5-5", ""), "")


class EffortLevelTest(unittest.TestCase):
    def test_valid_levels(self):
        for level in ("low", "medium", "high", "xhigh", "max"):
            self.assertEqual(ctx.effort_level({"level": level}), level)

    def test_stripped(self):
        self.assertEqual(ctx.effort_level({"level": "  high \n"}), "high")

    def test_wrong_types_omitted(self):
        for value in (None, "medium", ["medium"], 5, True, {}, {"level": ""},
                      {"level": "   "}, {"level": 5}, {"level": ["x"]},
                      {"level": None}, {"other": "high"}):
            self.assertEqual(ctx.effort_level(value), "")

    def test_long_string_truncated(self):
        out = ctx.effort_level({"level": "x" * 50})
        self.assertEqual(out, "x" * ctx.MAX_EFFORT_CHARS)

    def test_truncation_leaves_no_trailing_space(self):
        self.assertEqual(ctx.effort_level({"level": "abcdefghijk  z"}), "abcdefghijk")

    def test_c1_bidi_and_surrogate_removed(self):
        for raw, expected in (("\u009b31mhigh", "31mhigh"),
                              ("hi\u202egh", "high"),
                              ("\ud800high", "high")):
            self.assertEqual(ctx.effort_level({"level": raw}), expected)

    def test_control_characters_removed(self):
        self.assertEqual(ctx.effort_level({"level": "hi\x1b[31mgh"}), "hi[31mgh")


class SanitizeTest(unittest.TestCase):
    def test_removes_escape_surrogate_bidi_c1(self):
        self.assertEqual(ctx._sanitize("a\x1b[31mb\ud800c\u202ed\u009be", 40), "a[31mbcde")

    def test_strips_and_caps_without_trailing_space(self):
        self.assertEqual(ctx._sanitize("  abc  def ", 4), "abc")
        self.assertEqual(ctx._sanitize("x" * 100, 40), "x" * 40)


class ContextBarTest(_TruecolorMixin, unittest.TestCase):
    def test_width_is_constant(self):
        for pct in (0, 1, 23, 50, 99, 100):
            self.assertEqual(len(_plain(ctx.context_bar(pct))), ctx.BAR_WIDTH)
        self.assertEqual(ctx.BAR_WIDTH, 12)

    def test_eighth_block_smoothing(self):
        self.assertEqual(_plain(ctx.context_bar(23)), "██\u258a" + "\u2500" * 9)
        self.assertEqual(_plain(ctx.context_bar(0)), "\u2500" * 12)
        self.assertEqual(_plain(ctx.context_bar(100)), "\u2588" * 12)
        self.assertEqual(_plain(ctx.context_bar(50)), "\u2588" * 6 + "\u2500" * 6)

    def test_level_colors_and_track(self):
        self.assertIn(ctx.fg(ctx.OK_RGB), ctx.context_bar(10))
        self.assertIn(ctx.fg(ctx.WARN_RGB), ctx.context_bar(75))
        self.assertIn(ctx.fg(ctx.CRIT_RGB), ctx.context_bar(90))
        self.assertIn(ctx.fg(ctx.TRACK_RGB), ctx.context_bar(10))


class RenderTest(_TruecolorMixin, unittest.TestCase):
    def test_layout_without_rate_limits(self):
        out = ctx.render(23, 229_005, 1_000_000, "Opus 5.5", model_id="claude-opus-5-5")
        self.assertEqual(_plain(out), " Opus 5.5  ██\u258a" + "\u2500" * 9 + " 23% 229k/1m")

    def test_pct_uses_level_color_and_usage_is_dim(self):
        out = ctx.render(75, 150_000, 200_000, "M")
        self.assertIn(ctx.fg(ctx.WARN_RGB) + "75%", out)
        self.assertIn(ctx.DIM + "150k/200k", out)

    def test_effort_passed_into_pill(self):
        out = ctx.render(23, 229_005, 1_000_000, "Opus 5.5", model_id="claude-opus-5-5",
                         effort="medium")
        self.assertEqual(
            _plain(out), " Opus 5.5 \u00b7 medium  ██\u258a" + "\u2500" * 9 + " 23% 229k/1m")

    def test_extra_appended_with_dim_pipe_separator(self):
        base = ctx.render(10, 20_000, 200_000, "M")
        out = ctx.render(10, 20_000, 200_000, "M", "EXTRA")
        self.assertEqual(out, base + ctx.DIM + " \u2502 " + ctx.RESET + "EXTRA")

    def test_empty_model_name_omits_pill(self):
        out = _plain(ctx.render(10, 20_000, 200_000, ""))
        self.assertTrue(out.startswith("\u2588"))


class CountdownTest(unittest.TestCase):
    NOW = 1_000_000.0

    def cd(self, delta):
        return ctx.format_countdown(self.NOW + delta, self.NOW)

    def test_minutes(self):
        self.assertEqual(self.cd(12 * 60), "12m")
        self.assertEqual(self.cd(59 * 60 + 59), "59m")
        self.assertEqual(self.cd(5), "1m")

    def test_hours_zero_padded_minutes(self):
        self.assertEqual(self.cd(2 * 3600 + 41 * 60), "2h41m")
        self.assertEqual(self.cd(4 * 3600 + 5 * 60), "4h05m")
        self.assertEqual(self.cd(3600), "1h00m")
        self.assertEqual(self.cd(23 * 3600 + 59 * 60), "23h59m")

    def test_days(self):
        self.assertEqual(self.cd(3 * 86400 + 4 * 3600), "3d4h")
        self.assertEqual(self.cd(5 * 86400), "5d")
        self.assertEqual(self.cd(86400), "1d")

    def test_huge_int_does_not_raise(self):
        self.assertEqual(ctx.format_countdown(10 ** 400, self.NOW), "")
        self.assertEqual(ctx.format_countdown(-(10 ** 400), self.NOW), "")

    def test_past_or_invalid_omitted(self):
        for v in (self.NOW, self.NOW - 10, None, "x", True, float("nan"),
                  float("inf"), 1e308, 10 ** 400, -1):
            self.assertEqual(ctx.format_countdown(v, self.NOW), "")


class RateLimitTest(_TruecolorMixin, unittest.TestCase):
    NOW = 1_000_000.0

    def rl(self, value):
        return ctx.render_rate_limits(value, self.NOW)

    def test_absent_returns_empty(self):
        for value in (None, {}, "x", {"five_hour": "x"}, {"five_hour": {}}):
            self.assertEqual(self.rl(value), "")

    def test_both_windows_format(self):
        out = self.rl({
            "five_hour": {"used_percentage": 11, "resets_at": self.NOW + 9660},
            "seven_day": {"used_percentage": 14, "resets_at": self.NOW + 3 * 86400 + 4 * 3600},
        })
        self.assertRegex(_plain(out), r"^5h 11% 2h41m \u2502 7d 14% 3d4h \u2192\d+%$")
        self.assertIn(ctx.DIM + "5h", out)
        self.assertIn(ctx.fg(ctx.OK_RGB) + "11%", out)
        self.assertIn(ctx.DIM + "2h41m", out)

    def test_partial_only_seven_day_and_no_countdown(self):
        out = self.rl({"seven_day": {"used_percentage": 90}})
        self.assertEqual(_plain(out), "7d 90%")
        self.assertIn(ctx.fg(ctx.CRIT_RGB) + "90%", out)

    def test_past_reset_omits_countdown(self):
        out = self.rl({"five_hour": {"used_percentage": 10, "resets_at": self.NOW - 5}})
        self.assertEqual(_plain(out), "5h 10%")

    def test_colors_by_threshold(self):
        out = self.rl({"five_hour": {"used_percentage": 75}})
        self.assertIn(ctx.fg(ctx.WARN_RGB) + "75%", out)

    def test_percentage_clamped_to_0_100(self):
        out = _plain(self.rl({
            "five_hour": {"used_percentage": 250},
            "seven_day": {"used_percentage": -20},
        }))
        self.assertEqual(out, "5h 100% \u2502 7d 0%")

    def test_huge_percentage_does_not_raise(self):
        for v in (1e308, 10 ** 400):
            out = self.rl({"five_hour": {"used_percentage": v}})
            self.assertEqual(_plain(out), "5h 100%")

    def test_non_number_percentage_skipped(self):
        self.assertEqual(self.rl({"five_hour": {"used_percentage": "11"}}), "")

    def test_now_defaults_to_wall_clock(self):
        with mock.patch.object(ctx.time, "time", return_value=self.NOW):
            out = ctx.render_rate_limits(
                {"five_hour": {"used_percentage": 1, "resets_at": self.NOW + 600}})
        self.assertEqual(_plain(out), "5h 1% 10m")


class CountdownColorTest(_TruecolorMixin, unittest.TestCase):
    NOW = 1_000_000.0
    BRIGHT = ctx.fg(ctx.CYAN_BRIGHT_RGB) + ctx.BOLD
    SOFT = ctx.fg(ctx.CYAN_SOFT_RGB)

    def segment(self, key, pct, remaining):
        out = ctx.render_rate_limits(
            {key: {"used_percentage": pct, "resets_at": self.NOW + remaining}}, self.NOW)
        return out.split("%" + ctx.RESET + " ", 1)[1]

    def style(self, key, pct, remaining):
        seg = self.segment(key, pct, remaining)
        if seg.startswith(self.BRIGHT):
            return "bright"
        if seg.startswith(self.SOFT):
            return "soft"
        self.assertTrue(seg.startswith(ctx.DIM), seg)
        return "dim"

    def test_constants_and_palette(self):
        self.assertEqual(
            (ctx.RELEASE_SOON_5H, ctx.RELEASE_NEAR_5H,
             ctx.RELEASE_SOON_7D, ctx.RELEASE_NEAR_7D),
            (1800, 3600, 21600, 86400))
        self.assertEqual(ctx.CYAN_BRIGHT_RGB, (80, 220, 230))
        self.assertEqual(ctx.CYAN_SOFT_RGB, (120, 170, 180))
        self.assertEqual(ctx.nearest_256(ctx.CYAN_BRIGHT_RGB), 80)
        self.assertEqual(ctx.nearest_256(ctx.CYAN_SOFT_RGB), 109)

    def test_five_hour_boundaries_gate_on(self):
        for remaining, expected in ((1, "bright"), (1799.9, "bright"), (1800, "soft"),
                                    (1859.9, "soft"), (3599.9, "soft"), (3600, "dim"),
                                    (4 * 3600, "dim")):
            self.assertEqual(self.style("five_hour", 92, remaining), expected, remaining)

    def test_seven_day_boundaries_gate_on(self):
        for remaining, expected in ((60, "bright"), (21599.9, "bright"), (21600, "soft"),
                                    (86399.9, "soft"), (86400, "dim"), (89999, "dim"),
                                    (5 * 86400, "dim")):
            self.assertEqual(self.style("seven_day", 92, remaining), expected, remaining)

    def test_usage_gate_uses_rounded_percentage(self):
        self.assertEqual(self.style("five_hour", 69.5, 600), "bright")
        self.assertEqual(self.style("five_hour", 69.4, 600), "dim")

    def test_each_displayed_string_maps_to_exactly_one_style(self):
        windows = (
            ("five_hour", (ctx.RELEASE_SOON_5H, ctx.RELEASE_NEAR_5H)),
            ("seven_day", (ctx.RELEASE_SOON_7D, ctx.RELEASE_NEAR_7D)),
        )
        for key, thresholds in windows:
            seen = {}
            for threshold in thresholds:
                for step in range(-240, 241):
                    remaining = threshold + step * 0.5
                    if remaining <= 0:
                        continue
                    text = ctx.format_countdown(self.NOW + remaining, self.NOW)
                    seen.setdefault(text, set()).add(self.style(key, 92, remaining))
            for text, styles in seen.items():
                self.assertEqual(len(styles), 1, (key, text, styles))

    def test_gate_boundary_at_warn_pct(self):
        self.assertEqual(self.style("five_hour", ctx.WARN_PCT, 600), "bright")
        self.assertEqual(self.style("five_hour", ctx.WARN_PCT - 1, 600), "dim")
        self.assertEqual(self.style("seven_day", ctx.WARN_PCT, 600), "bright")
        self.assertEqual(self.style("seven_day", ctx.WARN_PCT - 1, 600), "dim")

    def test_gate_off_is_dim_everywhere(self):
        for key, remaining in (("five_hour", 600), ("five_hour", 3000),
                               ("seven_day", 3600), ("seven_day", 50000)):
            self.assertEqual(self.style(key, 11, remaining), "dim")

    def test_exact_sgr(self):
        hot = ctx.render_rate_limits(
            {"five_hour": {"used_percentage": 92, "resets_at": self.NOW + 25 * 60}}, self.NOW)
        self.assertEqual(hot, (
            ctx.DIM + "5h" + ctx.RESET + " " + ctx.fg(ctx.CRIT_RGB) + "92%" + ctx.RESET
            + " " + ctx.fg(ctx.CYAN_BRIGHT_RGB) + ctx.BOLD + "25m" + ctx.RESET))
        cold = ctx.render_rate_limits(
            {"five_hour": {"used_percentage": 11, "resets_at": self.NOW + 25 * 60}}, self.NOW)
        self.assertEqual(cold, (
            ctx.DIM + "5h" + ctx.RESET + " " + ctx.fg(ctx.OK_RGB) + "11%" + ctx.RESET
            + " " + ctx.DIM + "25m" + ctx.RESET))

    def test_percentage_color_unchanged(self):
        seg = ctx.render_rate_limits(
            {"five_hour": {"used_percentage": 75, "resets_at": self.NOW + 600}}, self.NOW)
        self.assertIn(ctx.fg(ctx.WARN_RGB) + "75%", seg)

    def test_invalid_resets_at_still_no_countdown(self):
        for v in (None, "x", True, self.NOW - 5, float("nan"), 1e308, 10 ** 400):
            out = ctx.render_rate_limits(
                {"five_hour": {"used_percentage": 92, "resets_at": v}}, self.NOW)
            self.assertEqual(_plain(out), "5h 92%", v)
            self.assertNotIn(ctx.fg(ctx.CYAN_BRIGHT_RGB), out)

    def test_256_color_indexes_in_output(self):
        os.environ.pop("COLORTERM", None)
        out = ctx.render_rate_limits(
            {"five_hour": {"used_percentage": 92, "resets_at": self.NOW + 600},
             "seven_day": {"used_percentage": 92, "resets_at": self.NOW + 80000}}, self.NOW)
        self.assertIn("\033[38;5;80m", out)
        self.assertIn("\033[38;5;109m", out)


class _IsolatedStateMixin(_TruecolorMixin):
    """TZ 固定 UTC、XDG_CACHE_HOME 指向暫存目錄，絕不碰真實的家目錄。

    Pin TZ=UTC and point XDG_CACHE_HOME at a temp dir so the real home is
    never touched.
    """

    def setUp(self):
        self.addCleanup(ctx.time.tzset)  # 最先登記 = 最後執行，晚於環境還原 / runs last, after env restore
        super().setUp()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.cache_dir = tmp.name
        os.environ["XDG_CACHE_HOME"] = tmp.name
        os.environ["TZ"] = "UTC"
        ctx.time.tzset()


class DailyTargetTest(_IsolatedStateMixin, unittest.TestCase):
    NOW = 1_000_000_000.0  # UTC 2001-09-09 01:46:40
    MIDNIGHT = NOW - (NOW % 86400)

    def setUp(self):
        super().setUp()
        self.path = os.path.join(self.cache_dir, "sub", "weekly-target.json")

    def target(self, pct, days_from_midnight, path="default", now=None):
        path = self.path if path == "default" else path
        now = self.NOW if now is None else now
        return ctx.daily_target(pct, self.MIDNIGHT + days_from_midnight * 86400, now, path)

    def records(self):
        with open(self.path, encoding="utf-8") as f:
            return json.load(f)["records"]

    def state(self):
        return self.records()[0]

    def test_formula_example(self):
        self.assertEqual(self.target(60, 3), 73)

    def test_last_day_is_100(self):
        self.assertEqual(self.target(60, 1), 100)
        self.assertEqual(self.target(60, 0.5), 100)  # d 夾在 >= 1

    def test_no_state_path_uses_live_pct(self):
        self.assertEqual(self.target(60, 3, path=None), 73)
        self.assertFalse(os.path.exists(self.path))

    def test_first_render_writes_state(self):
        self.target(60, 3)
        self.assertEqual(self.records(), [{
            "window": self.MIDNIGHT + 3 * 86400,
            "date": "2001-09-09", "baseline": 60}])

    def test_baseline_anchors_target_within_the_day(self):
        self.target(60, 3)
        self.assertEqual(self.target(73, 3), 73)  # 不隨用量後退 / does not recede

    def test_state_not_rewritten_when_valid(self):
        self.target(60, 3)
        with mock.patch.object(ctx.os, "replace") as replace:
            self.target(65, 3)
        replace.assert_not_called()

    def test_new_day_rebaselines(self):
        self.target(60, 3)
        self.assertEqual(self.target(70, 3, now=self.NOW + 86400), 85)  # d = 2
        self.assertEqual(self.state()["baseline"], 70)
        self.assertEqual(self.state()["date"], "2001-09-10")

    def test_new_window_rebaselines(self):
        self.target(60, 3)
        self.target(10, 3 + 7)
        self.assertEqual([r["baseline"] for r in self.records()], [60, 10])

    def test_usage_below_baseline_rebaselines(self):
        self.target(60, 3)
        self.assertEqual(self.target(20, 3), int(20 + 80 / 3 + 0.5))
        self.assertEqual(self.state()["baseline"], 20)

    def test_corrupt_or_invalid_state_falls_back_and_rewrites(self):
        os.makedirs(os.path.dirname(self.path))
        window = self.MIDNIGHT + 3 * 86400

        def rec(**kw):
            r = {"window": window, "date": "2001-09-09", "baseline": 5}
            r.update(kw)
            return json.dumps({"records": [r]})

        bad = [
            "not json", "[]", "{}", '{"records": 5}', '{"records": [5]}',
            "[" * 200000,  # 過深巢狀 / deeply nested
            rec(baseline=True), rec(baseline=101), rec(baseline=-1), rec(baseline=5.5),
            rec(window=True), rec(window="x"), rec(window=float("inf")), rec(date=20010909),
        ]
        for text in bad:
            with open(self.path, "w", encoding="utf-8") as f:
                f.write(text)
            self.assertEqual(self.target(60, 3), 73, text)
            self.assertEqual(self.records(), [{"window": window, "date": "2001-09-09", "baseline": 60}], text)

    def test_unwritable_path_falls_back_silently(self):
        blocker = os.path.join(self.cache_dir, "file")
        with open(blocker, "w") as f:
            f.write("x")
        self.assertEqual(self.target(60, 3, path=os.path.join(blocker, "x", "s.json")), 73)

    def test_no_temp_file_left_behind(self):
        self.target(60, 3)
        self.assertEqual(os.listdir(os.path.dirname(self.path)), ["weekly-target.json"])

    def test_target_rounds_half_up(self):
        self.assertEqual(self.target(50, 4), 63)  # 62.5 -> 63，非銀行家進位 / not banker's

    def test_jittering_reset_time_keeps_baseline(self):
        reset = self.MIDNIGHT + 3 * 86400 + 1800
        ctx.daily_target(60, reset - 1, self.NOW, self.path)
        with mock.patch.object(ctx.os, "replace") as replace:
            for i, pct in enumerate((65, 66, 67, 68)):
                got = ctx.daily_target(pct, reset + (1 if i % 2 else -1), self.NOW, self.path)
                self.assertEqual(got, int(60 + 40 / ((reset - self.MIDNIGHT) / 86400) + 0.5))
        replace.assert_not_called()
        self.assertEqual(self.state()["baseline"], 60)

    def test_two_accounts_keep_their_own_baselines(self):
        a, b = self.MIDNIGHT + 3 * 86400, self.MIDNIGHT + 5 * 86400
        ctx.daily_target(60, a, self.NOW, self.path)
        ctx.daily_target(20, b, self.NOW, self.path)
        with mock.patch.object(ctx.os, "replace") as replace:
            for _ in range(2):
                self.assertEqual(ctx.daily_target(70, a, self.NOW, self.path), 73)
                self.assertEqual(ctx.daily_target(30, b, self.NOW, self.path), 36)
        replace.assert_not_called()
        self.assertEqual(sorted(r["baseline"] for r in self.records()), [20, 60])

    def test_keeps_at_most_three_and_drops_past_windows(self):
        for days in (3, 4, 5, 6):
            ctx.daily_target(10, self.MIDNIGHT + days * 86400, self.NOW, self.path)
        self.assertEqual([r["window"] for r in self.records()],
                         [self.MIDNIGHT + d * 86400 for d in (4, 5, 6)])
        later = self.NOW + 4.5 * 86400  # 4 天後的視窗已過去 / the day-4 window is past
        ctx.daily_target(10, self.MIDNIGHT + 8 * 86400, later, self.path)
        self.assertEqual([r["window"] for r in self.records()],
                         [self.MIDNIGHT + d * 86400 for d in (5, 6, 8)])

    def test_replace_failure_leaves_no_temp_file(self):
        with mock.patch.object(ctx.os, "replace", side_effect=OSError("boom")):
            self.assertEqual(self.target(60, 3), 73)
        self.assertEqual(os.listdir(os.path.dirname(self.path)), [])

    def test_fdopen_failure_closes_fd(self):
        with mock.patch.object(ctx.os, "fdopen", side_effect=OSError("boom")), \
                mock.patch.object(ctx.os, "close", wraps=os.close) as close:
            self.assertEqual(self.target(60, 3), 73)
        close.assert_called_once()
        self.assertEqual(os.listdir(os.path.dirname(self.path)), [])

    def test_huge_values_do_not_raise(self):
        self.assertIsNone(ctx.daily_target(60, 10 ** 400, self.NOW, self.path))

    def test_default_state_path_follows_xdg(self):
        self.assertEqual(ctx.default_state_path(),
                         os.path.join(self.cache_dir, "ctx-statusline", "weekly-target.json"))
        del os.environ["XDG_CACHE_HOME"]
        self.assertEqual(
            ctx.default_state_path(),
            os.path.join(os.path.expanduser("~"), ".cache", "ctx-statusline", "weekly-target.json"))

    def render(self, five=None, seven=None):
        rl = {}
        if five:
            rl["five_hour"] = five
        if seven:
            rl["seven_day"] = seven
        return ctx.render_rate_limits(rl, self.NOW, self.path)

    def test_render_appends_target_to_seven_day_only(self):
        out = self.render(
            {"used_percentage": 60, "resets_at": self.MIDNIGHT + 3 * 86400},
            {"used_percentage": 60, "resets_at": self.MIDNIGHT + 3 * 86400})
        self.assertEqual(_plain(out).count("\u2192"), 1)
        self.assertTrue(_plain(out).endswith("7d 60% 2d22h \u219273%"))

    def test_render_target_dim_when_under_and_warn_when_reached(self):
        reset = self.MIDNIGHT + 3 * 86400
        under = self.render(seven={"used_percentage": 60, "resets_at": reset})
        self.assertIn(ctx.DIM + "\u219273%", under)
        over = self.render(seven={"used_percentage": 73, "resets_at": reset})
        self.assertIn(ctx.fg(ctx.WARN_RGB) + "\u219273%", over)

    def test_render_no_target_without_valid_countdown(self):
        self.assertNotIn("\u2192", self.render(seven={"used_percentage": 60}))
        self.assertNotIn("\u2192", self.render(
            seven={"used_percentage": 60, "resets_at": self.NOW - 5}))


class LocalTimezoneTest(_IsolatedStateMixin, unittest.TestCase):
    """當地午夜依 TZ 計算，不是 UTC。 Local midnight follows TZ, not UTC."""

    def setUp(self):
        super().setUp()
        self.path = os.path.join(self.cache_dir, "weekly-target.json")

    def use_tz(self, name):
        os.environ["TZ"] = name
        ctx.time.tzset()

    def test_taipei_day_changes_at_utc_1600(self):
        self.use_tz("Asia/Taipei")
        before = calendar.timegm((2001, 9, 9, 15, 59, 0))  # 台北 23:59 / 23:59 local
        after = calendar.timegm((2001, 9, 9, 16, 1, 0))    # 台北隔天 00:01 / next day 00:01
        reset = calendar.timegm((2001, 9, 12, 16, 0, 0))   # 台北 9/13 00:00
        self.assertEqual(ctx.daily_target(60, reset, before, None), 70)  # d = 4
        self.assertEqual(ctx.daily_target(60, reset, after, None), 73)   # d = 3
        ctx.daily_target(60, reset, before, self.path)
        ctx.daily_target(60, reset, after, self.path)
        with open(self.path, encoding="utf-8") as f:
            self.assertEqual([r["date"] for r in json.load(f)["records"]], ["2001-09-10"])

    def test_new_york_dst_end_day_is_25_hours(self):
        self.use_tz("America/New_York")
        now = calendar.timegm((2001, 10, 28, 17, 0, 0))    # 夏令結束日 12:00 EST
        midnight = calendar.timegm((2001, 10, 28, 4, 0, 0))  # 00:00 EDT
        reset = calendar.timegm((2001, 10, 31, 5, 0, 0))     # 10/31 00:00 EST
        d = (reset - midnight) / 86400
        self.assertAlmostEqual(d, 3 + 1 / 24)
        self.assertEqual(ctx.daily_target(50, reset, now, None), int(50 + 50 / d + 0.5))
        self.assertEqual(ctx.daily_target(50, reset, now, None), 66)


class MainTest(_IsolatedStateMixin, unittest.TestCase):
    EXPECTED_TARGET = 37  # UTC：基準 14、距重置 3.75 天 / baseline 14, 3.75 days left
    def _run_main(self, stdin_text):
        buf = io.StringIO()
        old_stdin = ctx.sys.stdin
        ctx.sys.stdin = io.StringIO(stdin_text)
        try:
            with redirect_stdout(buf):
                ctx.main()
        finally:
            ctx.sys.stdin = old_stdin
        return buf.getvalue()

    def test_main_with_valid_payload(self):
        path = _write_transcript([_record(78_000)])
        try:
            payload = json.dumps({
                "model": {"id": "claude-opus-4-8", "display_name": "Opus 4.8"},
                "transcript_path": path,
            })
            out = _plain(self._run_main(payload))
            self.assertIn("Opus 4.8", out)
            self.assertIn("39%", out)
            self.assertIn("78k/200k", out)
        finally:
            os.remove(path)

    def test_main_with_bad_json_does_not_raise(self):
        out = _plain(self._run_main("this is not json"))
        self.assertIn("0%", out)
        self.assertIn("0/200k", out)

    def test_main_with_million_window(self):
        path = _write_transcript([_record(500_000)])
        try:
            payload = json.dumps({
                "model": {"id": "claude-opus-4-8[1m]", "display_name": "Opus 4.8"},
                "transcript_path": path,
            })
            out = _plain(self._run_main(payload))
            self.assertIn("50%", out)
            self.assertIn("500k/1m", out)
        finally:
            os.remove(path)

    def test_main_full_payload(self):
        now = 1793091600 - (2 * 3600 + 41 * 60)
        with mock.patch.object(ctx.time, "time", return_value=now):
            out = self._run_main(json.dumps(FULL_PAYLOAD))
        self.assertEqual(
            _plain(out),
            " Opus 5.5  ██\u258a" + "\u2500" * 9
            + " 23% 229k/1m \u2502 5h 11% 2h41m \u2502 7d 14% 3d11h \u2192{}%".format(self.EXPECTED_TARGET),
        )
        self.assertIn(ctx.bg(ctx.OPUS_RGB), out)

    def test_main_countdown_highlight_end_to_end(self):
        now = 1793091600 - 25 * 60
        payload = json.loads(json.dumps(FULL_PAYLOAD))
        payload["rate_limits"]["five_hour"]["used_percentage"] = 92
        with mock.patch.object(ctx.time, "time", return_value=now):
            out = self._run_main(json.dumps(payload))
        self.assertIn(ctx.fg(ctx.CYAN_BRIGHT_RGB) + ctx.BOLD + "25m" + ctx.RESET, out)
        # 7d 只有 14%，倒數維持暗色 / 7d is only 14%, so its countdown stays dim
        self.assertIn(ctx.DIM + "3d", out)
        self.assertNotIn(ctx.fg(ctx.CYAN_SOFT_RGB), out)

    def test_main_effort_end_to_end(self):
        payload = dict(FULL_PAYLOAD, effort={"level": "medium"})
        now = 1793091600 - (2 * 3600 + 41 * 60)
        with mock.patch.object(ctx.time, "time", return_value=now):
            out = self._run_main(json.dumps(payload))
        self.assertEqual(
            _plain(out),
            " Opus 5.5 \u00b7 medium  ██\u258a" + "\u2500" * 9
            + " 23% 229k/1m \u2502 5h 11% 2h41m \u2502 7d 14% 3d11h \u2192{}%".format(self.EXPECTED_TARGET),
        )
        self.assertIn(ctx.UNBOLD, out)

    def test_main_surrogate_effort_renders_not_guard(self):
        out = _plain(self._run_main(json.dumps(
            dict(FULL_PAYLOAD, effort={"level": "\ud800x"}))))
        self.assertIn("\u00b7 x ", out)
        self.assertNotEqual(out, ctx.guard_line())

    def test_main_model_name_is_sanitized(self):
        for name in ("Op\x1b[31mus", "Op\ud800us", "Op\u009b31mus"):
            raw = self._run_main(json.dumps(
                dict(FULL_PAYLOAD, model={"id": "claude-opus-5-5", "display_name": name})))
            self.assertNotIn("\x1b[31m", raw)
            self.assertNotIn("\u009b", raw)
            self.assertIn("Op", _plain(raw))
            self.assertIn("229k/1m", raw)

    def test_main_long_model_name_truncated(self):
        out = _plain(self._run_main(json.dumps(
            dict(FULL_PAYLOAD, model={"id": "claude-opus-5-5", "display_name": "N" * 200}))))
        self.assertIn(" " + "N" * 40 + " ", out)
        self.assertNotIn("N" * 41, out)

    def test_main_name_that_sanitizes_to_empty_falls_back_to_id(self):
        out = _plain(self._run_main(json.dumps(
            dict(FULL_PAYLOAD, model={"id": "claude-opus-5-5", "display_name": "\x1b\ud800"}))))
        self.assertIn("claude-opus-5-5", out)

    def test_main_garbage_effort_omitted(self):
        for effort in ("medium", ["medium"], 5, {}, {"level": ""}, {"level": ["x"]}, None):
            out = _plain(self._run_main(json.dumps(
                dict(FULL_PAYLOAD, effort=effort))))
            self.assertTrue(out.startswith(" Opus 5.5  "), out)
            self.assertNotIn("\u00b7", out)

    def test_main_256_color_fallback(self):
        os.environ.pop("COLORTERM", None)
        out = self._run_main(json.dumps(FULL_PAYLOAD))
        self.assertNotIn("38;2;", out)
        self.assertNotIn("48;2;", out)
        self.assertIn("48;5;", out)

    def test_main_current_usage_wins_over_used_percentage(self):
        payload = json.loads(json.dumps(FULL_PAYLOAD))
        payload["context_window"]["used_percentage"] = 99
        out = _plain(self._run_main(json.dumps(payload)))
        self.assertIn("23%", out)
        self.assertNotIn("99%", out)

    def test_main_overflow_inputs_render_without_outer_guard(self):
        for cw in ({"current_usage": {"input_tokens": 10 ** 400}},
                   {"used_percentage": 1e308},
                   {"current_usage": {"input_tokens": -5_000}}):
            out = _plain(self._run_main(json.dumps({
                "model": {"id": "claude-opus-4-8", "display_name": "Opus"},
                "context_window": cw,
            })))
            self.assertIn("Opus", out)
            self.assertIn("/200k", out)
            self.assertNotIn("-", out)

    def test_main_huge_resets_at_keeps_full_line(self):
        payload = json.loads(json.dumps(FULL_PAYLOAD))
        payload["model"] = {"id": "claude-opus-4-8", "display_name": "Opus"}
        del payload["context_window"]["context_window_size"]
        raw = json.dumps(payload).replace("1793091600", "1" + "0" * 400)
        out = _plain(self._run_main(raw))
        self.assertIn("Opus", out)
        self.assertIn("/200k", out)
        self.assertIn("5h 11%", out)
        self.assertNotEqual(out, ctx.guard_line())

    def test_main_non_string_display_name_falls_back_to_id(self):
        out = _plain(self._run_main(json.dumps({
            "model": {"id": "claude-opus-4-8", "display_name": ["x"]}})))
        self.assertIn("claude-opus-4-8", out)

    def test_main_non_string_transcript_path_does_not_raise(self):
        out = _plain(self._run_main(json.dumps({
            "model": {"id": "claude-opus-4-8"}, "transcript_path": ["x"]})))
        self.assertIn("0/200k", out)

    def test_main_without_rate_limits_has_no_separator(self):
        payload = dict(FULL_PAYLOAD)
        del payload["rate_limits"]
        out = self._run_main(json.dumps(payload))
        self.assertEqual(out, ctx.render(
            23, 229_005, 1_000_000, "Opus 5.5", model_id="claude-opus-5-5"))
        self.assertNotIn("\u2502", out)

    def test_main_garbage_new_fields_do_not_raise(self):
        payload = {"model": {"id": 5, "display_name": ["x"]}, "context_window": [1],
                   "rate_limits": {"five_hour": [], "seven_day": {"used_percentage": {}}}}
        out = _plain(self._run_main(json.dumps(payload)))
        self.assertIn("0%", out)
        self.assertIn("0/200k", out)
        payload["context_window"] = {"current_usage": {"input_tokens": 1e999}}
        out = _plain(self._run_main(json.dumps(payload)))
        self.assertIn("0/200k", out)


class OuterGuardTest(unittest.TestCase):
    def test_guard_line_is_plain_and_sane(self):
        line = ctx.guard_line()
        self.assertEqual(line, "\u2500" * ctx.BAR_WIDTH + " 0%")
        self.assertNotIn("\033", line)


if __name__ == "__main__":
    unittest.main()
