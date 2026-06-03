#!/usr/bin/env bash
# 安裝 Claude Code context 用量狀態列。
# Install the Claude Code context-usage statusline.
#
# 做兩件事 / Two steps:
#   (1) 複製腳本到 ~/.claude/hooks/      copy the script into ~/.claude/hooks/
#   (2) 把 statusLine 併進 settings.json  merge statusLine into settings.json
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
HOOKS_DIR="$CLAUDE_DIR/hooks"
SETTINGS="$CLAUDE_DIR/settings.json"
SOURCE="$SCRIPT_DIR/ctx-statusline.py"
TARGET="$HOOKS_DIR/ctx-statusline.py"
PYTHON="/usr/bin/python3"

# --- 前置檢查 / preflight ---------------------------------------------------
if [ ! -x "$PYTHON" ]; then
  echo "!! 找不到 $PYTHON（本工具依賴 macOS 內建 python3）。" >&2
  echo "!! $PYTHON not found (this tool relies on macOS's built-in python3)." >&2
  exit 1
fi
if [ ! -f "$SOURCE" ]; then
  echo "!! 找不到來源腳本 / source script missing: $SOURCE" >&2
  exit 1
fi

echo "==> 安裝腳本到 / installing script to: $TARGET"
mkdir -p "$HOOKS_DIR"
cp "$SOURCE" "$TARGET"
chmod +x "$TARGET"

echo "==> 設定 statusLine / configuring statusLine: $SETTINGS"
# 合併邏輯統一由 ctx-statusline-setup 處理（含建立、備份、非法 JSON 中止、保留其他設定）。
# Delegate the merge to ctx-statusline-setup (create, backup, invalid-JSON guard, key preservation).
"$PYTHON" "$SCRIPT_DIR/ctx-statusline-setup" --command "$PYTHON $TARGET"

echo
echo "✅ 安裝完成。請重新開啟一個 Claude Code session 即可在底部看到："
echo "✅ Done. Open a new Claude Code session to see it at the bottom:"
echo "   Opus 4.8 · [████░░░░░░] 39% · 78k/200k"
