#!/usr/bin/env bash
# 安裝 Claude Code context 用量狀態列。
# 做兩件事：(1) 複製腳本到 ~/.claude/hooks/  (2) 把 statusLine 併進 ~/.claude/settings.json
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="$HOME/.claude"
HOOKS_DIR="$CLAUDE_DIR/hooks"
SETTINGS="$CLAUDE_DIR/settings.json"
TARGET="$HOOKS_DIR/ctx-statusline.py"

echo "==> 安裝腳本到 $TARGET"
mkdir -p "$HOOKS_DIR"
cp "$SCRIPT_DIR/ctx-statusline.py" "$TARGET"
chmod +x "$TARGET"

echo "==> 設定 statusLine: ${SETTINGS}"
# settings.json 不存在則建立空物件
[ -f "$SETTINGS" ] || echo '{}' > "$SETTINGS"
# 改動前備份
cp "$SETTINGS" "$SETTINGS.bak.$(date +%Y%m%d%H%M%S)"

# 用系統 python3 安全地合併 statusLine（保留其他設定），不依賴 jq
/usr/bin/python3 - "$SETTINGS" "$TARGET" <<'PY'
import json, sys
settings_path, target = sys.argv[1], sys.argv[2]
try:
    with open(settings_path) as f:
        data = json.load(f)
except (json.JSONDecodeError, ValueError):
    print("!! settings.json 不是合法 JSON，已中止（檔案未變動，請見備份）", file=sys.stderr)
    sys.exit(1)
data["statusLine"] = {
    "type": "command",
    "command": "/usr/bin/python3 " + target,
}
with open(settings_path, "w") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
    f.write("\n")
print("   statusLine ->", data["statusLine"]["command"])
PY

echo
echo "✅ 安裝完成。請重新開啟一個 Claude Code session 即可在底部看到："
echo "   Opus 4.8 · [████░░░░░░] 39% · 78k/200k"
