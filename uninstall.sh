#!/usr/bin/env bash
# 移除 context 用量狀態列：刪腳本、從 settings.json 拿掉 statusLine。
set -euo pipefail

CLAUDE_DIR="$HOME/.claude"
SETTINGS="$CLAUDE_DIR/settings.json"
TARGET="$CLAUDE_DIR/hooks/ctx-statusline.py"

echo "==> 移除 $TARGET"
rm -f "$TARGET"

if [ -f "$SETTINGS" ]; then
  cp "$SETTINGS" "$SETTINGS.bak.$(date +%Y%m%d%H%M%S)"
  /usr/bin/python3 - "$SETTINGS" <<'PY'
import json, sys
p = sys.argv[1]
with open(p) as f:
    data = json.load(f)
data.pop("statusLine", None)
with open(p, "w") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
    f.write("\n")
print("   已從 settings.json 移除 statusLine")
PY
fi

echo "✅ 已移除。重開 Claude Code session 生效。"
