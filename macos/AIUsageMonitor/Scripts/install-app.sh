#!/usr/bin/env bash
# 建置並安裝 AI Usage Monitor 到 /Applications。
# Build and install AI Usage Monitor into /Applications.
#
# 為何要安裝到穩定位置：.build/ 內的 bundle 每次重 build 會被覆蓋，
# 不適合當常駐 / 開機啟動的目標；複製到 /Applications 後路徑固定，
# 「Launch at Login」(SMAppService) 的註冊才可靠。
# Why install to a stable location: the bundle in .build/ is wiped on every
# rebuild, so it's a poor target for a persistent / login item. Copying to
# /Applications gives a fixed path so the "Launch at Login" registration sticks.
#
# 覆寫安裝目錄 / override the install dir:
#   APP_INSTALL_DIR="$HOME/Applications" ./Scripts/install-app.sh
# 不要在安裝後自動開啟（測試 / CI 用）/ don't open after install (test / CI):
#   APP_INSTALL_OPEN=0 ./Scripts/install-app.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_NAME="AIUsageMonitor"
BUILT="$ROOT/.build/$APP_NAME.app"
DEST_DIR="${APP_INSTALL_DIR:-/Applications}"
DEST="$DEST_DIR/$APP_NAME.app"
OPEN_AFTER="${APP_INSTALL_OPEN:-1}"

# --- 建置 / build -----------------------------------------------------------
echo "==> 建置 / building…"
"$ROOT/Scripts/build-app.sh" >/dev/null
[ -d "$BUILT" ] || { echo "!! 建置產物不存在 / build output missing: $BUILT" >&2; exit 1; }

# --- 安裝目錄檢查 / install-dir checks --------------------------------------
mkdir -p "$DEST_DIR"
if [ ! -w "$DEST_DIR" ]; then
  echo "!! 沒有寫入權限 / no write permission: $DEST_DIR" >&2
  echo "   改用個人目錄或加 sudo / use a per-user dir or sudo:" >&2
  echo "     APP_INSTALL_DIR=\"\$HOME/Applications\" ./Scripts/install-app.sh" >&2
  exit 1
fi

# --- 關閉執行中的舊版 / quit a running instance -----------------------------
osascript -e "tell application \"$APP_NAME\" to quit" 2>/dev/null || true
pkill -x "$APP_NAME" 2>/dev/null || true

# --- 複製 / copy ------------------------------------------------------------
echo "==> 安裝到 / installing to: $DEST"
rm -rf "$DEST"
cp -R "$BUILT" "$DEST"

# --- 開啟 / launch ----------------------------------------------------------
if [ "$OPEN_AFTER" = "1" ]; then
  open "$DEST"
fi

echo
echo "✅ 安裝完成 / Done: $DEST"
echo "   點選單列圖示 → 勾「Launch at Login」即可開機自動啟動。"
echo "   Click the menu bar icon → check \"Launch at Login\" to start at login."
echo "   （也可在 系統設定 → 一般 → 登入項目 看到並開關。"
echo "    You can also see/toggle it in System Settings → General → Login Items.）"
