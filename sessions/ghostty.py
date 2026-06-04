#!/usr/bin/env python3
"""ghostty.py — Ghostty AppleScript 橋接（階段二一鍵切換）。

純函式 pick_terminal（cwd + 標題啟發式選分頁）可單測；
list_terminals / focus_terminal 為 osascript subprocess 薄邊界，不單測
（對齊 repo 既有 PTY 邊界慣例）。永不崩潰：所有失敗回安全值。
"""
import os
import re
import shutil
import subprocess


def _norm_cwd(path):
    """正規化 cwd：去尾斜線，root 保留為 '/'；非字串回 ''。"""
    if not isinstance(path, str):
        return ""
    p = path.rstrip("/")
    if not p:
        return "/" if path else ""
    return p


def _title_is_pathlike(title, cwd):
    """shell 分頁標題通常是路徑（縮寫 / user@host: ~ / 純 basename）；
    CLI session 標題是任務摘要。回 True 代表像 shell，去歧義時降權。"""
    if not isinstance(title, str):
        return True
    t = title.strip()
    if not t:
        return True
    if t.startswith("/") or t.startswith("~") or "…/" in t or ": ~" in t:
        return True
    base = os.path.basename(_norm_cwd(cwd))
    if base and t == base:
        return True
    return False


def pick_terminal(record, terminals):
    """從 Ghostty terminals 選出最符合該 session 的 terminal id（best-effort）。
    純函式、不改輸入。無 cwd 對應回 None。"""
    if not isinstance(record, dict):
        return None
    if not isinstance(terminals, (list, tuple)):
        return None
    target = _norm_cwd(record.get("cwd", ""))
    if not target:
        return None
    matches = [t for t in terminals
               if isinstance(t, dict) and _norm_cwd(t.get("cwd", "")) == target]
    if not matches:
        return None
    cli_like = [t for t in matches
                if not _title_is_pathlike(t.get("title", ""), target)]
    chosen = cli_like[0] if cli_like else matches[0]
    return chosen.get("id")


# ---- osascript 薄邊界（不單測；永不崩潰）-----------------------------------

_LIST_SCRIPT = (
    'tell application "Ghostty"\n'
    '  set out to ""\n'
    '  repeat with t in terminals\n'
    '    try\n'
    '      set out to out & (id of t) & (ASCII character 9) '
    '& (working directory of t) & (ASCII character 9) & (name of t) & linefeed\n'
    '    end try\n'
    '  end repeat\n'
    '  return out\n'
    'end tell'
)

_ID_RE = re.compile(r"^[A-Za-z0-9-]+$")


def _run_osascript(script, timeout=3):
    """跑 osascript；失敗（無 osascript / 非 0 / 例外）回 None，成功回 stdout 字串。"""
    osa = shutil.which("osascript")
    if not osa:
        return None
    try:
        proc = subprocess.run([osa, "-e", script],
                              capture_output=True, timeout=timeout)
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    try:
        return proc.stdout.decode("utf-8", "replace")
    except Exception:
        return None


def list_terminals():
    """列舉 Ghostty terminals → [{"id","cwd","title"}]。失敗回 []。"""
    raw = _run_osascript(_LIST_SCRIPT)
    if not raw:
        return []
    out = []
    for line in raw.splitlines():
        if not line:
            continue
        parts = line.split("\t", 2)
        if len(parts) < 2:
            continue
        out.append({
            "id": parts[0],
            "cwd": parts[1],
            "title": parts[2] if len(parts) > 2 else "",
        })
    return out


def focus_terminal(term_id):
    """focus 指定 terminal 並把 Ghostty 帶到最前。成功回 True，否則 False。"""
    if not isinstance(term_id, str) or not _ID_RE.match(term_id):
        return False
    script = (
        'tell application "Ghostty"\n'
        '  focus (first terminal whose id is "%s")\n'
        '  activate\n'
        'end tell' % term_id
    )
    return _run_osascript(script) is not None
