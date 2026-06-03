#!/usr/bin/env bash
# 移除 context 用量狀態列：刪腳本、從 settings.json 拿掉 statusLine。
# Remove the context-usage statusline: delete the script, drop statusLine from settings.json.
set -euo pipefail

CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
TARGET="$CLAUDE_DIR/hooks/ctx-statusline.py"
PYTHON="/usr/bin/python3"

echo "==> 移除 / removing: $TARGET"
rm -f "$TARGET"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -x "$PYTHON" ]; then
  "$PYTHON" "$SCRIPT_DIR/ctx-statusline-setup" --remove
fi

echo "✅ 已移除。重開 Claude Code session 生效。"
echo "✅ Removed. Restart a Claude Code session to take effect."
