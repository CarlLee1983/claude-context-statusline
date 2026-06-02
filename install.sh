#!/usr/bin/env bash
# 安裝 Claude Code context 用量狀態列。
# Install the Claude Code context-usage statusline.
#
# 做兩件事 / Two steps:
#   (1) 複製腳本到 ~/.claude/hooks/      copy the script into ~/.claude/hooks/
#   (2) 把 statusLine 併進 settings.json  merge statusLine into settings.json
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
HOOKS_DIR="$CLAUDE_DIR/hooks"
SETTINGS="$CLAUDE_DIR/settings.json"
SOURCE="$SCRIPT_DIR/ctx-statusline.py"
TARGET="$HOOKS_DIR/ctx-statusline.py"
PYTHON="/usr/bin/python3"

# --- 前置檢查 / preflight ---------------------------------------------------
if [ ! -x "$PYTHON" ]; then
  echo "!! 找不到 $PYTHON（本工具依賴 macOS 內建 python3）。" >&2
  echo "!! $PYTHON not found (this tool relies on macOS's built-in python3)." >&2
  exit 1
fi
if [ ! -f "$SOURCE" ]; then
  echo "!! 找不到來源腳本 / source script missing: $SOURCE" >&2
  exit 1
fi

echo "==> 安裝腳本到 / installing script to: $TARGET"
mkdir -p "$HOOKS_DIR"
cp "$SOURCE" "$TARGET"
chmod +x "$TARGET"

echo "==> 設定 statusLine / configuring statusLine: $SETTINGS"
# settings.json 不存在則建立空物件 / create an empty object if it does not exist
[ -f "$SETTINGS" ] || echo '{}' > "$SETTINGS"
# 改動前備份 / back up before modifying
BACKUP="$SETTINGS.bak.$(date +%Y%m%d%H%M%S)"
cp "$SETTINGS" "$BACKUP"
echo "   備份 / backup: $BACKUP"

# 用系統 python3 安全地合併 statusLine（保留其他設定），不依賴 jq。
# Safely merge statusLine with the system python3 (keeping other settings); no jq.
"$PYTHON" - "$SETTINGS" "$TARGET" "$PYTHON" <<'PY'
import json, sys
settings_path, target, python = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    with open(settings_path) as f:
        data = json.load(f)
except (json.JSONDecodeError, ValueError):
    print("!! settings.json 不是合法 JSON，已中止（檔案未變動，請見備份）", file=sys.stderr)
    print("!! settings.json is not valid JSON; aborted (file untouched, see backup).", file=sys.stderr)
    sys.exit(1)
if not isinstance(data, dict):
    print("!! settings.json 頂層不是物件，已中止 / top level is not an object; aborted.", file=sys.stderr)
    sys.exit(1)
data["statusLine"] = {"type": "command", "command": python + " " + target}
with open(settings_path, "w") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
    f.write("\n")
print("   statusLine ->", data["statusLine"]["command"])
PY

echo
echo "✅ 安裝完成。請重新開啟一個 Claude Code session 即可在底部看到："
echo "✅ Done. Open a new Claude Code session to see it at the bottom:"
echo "   Opus 4.8 · [████░░░░░░] 39% · 78k/200k"
