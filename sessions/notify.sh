#!/bin/sh
# sessions/notify.sh — Codex 完成事件的合併派發器（選項 A）。
# 同時觸發 bell（送 BEL 標記分頁）與 sessions（寫狀態檔）。永不崩潰。
# Codex notify 會把 payload 接在最後一個參數，故兩者都收到相同的 "$@"。
dir=$(cd "$(dirname "$0")" 2>/dev/null && pwd)
[ -z "$dir" ] && exit 0
{ "$dir/../bell/notify.sh" "$@"; } 2>/dev/null || true
{ "$dir/track.sh" "$@"; } 2>/dev/null || true
exit 0
