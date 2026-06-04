#!/usr/bin/env bash
# 安裝多 session 總覽儀表板的狀態追蹤 hook。
# Install session-dashboard state tracking hooks.
#
# 做的事（皆先備份、只增不刪、可重複執行）:
#   (1) Claude settings.json 加 SessionStart/UserPromptSubmit/Stop/Notification
#       hook → sessions/track.sh claude
#   (2) Codex config.toml 的 notify 指向 sessions/notify.sh（合併派發器：同時觸發
#       bell 與狀態追蹤）。無 notify → 新增；bell 既有 notify → 升級；外來 → 略過。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="/usr/bin/python3"
TRACK="$SCRIPT_DIR/track.sh"
DISPATCH="$SCRIPT_DIR/notify.sh"
SETUP="$SCRIPT_DIR/sessions-setup"

if [ ! -x "$PYTHON" ]; then
  echo "!! 找不到 $PYTHON（本工具依賴 macOS 內建 python3）。" >&2
  echo "!! $PYTHON not found (relies on macOS's built-in python3)." >&2
  exit 1
fi
if [ ! -f "$TRACK" ] || [ ! -f "$DISPATCH" ] || [ ! -f "$SETUP" ]; then
  echo "!! 找不到 sessions 元件檔案 / sessions component files missing." >&2
  exit 1
fi
chmod +x "$TRACK" "$DISPATCH" "$SETUP" "$SCRIPT_DIR/sessions-track"
if [ -f "$SCRIPT_DIR/dashboard.py" ]; then chmod +x "$SCRIPT_DIR/dashboard.py"; fi

echo "==> 併入設定 / merging config (Claude / Codex)"
"$PYTHON" "$SETUP" install --track "$TRACK" --dispatch "$DISPATCH"

cat <<'EOF'

✅ 安裝完成 / Done.
後續 / Next:
 • 重新開啟 Claude Code session 讓 hooks 生效。
   Reopen a Claude Code session so the hooks load.
 • 開啟儀表板 / Open the dashboard:  ./sessions/dashboard.py
 • 若上面 Codex 那行標「•（略過）」表示你已有自訂 notify；請手動指到
   sessions/notify.sh（它會同時觸發 bell 與狀態追蹤）。
   If Codex shows "• (skipped)", point your existing notify at sessions/notify.sh.
EOF
