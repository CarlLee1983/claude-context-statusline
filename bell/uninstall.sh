#!/usr/bin/env bash
# 移除 AI CLI 完成提示設定（還原三邊，留備份）。
# Remove AI CLI completion bell config (restores all three, keeps backups).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="/usr/bin/python3"
NOTIFY="$SCRIPT_DIR/notify.sh"
SETUP="$SCRIPT_DIR/bell-setup"

if [ ! -x "$PYTHON" ]; then
  echo "!! 找不到 $PYTHON。" >&2
  exit 1
fi

echo "==> 移除三邊設定 / removing config (Claude / Codex / Ghostty)"
"$PYTHON" "$SETUP" uninstall --notify "$NOTIFY"

echo
echo "✅ 已移除 / Done. 重新開啟 Claude Code session 與重載 Ghostty 設定即生效。"
