#!/bin/sh
# sessions/track.sh — 把 AI CLI hook 事件寫成 session 狀態（永不弄崩 host CLI）。
# 用法 / Usage:
#   track.sh claude          Claude hook：事件 JSON 由 stdin 提供
#   track.sh codex <payload> Codex notify：payload 為 JSON 字串
# 任何失敗（含 python3 缺席）都吞掉並 exit 0。
dir=$(cd "$(dirname "$0")" 2>/dev/null && pwd)
{ /usr/bin/python3 "$dir/sessions-track" "$@"; } 2>/dev/null || true
exit 0
