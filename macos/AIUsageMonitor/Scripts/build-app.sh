#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_NAME="AIUsageMonitor"
PRODUCT_NAME="AIUsageMonitorApp"
CONFIGURATION="${CONFIGURATION:-debug}"
APP_VERSION="${APP_VERSION:-0.1.0}"
BUNDLE_DIR="$ROOT/.build/$APP_NAME.app"
MACOS_DIR="$BUNDLE_DIR/Contents/MacOS"
RESOURCES_DIR="$BUNDLE_DIR/Contents/Resources"

cd "$ROOT"
# swiftpm 在受限環境（如 Homebrew 從源碼安裝）會用 sandbox-exec 編譯 manifest，
# 在某些機器上會 `sandbox_apply: Operation not permitted` 而失敗。設 SWIFT_DISABLE_SANDBOX=1
# 改為跳過 swiftpm sandbox。本機一般開發不需設定，行為不變。
# swiftpm sandboxes manifest compilation via sandbox-exec, which fails with
# `sandbox_apply: Operation not permitted` in restricted environments (e.g. a
# Homebrew source build). Set SWIFT_DISABLE_SANDBOX=1 to skip the swiftpm sandbox.
# Unset for normal local dev — behavior is unchanged.
SWIFT_BUILD_FLAGS=(-c "$CONFIGURATION" --product "$PRODUCT_NAME")
if [ -n "${SWIFT_DISABLE_SANDBOX:-}" ]; then
  SWIFT_BUILD_FLAGS+=(--disable-sandbox)
fi
swift build "${SWIFT_BUILD_FLAGS[@]}"

rm -rf "$BUNDLE_DIR"
mkdir -p "$MACOS_DIR" "$RESOURCES_DIR"
cp "$ROOT/.build/$CONFIGURATION/$PRODUCT_NAME" "$MACOS_DIR/$APP_NAME"
cat > "$BUNDLE_DIR/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key>
  <string>$APP_NAME</string>
  <key>CFBundleIdentifier</key>
  <string>local.ai-usage-monitor</string>
  <key>CFBundleName</key>
  <string>$APP_NAME</string>
  <key>CFBundleDisplayName</key>
  <string>AI Usage Monitor</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>$APP_VERSION</string>
  <key>CFBundleVersion</key>
  <string>1</string>
  <key>LSMinimumSystemVersion</key>
  <string>14.0</string>
  <key>LSUIElement</key>
  <true/>
  <key>NSHighResolutionCapable</key>
  <true/>
</dict>
</plist>
PLIST

echo "$BUNDLE_DIR"
