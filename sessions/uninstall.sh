#!/usr/bin/env bash
# 移除 session 儀表板狀態追蹤設定（還原，留備份）。
# Remove session-dashboard state tracking config (restores, keeps backups).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="/usr/bin/python3"
TRACK="$SCRIPT_DIR/track.sh"
DISPATCH="$SCRIPT_DIR/notify.sh"
SETUP="$SCRIPT_DIR/sessions-setup"

if [ ! -x "$PYTHON" ]; then
  echo "!! 找不到 $PYTHON。" >&2
  exit 1
fi

echo "==> 移除設定 / removing config (Claude / Codex)"
"$PYTHON" "$SETUP" uninstall --track "$TRACK" --dispatch "$DISPATCH"

cat <<'EOF'

✅ 已移除 / Done.
 • Codex notify 已整個移除；若仍要 bell 的 Codex 提示，重跑 ./bell/install.sh。
   Codex notify fully removed; re-run ./bell/install.sh to restore the bell-only notify.
EOF
