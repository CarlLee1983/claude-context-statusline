#!/usr/bin/env bash
# 安裝 AI Usage SwiftBar 外掛。
# Install the AI Usage SwiftBar plugin.
#
# 做的事 / What it does:
#   (1) 找出 SwiftBar 的 plugin 目錄   locate SwiftBar's plugin folder
#   (2) 把外掛 symlink 進該目錄          symlink the plugin into it
#   (3) chmod +x 並請 SwiftBar 刷新     chmod +x and ask SwiftBar to refresh
#
# 覆寫 plugin 目錄 / override the plugin dir（依序）:
#   ./install.sh /path/to/plugins        位置參數 / positional arg
#   SWIFTBAR_PLUGIN_DIR=/path ./install.sh
# 改用「複製」而非 symlink / copy instead of symlink:
#   SWIFTBAR_INSTALL_COPY=1 ./install.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_NAME="ai-usage.60s.py"
PLUGIN_SRC="$SCRIPT_DIR/$PLUGIN_NAME"
BUNDLE_ID="com.ameba.SwiftBar"
DEFAULT_DIR="$HOME/.config/swiftbar"
SWIFTBAR_APP="/Applications/SwiftBar.app"

# --- 前置檢查 / preflight ---------------------------------------------------
if [ ! -f "$PLUGIN_SRC" ]; then
  echo "!! 找不到外掛來源 / plugin source missing: $PLUGIN_SRC" >&2
  exit 1
fi

if [ ! -d "$SWIFTBAR_APP" ] && ! mdfind "kMDItemCFBundleIdentifier == '$BUNDLE_ID'" 2>/dev/null | grep -q .; then
  echo "!! 偵測不到 SwiftBar / SwiftBar not detected." >&2
  echo "   先安裝再執行本腳本 / install it first, then re-run:" >&2
  echo "     brew install --cask swiftbar" >&2
  echo "   （外掛仍會被放到下方目錄，裝好 SwiftBar 後即可生效）" >&2
  echo "   (the plugin is still placed below; it works once SwiftBar is installed)" >&2
fi

# --- 解析 plugin 目錄 / resolve the plugin folder ---------------------------
read_pref() {  # 從非沙盒與沙盒兩處偏好讀 PluginDirectory / read from both pref locations
  defaults read "$BUNDLE_ID" PluginDirectory 2>/dev/null && return 0
  defaults read \
    "$HOME/Library/Containers/$BUNDLE_ID/Data/Library/Preferences/$BUNDLE_ID" \
    PluginDirectory 2>/dev/null && return 0
  return 1
}

FROM_PREF=1
if [ "${1:-}" != "" ]; then
  PLUGIN_DIR="$1"; FROM_PREF=0
elif [ "${SWIFTBAR_PLUGIN_DIR:-}" != "" ]; then
  PLUGIN_DIR="$SWIFTBAR_PLUGIN_DIR"; FROM_PREF=0
elif PLUGIN_DIR="$(read_pref)" && [ -n "$PLUGIN_DIR" ]; then
  : # 取自 SwiftBar 偏好 / taken from SwiftBar's own preference
else
  PLUGIN_DIR="$DEFAULT_DIR"; FROM_PREF=0
fi

# defaults 偶爾回傳 ~ 開頭 / expand a leading ~ just in case.
# 這裡刻意比對「字面」波浪號的 case pattern，非要 shell 展開。
# shellcheck disable=SC2088
case "$PLUGIN_DIR" in
  "~/"*) PLUGIN_DIR="$HOME/${PLUGIN_DIR#\~/}" ;;
  "~")   PLUGIN_DIR="$HOME" ;;
esac

# --- 安裝 / install ---------------------------------------------------------
echo "==> 外掛目錄 / plugin folder: $PLUGIN_DIR"
mkdir -p "$PLUGIN_DIR"
chmod +x "$PLUGIN_SRC"
TARGET="$PLUGIN_DIR/$PLUGIN_NAME"

if [ "${SWIFTBAR_INSTALL_COPY:-}" = "1" ]; then
  cp "$PLUGIN_SRC" "$TARGET"
  chmod +x "$TARGET"
  echo "==> 已複製 / copied: $TARGET"
else
  ln -sfn "$PLUGIN_SRC" "$TARGET"
  echo "==> 已連結 / symlinked: $TARGET -> $PLUGIN_SRC"
fi

# 請 SwiftBar 立即刷新（未開啟則忽略）/ ask SwiftBar to refresh (ignored if not running)
open -g "swiftbar://refreshallplugins" 2>/dev/null || true

# --- 後續提示 / next steps --------------------------------------------------
echo
echo "✅ 安裝完成 / Done."
if [ "$FROM_PREF" -ne 1 ]; then
  echo
  echo "⚠  SwiftBar 的 plugin 目錄尚未指向此處（或偵測不到）。"
  echo "⚠  SwiftBar's plugin folder isn't pointed here yet (or wasn't detected)."
  echo "   開啟 SwiftBar → Preferences → Plugin Folder，設成 / set it to:"
  echo "     $PLUGIN_DIR"
fi
echo
echo "提示 / Notes:"
echo " • 選單列膠囊圖示需要 Pillow（選用）；沒有會退回文字。"
echo "   Capsule icons need Pillow (optional); without it it falls back to text."
echo " • 解除安裝：移除 ${TARGET}（symlink 不影響原始碼）。"
echo "   Uninstall: remove ${TARGET} (removing the symlink leaves the source intact)."
