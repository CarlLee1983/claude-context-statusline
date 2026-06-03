# Homebrew tap 一鍵安裝 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓 `claude-context-statusline` 的三個元件都能透過 `brew tap CarlLee1983/tap && brew install …` 一鍵安裝。

**Architecture:** 全部走「從源碼 build」的 Homebrew formula（不簽章、不公證、不需 CI）。formula 權威範本放本 repo 的 `packaging/homebrew/Formula/`，`Scripts/release.sh` 在發版時填入版本與 sha256 後推到獨立的 `CarlLee1983/homebrew-tap` repo。`brew install` 期間不碰使用者設定檔；需要動 `~/.claude/settings.json` 或 `~/Applications` 的步驟改由安裝後的命令完成。

**Tech Stack:** Homebrew formula（Ruby）、純標準庫 Python（`ctx-statusline-setup` + unittest）、bash（build/release/install 腳本）、Swift（既有 App，僅參數化建置）。

**設計文件：** `docs/superpowers/specs/2026-06-03-homebrew-tap-distribution-design.md`

---

## 檔案結構

**本 repo 新增 / 修改：**
- Create: `ctx-statusline-setup`（純 Python CLI，合併/移除 settings.json 的 statusLine）
- Create: `tests/test_ctx_statusline_setup.py`
- Modify: `install.sh`、`uninstall.sh`（改為委派 `ctx-statusline-setup`，DRY）
- Modify: `macos/AIUsageMonitor/Scripts/build-app.sh`（`CONFIGURATION` / `APP_VERSION` 參數化）
- Create: `packaging/homebrew/Formula/ctx-statusline.rb`
- Create: `packaging/homebrew/Formula/ai-usage-monitor.rb`
- Create: `packaging/homebrew/Formula/swiftbar-ai-usage.rb`
- Create: `packaging/homebrew/README.md`（tap 建立與發版流程）
- Create: `Scripts/release.sh`（撞版本 → tag → 更新 tap formula）
- Modify: `README.md`、`README.en.md`、`macos/AIUsageMonitor/README.md`、`swiftbar/README.md`、`CHANGELOG.md`

**外部（不在本 worktree，由 `packaging/homebrew/README.md` 指引建立）：**
- `CarlLee1983/homebrew-tap` repo，含 `Formula/`（release.sh 的推送目標）

---

## Task 1: `ctx-statusline-setup` — 純函式與測試

**Files:**
- Create: `ctx-statusline-setup`
- Test: `tests/test_ctx_statusline_setup.py`

- [ ] **Step 1: 寫失敗測試**

建立 `tests/test_ctx_statusline_setup.py`：

```python
#!/usr/bin/env python3
"""ctx-statusline-setup 的單元測試（純標準庫 unittest）。"""
import importlib.util
import json
import os
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODULE_PATH = os.path.join(_HERE, os.pardir, "ctx-statusline-setup")
_spec = importlib.util.spec_from_file_location("ctx_statusline_setup", _MODULE_PATH)
setup = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(setup)


class PureFnTests(unittest.TestCase):
    def test_apply_sets_status_line_without_mutating(self):
        original = {"other": 1}
        result = setup.apply_status_line(original, "/usr/bin/python3 /x/ctx-statusline")
        self.assertEqual(
            result["statusLine"],
            {"type": "command", "command": "/usr/bin/python3 /x/ctx-statusline"},
        )
        self.assertEqual(result["other"], 1)
        self.assertNotIn("statusLine", original)  # 不可變：原 dict 未被改

    def test_remove_drops_key_and_reports(self):
        data = {"statusLine": {"type": "command"}, "keep": 2}
        new_data, removed = setup.remove_status_line(data)
        self.assertTrue(removed)
        self.assertNotIn("statusLine", new_data)
        self.assertEqual(new_data["keep"], 2)
        self.assertIn("statusLine", data)  # 原 dict 未被改

    def test_remove_absent_reports_false(self):
        new_data, removed = setup.remove_status_line({"keep": 1})
        self.assertFalse(removed)
        self.assertEqual(new_data, {"keep": 1})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python3 -m unittest tests.test_ctx_statusline_setup -v`
Expected: FAIL —— `ModuleNotFoundError` 或載入失敗（`ctx-statusline-setup` 尚不存在）。

- [ ] **Step 3: 寫最小實作**

建立 `ctx-statusline-setup`：

```python
#!/usr/bin/env python3
"""ctx-statusline-setup — 把 ctx-statusline 併入/移出 Claude Code 的 settings.json。

純標準庫、零相依。預設 command 指向與本腳本同目錄的 ctx-statusline（Homebrew 情境）；
install.sh 會以 --command 明確指定來源 checkout 的路徑。honors CLAUDE_CONFIG_DIR。

Merge or remove the statusLine entry in Claude Code's settings.json.
"""
import json
import os
import shutil
import sys
import time

STATUS_LINE_KEY = "statusLine"


class InvalidSettings(Exception):
    """settings.json 不是合法 JSON 物件 / not a valid JSON object."""


def apply_status_line(data, command):
    """回傳設好 statusLine 的新 dict（不可變：不改原輸入）。"""
    return {**data, STATUS_LINE_KEY: {"type": "command", "command": command}}


def remove_status_line(data):
    """回傳 (新 dict, 是否移除)。"""
    if STATUS_LINE_KEY not in data:
        return data, False
    return {k: v for k, v in data.items() if k != STATUS_LINE_KEY}, True
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python3 -m unittest tests.test_ctx_statusline_setup -v`
Expected: PASS（3 個測試）。

- [ ] **Step 5: Commit**

```bash
git add ctx-statusline-setup tests/test_ctx_statusline_setup.py
git commit -m "feat: [statusline] Add ctx-statusline-setup pure merge/remove helpers"
```

---

## Task 2: `ctx-statusline-setup` — 檔案 IO（備份 / 非法 JSON / 寫回）

**Files:**
- Modify: `ctx-statusline-setup`
- Test: `tests/test_ctx_statusline_setup.py`

- [ ] **Step 1: 寫失敗測試**

在 `tests/test_ctx_statusline_setup.py` 的 `unittest.main()` 之前，加入：

```python
class RunTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.settings = os.path.join(self.dir, "settings.json")

    def _read(self):
        with open(self.settings) as f:
            return json.load(f)

    def test_merge_creates_file_when_missing(self):
        msg = setup.run(self.settings, command="/usr/bin/python3 /x/ctx-statusline")
        self.assertIn("statusLine ->", msg)
        self.assertEqual(
            self._read()["statusLine"]["command"],
            "/usr/bin/python3 /x/ctx-statusline",
        )

    def test_merge_preserves_existing_keys_and_backs_up(self):
        with open(self.settings, "w") as f:
            json.dump({"model": "opus"}, f)
        setup.run(self.settings, command="cmd")
        self.assertEqual(self._read()["model"], "opus")
        backups = [n for n in os.listdir(self.dir) if ".bak." in n]
        self.assertEqual(len(backups), 1)  # 改動前有備份

    def test_merge_invalid_json_raises_and_leaves_file_untouched(self):
        with open(self.settings, "w") as f:
            f.write("{ not json")
        with self.assertRaises(setup.InvalidSettings):
            setup.run(self.settings, command="cmd")
        with open(self.settings) as f:
            self.assertEqual(f.read(), "{ not json")  # 未被覆寫

    def test_remove_drops_status_line_keeping_others(self):
        with open(self.settings, "w") as f:
            json.dump({"statusLine": {"type": "command"}, "keep": 1}, f)
        msg = setup.run(self.settings, remove=True)
        self.assertIn("removed statusLine", msg)
        self.assertEqual(self._read(), {"keep": 1})

    def test_remove_when_absent_is_noop(self):
        with open(self.settings, "w") as f:
            json.dump({"keep": 1}, f)
        msg = setup.run(self.settings, remove=True)
        self.assertIn("nothing to do", msg)
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python3 -m unittest tests.test_ctx_statusline_setup -v`
Expected: FAIL —— `AttributeError: module ... has no attribute 'run'`。

- [ ] **Step 3: 寫最小實作**

在 `ctx-statusline-setup` 的純函式之後、`if __name__` 之前加入：

```python
def _load(settings_path):
    if not os.path.exists(settings_path):
        return {}
    with open(settings_path) as f:
        try:
            data = json.load(f)
        except (json.JSONDecodeError, ValueError) as exc:
            raise InvalidSettings(str(exc)) from exc
    if not isinstance(data, dict):
        raise InvalidSettings("top level is not an object")
    return data


def _backup(settings_path):
    if not os.path.exists(settings_path):
        return None
    backup = f"{settings_path}.bak.{time.strftime('%Y%m%d%H%M%S')}"
    shutil.copy(settings_path, backup)
    return backup


def _write(settings_path, data):
    os.makedirs(os.path.dirname(settings_path) or ".", exist_ok=True)
    with open(settings_path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def run(settings_path, command=None, remove=False):
    """備份 → 載入 → 套用/移除 → 寫回。回傳訊息字串；非法 JSON 拋 InvalidSettings。

    注意：_load 在任何寫入前先驗證，故非法 JSON 時檔案保持原狀（不寫、不備份）。
    """
    data = _load(settings_path)
    if remove:
        new_data, removed = remove_status_line(data)
        if not removed:
            return "no statusLine present, nothing to do"
        _backup(settings_path)
        _write(settings_path, new_data)
        return "removed statusLine from settings.json"
    new_data = apply_status_line(data, command)
    _backup(settings_path)
    _write(settings_path, new_data)
    return f"statusLine -> {command}"
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python3 -m unittest tests.test_ctx_statusline_setup -v`
Expected: PASS（共 8 個測試）。

- [ ] **Step 5: Commit**

```bash
git add ctx-statusline-setup tests/test_ctx_statusline_setup.py
git commit -m "feat: [statusline] Add ctx-statusline-setup file IO with backup and invalid-JSON guard"
```

---

## Task 3: `ctx-statusline-setup` — CLI（args / env / 預設 command）

**Files:**
- Modify: `ctx-statusline-setup`
- Test: `tests/test_ctx_statusline_setup.py`

- [ ] **Step 1: 寫失敗測試**

在 `tests/test_ctx_statusline_setup.py` 的 `unittest.main()` 之前，加入：

```python
class MainTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def test_main_uses_claude_config_dir_and_command(self):
        rc = setup.main(["--command", "mycmd"], env={"CLAUDE_CONFIG_DIR": self.dir})
        self.assertEqual(rc, 0)
        with open(os.path.join(self.dir, "settings.json")) as f:
            self.assertEqual(json.load(f)["statusLine"]["command"], "mycmd")

    def test_main_remove_returns_zero(self):
        path = os.path.join(self.dir, "settings.json")
        with open(path, "w") as f:
            json.dump({"statusLine": {"x": 1}}, f)
        rc = setup.main(["--remove"], env={"CLAUDE_CONFIG_DIR": self.dir})
        self.assertEqual(rc, 0)
        with open(path) as f:
            self.assertNotIn("statusLine", json.load(f))

    def test_main_merge_invalid_json_returns_one(self):
        path = os.path.join(self.dir, "settings.json")
        with open(path, "w") as f:
            f.write("nope")
        rc = setup.main(["--command", "c"], env={"CLAUDE_CONFIG_DIR": self.dir})
        self.assertEqual(rc, 1)

    def test_main_remove_invalid_json_returns_zero(self):
        path = os.path.join(self.dir, "settings.json")
        with open(path, "w") as f:
            f.write("nope")
        rc = setup.main(["--remove"], env={"CLAUDE_CONFIG_DIR": self.dir})
        self.assertEqual(rc, 0)

    def test_default_command_points_at_sibling(self):
        cmd = setup.default_command()
        self.assertTrue(cmd.startswith("/usr/bin/python3 "))
        self.assertTrue(cmd.rstrip().endswith("ctx-statusline"))
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python3 -m unittest tests.test_ctx_statusline_setup -v`
Expected: FAIL —— `module ... has no attribute 'main'` / `default_command`。

- [ ] **Step 3: 寫最小實作**

在 `ctx-statusline-setup` 的 `run()` 之後、`if __name__` 之前加入：

```python
def default_command():
    """預設 command：/usr/bin/python3 <與本腳本同目錄的 ctx-statusline>。"""
    here = os.path.dirname(os.path.realpath(__file__))
    return f"/usr/bin/python3 {os.path.join(here, 'ctx-statusline')}"


def main(argv=None, env=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    env = os.environ if env is None else env
    remove = "--remove" in argv
    command = None
    if "--command" in argv:
        i = argv.index("--command")
        if i + 1 >= len(argv):
            print("!! --command needs a value", file=sys.stderr)
            return 2
        command = argv[i + 1]
    claude_dir = env.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")
    settings_path = os.path.join(claude_dir, "settings.json")
    if not remove and command is None:
        command = default_command()
    try:
        msg = run(settings_path, command=command, remove=remove)
    except InvalidSettings:
        if remove:
            print("!! settings.json 不是合法 JSON，略過移除 statusLine（請手動編輯）",
                  file=sys.stderr)
            return 0
        print("!! settings.json 不是合法 JSON，已中止（檔案未變動，請見備份）",
              file=sys.stderr)
        return 1
    print("   " + msg)
    return 0
```

並把檔案結尾改成：

```python
if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 跑全部測試確認通過 + 手動冒煙**

Run: `python3 -m unittest discover -s tests -v`
Expected: PASS（既有 22 個 + 本檔 13 個）。

手動冒煙（驗證 CLI 真的能跑）：
```bash
chmod +x ctx-statusline-setup
TMP=$(mktemp -d) && ./ctx-statusline-setup --command "echo hi" 2>&1; \
CLAUDE_CONFIG_DIR=$TMP ./ctx-statusline-setup --command "echo hi"; \
cat "$TMP/settings.json"
```
Expected: `settings.json` 含 `"command": "echo hi"`。

- [ ] **Step 5: Commit**

```bash
git add ctx-statusline-setup tests/test_ctx_statusline_setup.py
git commit -m "feat: [statusline] Add ctx-statusline-setup CLI (args/env/default command)"
```

---

## Task 4: `install.sh` / `uninstall.sh` 改為委派（DRY）

**Files:**
- Modify: `install.sh`
- Modify: `uninstall.sh`

- [ ] **Step 1: 改 `install.sh` 委派合併邏輯**

把 `install.sh` 第 34–62 行整段（從 `echo "==> 設定 statusLine …"` 到 heredoc 結尾的 `PY`，
**含**中間的「建立空物件」`[ -f "$SETTINGS" ] …`、`BACKUP=…cp…echo` 備份區塊與整個 python
heredoc）一次替換成下面 4 行——保留上方第 29–32 行的「複製腳本」步驟不動：

```bash
echo "==> 設定 statusLine / configuring statusLine: $SETTINGS"
# 合併邏輯統一由 ctx-statusline-setup 處理（含建立、備份、非法 JSON 中止、保留其他設定）。
# Delegate the merge to ctx-statusline-setup (create, backup, invalid-JSON guard, key preservation).
"$PYTHON" "$SCRIPT_DIR/ctx-statusline-setup" --command "$PYTHON $TARGET"
```

如此一來建立與備份只發生在 `ctx-statusline-setup` 內，不會雙重備份。

- [ ] **Step 2: 改 `uninstall.sh` 委派移除邏輯**

把 `uninstall.sh` 第 14–36 行（`if [ -f "$SETTINGS" ] …` 整個 if 區塊）替換成：

```bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -x "$PYTHON" ]; then
  "$PYTHON" "$SCRIPT_DIR/ctx-statusline-setup" --remove
fi
```

- [ ] **Step 3: 語法檢查**

Run:
```bash
bash -n install.sh uninstall.sh
shellcheck install.sh uninstall.sh
```
Expected: 無錯誤輸出。

- [ ] **Step 4: 端到端功能驗證（用臨時設定目錄）**

Run:
```bash
TMP=$(mktemp -d)
CLAUDE_CONFIG_DIR=$TMP ./install.sh
python3 -c "import json;d=json.load(open('$TMP/settings.json'));assert d['statusLine']['command'].endswith('ctx-statusline.py'),d;print('install OK')"
CLAUDE_CONFIG_DIR=$TMP ./uninstall.sh
python3 -c "import json;d=json.load(open('$TMP/settings.json'));assert 'statusLine' not in d;print('uninstall OK')"
```
Expected: 印出 `install OK` 與 `uninstall OK`。

- [ ] **Step 5: Commit**

```bash
git add install.sh uninstall.sh
git commit -m "refactor: [statusline] Delegate settings.json merge/remove to ctx-statusline-setup"
```

---

## Task 5: `build-app.sh` 參數化（CONFIGURATION / APP_VERSION）

**Files:**
- Modify: `macos/AIUsageMonitor/Scripts/build-app.sh`

- [ ] **Step 1: 改為讀環境變數**

把 `macos/AIUsageMonitor/Scripts/build-app.sh` 第 8 行：
```bash
CONFIGURATION="debug"
```
改為：
```bash
CONFIGURATION="${CONFIGURATION:-debug}"
APP_VERSION="${APP_VERSION:-0.1.0}"
```

並把 Info.plist heredoc 內第 34 行的：
```
  <string>0.1.0</string>
```
改為：
```
  <string>$APP_VERSION</string>
```
（即 `CFBundleShortVersionString` 的值。`CFBundleVersion` 的 `1` 保持不變。）

- [ ] **Step 2: 語法檢查**

Run:
```bash
bash -n macos/AIUsageMonitor/Scripts/build-app.sh
shellcheck macos/AIUsageMonitor/Scripts/build-app.sh
```
Expected: 無錯誤。

- [ ] **Step 3: 實際建置驗證（release + 版本）**

Run:
```bash
cd macos/AIUsageMonitor
CONFIGURATION=release APP_VERSION=0.2.0 ./Scripts/build-app.sh >/dev/null
/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' .build/AIUsageMonitor.app/Contents/Info.plist
test -x .build/AIUsageMonitor.app/Contents/MacOS/AIUsageMonitor && echo "bundle OK"
```
Expected: 印出 `0.2.0` 與 `bundle OK`。

- [ ] **Step 4: 確認預設行為不變**

Run:
```bash
cd macos/AIUsageMonitor && ./Scripts/build-app.sh >/dev/null && \
/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' .build/AIUsageMonitor.app/Contents/Info.plist
```
Expected: 印出 `0.1.0`（未設環境變數時維持原值）。

- [ ] **Step 5: Commit**

```bash
git add macos/AIUsageMonitor/Scripts/build-app.sh
git commit -m "feat: [macos] Parameterize build-app.sh with CONFIGURATION and APP_VERSION"
```

---

## Task 6: Formula — `ctx-statusline.rb`

**Files:**
- Create: `packaging/homebrew/Formula/ctx-statusline.rb`

- [ ] **Step 1: 建立 formula**

```ruby
class CtxStatusline < Formula
  desc "Claude Code statusline showing context-window usage"
  homepage "https://github.com/CarlLee1983/claude-context-statusline"
  url "https://github.com/CarlLee1983/claude-context-statusline/archive/refs/tags/v0.2.0.tar.gz"
  sha256 "0000000000000000000000000000000000000000000000000000000000000000"
  license "MIT"

  def install
    bin.install "ctx-statusline.py" => "ctx-statusline"
    bin.install "ctx-statusline-setup"
  end

  def caveats
    <<~EOS
      Wire the statusline into Claude Code, then restart a Claude Code session:
        ctx-statusline-setup
      Remove it later with:
        ctx-statusline-setup --remove
      Honors CLAUDE_CONFIG_DIR if your config lives outside ~/.claude.
    EOS
  end

  test do
    json = '{"model":{"id":"claude-opus-4-8","display_name":"Opus 4.8"},' \
           '"transcript_path":"/nonexistent.jsonl"}'
    output = pipe_output("/usr/bin/python3 #{bin}/ctx-statusline", json)
    assert_match "Opus", output
  end
end
```

- [ ] **Step 2: Ruby 語法檢查**

Run: `ruby -c packaging/homebrew/Formula/ctx-statusline.rb`
Expected: `Syntax OK`。

- [ ] **Step 3: （有裝 Homebrew 時）風格檢查**

Run: `brew style packaging/homebrew/Formula/ctx-statusline.rb 2>/dev/null || echo "brew not available — skip (will run in release verification)"`
Expected: `style` 無錯，或印出 skip 訊息。

- [ ] **Step 4: Commit**

```bash
git add packaging/homebrew/Formula/ctx-statusline.rb
git commit -m "feat: [homebrew] Add ctx-statusline formula"
```

---

## Task 7: Formula — `ai-usage-monitor.rb`

**Files:**
- Create: `packaging/homebrew/Formula/ai-usage-monitor.rb`

- [ ] **Step 1: 建立 formula**

```ruby
class AiUsageMonitor < Formula
  desc "Native macOS menu-bar monitor for Claude/Codex/Antigravity usage"
  homepage "https://github.com/CarlLee1983/claude-context-statusline"
  url "https://github.com/CarlLee1983/claude-context-statusline/archive/refs/tags/v0.2.0.tar.gz"
  sha256 "0000000000000000000000000000000000000000000000000000000000000000"
  license "MIT"

  depends_on :macos
  depends_on xcode: ["16.0", :build]

  def install
    cd "macos/AIUsageMonitor" do
      ENV["CONFIGURATION"] = "release"
      ENV["APP_VERSION"] = version.to_s
      system "./Scripts/build-app.sh"
      prefix.install ".build/AIUsageMonitor.app"
    end

    # 啟動器：本機編譯的 .app 不帶 quarantine，複製到使用者可寫的 ~/Applications
    # （路徑跨 brew upgrade 穩定，Launch-at-Login 的 SMAppService 才可靠）。
    (bin/"ai-usage-monitor").write <<~EOS
      #!/bin/bash
      set -euo pipefail
      SRC="#{opt_prefix}/AIUsageMonitor.app"
      DEST="$HOME/Applications/AIUsageMonitor.app"
      BIN="Contents/MacOS/AIUsageMonitor"
      mkdir -p "$HOME/Applications"
      if [ ! -d "$DEST" ] || [ "$SRC/$BIN" -nt "$DEST/$BIN" ]; then
        osascript -e 'tell application "AIUsageMonitor" to quit' 2>/dev/null || true
        pkill -x AIUsageMonitor 2>/dev/null || true
        rm -rf "$DEST"
        cp -R "$SRC" "$DEST"
      fi
      open "$DEST"
    EOS
    chmod 0755, bin/"ai-usage-monitor"
  end

  def caveats
    <<~EOS
      Launch the menu-bar app (first run installs it to ~/Applications):
        ai-usage-monitor
      Then click the menu-bar icon and enable "Launch at Login".
      After `brew upgrade`, run `ai-usage-monitor` again to refresh the copy.
    EOS
  end

  test do
    assert_predicate prefix/"AIUsageMonitor.app/Contents/MacOS/AIUsageMonitor", :executable?
  end
end
```

- [ ] **Step 2: Ruby 語法檢查**

Run: `ruby -c packaging/homebrew/Formula/ai-usage-monitor.rb`
Expected: `Syntax OK`。

- [ ] **Step 3: （有裝 Homebrew 時）風格檢查**

Run: `brew style packaging/homebrew/Formula/ai-usage-monitor.rb 2>/dev/null || echo "brew not available — skip"`
Expected: 無錯或 skip。

- [ ] **Step 4: Commit**

```bash
git add packaging/homebrew/Formula/ai-usage-monitor.rb
git commit -m "feat: [homebrew] Add ai-usage-monitor formula (build-from-source)"
```

---

## Task 8: Formula — `swiftbar-ai-usage.rb`

**Files:**
- Create: `packaging/homebrew/Formula/swiftbar-ai-usage.rb`

- [ ] **Step 1: 建立 formula**

```ruby
class SwiftbarAiUsage < Formula
  desc "SwiftBar plugin for Claude/Codex/Antigravity rate-limit headroom"
  homepage "https://github.com/CarlLee1983/claude-context-statusline"
  url "https://github.com/CarlLee1983/claude-context-statusline/archive/refs/tags/v0.2.0.tar.gz"
  sha256 "0000000000000000000000000000000000000000000000000000000000000000"
  license "MIT"

  def install
    libexec.install "swiftbar/ai-usage.60s.py"
  end

  def caveats
    <<~EOS
      This is a SwiftBar plugin (requires SwiftBar: brew install --cask swiftbar).
      Symlink it into your SwiftBar plugin folder, then refresh SwiftBar:
        ln -sf "#{opt_libexec}/ai-usage.60s.py" \\
          "$HOME/Library/Application Support/SwiftBar/Plugins/ai-usage.60s.py"
      Optional: `pip3 install Pillow` for capsule icons (falls back to text otherwise).
    EOS
  end

  test do
    output = shell_output("/usr/bin/python3 #{libexec}/ai-usage.60s.py")
    refute_empty output
  end
end
```

- [ ] **Step 2: Ruby 語法檢查**

Run: `ruby -c packaging/homebrew/Formula/swiftbar-ai-usage.rb`
Expected: `Syntax OK`。

- [ ] **Step 3: （有裝 Homebrew 時）風格檢查**

Run: `brew style packaging/homebrew/Formula/swiftbar-ai-usage.rb 2>/dev/null || echo "brew not available — skip"`
Expected: 無錯或 skip。

- [ ] **Step 4: Commit**

```bash
git add packaging/homebrew/Formula/swiftbar-ai-usage.rb
git commit -m "feat: [homebrew] Add swiftbar-ai-usage formula"
```

---

## Task 9: `Scripts/release.sh`（撞版本 → tag → 更新 tap）

**Files:**
- Create: `Scripts/release.sh`

- [ ] **Step 1: 建立發版腳本**

```bash
#!/usr/bin/env bash
# 發版：打 tag、算 tarball sha256、把 packaging/homebrew/Formula 的範本填入版本與 sha
# 後寫進 homebrew-tap repo 並推送。
# Cut a release: tag, compute the tag tarball's sha256, render the formula templates
# into the homebrew-tap repo, and push.
#
# 用法 / Usage:  Scripts/release.sh <version>        # 例：Scripts/release.sh 0.2.0
# tap 位置覆寫 / override tap location:  HOMEBREW_TAP_DIR=/path/to/homebrew-tap
# 只試跑不推送 / dry run (no tag/push):  RELEASE_DRY_RUN=1 Scripts/release.sh 0.2.0
set -euo pipefail

VERSION="${1:?usage: Scripts/release.sh <version e.g. 0.2.0>}"
DRY_RUN="${RELEASE_DRY_RUN:-0}"
REPO="CarlLee1983/claude-context-statusline"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="$ROOT/packaging/homebrew/Formula"
TAP_DIR="${HOMEBREW_TAP_DIR:-$(dirname "$ROOT")/homebrew-tap}"
TARBALL="https://github.com/$REPO/archive/refs/tags/v$VERSION.tar.gz"

run() { if [ "$DRY_RUN" = "1" ]; then echo "[dry-run] $*"; else "$@"; fi; }

echo "==> tag v$VERSION"
run git tag "v$VERSION"
run git push origin "v$VERSION"

echo "==> sha256 of $TARBALL"
SHA="$(curl -fsSL "$TARBALL" | shasum -a 256 | awk '{print $1}')"
echo "    $SHA"

if [ ! -d "$TAP_DIR/Formula" ]; then
  echo "!! tap 不存在 / tap not found: $TAP_DIR" >&2
  echo "   先 clone：git clone https://github.com/CarlLee1983/homebrew-tap \"$TAP_DIR\"" >&2
  exit 1
fi

for f in ctx-statusline ai-usage-monitor swiftbar-ai-usage; do
  sed -e "s|archive/refs/tags/v[0-9][0-9.]*\\.tar\\.gz|archive/refs/tags/v$VERSION.tar.gz|" \
      -e "s|sha256 \"[a-f0-9]*\"|sha256 \"$SHA\"|" \
      "$SRC_DIR/$f.rb" > "$TAP_DIR/Formula/$f.rb"
  echo "    rendered $TAP_DIR/Formula/$f.rb"
done

echo "==> commit & push tap"
run bash -c "cd '$TAP_DIR' && git add Formula && git commit -m 'release: v$VERSION' && git push"
echo "✅ released v$VERSION"
```

- [ ] **Step 2: 語法檢查**

Run:
```bash
chmod +x Scripts/release.sh
bash -n Scripts/release.sh
shellcheck Scripts/release.sh
```
Expected: 無錯誤。

- [ ] **Step 3: dry-run 驗證流程（不打 tag、不推送）**

Run: `RELEASE_DRY_RUN=1 Scripts/release.sh 0.2.0 2>&1 | head -20 || true`
Expected: 印出 `[dry-run] git tag v0.2.0` 等行；因 tap 未 clone 會在 sha 後停在 tap 檢查
（這是預期的——dry-run 仍會真的算 sha256，需網路且 tag 須已存在才有 tarball；無網路時
此步可略過，於實際發版時驗證）。

- [ ] **Step 4: Commit**

```bash
git add Scripts/release.sh
git commit -m "feat: [repo] Add release.sh to tag and sync homebrew-tap formulae"
```

---

## Task 10: 文件更新（README ×4 + CHANGELOG）

**Files:**
- Modify: `README.md`
- Modify: `README.en.md`
- Modify: `macos/AIUsageMonitor/README.md`
- Modify: `swiftbar/README.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: 頂層 `README.md` 安裝表加上 brew 列**

把 `README.md` 工具表（第 10–14 行）三列的「安裝」欄，各自在現有指令前加上 brew 主要路徑。
ctx-statusline 列改為：

```
| [**ctx-statusline**](#1-context-狀態列ctx-statuslinepy) | Claude Code 狀態列 | 目前 session 的 **context window** 用量 | 系統 `python3`，零相依 | `brew install CarlLee1983/tap/ctx-statusline`（或 `./install.sh`） |
```

App 列「安裝」欄改為 `brew install CarlLee1983/tap/ai-usage-monitor`（或 `./Scripts/install-app.sh`）；
SwiftBar 列改為 `brew install CarlLee1983/tap/swiftbar-ai-usage`（或 `./swiftbar/install.sh`）。

並在第 19 行 `---` 之後、`## 1.` 之前插入一個新區段：

```markdown
## 用 Homebrew 一鍵安裝（推薦）

```bash
brew tap CarlLee1983/tap
brew install ctx-statusline ai-usage-monitor swiftbar-ai-usage
```

安裝後各自跑一次設定（不會在安裝期間改你的設定檔）：

```bash
ctx-statusline-setup     # 併入 ~/.claude/settings.json，然後重開 Claude Code session
ai-usage-monitor         # 首次執行會把 App 裝到 ~/Applications 並啟動
# SwiftBar 外掛：依 brew 安裝後的 caveats 提示 symlink 進 SwiftBar plugins 目錄
```

只想裝其中一個？三個 formula 可單獨 `brew install`。

---
```

- [ ] **Step 2: `README.en.md` 同步英文版**

在 `README.en.md` 對應位置插入等義英文區段：

```markdown
## Install with Homebrew (recommended)

```bash
brew tap CarlLee1983/tap
brew install ctx-statusline ai-usage-monitor swiftbar-ai-usage
```

Run each tool's one-time setup afterwards (install never touches your config files):

```bash
ctx-statusline-setup     # merge into ~/.claude/settings.json, then restart Claude Code
ai-usage-monitor         # first run installs the app to ~/Applications and launches it
# SwiftBar plugin: follow the brew caveats to symlink it into your SwiftBar plugins folder
```

Each formula can be installed independently.

---
```

並同步更新 README.en.md 安裝表三列的 install 欄（與 Step 1 對應）。

- [ ] **Step 3: 子目錄 README 補 brew 安裝**

在 `macos/AIUsageMonitor/README.md` 的安裝段落最前面加一句：
```markdown
> 用 Homebrew：`brew install CarlLee1983/tap/ai-usage-monitor`，再執行 `ai-usage-monitor`
> 啟動（首次會裝到 `~/Applications`）。以下為從源碼建置的方式。
```
在 `swiftbar/README.md` 的安裝段落最前面加一句：
```markdown
> 用 Homebrew：`brew install CarlLee1983/tap/swiftbar-ai-usage`，再依 caveats 把外掛 symlink
> 進 SwiftBar 的 plugins 目錄。以下為手動安裝方式。
```

- [ ] **Step 4: `CHANGELOG.md` 新增條目**

在 `CHANGELOG.md` 的 `## [Unreleased]` → `### Added 新增` 區段最上方插入：

```markdown
- Homebrew tap 一鍵安裝：`brew tap CarlLee1983/tap` 後可 `brew install` 三個元件
  （`ctx-statusline` / `ai-usage-monitor` / `swiftbar-ai-usage`）。三者皆從源碼 build，
  無需簽章/公證；安裝期間不改使用者設定，改由 `ctx-statusline-setup`、`ai-usage-monitor`
  啟動器與 caveats 完成。新增 `ctx-statusline-setup`、`packaging/homebrew/Formula/*.rb`、
  `Scripts/release.sh`，並把 `build-app.sh` 參數化（`CONFIGURATION` / `APP_VERSION`）。
  One-shot Homebrew install: `brew tap CarlLee1983/tap` then `brew install` the three
  components. All build from source (no signing/notarization); install never touches user
  config — wiring is done by `ctx-statusline-setup`, the `ai-usage-monitor` launcher, and
  caveats. Adds `ctx-statusline-setup`, `packaging/homebrew/Formula/*.rb`, `Scripts/release.sh`,
  and parameterizes `build-app.sh` (`CONFIGURATION` / `APP_VERSION`).
```

- [ ] **Step 5: Commit**

```bash
git add README.md README.en.md macos/AIUsageMonitor/README.md swiftbar/README.md CHANGELOG.md
git commit -m "docs: [repo] Document Homebrew tap install across READMEs and CHANGELOG"
```

---

## Task 11: tap 建立與發版流程文件（`packaging/homebrew/README.md`）

**Files:**
- Create: `packaging/homebrew/README.md`

- [ ] **Step 1: 建立說明文件**

```markdown
# Homebrew tap 維護

本資料夾的 `Formula/*.rb` 是三個 formula 的**權威範本**。實際被使用者 tap 的是獨立 repo
`CarlLee1983/homebrew-tap`；`Scripts/release.sh` 在發版時把範本填入版本與 sha256 後推到該 repo。

## 一次性建立 tap repo

```bash
gh repo create CarlLee1983/homebrew-tap --public \
  --description "Homebrew tap for claude-context-statusline tools"
git clone https://github.com/CarlLee1983/homebrew-tap ../homebrew-tap
mkdir -p ../homebrew-tap/Formula
# 首次可手動複製範本並填入第一個版本的 sha256，或直接跑 release.sh
```

## 發版

```bash
# 1) 更新 CHANGELOG 的 Unreleased → 版本號
# 2) 跑發版腳本（會打 tag、算 sha、更新 tap 並推送）
Scripts/release.sh 0.2.0
```

`HOMEBREW_TAP_DIR` 可覆寫 tap 本地路徑（預設為與本專案同層的 `../homebrew-tap`）。

## 發版後驗證

```bash
brew untap CarlLee1983/tap 2>/dev/null || true
brew tap CarlLee1983/tap
brew install --build-from-source ctx-statusline ai-usage-monitor swiftbar-ai-usage
brew audit --strict --online CarlLee1983/tap/ctx-statusline
brew test CarlLee1983/tap/ctx-statusline
```
```

- [ ] **Step 2: Commit**

```bash
git add packaging/homebrew/README.md
git commit -m "docs: [homebrew] Document tap creation and release flow"
```

---

## 發版後手動驗收（不在自動化任務內）

所有 task 完成、合併後，實際發第一版時執行：

1. 依 `packaging/homebrew/README.md` 建立 `CarlLee1983/homebrew-tap` repo。
2. `Scripts/release.sh 0.2.0`。
3. 乾淨環境跑：`brew tap CarlLee1983/tap && brew install --build-from-source ctx-statusline ai-usage-monitor swiftbar-ai-usage`。
4. `brew audit --strict --online` 三個 formula 皆過。
5. 手動確認：`ctx-statusline-setup` 後狀態列出現；`ai-usage-monitor` 啟動選單列 App；SwiftBar 外掛顯示。
