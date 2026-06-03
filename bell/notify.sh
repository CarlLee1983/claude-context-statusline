#!/bin/sh
# bell/notify.sh — AI CLI 跑完一輪時送出終端機 BEL，由 Ghostty 標記分頁。
# 永不讓 host CLI 崩潰：任何失敗都吞掉並 exit 0。
#
# 用法 / Usage: notify.sh <source> [payload]
#   claude  無條件送 BEL（Stop hook 已代表一輪完成）
#   codex   僅當 payload JSON 的 type 為 agent-turn-complete 時送
# 測試/特殊情境可用 BELL_TTY 覆寫輸出目標（預設 /dev/tty）。
src="${1:-}"

if [ "$src" = "codex" ]; then
  case "${2:-}" in
    *'"type":"agent-turn-complete"'*|*'"type": "agent-turn-complete"'*) : ;;
    *) exit 0 ;;
  esac
fi

tty_out="${BELL_TTY:-/dev/tty}"
{ printf '\a' > "$tty_out"; } 2>/dev/null || true
exit 0
