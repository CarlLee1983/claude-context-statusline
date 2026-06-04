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


def _coerce_times(record):
    """把 updated_at / started_at 正規化成 float（壞值→0.0），下游純函式才不會因
    state 檔型別異常而拋例外（永不崩潰）。回傳同一個 dict（就地補正時間欄位）。"""
    for key in ("updated_at", "started_at"):
        try:
            record[key] = float(record.get(key, 0))
        except (TypeError, ValueError):
            record[key] = 0.0
    return record


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
            out.append(_coerce_times(rec))
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


# ---- curses 薄殼（不單測；永不崩潰）---------------------------------------
HEADER = "  狀態      CLI     目錄                      時間  路徑"
HELP = "  j/k 移動 · r 刷新 · Enter 跳到 · c 複製 · q 離開"


def _load_ghostty():
    """懶載入同目錄的 ghostty 模組（dashboard 被 importlib 以非標準名載入時，
    sys.path 可能沒有 sessions/，故顯式補上）。"""
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import ghostty
    return ghostty


def _jump(record):
    """focus 到該 session 的 Ghostty 分頁。回提示訊息（成功為空字串）。永不崩潰。"""
    try:
        gh = _load_ghostty()
        terms = gh.list_terminals()
        if not terms:
            return "找不到 Ghostty 分頁（需 Ghostty 1.3+ 並核准自動化權限）"
        tid = gh.pick_terminal(record, terms)
        if not tid:
            return "找不到對應分頁"
        if gh.focus_terminal(tid):
            return ""
        return "切換失敗（檢查 系統設定›隱私權›自動化）"
    except Exception:
        return "切換失敗"


def _copy_path(path):
    try:
        subprocess.run(["pbcopy"], input=path.encode(), timeout=2)
    except Exception:
        pass


def _draw(stdscr, records, selected, now, message=""):
    stdscr.erase()
    height, width = stdscr.getmaxyx()
    title = f" AI session 總覽（{len(records)}）"
    stdscr.addnstr(0, 0, title.ljust(width - 1), width - 1, curses.A_BOLD)
    if height > 1:
        stdscr.addnstr(1, 0, HEADER, width - 1, curses.A_DIM)
    for i, rec in enumerate(records):
        row = 2 + i
        if row >= height - 1:
            break
        attr = curses.A_REVERSE if i == selected else curses.A_NORMAL
        stdscr.addnstr(row, 0, format_row(rec, now).ljust(width - 1), width - 1, attr)
    if not records and height > 4 and width > 5:
        stdscr.addnstr(3, 2, "（目前沒有 session；開個 Claude Code 跑跑看）", width - 3)
    footer = message or HELP
    stdscr.addnstr(height - 1, 0, footer[:width - 1], width - 1, curses.A_DIM)
    stdscr.refresh()


def _loop(stdscr, directory):
    curses.curs_set(0)
    stdscr.nodelay(True)
    selected = 0
    last_load = 0.0
    records = []
    message = ""
    while True:
        now = time.time()
        if now - last_load >= REFRESH_SEC:
            records = sorted(load_records(directory), key=sort_key)
            last_load = now
            selected = max(0, min(selected, len(records) - 1))
        _draw(stdscr, records, selected, int(now), message)
        try:
            ch = stdscr.getch()
        except curses.error:
            ch = -1
        if ch in (ord("q"), 27):
            return
        if ch in (ord("j"), curses.KEY_DOWN):
            selected = min(selected + 1, max(0, len(records) - 1))
            message = ""
        elif ch in (ord("k"), curses.KEY_UP):
            selected = max(selected - 1, 0)
            message = ""
        elif ch == ord("r"):
            last_load = 0.0
            message = ""
        elif ch == ord("c") and records:
            _copy_path(records[selected].get("cwd", ""))
            message = "已複製路徑"
        elif ch in (curses.KEY_ENTER, 10, 13) and records:
            message = _jump(records[selected])
        else:
            time.sleep(0.05)


def main(argv=None, env=None):  # argv 保留供未來旗標解析；目前未用
    env = os.environ if env is None else env
    directory = default_dir(env)
    try:
        curses.wrapper(_loop, directory)
    except KeyboardInterrupt:
        pass
    except Exception:
        return 0   # 永不崩潰：離開時 curses.wrapper 已還原終端機
    return 0


if __name__ == "__main__":
    sys.exit(main())
