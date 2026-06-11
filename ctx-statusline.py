#!/usr/bin/env python3
"""Claude Code 狀態列：顯示目前 session 的 context window 佔用程度。

Claude Code statusline: show how much of the current session's context
window is in use.

從 stdin 讀取 Claude Code 傳入的 statusline JSON，解析 transcript（JSONL）
中最後一筆 usage，算出已用 context 佔模型上限的百分比，輸出一條彩色進度條。

Reads the statusline JSON Claude Code pipes in on stdin, parses the last
usage record from the transcript (JSONL), computes how much of the model's
context limit is used, and prints one colored progress bar.

設計上絕不拋例外中斷 statusline：任何錯誤都退回 0% 顯示。
By design this never raises out to the statusline: any error falls back to
a 0% display.
"""
import json
import os
import sys
from typing import Optional

GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
DIM = "\033[2m"
RESET = "\033[0m"

BAR_WIDTH = 10
WARN_PCT = 70   # >= 此值轉黃 / turn yellow at/above this
CRIT_PCT = 85   # >= 此值轉紅 / turn red at/above this

# transcript 可能很大；只讀尾端這麼多 bytes 找最後一筆 usage。
# Transcripts can be large; only read this many trailing bytes to find the
# most recent usage record. Falls back to a full scan if nothing is found.
TAIL_BYTES = 2_000_000

DEFAULT_LIMIT = 200_000
MILLION_LIMIT = 1_000_000


def context_limit(model_id: Optional[str]) -> int:
    """依 model id 判斷 context 上限；含 1m 或 Fable 5 視為百萬窗。

    Pick the context limit from the model id; ids containing ``1m`` or Fable 5
    map to the 1,000,000-token window, otherwise the default 200,000.
    """
    normalized = (model_id or "").lower().replace("_", "-")
    if "1m" in normalized or "fable-5" in normalized or "fable 5" in normalized:
        return MILLION_LIMIT
    return DEFAULT_LIMIT


def _usage_tokens(obj: dict) -> int:
    """從單筆記錄取出已用 context tokens；非主 session 或無 usage 回傳 0。

    Extract used context tokens from one record; returns 0 for non-main-session
    records (sidechain/subagent) or records without usage.
    """
    # 跳過 subagent（sidechain）訊息，只反映主 session 的 context（與 /context 一致）
    # Skip subagent (sidechain) messages so we mirror the main session only.
    if obj.get("isSidechain"):
        return 0
    message = obj.get("message")
    if not isinstance(message, dict):
        return 0
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return 0
    return (
        (usage.get("input_tokens") or 0)
        + (usage.get("cache_read_input_tokens") or 0)
        + (usage.get("cache_creation_input_tokens") or 0)
    )


def _scan_lines(lines) -> int:
    """從尾端往前找第一筆含 usage 的主 session 記錄。

    Scan from the end for the first main-session record carrying usage.
    """
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        total = _usage_tokens(obj)
        if total > 0:
            return total
    return 0


def _read_lines(path: str) -> list:
    """讀 transcript 行；先試尾端 TAIL_BYTES，必要時退回整檔。

    Read transcript lines: try the trailing TAIL_BYTES first, falling back to
    the whole file when the file is larger than the tail window.
    """
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        if size > TAIL_BYTES:
            f.seek(size - TAIL_BYTES)
            f.readline()  # 丟掉可能被切半的第一行 / drop the partial first line
        data = f.read()
    return data.decode("utf-8", errors="replace").splitlines()


def used_tokens(transcript_path: Optional[str]) -> int:
    """回傳目前主 session 已用的 context tokens。

    Return the context tokens currently used by the main session.
    """
    if not transcript_path or not os.path.isfile(transcript_path):
        return 0
    try:
        size = os.path.getsize(transcript_path)
        lines = _read_lines(transcript_path)
    except OSError:
        return 0

    total = _scan_lines(lines)
    # 尾端找不到，且檔案曾被截斷，整檔再掃一次（涵蓋「近期全是 sidechain」的情況）
    # Nothing in the tail and the file was truncated: rescan the whole file
    # (covers the "recent records are all sidechain" case).
    if total == 0 and size > TAIL_BYTES:
        try:
            with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
                total = _scan_lines(f.readlines())
        except OSError:
            return 0
    return total


def humanize(n: int) -> str:
    """把 token 數縮寫成人類可讀（72000 -> 72k、1000000 -> 1m）。

    Abbreviate a token count for humans (72000 -> 72k, 1000000 -> 1m).
    """
    if n >= 1_000_000:
        v = n / 1_000_000
        return "{}m".format(int(v) if v == int(v) else round(v, 1))
    if n >= 1_000:
        return "{}k".format(round(n / 1_000))
    return str(n)


def render(pct: int, used: int, limit: int, model_name: str) -> str:
    """組出狀態列字串：模型名 + 彩色進度條 + token 絕對數字。

    Build the statusline string: model name + colored bar + absolute tokens.
    """
    if pct >= CRIT_PCT:
        color = RED
    elif pct >= WARN_PCT:
        color = YELLOW
    else:
        color = GREEN
    filled = max(0, min(BAR_WIDTH, round(pct * BAR_WIDTH / 100)))
    bar = "█" * filled + "░" * (BAR_WIDTH - filled)
    prefix = "{}{} · {}".format(DIM, model_name, RESET) if model_name else ""
    return "{}{}[{}] {}% · {}/{}{}".format(
        prefix, color, bar, pct, humanize(used), humanize(limit), RESET
    )


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}

    model = data.get("model")
    model = model if isinstance(model, dict) else {}
    model_id = model.get("id", "")
    model_name = model.get("display_name") or model_id
    transcript = data.get("transcript_path", "")

    limit = context_limit(model_id)
    used = used_tokens(transcript)
    pct = min(100, round(used * 100 / limit)) if limit else 0

    sys.stdout.write(render(pct, used, limit, model_name))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # 最後防線：任何未預期錯誤都不該讓 statusline 變紅噴錯
        # Last resort: no unexpected error should make the statusline error out.
        sys.stdout.write("[" + "░" * BAR_WIDTH + "] 0%")
