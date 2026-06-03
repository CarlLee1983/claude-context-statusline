# AI CLI 完成提示（Ghostty 分頁標記）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓 AI CLI 跑完一輪時，透過終端機 BEL 觸發 Ghostty 把未聚焦的分頁/視窗標記為「需要注意」。

**Architecture:** 兩層。觸發層 `bell/notify.sh` 在 CLI 完成時送 `\a` 到 `/dev/tty`（Claude 用 Stop hook、Codex 用 notify），永不讓 host CLI 崩潰。顯示層由 Ghostty `bell-features = title,attention` 呈現。設定合併邏輯集中在可匯入、可測的 `bell/bell-setup`（純函式 + 薄 I/O），install/uninstall.sh 只做編排——對齊 repo 既有 `ctx-statusline-setup` 的做法。

**Tech Stack:** `/bin/sh`（notify.sh）、macOS 內建 `/usr/bin/python3`（3.9.6，純標準庫，**無 tomllib**，故 TOML 用文字行掃描）、`bash`（install/uninstall）、`unittest`（測試）。

---

## 檔案結構

```
bell/
  notify.sh        # 執行期 BEL 發送器；來源感知；永不崩潰
  bell-setup       # python 模組（無副檔名）：三邊設定的純函式 + 薄 I/O + main()
  install.sh       # bash 編排：呼叫 bell-setup install，印 Ghostty 雙位置/手動提示
  uninstall.sh     # bash 編排：呼叫 bell-setup uninstall
  README.md        # 繁中（主）
  README.en.md     # 英文（同步）
tests/
  test_bell.py     # 純標準庫 unittest；importlib 載入 bell-setup、subprocess 跑 notify.sh
docs/superpowers/specs/2026-06-03-ghostty-completion-bell-design.md   # 已存在（設計）
README.md / README.en.md / CHANGELOG.md                              # 修改：新增第四元件
```

**責任切分**：
- `notify.sh` 只管「送不送 bell」這一件事（執行期、零相依）。
- `bell-setup` 純函式（`apply_*`/`remove_*`/`*_has_*`）不碰檔案，可單測；薄 I/O（`_load`/`_backup`/`_write`/`run_install`/`run_uninstall`）負責備份與寫回；`main()` 從環境變數解析路徑。
- `install.sh`/`uninstall.sh` 不含合併邏輯，只解析來源路徑、呼叫 `bell-setup`、印使用者提示。

---

## Task 1: `bell/notify.sh` — 執行期 BEL 發送器

**Files:**
- Create: `bell/notify.sh`
- Test: `tests/test_bell.py`（本任務新增 `NotifyShTest`）

設計：寫入目標可用 `BELL_TTY` 覆寫（預設 `/dev/tty`），讓測試能斷言有沒有送出 `\a`；正式環境不設此變數即走 `/dev/tty`。

- [ ] **Step 1: 先寫會失敗的測試**

在 `tests/test_bell.py` 建立檔案開頭與第一個測試類別：

```python
#!/usr/bin/env python3
"""bell 元件測試：notify.sh 行為 + bell-setup 設定合併。純標準庫。"""
import importlib.util
import os
import subprocess
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_BELL_DIR = os.path.join(_HERE, os.pardir, "bell")
_NOTIFY = os.path.join(_BELL_DIR, "notify.sh")


class NotifyShTest(unittest.TestCase):
    def _run(self, *args, payload_tty=None):
        """跑 notify.sh，BELL_TTY 指到暫存檔；回傳該檔內容（bytes）。"""
        fd, tty = tempfile.mkstemp(suffix=".tty")
        os.close(fd)
        env = {**os.environ, "BELL_TTY": payload_tty if payload_tty else tty}
        try:
            proc = subprocess.run(
                ["/bin/sh", _NOTIFY, *args], env=env,
                capture_output=True, timeout=10,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            with open(tty, "rb") as f:
                return f.read()
        finally:
            os.path.exists(tty) and os.remove(tty)

    def test_claude_source_always_emits_bell(self):
        self.assertIn(b"\a", self._run("claude"))

    def test_codex_turn_complete_emits_bell(self):
        payload = '{"type":"agent-turn-complete","last-assistant-message":"hi"}'
        self.assertIn(b"\a", self._run("codex", payload))

    def test_codex_other_event_is_silent(self):
        payload = '{"type":"task-started"}'
        self.assertEqual(b"", self._run("codex", payload))

    def test_unwritable_tty_does_not_error(self):
        # 不可寫的目標仍須 exit 0、不噴錯
        proc = subprocess.run(
            ["/bin/sh", _NOTIFY, "claude"],
            env={**os.environ, "BELL_TTY": "/nonexistent-dir/nope"},
            capture_output=True, timeout=10,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python3 -m unittest tests.test_bell.NotifyShTest -v`
Expected: FAIL（`notify.sh` 不存在 → 4 個測試錯）

- [ ] **Step 3: 寫最小實作**

`bell/notify.sh`：

```sh
#!/bin/sh
# bell/notify.sh — AI CLI 跑完一輪時送出終端機 BEL，由 Ghostty 標記分頁。
# 永不讓 host CLI 崩潰：任何失敗都吞掉並 exit 0。
#
# 用法 / Usage: notify.sh <source> [payload]
#   claude  無條件送 BEL（Stop hook 已代表一輪完成）
#   codex   僅當 payload JSON 的 type 為 agent-turn-complete 時送
# 測試/特殊情境可用 BELL_TTY 覆寫輸出目標（預設 /dev/tty）。
src="${1:-}"

if [ "$src" = "codex" ]; then
  case "${2:-}" in
    *'"type":"agent-turn-complete"'*|*'"type": "agent-turn-complete"'*) : ;;
    *) exit 0 ;;
  esac
fi

tty_out="${BELL_TTY:-/dev/tty}"
printf '\a' > "$tty_out" 2>/dev/null || true
exit 0
```

- [ ] **Step 4: 跑測試確認通過**

Run: `chmod +x bell/notify.sh && python3 -m unittest tests.test_bell.NotifyShTest -v`
Expected: PASS（4 passed）

- [ ] **Step 5: shellcheck**

Run: `shellcheck bell/notify.sh`
Expected: 無輸出（無警告）

- [ ] **Step 6: Commit**

```bash
git add bell/notify.sh tests/test_bell.py
git commit -m "feat: [bell] 新增 notify.sh 終端機 BEL 發送器（來源感知、永不崩潰）"
```

---

## Task 2: `bell-setup` — Claude Stop hook 合併（純函式）

**Files:**
- Create: `bell/bell-setup`
- Test: `tests/test_bell.py`（新增 `ClaudeStopHookTest`）

settings.json 目標結構：
```json
{ "hooks": { "Stop": [ { "hooks": [ {"type":"command","command":"<cmd>"} ] } ] } }
```

- [ ] **Step 1: 先寫會失敗的測試**

在 `tests/test_bell.py` 的 import 區塊後加入模組載入與測試：

```python
_SETUP = os.path.join(_BELL_DIR, "bell-setup")
_spec = importlib.util.spec_from_file_location("bell_setup", _SETUP)
bell_setup = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bell_setup)


class ClaudeStopHookTest(unittest.TestCase):
    CMD = "/abs/bell/notify.sh claude"

    def test_apply_adds_stop_hook_to_empty(self):
        out = bell_setup.apply_stop_hook({}, self.CMD)
        self.assertEqual(
            out["hooks"]["Stop"],
            [{"hooks": [{"type": "command", "command": self.CMD}]}],
        )

    def test_apply_preserves_existing_keys_and_other_hooks(self):
        data = {"model": "opus", "hooks": {"Stop": [
            {"hooks": [{"type": "command", "command": "other"}]}]}}
        out = bell_setup.apply_stop_hook(data, self.CMD)
        self.assertEqual(out["model"], "opus")
        cmds = [h["command"] for m in out["hooks"]["Stop"] for h in m["hooks"]]
        self.assertEqual(cmds, ["other", self.CMD])

    def test_apply_is_idempotent(self):
        once = bell_setup.apply_stop_hook({}, self.CMD)
        twice = bell_setup.apply_stop_hook(once, self.CMD)
        self.assertEqual(once, twice)

    def test_apply_does_not_mutate_input(self):
        data = {"hooks": {"Stop": []}}
        bell_setup.apply_stop_hook(data, self.CMD)
        self.assertEqual(data, {"hooks": {"Stop": []}})

    def test_remove_drops_only_our_matcher(self):
        data = bell_setup.apply_stop_hook(
            {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "other"}]}]}},
            self.CMD)
        out, removed = bell_setup.remove_stop_hook(data, self.CMD)
        self.assertTrue(removed)
        cmds = [h["command"] for m in out["hooks"]["Stop"] for h in m["hooks"]]
        self.assertEqual(cmds, ["other"])

    def test_remove_returns_false_when_absent(self):
        out, removed = bell_setup.remove_stop_hook({}, self.CMD)
        self.assertFalse(removed)
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python3 -m unittest tests.test_bell.ClaudeStopHookTest -v`
Expected: FAIL（`bell-setup` 不存在 / 無 `apply_stop_hook`）

- [ ] **Step 3: 寫最小實作**

建立 `bell/bell-setup`，先放檔頭與 Claude 區段：

```python
#!/usr/bin/env python3
"""bell-setup — 把「完成提示」設定併入/移出 Claude / Codex / Ghostty 三邊設定。

純標準庫、零相依。每個 apply_/remove_ 都是純函式（不改輸入、回傳新值）；
薄 I/O 負責備份與寫回。honors CLAUDE_CONFIG_DIR / CODEX_HOME / XDG_CONFIG_HOME。
"""
import json
import os
import re
import shutil
import sys
import time

MARKER = "# added by claude-context-statusline bell/install.sh"


# ---- Claude Code: settings.json 的 Stop hook ------------------------------
def _stop_has_command(stop, command):
    return any(h.get("command") == command
               for matcher in stop for h in matcher.get("hooks", []))


def apply_stop_hook(data, command):
    """回傳加入我們 Stop hook 的新 dict（以 command 比對，冪等；不改輸入）。"""
    hooks = dict(data.get("hooks", {}))
    stop = list(hooks.get("Stop", []))
    if _stop_has_command(stop, command):
        return data
    entry = {"hooks": [{"type": "command", "command": command}]}
    hooks = {**hooks, "Stop": stop + [entry]}
    return {**data, "hooks": hooks}


def remove_stop_hook(data, command):
    """回傳 (新 dict, 是否移除)。只移除引用到 command 的 matcher。"""
    hooks = dict(data.get("hooks", {}))
    stop = hooks.get("Stop")
    if not stop:
        return data, False
    kept = [m for m in stop
            if not any(h.get("command") == command for h in m.get("hooks", []))]
    if len(kept) == len(stop):
        return data, False
    if kept:
        hooks = {**hooks, "Stop": kept}
    else:
        hooks = {k: v for k, v in hooks.items() if k != "Stop"}
    return {**data, "hooks": hooks}, True
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python3 -m unittest tests.test_bell.ClaudeStopHookTest -v`
Expected: PASS（6 passed）

- [ ] **Step 5: Commit**

```bash
git add bell/bell-setup tests/test_bell.py
git commit -m "feat: [bell] bell-setup 新增 Claude Stop hook 合併純函式"
```

---

## Task 3: `bell-setup` — Codex notify 守衛式 append（純函式）

**Files:**
- Modify: `bell/bell-setup`（新增 Codex 區段）
- Test: `tests/test_bell.py`（新增 `CodexNotifyTest`）

策略：**不解析整份 TOML**（3.9.6 無 tomllib），只用文字行掃描判斷有無「頂層 `notify`」（出現在第一個 `[table]` 之前）。沒有才在檔案最前面 prepend 帶 MARKER 的 notify。

- [ ] **Step 1: 先寫會失敗的測試**

```python
class CodexNotifyTest(unittest.TestCase):
    ARGS = ["/abs/bell/notify.sh", "codex"]

    def test_detect_toplevel_notify_present(self):
        self.assertTrue(bell_setup.codex_has_toplevel_notify(
            'model = "o3"\nnotify = ["x"]\n[tools]\n'))

    def test_notify_inside_table_is_not_toplevel(self):
        self.assertFalse(bell_setup.codex_has_toplevel_notify(
            '[some]\nnotify = ["x"]\n'))

    def test_apply_prepends_when_absent(self):
        text = '[mcp_servers.foo]\ncommand = "x"\n'
        out, changed = bell_setup.apply_codex_notify(text, self.ARGS)
        self.assertTrue(changed)
        self.assertTrue(out.startswith(MARKER := bell_setup.MARKER))
        self.assertIn('notify = ["/abs/bell/notify.sh", "codex"]', out)
        self.assertIn('[mcp_servers.foo]', out)  # 原內容保留
        # notify 必須在第一個 table 之前
        self.assertLess(out.index("notify ="), out.index("[mcp_servers.foo]"))

    def test_apply_noop_when_present(self):
        text = 'notify = ["existing"]\n[t]\n'
        out, changed = bell_setup.apply_codex_notify(text, self.ARGS)
        self.assertFalse(changed)
        self.assertEqual(out, text)

    def test_remove_strips_our_block_only(self):
        text = '[mcp_servers.foo]\ncommand = "x"\n'
        applied, _ = bell_setup.apply_codex_notify(text, self.ARGS)
        out, removed = bell_setup.remove_codex_notify(applied)
        self.assertTrue(removed)
        self.assertNotIn("notify =", out)
        self.assertIn('[mcp_servers.foo]', out)

    def test_remove_noop_without_marker(self):
        out, removed = bell_setup.remove_codex_notify('notify = ["hand"]\n')
        self.assertFalse(removed)
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python3 -m unittest tests.test_bell.CodexNotifyTest -v`
Expected: FAIL（無 `codex_has_toplevel_notify`）

- [ ] **Step 3: 寫最小實作**

在 `bell/bell-setup` 接續加入：

```python
# ---- Codex: config.toml 的 notify（文字行掃描，不解析 TOML）-----------------
_NOTIFY_RE = re.compile(r"^\s*notify\s*=")


def codex_has_toplevel_notify(text):
    """是否已有頂層 notify（第一個 [table] 之前出現 notify =）。"""
    for line in text.splitlines():
        s = line.lstrip()
        if s.startswith("["):          # table 或 array-of-tables 表頭
            return False
        if _NOTIFY_RE.match(line):
            return True
    return False


def apply_codex_notify(text, command_args):
    """回傳 (新 text, 是否變更)。無頂層 notify 時於檔首 prepend 帶 MARKER 的區段。"""
    if codex_has_toplevel_notify(text):
        return text, False
    arr = ", ".join(json.dumps(a) for a in command_args)
    block = f"{MARKER}\nnotify = [{arr}]\n"
    if text and not text.startswith("\n"):
        block += "\n"
    return block + text, True


def remove_codex_notify(text):
    """移除我們以 MARKER 標記的 notify 區段（MARKER 行 + 其後 notify 行 + 一個空行）。"""
    lines = text.splitlines()
    out, removed, i = [], False, 0
    while i < len(lines):
        if lines[i].strip() == MARKER:
            removed = True
            i += 1
            if i < len(lines) and _NOTIFY_RE.match(lines[i]):
                i += 1
            if i < len(lines) and lines[i].strip() == "":
                i += 1
            continue
        out.append(lines[i])
        i += 1
    if not removed:
        return text, False
    new = "\n".join(out)
    if text.endswith("\n") and new and not new.endswith("\n"):
        new += "\n"
    return new, True
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python3 -m unittest tests.test_bell.CodexNotifyTest -v`
Expected: PASS（6 passed）

- [ ] **Step 5: Commit**

```bash
git add bell/bell-setup tests/test_bell.py
git commit -m "feat: [bell] bell-setup 新增 Codex notify 守衛式 append（文字掃描）"
```

---

## Task 4: `bell-setup` — Ghostty bell-features（純函式）

**Files:**
- Modify: `bell/bell-setup`（新增 Ghostty 區段）
- Test: `tests/test_bell.py`（新增 `GhosttyBellTest`）

- [ ] **Step 1: 先寫會失敗的測試**

```python
class GhosttyBellTest(unittest.TestCase):
    def test_apply_appends_when_absent(self):
        out, changed = bell_setup.apply_ghostty_bell("font-size = 14\n")
        self.assertTrue(changed)
        self.assertIn("bell-features = title,attention", out)
        self.assertIn("font-size = 14", out)
        self.assertTrue(out.endswith("\n"))

    def test_apply_adds_trailing_newline_when_missing(self):
        out, changed = bell_setup.apply_ghostty_bell("font-size = 14")  # 無結尾換行
        self.assertIn("font-size = 14\n", out)
        self.assertIn("bell-features = title,attention", out)

    def test_apply_noop_when_bell_features_present(self):
        text = "bell-features = no-audio\n"
        out, changed = bell_setup.apply_ghostty_bell(text)
        self.assertFalse(changed)
        self.assertEqual(out, text)

    def test_remove_strips_our_block(self):
        applied, _ = bell_setup.apply_ghostty_bell("font-size = 14\n")
        out, removed = bell_setup.remove_ghostty_bell(applied)
        self.assertTrue(removed)
        self.assertNotIn("bell-features", out)
        self.assertIn("font-size = 14", out)

    def test_remove_noop_for_hand_written(self):
        out, removed = bell_setup.remove_ghostty_bell("bell-features = audio\n")
        self.assertFalse(removed)
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python3 -m unittest tests.test_bell.GhosttyBellTest -v`
Expected: FAIL（無 `apply_ghostty_bell`）

- [ ] **Step 3: 寫最小實作**

接續加入 `bell/bell-setup`：

```python
# ---- Ghostty: 行導向 config 的 bell-features ------------------------------
_BELL_FEATURES_RE = re.compile(r"^\s*bell-features\s*=")
GHOSTTY_BELL_VALUE = "title,attention"


def ghostty_has_bell_features(text):
    return any(_BELL_FEATURES_RE.match(l) for l in text.splitlines())


def apply_ghostty_bell(text, value=GHOSTTY_BELL_VALUE):
    """回傳 (新 text, 是否變更)。已有 bell-features 則不動。"""
    if ghostty_has_bell_features(text):
        return text, False
    block = f"{MARKER}\nbell-features = {value}\n"
    if text and not text.endswith("\n"):
        text += "\n"
    return text + block, True


def remove_ghostty_bell(text):
    """移除我們以 MARKER 標記的 bell-features 區段。"""
    lines = text.splitlines()
    out, removed, i = [], False, 0
    while i < len(lines):
        if lines[i].strip() == MARKER:
            removed = True
            i += 1
            if i < len(lines) and _BELL_FEATURES_RE.match(lines[i]):
                i += 1
            continue
        out.append(lines[i])
        i += 1
    if not removed:
        return text, False
    new = "\n".join(out)
    if text.endswith("\n") and new and not new.endswith("\n"):
        new += "\n"
    return new, True
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python3 -m unittest tests.test_bell.GhosttyBellTest -v`
Expected: PASS（5 passed）

- [ ] **Step 5: Commit**

```bash
git add bell/bell-setup tests/test_bell.py
git commit -m "feat: [bell] bell-setup 新增 Ghostty bell-features 合併純函式"
```

---

## Task 5: `bell-setup` — 薄 I/O 與 `main()`（備份、寫回、路徑解析）

**Files:**
- Modify: `bell/bell-setup`（新增 I/O + `run_install`/`run_uninstall` + `main`）
- Test: `tests/test_bell.py`（新增 `BellSetupIoTest`）

`run_install`/`run_uninstall` 接「明確路徑」（測試傳暫存檔），`main()` 從環境變數解析後呼叫。各邊：載入文字/JSON → 套用 → 有變更才備份並寫回。任一邊失敗不影響其他邊。

- [ ] **Step 1: 先寫會失敗的測試**

```python
class BellSetupIoTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.claude = os.path.join(self.dir, "settings.json")
        self.codex = os.path.join(self.dir, "config.toml")
        self.ghostty = os.path.join(self.dir, "ghostty.config")
        self.cmd = "/abs/bell/notify.sh claude"
        self.codex_args = ["/abs/bell/notify.sh", "codex"]

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _write(self, path, text):
        with open(path, "w") as f:
            f.write(text)

    def test_install_creates_and_backs_up(self):
        self._write(self.claude, '{"model":"opus"}')
        self._write(self.codex, '[t]\n')
        self._write(self.ghostty, 'font-size = 14\n')
        results = bell_setup.run_install(
            self.claude, self.cmd, self.codex, self.codex_args, self.ghostty)
        # Claude 有了 Stop hook
        with open(self.claude) as f:
            data = json.load(f)
        cmds = [h["command"] for m in data["hooks"]["Stop"] for h in m["hooks"]]
        self.assertIn(self.cmd, cmds)
        # 三邊都各有一份 .bak.*
        for base in (self.claude, self.codex, self.ghostty):
            self.assertTrue(any(f.startswith(os.path.basename(base) + ".bak.")
                                for f in os.listdir(self.dir)))
        self.assertEqual(len(results), 3)

    def test_install_is_idempotent_no_second_change(self):
        self._write(self.claude, "{}")
        self._write(self.codex, "")
        self._write(self.ghostty, "")
        bell_setup.run_install(self.claude, self.cmd, self.codex,
                               self.codex_args, self.ghostty)
        before = open(self.ghostty).read()
        bell_setup.run_install(self.claude, self.cmd, self.codex,
                               self.codex_args, self.ghostty)
        self.assertEqual(open(self.ghostty).read(), before)  # 第二次不再加

    def test_install_aborts_claude_on_invalid_json(self):
        self._write(self.claude, "{ not json")
        self._write(self.codex, "")
        self._write(self.ghostty, "")
        results = bell_setup.run_install(self.claude, self.cmd, self.codex,
                                         self.codex_args, self.ghostty)
        # Claude 那邊標記為錯誤、檔案未變動；Codex/Ghostty 仍照常
        self.assertEqual(open(self.claude).read(), "{ not json")
        claude_res = [r for r in results if r["target"] == self.claude][0]
        self.assertEqual(claude_res["status"], "error")

    def test_uninstall_restores(self):
        self._write(self.claude, "{}")
        self._write(self.codex, "")
        self._write(self.ghostty, "")
        bell_setup.run_install(self.claude, self.cmd, self.codex,
                               self.codex_args, self.ghostty)
        bell_setup.run_uninstall(self.claude, self.cmd, self.codex, self.ghostty)
        with open(self.claude) as f:
            self.assertNotIn("Stop", json.load(f).get("hooks", {}))
        self.assertNotIn("notify", open(self.codex).read())
        self.assertNotIn("bell-features", open(self.ghostty).read())
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python3 -m unittest tests.test_bell.BellSetupIoTest -v`
Expected: FAIL（無 `run_install`）

- [ ] **Step 3: 寫最小實作**

接續加入 `bell/bell-setup`（I/O、orchestration、main）：

```python
# ---- 薄 I/O -----------------------------------------------------------------
class InvalidJSON(Exception):
    pass


def _read_text(path):
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as f:
        return f.read()


def _backup(path):
    if not os.path.exists(path):
        return None
    backup = f"{path}.bak.{time.strftime('%Y%m%d%H%M%S')}"
    shutil.copy(path, backup)
    return backup


def _write_text(path, text, mode=None):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    if mode is not None:
        os.chmod(path, mode)


def _result(target, status, detail=""):
    return {"target": target, "status": status, "detail": detail}


def _apply_json(path, apply_fn):
    """Claude settings.json：非法 JSON 回 error（不動檔）；有變更才備份寫回。"""
    text = _read_text(path)
    if text.strip():
        try:
            data = json.loads(text)
        except ValueError:
            return _result(path, "error", "settings.json 非合法 JSON，未變動")
        if not isinstance(data, dict):
            return _result(path, "error", "settings.json 頂層非物件，未變動")
    else:
        data = {}
    new = apply_fn(data)
    if new == data:
        return _result(path, "skipped", "已安裝或無需變更")
    _backup(path)
    _write_text(path, json.dumps(new, indent=2, ensure_ascii=False) + "\n")
    return _result(path, "ok")


def _apply_text(path, apply_fn, mode=None):
    """Codex / Ghostty：純文字；有變更才備份寫回（保留原權限）。"""
    text = _read_text(path)
    new, changed = apply_fn(text)
    if not changed:
        return _result(path, "skipped", "已安裝或已有手動設定")
    keep_mode = mode
    if keep_mode is None and os.path.exists(path):
        keep_mode = os.stat(path).st_mode & 0o777
    _backup(path)
    _write_text(path, new, keep_mode)
    return _result(path, "ok")


# ---- orchestration ----------------------------------------------------------
def run_install(claude_path, claude_cmd, codex_path, codex_args, ghostty_path):
    return [
        _apply_json(claude_path, lambda d: apply_stop_hook(d, claude_cmd)),
        _apply_text(codex_path, lambda t: apply_codex_notify(t, codex_args), mode=0o600),
        _apply_text(ghostty_path, apply_ghostty_bell),
    ]


def run_uninstall(claude_path, claude_cmd, codex_path, ghostty_path):
    return [
        _apply_json(claude_path, lambda d: remove_stop_hook(d, claude_cmd)[0]),
        _apply_text(codex_path, remove_codex_notify, mode=0o600),
        _apply_text(ghostty_path, remove_ghostty_bell),
    ]


# ---- 路徑解析 + main --------------------------------------------------------
def _paths(env):
    claude = (env.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude"))
    codex = (env.get("CODEX_HOME") or os.path.expanduser("~/.codex"))
    xdg = (env.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"))
    return (
        os.path.join(claude, "settings.json"),
        os.path.join(codex, "config.toml"),
        os.path.join(xdg, "ghostty", "config"),
    )


def main(argv=None, env=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    env = os.environ if env is None else env
    if not argv or argv[0] not in ("install", "uninstall"):
        print("usage: bell-setup install|uninstall --notify <abs-path>", file=sys.stderr)
        return 2
    action = argv[0]
    notify = None
    if "--notify" in argv:
        notify = argv[argv.index("--notify") + 1]
    if not notify:
        print("!! --notify <abs path to bell/notify.sh> 為必填", file=sys.stderr)
        return 2
    claude_path, codex_path, ghostty_path = _paths(env)
    claude_cmd = f"{notify} claude"
    codex_args = [notify, "codex"]
    if action == "install":
        results = run_install(claude_path, claude_cmd, codex_path, codex_args, ghostty_path)
    else:
        results = run_uninstall(claude_path, claude_cmd, codex_path, ghostty_path)
    for r in results:
        mark = {"ok": "✓", "skipped": "•", "error": "!!"}[r["status"]]
        print(f"   {mark} {r['target']} {r['detail']}".rstrip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python3 -m unittest tests.test_bell.BellSetupIoTest -v`
Expected: PASS（4 passed）

- [ ] **Step 5: 全元件測試 + chmod**

Run: `chmod +x bell/bell-setup && python3 -m unittest discover -s tests -v`
Expected: 全綠（含既有 test_ctx_statusline / test_ai_usage 不受影響）

- [ ] **Step 6: Commit**

```bash
git add bell/bell-setup tests/test_bell.py
git commit -m "feat: [bell] bell-setup 補上備份/寫回 I/O 與 install/uninstall 編排"
```

---

## Task 6: `bell/install.sh` 與 `bell/uninstall.sh`（bash 編排）

**Files:**
- Create: `bell/install.sh`, `bell/uninstall.sh`

職責：解析來源路徑、呼叫 `bell-setup`、處理 Ghostty 雙位置警告與 Codex 已存在提示。不含合併邏輯。

- [ ] **Step 1: 寫 `bell/install.sh`**

```bash
#!/usr/bin/env bash
# 安裝 AI CLI 完成提示（Ghostty 分頁標記）。
# Install AI CLI completion bell (Ghostty tab attention).
#
# 做的事 / What it does（皆先備份、只增不刪、可重複執行）:
#   (1) Claude Code settings.json 加 Stop hook → bell/notify.sh claude
#   (2) Codex config.toml 加 notify → bell/notify.sh codex（已有 notify 則略過並提示）
#   (3) Ghostty config 加 bell-features = title,attention（XDG 那份）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="/usr/bin/python3"
NOTIFY="$SCRIPT_DIR/notify.sh"
SETUP="$SCRIPT_DIR/bell-setup"

if [ ! -x "$PYTHON" ]; then
  echo "!! 找不到 $PYTHON（本工具依賴 macOS 內建 python3）。" >&2
  echo "!! $PYTHON not found (relies on macOS's built-in python3)." >&2
  exit 1
fi
chmod +x "$NOTIFY" "$SETUP"

echo "==> 併入三邊設定 / merging config (Claude / Codex / Ghostty)"
"$PYTHON" "$SETUP" install --notify "$NOTIFY"

# --- Ghostty 雙位置警告 / dual-location warning ----------------------------
APP_SUPPORT="$HOME/Library/Application Support/com.mitchellh.ghostty/config"
if [ -f "$APP_SUPPORT" ] && grep -q '^\s*bell-features' "$APP_SUPPORT" 2>/dev/null; then
  echo
  echo "⚠  另一份 Ghostty 設定也定義了 bell-features（未更動它）：" >&2
  echo "⚠  A second Ghostty config also sets bell-features (left untouched):" >&2
  echo "     $APP_SUPPORT" >&2
fi

cat <<'EOF'

✅ 安裝完成 / Done.
後續 / Next:
 • 重新開啟 Claude Code session 讓 Stop hook 生效。
   Reopen a Claude Code session so the Stop hook loads.
 • 重新載入 Ghostty 設定：Cmd+Shift+, 或重開 Ghostty。
   Reload Ghostty config: Cmd+Shift+, or restart Ghostty.
 • 若上面 Codex 那行標「•（略過）」表示你已有 notify 設定；
   請手動把它指到 bell/notify.sh，並在腳本判斷 agent-turn-complete。
   If Codex shows "• (skipped)", you already have a notify; point it at
   bell/notify.sh manually.
EOF
```

- [ ] **Step 2: 寫 `bell/uninstall.sh`**

```bash
#!/usr/bin/env bash
# 移除 AI CLI 完成提示設定（還原三邊，留備份）。
# Remove AI CLI completion bell config (restores all three, keeps backups).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="/usr/bin/python3"
NOTIFY="$SCRIPT_DIR/notify.sh"
SETUP="$SCRIPT_DIR/bell-setup"

if [ ! -x "$PYTHON" ]; then
  echo "!! 找不到 $PYTHON。" >&2
  exit 1
fi

echo "==> 移除三邊設定 / removing config (Claude / Codex / Ghostty)"
"$PYTHON" "$SETUP" uninstall --notify "$NOTIFY"

echo
echo "✅ 已移除 / Done. 重新開啟 Claude Code session 與重載 Ghostty 設定即生效。"
```

- [ ] **Step 3: 語法檢查**

Run: `chmod +x bell/install.sh bell/uninstall.sh && bash -n bell/install.sh bell/uninstall.sh && shellcheck bell/install.sh bell/uninstall.sh`
Expected: 無錯誤輸出

- [ ] **Step 4: 端對端煙霧測試（用暫存設定目錄）**

Run:
```bash
TMP="$(mktemp -d)"
mkdir -p "$TMP/claude" "$TMP/codex" "$TMP/config/ghostty"
echo '{"model":"opus"}' > "$TMP/claude/settings.json"
printf '[mcp]\n' > "$TMP/codex/config.toml"
printf 'font-size = 14\n' > "$TMP/config/ghostty/config"
CLAUDE_CONFIG_DIR="$TMP/claude" CODEX_HOME="$TMP/codex" XDG_CONFIG_HOME="$TMP/config" \
  ./bell/install.sh
echo "--- settings.json ---"; cat "$TMP/claude/settings.json"
echo "--- config.toml ---";   cat "$TMP/codex/config.toml"
echo "--- ghostty ---";       cat "$TMP/config/ghostty/config"
CLAUDE_CONFIG_DIR="$TMP/claude" CODEX_HOME="$TMP/codex" XDG_CONFIG_HOME="$TMP/config" \
  ./bell/uninstall.sh
echo "--- after uninstall: ghostty ---"; cat "$TMP/config/ghostty/config"
rm -rf "$TMP"
```
Expected: install 後三檔各含我們的設定且有 `.bak.*`；uninstall 後 `bell-features`/`notify`/`Stop` 皆消失。

- [ ] **Step 5: Commit**

```bash
git add bell/install.sh bell/uninstall.sh
git commit -m "feat: [bell] 新增 install.sh / uninstall.sh 編排與 Ghostty 雙位置提示"
```

---

## Task 7: 文件與 CHANGELOG

**Files:**
- Create: `bell/README.md`, `bell/README.en.md`
- Modify: `README.md`, `README.en.md`（頂層第四元件）, `CHANGELOG.md`, `CLAUDE.md`（專案概述補第四元件）

- [ ] **Step 1: 寫 `bell/README.md`（繁中）**

涵蓋：用途（對話完成→Ghostty 分頁標記）、架構兩層圖、安裝/移除指令、各 CLI 的觸發點（Claude=Stop、Codex=notify、Antigravity 尚未支援）、Ghostty 1.3.1 背景分頁限制與 1.4 改善、雙位置設定說明、`BELL_TTY` 測試覆寫、「永不崩潰」原則。內容依設計文件 §2–§6、§8。

- [ ] **Step 2: 寫 `bell/README.en.md`（英文，同步）**

與繁中版逐節對應。

- [ ] **Step 3: 更新頂層 `README.md` / `README.en.md`**

在三工具總覽加入第四項「完成提示 `bell/`」，一句話定位 + 連到 `bell/README.md`。明確區分：此元件看的是「**完成事件 → 終端機標記**」，與 context 用量、速率限制都不同。

- [ ] **Step 4: 更新 `CHANGELOG.md`**

新增條目：`feat: [bell] AI CLI 完成提示（Ghostty 分頁標記）— Claude Stop hook + Codex notify + Ghostty bell-features，含安裝/移除與測試`。

- [ ] **Step 5: 更新 `CLAUDE.md`**

「專案概述」由三元件改為四元件，補 `bell/` 一行；「開發指令」補 `python3 -m unittest tests.test_bell -v` 或沿用既有 discover 指令；「慣例」雙語 README 清單補 `bell/`。

- [ ] **Step 6: 驗證連結與測試**

Run: `python3 -m unittest discover -s tests -v && bash -n bell/install.sh bell/uninstall.sh`
Expected: 全綠

- [ ] **Step 7: Commit**

```bash
git add bell/README.md bell/README.en.md README.md README.en.md CHANGELOG.md CLAUDE.md
git commit -m "docs: [bell] 第四元件雙語文件、頂層總覽、CHANGELOG 與 CLAUDE.md 更新"
```

---

## Self-Review 結果

**Spec coverage（對照設計文件）：**
- §2 兩層架構 → Task 1（觸發）+ Task 4/6（顯示）✓
- §4 notify.sh 來源感知/永不崩潰 → Task 1 ✓
- §5 Ghostty `title,attention`/雙位置/不覆蓋既有 → Task 4 + Task 6 Step 1 ✓
- §6.1 Claude Stop hook 合併/保留/壞 JSON 中止 → Task 2 + Task 5（`_apply_json`）✓
- §6.2 Codex 文字掃描守衛 append/保留權限 600 → Task 3 + Task 5（`_apply_text` mode=0o600）✓
- §6.3 Ghostty 偵測/append/警告 → Task 4 + Task 6 ✓
- §6 備份/只增不刪/冪等/CLAUDE_CONFIG_DIR/任一邊失敗不影響其他 → Task 5 ✓
- §7 測試三類 → Task 1/2/3/4/5 對應測試 ✓
- §8 Antigravity 列後續、README 標未支援 → Task 7 ✓
- §9 驗收 → Task 6 Step 4 煙霧測試 + Task 7 Step 6 ✓

**Placeholder scan：** 無 TBD/TODO；每個程式步驟皆含完整程式碼。Antigravity「列後續」是設計決定的範圍排除，非佔位。

**Type/名稱一致性：** `apply_stop_hook`/`remove_stop_hook`、`codex_has_toplevel_notify`/`apply_codex_notify`/`remove_codex_notify`、`apply_ghostty_bell`/`remove_ghostty_bell`、`run_install`/`run_uninstall`、`MARKER`、`BELL_TTY`、`--notify` 於各 Task 與測試間一致；`run_install(claude_path, claude_cmd, codex_path, codex_args, ghostty_path)` 簽名於 Task 5 定義並於測試一致引用。
