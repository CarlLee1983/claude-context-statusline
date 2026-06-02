#!/usr/bin/env python3
"""ctx-statusline.py 的單元測試（純標準庫 unittest）。

Unit tests for ctx-statusline.py (pure-stdlib unittest, no third-party deps).

執行 / Run:  python3 -m unittest discover -s tests
"""
import importlib.util
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout

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


class RenderTest(unittest.TestCase):
    def test_color_thresholds(self):
        self.assertIn(ctx.GREEN, ctx.render(10, 20_000, 200_000, "M"))
        self.assertIn(ctx.YELLOW, ctx.render(75, 150_000, 200_000, "M"))
        self.assertIn(ctx.RED, ctx.render(90, 180_000, 200_000, "M"))

    def test_bar_width_and_fill(self):
        out = ctx.render(50, 100_000, 200_000, "M")
        self.assertEqual(out.count("█") + out.count("░"), ctx.BAR_WIDTH)
        self.assertEqual(out.count("█"), 5)

    def test_includes_model_name_and_tokens(self):
        out = ctx.render(39, 78_000, 200_000, "Opus 4.8")
        self.assertIn("Opus 4.8", out)
        self.assertIn("39%", out)
        self.assertIn("78k/200k", out)

    def test_empty_model_name_omits_prefix(self):
        out = ctx.render(10, 20_000, 200_000, "")
        self.assertNotIn("·", out.split("%")[0].replace("/", ""))


class MainTest(unittest.TestCase):
    def _run_main(self, stdin_text, monkey_stdin=True):
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
            out = self._run_main(payload)
            self.assertIn("Opus 4.8", out)
            self.assertIn("39%", out)
        finally:
            os.remove(path)

    def test_main_with_bad_json_does_not_raise(self):
        out = self._run_main("this is not json")
        self.assertIn("0%", out)

    def test_main_with_million_window(self):
        path = _write_transcript([_record(500_000)])
        try:
            payload = json.dumps({
                "model": {"id": "claude-opus-4-8[1m]", "display_name": "Opus 4.8"},
                "transcript_path": path,
            })
            out = self._run_main(payload)
            self.assertIn("50%", out)
            self.assertIn("500k/1m", out)
        finally:
            os.remove(path)


if __name__ == "__main__":
    unittest.main()
