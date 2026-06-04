#!/usr/bin/env python3
"""dashboard.py — 多 session 總覽 TUI（stdlib curses）。

純函式（載入/排序/過期/格式化）可單測；curses 主迴圈為薄殼。永不崩潰。
honors AI_SESSIONS_DIR。階段一唯讀；偵測 $TMUX 的階段二功能為後續。
"""
import curses
import json
import os
import subprocess
import sys
import time

REFRESH_SEC = 1.0
STALE_SEC = 1800
STATUS_ORDER = {"waiting": 0, "running": 1, "idle": 2}
# (emoji, 形狀角標)：色盲友善雙重編碼，對齊 repo 慣例。
STATUS_GLYPH = {"waiting": ("⏳", "!"), "running": ("▶", "*"), "idle": ("✓", " ")}


def default_dir(env=None):
    env = os.environ if env is None else env
    return env.get("AI_SESSIONS_DIR") or os.path.expanduser("~/.cache/ai-sessions")


def load_records(directory):
    out = []
    try:
        names = os.listdir(directory)
    except OSError:
        return out
    for name in names:
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(directory, name), encoding="utf-8") as f:
                rec = json.load(f)
        except Exception:
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out


def is_stale(record, now, threshold=STALE_SEC):
    return (now - record.get("updated_at", 0)) > threshold


def sort_key(record):
    return (STATUS_ORDER.get(record.get("status"), 9), -record.get("updated_at", 0))


def humanize(seconds):
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    return f"{seconds // 3600}h"


def format_row(record, now):
    status = record.get("status", "idle")
    glyph, shape = STATUS_GLYPH.get(status, ("?", "?"))
    cwd = record.get("cwd", "")
    base = os.path.basename(cwd.rstrip("/")) or cwd or "?"
    age = humanize(now - record.get("updated_at", now))
    cli = record.get("cli", "?")
    stale = " (stale)" if is_stale(record, now) else ""
    return f"{glyph}{shape} {status:<8} {cli:<7} {base:<24} {age:>4}{stale}  {cwd}"
