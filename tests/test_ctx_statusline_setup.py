#!/usr/bin/env python3
"""ctx-statusline-setup 的單元測試（純標準庫 unittest）。"""
import importlib.machinery
import importlib.util
import json
import os
import tempfile
import unittest

# 腳本名含連字號且無副檔名，需明確傳入 SourceFileLoader，
# 否則 spec_from_file_location 在 Python 3.14 回傳 None。
_HERE = os.path.dirname(os.path.abspath(__file__))
_MODULE_PATH = os.path.join(_HERE, os.pardir, "ctx-statusline-setup")
_loader = importlib.machinery.SourceFileLoader("ctx_statusline_setup", _MODULE_PATH)
_spec = importlib.util.spec_from_file_location("ctx_statusline_setup", _MODULE_PATH, loader=_loader)
setup = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(setup)


class PureFnTests(unittest.TestCase):
    def test_apply_sets_status_line_without_mutating(self):
        original = {"other": 1}
        result = setup.apply_status_line(original, "/usr/bin/python3 /x/ctx-statusline")
        self.assertEqual(
            result["statusLine"],
            {"type": "command", "command": "/usr/bin/python3 /x/ctx-statusline"},
        )
        self.assertEqual(result["other"], 1)
        self.assertNotIn("statusLine", original)

    def test_remove_drops_key_and_reports(self):
        data = {"statusLine": {"type": "command"}, "keep": 2}
        new_data, removed = setup.remove_status_line(data)
        self.assertTrue(removed)
        self.assertNotIn("statusLine", new_data)
        self.assertEqual(new_data["keep"], 2)
        self.assertIn("statusLine", data)

    def test_remove_absent_reports_false(self):
        new_data, removed = setup.remove_status_line({"keep": 1})
        self.assertFalse(removed)
        self.assertEqual(new_data, {"keep": 1})


if __name__ == "__main__":
    unittest.main()
