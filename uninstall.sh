#!/usr/bin/env bash
# 移除 context 用量狀態列：刪腳本、從 settings.json 拿掉 statusLine。
# Remove the context-usage statusline: delete the script, drop statusLine from settings.json.
set -euo pipefail

CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
SETTINGS="$CLAUDE_DIR/settings.json"
TARGET="$CLAUDE_DIR/hooks/ctx-statusline.py"
PYTHON="/usr/bin/python3"

echo "==> 移除 / removing: $TARGET"
rm -f "$TARGET"

if [ -f "$SETTINGS" ] && [ -x "$PYTHON" ]; then
  BACKUP="$SETTINGS.bak.$(date +%Y%m%d%H%M%S)"
  cp "$SETTINGS" "$BACKUP"
  echo "   備份 / backup: $BACKUP"
  "$PYTHON" - "$SETTINGS" <<'PY'
import json, sys
p = sys.argv[1]
try:
    with open(p) as f:
        data = json.load(f)
except (json.JSONDecodeError, ValueError):
    print("!! settings.json 不是合法 JSON，略過移除 statusLine（請手動編輯）", file=sys.stderr)
    print("!! settings.json is not valid JSON; skipped removing statusLine (edit manually).", file=sys.stderr)
    sys.exit(0)
if isinstance(data, dict) and data.pop("statusLine", None) is not None:
    with open(p, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print("   已從 settings.json 移除 statusLine / removed statusLine from settings.json")
else:
    print("   settings.json 沒有 statusLine，無需變動 / no statusLine present, nothing to do")
PY
fi

echo "✅ 已移除。重開 Claude Code session 生效。"
echo "✅ Removed. Restart a Claude Code session to take effect."
