#!/usr/bin/env python3
"""Claude Code 狀態列：顯示目前 session 的 context window 佔用程度。

從 stdin 讀取 Claude Code 傳入的 statusline JSON，解析 transcript（JSONL）
中最後一筆 usage，算出已用 context 佔模型上限的百分比，輸出一條彩色進度條。

設計上絕不拋例外中斷 statusline：任何錯誤都退回 0% 顯示。
"""
import sys
import os
import json

GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
DIM = "\033[2m"
RESET = "\033[0m"

BAR_WIDTH = 10
WARN_PCT = 70   # >= 此值轉黃
CRIT_PCT = 85   # >= 此值轉紅


def context_limit(model_id):
    """依 model id 判斷 context 上限；含 1m 視為百萬窗。"""
    return 1_000_000 if "1m" in (model_id or "").lower() else 200_000


def used_tokens(transcript_path):
    """從 transcript 尾端往前找第一筆含 usage 的記錄，回傳已用 context tokens。"""
    if not transcript_path or not os.path.isfile(transcript_path):
        return 0
    try:
        with open(transcript_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return 0

    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        # 跳過 subagent（sidechain）訊息，只反映主 session 的 context
        if obj.get("isSidechain"):
            continue
        message = obj.get("message")
        if not isinstance(message, dict):
            continue
        usage = message.get("usage")
        if not isinstance(usage, dict):
            continue
        total = (
            (usage.get("input_tokens") or 0)
            + (usage.get("cache_read_input_tokens") or 0)
            + (usage.get("cache_creation_input_tokens") or 0)
        )
        if total > 0:
            return total
    return 0


def humanize(n):
    """把 token 數縮寫成人類可讀（72000 -> 72k、1000000 -> 1m）。"""
    if n >= 1_000_000:
        v = n / 1_000_000
        return "{}m".format(int(v) if v == int(v) else round(v, 1))
    if n >= 1_000:
        return "{}k".format(round(n / 1_000))
    return str(n)


def render(pct, used, limit, model_name):
    """組出狀態列字串：模型名 + 彩色進度條 + token 絕對數字。"""
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


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        data = {}

    model = data.get("model") or {}
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
        sys.stdout.write("[" + "░" * BAR_WIDTH + "] 0%")
