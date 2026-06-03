#!/usr/bin/env bash
# 安裝 AI CLI 完成提示（Ghostty 分頁標記）。
# Install AI CLI completion bell (Ghostty tab attention).
#
# 做的事 / What it does（皆先備份、只增不刪、可重複執行）:
#   (1) Claude Code settings.json 加 Stop hook → bell/notify.sh claude
#   (2) Codex config.toml 加 notify → bell/notify.sh codex（已有 notify 則略過並提示）
#   (3) Ghostty config 加 bell-features = title,attention（XDG 那份）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="/usr/bin/python3"
NOTIFY="$SCRIPT_DIR/notify.sh"
SETUP="$SCRIPT_DIR/bell-setup"

if [ ! -x "$PYTHON" ]; then
  echo "!! 找不到 $PYTHON（本工具依賴 macOS 內建 python3）。" >&2
  echo "!! $PYTHON not found (relies on macOS's built-in python3)." >&2
  exit 1
fi
if [ ! -f "$NOTIFY" ] || [ ! -f "$SETUP" ]; then
  echo "!! 找不到 bell 元件檔案 / bell component files missing:" >&2
  echo "     $NOTIFY" >&2
  echo "     $SETUP" >&2
  exit 1
fi
chmod +x "$NOTIFY" "$SETUP"

echo "==> 併入三邊設定 / merging config (Claude / Codex / Ghostty)"
"$PYTHON" "$SETUP" install --notify "$NOTIFY"

# --- Ghostty 雙位置警告 / dual-location warning ----------------------------
APP_SUPPORT="$HOME/Library/Application Support/com.mitchellh.ghostty/config"
if [ -f "$APP_SUPPORT" ] && grep -qE '^[[:space:]]*bell-features' "$APP_SUPPORT" 2>/dev/null; then
  echo >&2
  echo "⚠  另一份 Ghostty 設定也定義了 bell-features（未更動它）：" >&2
  echo "⚠  A second Ghostty config also sets bell-features (left untouched):" >&2
  echo "     $APP_SUPPORT" >&2
fi

cat <<'EOF'

✅ 安裝完成 / Done.
後續 / Next:
 • 重新開啟 Claude Code session 讓 Stop hook 生效。
   Reopen a Claude Code session so the Stop hook loads.
 • 重新載入 Ghostty 設定：Cmd+Shift+, 或重開 Ghostty。
   Reload Ghostty config: Cmd+Shift+, or restart Ghostty.
 • 若上面 Codex 那行標「•（略過）」表示你已有 notify 設定；
   請手動把它指到 bell/notify.sh，並在腳本判斷 agent-turn-complete。
   If Codex shows "• (skipped)", you already have a notify; point it at
   bell/notify.sh manually.
EOF
