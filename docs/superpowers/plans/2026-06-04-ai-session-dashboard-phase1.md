# 多 session 總覽儀表板 — 階段一 實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 `sessions/` 元件：AI CLI 的 hook 把每個 session 狀態寫成狀態檔，一個 curses TUI 寬版總覽「哪個在跑／等輸入／待命 + 各自路徑」。

**Architecture:** 觸發層 `track.sh`（純 sh，永不崩潰）被 Claude hooks / Codex notify 呼叫 → 寫 `~/.cache/ai-sessions/<id>.json`；顯示層 `dashboard.py`（stdlib curses）輪詢狀態目錄渲染。編排層 `sessions-setup` + `install.sh`/`uninstall.sh` 沿用 bell 的「備份／只增不刪／冪等／MARKER」合併策略。Codex 單槽 notify 衝突採合併派發器（選項 A）：一個 `sessions/notify.sh` 同時觸發 bell 與 sessions。

**Tech Stack:** Python 3（macOS 內建 `/usr/bin/python3`，純標準庫：`json`/`os`/`re`/`curses`/`unittest`）、POSIX `/bin/sh`。零第三方相依。

**設計來源：** `docs/superpowers/specs/2026-06-04-ai-session-dashboard-design.md`（階段一範圍）。

---

## 檔案結構

| 檔案 | 職責 |
|------|------|
| `sessions/sessions-track` | 純函式（事件→狀態、id 衍生、紀錄合併）+ 薄 I/O（讀寫/刪狀態檔）+ `main` 解析 Claude stdin / Codex payload |
| `sessions/track.sh` | `/bin/sh` 薄殼：呼叫 `sessions-track`，吞掉所有錯誤 `exit 0`（永不弄崩 host CLI） |
| `sessions/notify.sh` | Codex 合併派發器：同時呼叫 `../bell/notify.sh` 與 `track.sh`（選項 A） |
| `sessions/sessions-setup` | 純函式 apply/remove（Claude 多 hook、Codex dispatcher）+ 薄 I/O + 編排 + `main` |
| `sessions/install.sh` / `sessions/uninstall.sh` | bash 殼：檢查環境、呼叫 `sessions-setup`、印後續提示 |
| `sessions/dashboard.py` | 純函式（載入/排序/過期/格式化）+ curses 主迴圈 |
| `tests/test_sessions.py` | 全元件測試（importlib 依路徑載入連字號模組） |
| `sessions/README.md` / `README.en.md` | 雙語文件 |

**慣例對齊：** `MARKER = "# added by claude-context-statusline sessions/install.sh"`；
所有 hook 路徑用絕對路徑；honors `CLAUDE_CONFIG_DIR` / `CODEX_HOME` / `AI_SESSIONS_DIR`。

---

## Task 1: `sessions-track` 純函式（事件→狀態、id、紀錄合併）

**Files:**
- Create: `sessions/sessions-track`
- Test: `tests/test_sessions.py`

- [ ] **Step 1: 寫測試載入器 + 純函式測試**

建立 `tests/test_sessions.py`：

```python
#!/usr/bin/env python3
"""sessions 元件測試：track 事件映射 + setup 設定合併 + dashboard 純邏輯。純標準庫。"""
import importlib.machinery
import importlib.util
import io
import json
import os
import subprocess
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_DIR = os.path.join(_HERE, os.pardir, "sessions")


def _load(modname, filename):
    path = os.path.join(_DIR, filename)
    loader = importlib.machinery.SourceFileLoader(modname, path)
    spec = importlib.util.spec_from_file_location(modname, path, loader=loader)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


track = _load("sessions_track", "sessions-track")


class EventToStatusTest(unittest.TestCase):
    def test_known_events_map_to_status(self):
        self.assertEqual(track.event_to_status("UserPromptSubmit"), "running")
        self.assertEqual(track.event_to_status("Notification"), "waiting")
        self.assertEqual(track.event_to_status("Stop"), "idle")
        self.assertEqual(track.event_to_status("SessionStart"), "idle")

    def test_unknown_event_returns_none(self):
        self.assertIsNone(track.event_to_status("PreToolUse"))
        self.assertIsNone(track.event_to_status("SessionEnd"))

    def test_sanitize_id_replaces_unsafe_chars(self):
        self.assertEqual(track.sanitize_id("codex:/a/b c"), "codex__a_b_c")
        self.assertEqual(track.sanitize_id("abc-123_.OK"), "abc-123_.OK")
        self.assertEqual(track.sanitize_id(""), "unknown")

    def test_derive_codex_id_from_cwd(self):
        self.assertEqual(track.derive_codex_id("/Users/x/p"), "codex:/Users/x/p")

    def test_merge_record_preserves_started_at(self):
        old = {"started_at": 100, "status": "running", "session_id": "s"}
        new = track.merge_record(old, {"status": "idle"}, now=200)
        self.assertEqual(new["started_at"], 100)
        self.assertEqual(new["updated_at"], 200)
        self.assertEqual(new["status"], "idle")
        self.assertEqual(old["status"], "running")  # 不改輸入

    def test_merge_record_sets_started_when_new(self):
        new = track.merge_record(None, {"status": "running"}, now=50)
        self.assertEqual(new["started_at"], 50)
        self.assertEqual(new["updated_at"], 50)
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python3 -m unittest tests.test_sessions -v`
Expected: FAIL — `ModuleNotFoundError`/`FileNotFoundError`（`sessions-track` 不存在）

- [ ] **Step 3: 寫 `sessions/sessions-track` 純函式部分**

```python
#!/usr/bin/env python3
"""sessions-track — 把 AI CLI 的 hook 事件映射成 session 狀態，寫入狀態目錄。

純標準庫、零相依。純函式 + 薄 I/O。永不崩潰：__main__ 任何例外都靜默 exit 0。
honors AI_SESSIONS_DIR。
"""
import json
import os
import re
import sys
import time

_CLAUDE_EVENT_STATUS = {
    "SessionStart": "idle",
    "UserPromptSubmit": "running",
    "Notification": "waiting",
    "Stop": "idle",
}
_CLAUDE_DELETE_EVENTS = {"SessionEnd"}
CODEX_COMPLETE = "agent-turn-complete"


def default_dir(env):
    return env.get("AI_SESSIONS_DIR") or os.path.expanduser("~/.cache/ai-sessions")


def sanitize_id(session_id):
    """檔名安全化：非 [A-Za-z0-9._-] 換成底線；空字串回 'unknown'。"""
    return re.sub(r"[^A-Za-z0-9._-]", "_", session_id) or "unknown"


def derive_codex_id(cwd):
    """Codex 無穩定 session id，以 cwd 衍生（同專案目錄視為同一 session）。"""
    return "codex:" + cwd


def event_to_status(event):
    """Claude hook 事件 → 狀態字串；非追蹤事件回 None。"""
    return _CLAUDE_EVENT_STATUS.get(event)


def merge_record(old, new_fields, now):
    """合併狀態紀錄：保留既有 started_at、更新 updated_at 與 new_fields。
    old 為 dict 或 None；不改輸入，回傳新 dict。"""
    started = (old or {}).get("started_at", now)
    record = {**(old or {}), **new_fields}
    record["started_at"] = started
    record["updated_at"] = now
    return record
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python3 -m unittest tests.test_sessions -v`
Expected: PASS（6 個測試）

- [ ] **Step 5: Commit**

```bash
git add sessions/sessions-track tests/test_sessions.py
git commit -m "feat: [sessions] track 純函式（事件→狀態、id 衍生、紀錄合併）"
```

---

## Task 2: `sessions-track` 薄 I/O 與 main（解析 Claude stdin / Codex payload）

**Files:**
- Modify: `sessions/sessions-track`（append I/O + handlers + main）
- Test: `tests/test_sessions.py`（append）

- [ ] **Step 1: 寫失敗測試**

於 `tests/test_sessions.py` 末尾 append：

```python
class TrackMainTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.env = {"AI_SESSIONS_DIR": self.dir}

    def _read(self, session_id):
        path = os.path.join(self.dir, track.sanitize_id(session_id) + ".json")
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def test_claude_userpromptsubmit_writes_running(self):
        payload = json.dumps({"hook_event_name": "UserPromptSubmit",
                              "session_id": "abc", "cwd": "/p"})
        track.main(["claude"], stdin=io.StringIO(payload), env=self.env, now=10)
        rec = self._read("abc")
        self.assertEqual(rec["status"], "running")
        self.assertEqual(rec["cli"], "claude")
        self.assertEqual(rec["cwd"], "/p")
        self.assertEqual(rec["session_id"], "abc")

    def test_claude_notification_writes_waiting(self):
        payload = json.dumps({"hook_event_name": "Notification", "session_id": "abc"})
        track.main(["claude"], stdin=io.StringIO(payload), env=self.env, now=10)
        self.assertEqual(self._read("abc")["status"], "waiting")

    def test_claude_sessionend_deletes_file(self):
        track.main(["claude"], stdin=io.StringIO(json.dumps(
            {"hook_event_name": "Stop", "session_id": "abc", "cwd": "/p"})),
            env=self.env, now=10)
        track.main(["claude"], stdin=io.StringIO(json.dumps(
            {"hook_event_name": "SessionEnd", "session_id": "abc"})),
            env=self.env, now=20)
        self.assertFalse(os.path.exists(os.path.join(self.dir, "abc.json")))

    def test_claude_unknown_event_writes_nothing(self):
        track.main(["claude"], stdin=io.StringIO(json.dumps(
            {"hook_event_name": "PreToolUse", "session_id": "abc"})),
            env=self.env, now=10)
        self.assertEqual(os.listdir(self.dir), [])

    def test_codex_agent_turn_complete_writes_idle(self):
        payload = json.dumps({"type": "agent-turn-complete", "last-assistant-message": "hi"})
        cwd = self.dir  # 用暫存目錄當 cwd
        old = os.getcwd()
        os.chdir(cwd)
        try:
            track.main(["codex", payload], env=self.env, now=10)
        finally:
            os.chdir(old)
        rec = self._read(track.derive_codex_id(cwd))
        self.assertEqual(rec["status"], "idle")
        self.assertEqual(rec["cli"], "codex")

    def test_codex_other_event_writes_nothing(self):
        track.main(["codex", json.dumps({"type": "task-started"})], env=self.env, now=10)
        self.assertEqual(os.listdir(self.dir), [])

    def test_started_at_preserved_across_updates(self):
        for ev, t in [("UserPromptSubmit", 10), ("Stop", 30)]:
            track.main(["claude"], stdin=io.StringIO(json.dumps(
                {"hook_event_name": ev, "session_id": "abc", "cwd": "/p"})),
                env=self.env, now=t)
        rec = self._read("abc")
        self.assertEqual(rec["started_at"], 10)
        self.assertEqual(rec["updated_at"], 30)
        self.assertEqual(rec["status"], "idle")
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python3 -m unittest tests.test_sessions.TrackMainTest -v`
Expected: FAIL — `AttributeError: module has no attribute 'main'`

- [ ] **Step 3: append 薄 I/O 與 main 到 `sessions/sessions-track`**

```python
# ---- 薄 I/O ----------------------------------------------------------------
def _read_record(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def write_record(directory, session_id, fields, now):
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, sanitize_id(session_id) + ".json")
    record = merge_record(_read_record(path), {**fields, "session_id": session_id}, now)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False)
    os.replace(tmp, path)
    return record


def delete_record(directory, session_id):
    path = os.path.join(directory, sanitize_id(session_id) + ".json")
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


# ---- handlers + main -------------------------------------------------------
def _handle_claude(directory, stdin_text, now):
    data = json.loads(stdin_text)            # 壞 JSON → 例外 → __main__ 靜默吞
    event = data.get("hook_event_name", "")
    session_id = data.get("session_id") or ""
    if not session_id:
        return
    if event in _CLAUDE_DELETE_EVENTS:
        delete_record(directory, session_id)
        return
    status = event_to_status(event)
    if status is None:
        return
    fields = {"cli": "claude", "status": status, "cwd": data.get("cwd", "")}
    tp = data.get("transcript_path")
    if tp:
        fields["transcript_path"] = tp
    write_record(directory, session_id, fields, now)


def _handle_codex(directory, payload, cwd, now):
    try:
        data = json.loads(payload)
    except (ValueError, TypeError):
        return
    if data.get("type") != CODEX_COMPLETE:
        return
    write_record(directory, derive_codex_id(cwd),
                 {"cli": "codex", "status": "idle", "cwd": cwd}, now)


def main(argv=None, stdin=None, env=None, now=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    env = os.environ if env is None else env
    now = int(time.time()) if now is None else now
    directory = default_dir(env)
    src = argv[0] if argv else ""
    if src == "claude":
        text = (stdin if stdin is not None else sys.stdin).read()
        _handle_claude(directory, text, now)
    elif src == "codex":
        payload = argv[1] if len(argv) > 1 else ""
        _handle_codex(directory, payload, os.getcwd(), now)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)   # 永不崩潰：絕不讓狀態追蹤弄崩 host CLI
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python3 -m unittest tests.test_sessions -v`
Expected: PASS（全部）

- [ ] **Step 5: Commit**

```bash
git add sessions/sessions-track tests/test_sessions.py
git commit -m "feat: [sessions] track 薄 I/O 與 main（Claude stdin / Codex payload）"
```

---

## Task 3: `track.sh` 永不崩潰薄殼 + `notify.sh` 合併派發器

**Files:**
- Create: `sessions/track.sh`, `sessions/notify.sh`
- Test: `tests/test_sessions.py`（append）

- [ ] **Step 1: 寫失敗測試（subprocess 驗證永不崩潰）**

append：

```python
class TrackShTest(unittest.TestCase):
    TRACK = os.path.join(_DIR, "track.sh")

    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def _run(self, args, stdin=b""):
        return subprocess.run(["/bin/sh", self.TRACK, *args], input=stdin,
                              env={**os.environ, "AI_SESSIONS_DIR": self.dir},
                              capture_output=True, timeout=10)

    def test_claude_stop_writes_record_and_exits_zero(self):
        payload = json.dumps({"hook_event_name": "Stop", "session_id": "s1", "cwd": "/p"})
        proc = self._run(["claude"], stdin=payload.encode())
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(os.path.exists(os.path.join(self.dir, "s1.json")))

    def test_bad_stdin_does_not_error(self):
        proc = self._run(["claude"], stdin=b"NOT JSON")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stderr, b"")
        self.assertEqual(os.listdir(self.dir), [])

    def test_no_args_does_not_error(self):
        proc = self._run([])
        self.assertEqual(proc.returncode, 0, proc.stderr)
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python3 -m unittest tests.test_sessions.TrackShTest -v`
Expected: FAIL — 找不到 `track.sh`

- [ ] **Step 3: 建立 `sessions/track.sh`**

```sh
#!/bin/sh
# sessions/track.sh — 把 AI CLI hook 事件寫成 session 狀態（永不弄崩 host CLI）。
# 用法 / Usage:
#   track.sh claude          Claude hook：事件 JSON 由 stdin 提供
#   track.sh codex <payload> Codex notify：payload 為 JSON 字串
# 任何失敗（含 python3 缺席）都吞掉並 exit 0。
dir=$(cd "$(dirname "$0")" 2>/dev/null && pwd)
{ /usr/bin/python3 "$dir/sessions-track" "$@"; } 2>/dev/null || true
exit 0
```

- [ ] **Step 4: 建立 `sessions/notify.sh`（Codex 合併派發器，選項 A）**

```sh
#!/bin/sh
# sessions/notify.sh — Codex 完成事件的合併派發器（選項 A）。
# 同時觸發 bell（送 BEL 標記分頁）與 sessions（寫狀態檔）。永不崩潰。
# Codex notify 會把 payload 接在最後一個參數，故兩者都收到相同的 "$@"。
dir=$(cd "$(dirname "$0")" 2>/dev/null && pwd)
{ "$dir/../bell/notify.sh" "$@"; } 2>/dev/null || true
{ "$dir/track.sh" "$@"; } 2>/dev/null || true
exit 0
```

- [ ] **Step 5: 賦予執行權限、跑測試確認通過**

Run:
```bash
chmod +x sessions/track.sh sessions/notify.sh
python3 -m unittest tests.test_sessions.TrackShTest -v
```
Expected: PASS（3 個）

- [ ] **Step 6: Commit**

```bash
git add sessions/track.sh sessions/notify.sh tests/test_sessions.py
git commit -m "feat: [sessions] track.sh 永不崩潰薄殼與 notify.sh 合併派發器"
```

---

## Task 4: `sessions-setup` — Claude 多 hook apply/remove

**Files:**
- Create: `sessions/sessions-setup`
- Test: `tests/test_sessions.py`（append）

- [ ] **Step 1: 寫失敗測試**

append（先在檔頭附近的 `_load` 區塊後加一行載入，建議放在 `track = _load(...)` 之下）：

```python
setup = _load("sessions_setup", "sessions-setup")
```

再 append：

```python
class ClaudeHooksTest(unittest.TestCase):
    CMD = "/abs/sessions/track.sh claude"

    def test_apply_adds_all_four_events(self):
        out = setup.apply_claude_hooks({}, self.CMD)
        for ev in setup.CLAUDE_EVENTS:
            self.assertEqual(out["hooks"][ev],
                             [{"hooks": [{"type": "command", "command": self.CMD}]}])
        self.assertEqual(setup.CLAUDE_EVENTS,
                         ["SessionStart", "UserPromptSubmit", "Stop", "Notification"])

    def test_apply_is_idempotent(self):
        once = setup.apply_claude_hooks({}, self.CMD)
        twice = setup.apply_claude_hooks(once, self.CMD)
        self.assertEqual(once, twice)

    def test_apply_preserves_existing_unrelated_hook(self):
        data = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "other"}]}]}}
        out = setup.apply_claude_hooks(data, self.CMD)
        cmds = [h["command"] for m in out["hooks"]["Stop"] for h in m["hooks"]]
        self.assertIn("other", cmds)
        self.assertIn(self.CMD, cmds)

    def test_remove_drops_only_our_command(self):
        data = setup.apply_claude_hooks(
            {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "other"}]}]}},
            self.CMD)
        out, changed = setup.remove_claude_hooks(data, self.CMD)
        self.assertTrue(changed)
        cmds = [h["command"] for m in out["hooks"]["Stop"] for h in m["hooks"]]
        self.assertEqual(cmds, ["other"])
        self.assertNotIn("UserPromptSubmit", out["hooks"])

    def test_remove_when_absent_reports_false(self):
        _out, changed = setup.remove_claude_hooks({}, self.CMD)
        self.assertFalse(changed)
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python3 -m unittest tests.test_sessions.ClaudeHooksTest -v`
Expected: FAIL — 找不到 `sessions-setup`

- [ ] **Step 3: 建立 `sessions/sessions-setup`（先到 Claude hook 部分）**

```python
#!/usr/bin/env python3
"""sessions-setup — 把多 session 儀表板設定併入/移出 Claude / Codex 設定。

純標準庫、零相依。純函式（apply_/remove_，不改輸入、回傳新值）+ 薄 I/O。
honors CLAUDE_CONFIG_DIR / CODEX_HOME。
"""
import json
import os
import re
import shutil
import sys
import time

MARKER = "# added by claude-context-statusline sessions/install.sh"

# Claude：儀表板要追蹤的四個事件（同一個 command 掛在四個事件下）。
CLAUDE_EVENTS = ["SessionStart", "UserPromptSubmit", "Stop", "Notification"]


# ---- Claude Code: settings.json 的多 hook --------------------------------
def _event_has_command(matchers, command):
    return any(h.get("command") == command
               for m in matchers for h in m.get("hooks", []))


def apply_hook(data, event, command):
    """回傳加入 (event, command) hook 的新 dict（以 command 比對，冪等；不改輸入）。"""
    hooks = dict(data.get("hooks", {}))
    arr = list(hooks.get(event, []))
    if _event_has_command(arr, command):
        return data
    entry = {"hooks": [{"type": "command", "command": command}]}
    hooks = {**hooks, event: arr + [entry]}
    return {**data, "hooks": hooks}


def remove_hook(data, event, command):
    """回傳 (新 dict, 是否移除)。只移除引用到 command 的 matcher。"""
    hooks = dict(data.get("hooks", {}))
    arr = hooks.get(event)
    if not arr:
        return data, False
    kept = [m for m in arr
            if not any(h.get("command") == command for h in m.get("hooks", []))]
    if len(kept) == len(arr):
        return data, False
    if kept:
        hooks = {**hooks, event: kept}
    else:
        hooks = {k: v for k, v in hooks.items() if k != event}
    return {**data, "hooks": hooks}, True


def apply_claude_hooks(data, command):
    """把 command 掛到 CLAUDE_EVENTS 全部事件下（冪等）。"""
    for ev in CLAUDE_EVENTS:
        data = apply_hook(data, ev, command)
    return data


def remove_claude_hooks(data, command):
    """從 CLAUDE_EVENTS 全部事件移除 command；回傳 (新 dict, 是否有任一移除)。"""
    changed = False
    for ev in CLAUDE_EVENTS:
        data, c = remove_hook(data, ev, command)
        changed = changed or c
    return data, changed
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python3 -m unittest tests.test_sessions.ClaudeHooksTest -v`
Expected: PASS（5 個）

- [ ] **Step 5: Commit**

```bash
git add sessions/sessions-setup tests/test_sessions.py
git commit -m "feat: [sessions] setup — Claude 多 hook apply/remove"
```

---

## Task 5: `sessions-setup` — Codex 合併派發器 apply/remove

**Files:**
- Modify: `sessions/sessions-setup`（append Codex 部分）
- Test: `tests/test_sessions.py`（append）

- [ ] **Step 1: 寫失敗測試**

append：

```python
class CodexDispatchTest(unittest.TestCase):
    ARGS = ["/abs/sessions/notify.sh", "codex"]
    NOTIFY = 'notify = ["/abs/sessions/notify.sh", "codex"]'

    def test_no_notify_prepends_block(self):
        new, changed = setup.apply_codex_dispatch("model = \"x\"\n", self.ARGS)
        self.assertTrue(changed)
        self.assertTrue(new.startswith(setup.MARKER))
        self.assertIn(self.NOTIFY, new)
        self.assertIn('model = "x"', new)

    def test_upgrades_bell_notify(self):
        text = ('# added by claude-context-statusline bell/install.sh\n'
                'notify = ["/abs/bell/notify.sh", "codex"]\n\nmodel = "x"\n')
        new, changed = setup.apply_codex_dispatch(text, self.ARGS)
        self.assertTrue(changed)
        self.assertIn("sessions/notify.sh", new)
        self.assertNotIn("bell/notify.sh", new)
        self.assertIn(setup.MARKER, new)

    def test_idempotent_when_already_ours(self):
        text = f"{setup.MARKER}\n{self.NOTIFY}\n"
        new, changed = setup.apply_codex_dispatch(text, self.ARGS)
        self.assertFalse(changed)

    def test_foreign_notify_left_untouched(self):
        text = 'notify = ["/my/own/script"]\n'
        new, changed = setup.apply_codex_dispatch(text, self.ARGS)
        self.assertFalse(changed)
        self.assertEqual(new, text)

    def test_remove_our_dispatch(self):
        text = f"{setup.MARKER}\n{self.NOTIFY}\n\nmodel = \"x\"\n"
        new, changed = setup.remove_codex_dispatch(text)
        self.assertTrue(changed)
        self.assertNotIn("sessions/notify.sh", new)
        self.assertNotIn(setup.MARKER, new)
        self.assertIn('model = "x"', new)

    def test_remove_when_absent(self):
        new, changed = setup.remove_codex_dispatch('model = "x"\n')
        self.assertFalse(changed)
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python3 -m unittest tests.test_sessions.CodexDispatchTest -v`
Expected: FAIL — `apply_codex_dispatch` 不存在

- [ ] **Step 3: append Codex 部分到 `sessions/sessions-setup`**

```python
# ---- Codex: config.toml 的 notify 合併派發器（文字行掃描，不解析 TOML）------
_NOTIFY_RE = re.compile(r"^\s*notify\s*=")
_BELL_NOTIFY_SUBSTR = "bell/notify.sh"
_OUR_NOTIFY_SUBSTR = "sessions/notify.sh"
_MARKER_PREFIX = "# added by claude-context-statusline"


def _toplevel_notify_index(lines):
    """頂層 notify 行的索引（第一個 [table] 之前）；無則 -1。"""
    for i, line in enumerate(lines):
        s = line.lstrip()
        if s.startswith("["):
            return -1
        if _NOTIFY_RE.match(line):
            return i
    return -1


def apply_codex_dispatch(text, dispatch_args):
    """回傳 (新 text, 是否變更)。
    無 notify → 檔首 prepend dispatcher；bell 管理的 notify → 升級為 dispatcher；
    已是我們的 → 不動；外來 notify → 不動（呼叫端負責警告）。"""
    new_notify = "notify = [" + ", ".join(json.dumps(a) for a in dispatch_args) + "]"
    lines = text.splitlines()
    idx = _toplevel_notify_index(lines)
    if idx < 0:
        block = f"{MARKER}\n{new_notify}\n"
        if text:
            block += "\n"
        return block + text, True
    line = lines[idx]
    if _OUR_NOTIFY_SUBSTR in line:
        return text, False
    if _BELL_NOTIFY_SUBSTR in line:
        new_lines = list(lines)
        new_lines[idx] = new_notify
        if idx > 0 and new_lines[idx - 1].strip().startswith(_MARKER_PREFIX):
            new_lines[idx - 1] = MARKER
        else:
            new_lines.insert(idx, MARKER)
        new = "\n".join(new_lines)
        if text.endswith("\n") and new and not new.endswith("\n"):
            new += "\n"
        return new, True
    return text, False


def remove_codex_dispatch(text):
    """移除我們的 dispatcher 區段（MARKER 行 + 其後 notify 行 + 一個空行）。"""
    lines = text.splitlines()
    out, removed, i = [], False, 0
    while i < len(lines):
        if (lines[i].strip() == MARKER and i + 1 < len(lines)
                and _OUR_NOTIFY_SUBSTR in lines[i + 1]):
            removed = True
            i += 2
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

Run: `python3 -m unittest tests.test_sessions.CodexDispatchTest -v`
Expected: PASS（6 個）

- [ ] **Step 5: Commit**

```bash
git add sessions/sessions-setup tests/test_sessions.py
git commit -m "feat: [sessions] setup — Codex 合併派發器 apply/remove"
```

---

## Task 6: `sessions-setup` 薄 I/O、編排、main + 安裝殼層

**Files:**
- Modify: `sessions/sessions-setup`（append I/O + orchestration + main）
- Create: `sessions/install.sh`, `sessions/uninstall.sh`
- Test: `tests/test_sessions.py`（append）

- [ ] **Step 1: 寫失敗測試（端到端：run_install/run_uninstall 在暫存目錄）**

append：

```python
class OrchestrationTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.claude = os.path.join(self.root, "settings.json")
        self.codex = os.path.join(self.root, "config.toml")
        self.cmd = "/abs/sessions/track.sh claude"
        self.codex_args = ["/abs/sessions/notify.sh", "codex"]

    def test_install_then_uninstall_round_trip(self):
        r1 = setup.run_install(self.claude, self.cmd, self.codex, self.codex_args)
        self.assertTrue(all(x["status"] in ("ok", "skipped") for x in r1), r1)
        with open(self.claude, encoding="utf-8") as f:
            data = json.load(f)
        for ev in setup.CLAUDE_EVENTS:
            self.assertIn(ev, data["hooks"])
        with open(self.codex, encoding="utf-8") as f:
            self.assertIn("sessions/notify.sh", f.read())

        setup.run_uninstall(self.claude, self.cmd, self.codex)
        with open(self.claude, encoding="utf-8") as f:
            self.assertEqual(json.load(f).get("hooks", {}), {})
        with open(self.codex, encoding="utf-8") as f:
            self.assertNotIn("sessions/notify.sh", f.read())

    def test_bad_claude_json_aborts_that_target_only(self):
        with open(self.claude, "w") as f:
            f.write("{ not json")
        results = setup.run_install(self.claude, self.cmd, self.codex, self.codex_args)
        statuses = {r["target"]: r["status"] for r in results}
        self.assertEqual(statuses[self.claude], "error")
        self.assertEqual(statuses[self.codex], "ok")  # Codex 不受 Claude 失敗影響
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python3 -m unittest tests.test_sessions.OrchestrationTest -v`
Expected: FAIL — `run_install` 不存在

- [ ] **Step 3: append 薄 I/O + 編排 + main 到 `sessions/sessions-setup`**

```python
# ---- 薄 I/O（與 bell-setup 同形，刻意各自獨立、不跨元件 import）-------------
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
    try:
        text = _read_text(path)
    except Exception as exc:
        return _result(path, "error", f"讀取失敗：{exc}")
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
    try:
        _backup(path)
        _write_text(path, json.dumps(new, indent=2, ensure_ascii=False) + "\n")
    except Exception as exc:
        return _result(path, "error", f"寫入失敗：{exc}")
    return _result(path, "ok")


def _apply_text(path, apply_fn, mode=None):
    try:
        text = _read_text(path)
    except Exception as exc:
        return _result(path, "error", f"讀取失敗：{exc}")
    new, changed = apply_fn(text)
    if not changed:
        return _result(path, "skipped", "已安裝或已有手動設定")
    keep_mode = mode
    if keep_mode is None and os.path.exists(path):
        keep_mode = os.stat(path).st_mode & 0o777
    try:
        _backup(path)
        _write_text(path, new, keep_mode)
    except Exception as exc:
        return _result(path, "error", f"寫入失敗：{exc}")
    return _result(path, "ok")


# ---- orchestration ---------------------------------------------------------
def run_install(claude_path, claude_cmd, codex_path, codex_args):
    return [
        _apply_json(claude_path, lambda d: apply_claude_hooks(d, claude_cmd)),
        _apply_text(codex_path, lambda t: apply_codex_dispatch(t, codex_args), mode=0o600),
    ]


def run_uninstall(claude_path, claude_cmd, codex_path):
    return [
        _apply_json(claude_path, lambda d: remove_claude_hooks(d, claude_cmd)[0]),
        _apply_text(codex_path, remove_codex_dispatch, mode=0o600),
    ]


# ---- 路徑解析 + main --------------------------------------------------------
def _paths(env):
    claude = env.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")
    codex = env.get("CODEX_HOME") or os.path.expanduser("~/.codex")
    return (os.path.join(claude, "settings.json"),
            os.path.join(codex, "config.toml"))


def _arg_value(argv, flag):
    if flag in argv:
        i = argv.index(flag)
        if i + 1 < len(argv):
            return argv[i + 1]
    return None


def main(argv=None, env=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    env = os.environ if env is None else env
    if not argv or argv[0] not in ("install", "uninstall"):
        print("usage: sessions-setup install|uninstall --track <abs> --dispatch <abs>",
              file=sys.stderr)
        return 2
    action = argv[0]
    track = _arg_value(argv, "--track")
    dispatch = _arg_value(argv, "--dispatch")
    if not track or not dispatch:
        print("!! --track <abs track.sh> 與 --dispatch <abs notify.sh> 為必填",
              file=sys.stderr)
        return 2
    claude_path, codex_path = _paths(env)
    claude_cmd = f"{track} claude"
    codex_args = [dispatch, "codex"]
    if action == "install":
        results = run_install(claude_path, claude_cmd, codex_path, codex_args)
    else:
        results = run_uninstall(claude_path, claude_cmd, codex_path)
    for r in results:
        mark = {"ok": "✓", "skipped": "•", "error": "!!"}[r["status"]]
        print(f"   {mark} {r['target']} {r['detail']}".rstrip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python3 -m unittest tests.test_sessions.OrchestrationTest -v`
Expected: PASS（2 個）

- [ ] **Step 5: 建立 `sessions/install.sh`**

```bash
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
chmod +x "$TRACK" "$DISPATCH" "$SETUP" "$SCRIPT_DIR/sessions-track" "$SCRIPT_DIR/dashboard.py"

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
```

- [ ] **Step 6: 建立 `sessions/uninstall.sh`**

```bash
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
```

- [ ] **Step 7: 語法檢查 + 一次安裝煙霧測試（暫存設定目錄）**

Run:
```bash
chmod +x sessions/install.sh sessions/uninstall.sh
bash -n sessions/install.sh sessions/uninstall.sh
tmp=$(mktemp -d)
CLAUDE_CONFIG_DIR="$tmp/claude" CODEX_HOME="$tmp/codex" ./sessions/install.sh
cat "$tmp/claude/settings.json"
CLAUDE_CONFIG_DIR="$tmp/claude" CODEX_HOME="$tmp/codex" ./sessions/uninstall.sh
```
Expected: 安裝印出 `✓`，settings.json 含四個事件；移除後還原。

- [ ] **Step 8: Commit**

```bash
git add sessions/sessions-setup sessions/install.sh sessions/uninstall.sh tests/test_sessions.py
git commit -m "feat: [sessions] setup 編排與 main + install/uninstall 殼層"
```

---

## Task 7: `dashboard.py` 純函式（載入/排序/過期/格式化）

**Files:**
- Create: `sessions/dashboard.py`
- Test: `tests/test_sessions.py`（append）

- [ ] **Step 1: 寫失敗測試**

append（在 `_load` 區塊附近加載入）：

```python
dashboard = _load("sessions_dashboard", "dashboard.py")
```

再 append：

```python
class DashboardLogicTest(unittest.TestCase):
    def test_sort_waiting_first_then_running_then_idle(self):
        recs = [{"status": "idle", "updated_at": 5},
                {"status": "waiting", "updated_at": 1},
                {"status": "running", "updated_at": 9}]
        ordered = sorted(recs, key=dashboard.sort_key)
        self.assertEqual([r["status"] for r in ordered],
                         ["waiting", "running", "idle"])

    def test_is_stale_threshold(self):
        self.assertTrue(dashboard.is_stale({"updated_at": 0}, now=2000, threshold=1800))
        self.assertFalse(dashboard.is_stale({"updated_at": 1500}, now=2000, threshold=1800))

    def test_humanize(self):
        self.assertEqual(dashboard.humanize(45), "45s")
        self.assertEqual(dashboard.humanize(120), "2m")
        self.assertEqual(dashboard.humanize(7200), "2h")

    def test_format_row_contains_basename_and_status(self):
        row = dashboard.format_row(
            {"status": "waiting", "cli": "claude", "cwd": "/Users/x/proj", "updated_at": 90},
            now=100)
        self.assertIn("waiting", row)
        self.assertIn("proj", row)
        self.assertIn("claude", row)

    def test_load_records_skips_bad_files(self):
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "good.json"), "w") as f:
            json.dump({"status": "idle", "cwd": "/p", "updated_at": 1}, f)
        with open(os.path.join(d, "bad.json"), "w") as f:
            f.write("NOT JSON")
        with open(os.path.join(d, "ignore.txt"), "w") as f:
            f.write("x")
        recs = dashboard.load_records(d)
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["cwd"], "/p")

    def test_load_records_missing_dir_returns_empty(self):
        self.assertEqual(dashboard.load_records("/no/such/dir"), [])
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python3 -m unittest tests.test_sessions.DashboardLogicTest -v`
Expected: FAIL — 找不到 `dashboard.py`

- [ ] **Step 3: 建立 `sessions/dashboard.py` 純函式部分**

```python
#!/usr/bin/env python3
"""dashboard.py — 多 session 總覽 TUI（stdlib curses）。

純函式（載入/排序/過期/格式化）可單測；curses 主迴圈為薄殼。永不崩潰。
honors AI_SESSIONS_DIR。階段一唯讀；偵測 $TMUX 的階段二功能為後續。
"""
import curses
import json
import os
import subprocess
import sys
import time

REFRESH_SEC = 1.0
STALE_SEC = 1800
STATUS_ORDER = {"waiting": 0, "running": 1, "idle": 2}
# (emoji, 形狀角標)：色盲友善雙重編碼，對齊 repo 慣例。
STATUS_GLYPH = {"waiting": ("⏳", "!"), "running": ("▶", "*"), "idle": ("✓", " ")}


def default_dir(env=None):
    env = os.environ if env is None else env
    return env.get("AI_SESSIONS_DIR") or os.path.expanduser("~/.cache/ai-sessions")


def load_records(directory):
    out = []
    try:
        names = os.listdir(directory)
    except OSError:
        return out
    for name in names:
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(directory, name), encoding="utf-8") as f:
                rec = json.load(f)
        except Exception:
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out


def is_stale(record, now, threshold=STALE_SEC):
    return (now - record.get("updated_at", 0)) > threshold


def sort_key(record):
    return (STATUS_ORDER.get(record.get("status"), 9), -record.get("updated_at", 0))


def humanize(seconds):
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    return f"{seconds // 3600}h"


def format_row(record, now):
    status = record.get("status", "idle")
    glyph, shape = STATUS_GLYPH.get(status, ("?", "?"))
    cwd = record.get("cwd", "")
    base = os.path.basename(cwd.rstrip("/")) or cwd or "?"
    age = humanize(now - record.get("updated_at", now))
    cli = record.get("cli", "?")
    stale = " (stale)" if is_stale(record, now) else ""
    return f"{glyph}{shape} {status:<8} {cli:<7} {base:<24} {age:>4}{stale}  {cwd}"
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python3 -m unittest tests.test_sessions.DashboardLogicTest -v`
Expected: PASS（6 個）

- [ ] **Step 5: Commit**

```bash
git add sessions/dashboard.py tests/test_sessions.py
git commit -m "feat: [sessions] dashboard 純函式（載入/排序/過期/格式化）"
```

---

## Task 8: `dashboard.py` curses 主迴圈（薄殼，手動煙霧測試）

**Files:**
- Modify: `sessions/dashboard.py`（append curses 主迴圈 + `__main__`）

- [ ] **Step 1: append curses 主迴圈到 `sessions/dashboard.py`**

```python
# ---- curses 薄殼（不單測；永不崩潰）---------------------------------------
HEADER = "  狀態      CLI     目錄                      時間  路徑"
HELP = "  j/k 移動 · r 刷新 · Enter 複製路徑 · q 離開"


def _copy_path(path):
    try:
        subprocess.run(["pbcopy"], input=path.encode(), timeout=2)
    except Exception:
        pass


def _draw(stdscr, records, selected, now):
    stdscr.erase()
    height, width = stdscr.getmaxyx()
    title = f" AI session 總覽（{len(records)}）"
    stdscr.addnstr(0, 0, title.ljust(width - 1), width - 1, curses.A_BOLD)
    stdscr.addnstr(1, 0, HEADER, width - 1, curses.A_DIM)
    for i, rec in enumerate(records):
        row = 2 + i
        if row >= height - 1:
            break
        attr = curses.A_REVERSE if i == selected else curses.A_NORMAL
        stdscr.addnstr(row, 0, format_row(rec, now).ljust(width - 1), width - 1, attr)
    if not records:
        stdscr.addnstr(3, 2, "（目前沒有 session；開個 Claude Code 跑跑看）", width - 3)
    stdscr.addnstr(height - 1, 0, HELP[:width - 1], width - 1, curses.A_DIM)
    stdscr.refresh()


def _loop(stdscr, directory):
    curses.curs_set(0)
    stdscr.nodelay(True)
    selected = 0
    last_load = 0.0
    records = []
    while True:
        now = time.time()
        if now - last_load >= REFRESH_SEC:
            records = sorted(load_records(directory), key=sort_key)
            last_load = now
            selected = max(0, min(selected, len(records) - 1))
        _draw(stdscr, records, selected, int(now))
        try:
            ch = stdscr.getch()
        except curses.error:
            ch = -1
        if ch in (ord("q"), 27):
            return
        if ch in (ord("j"), curses.KEY_DOWN):
            selected = min(selected + 1, max(0, len(records) - 1))
        elif ch in (ord("k"), curses.KEY_UP):
            selected = max(selected - 1, 0)
        elif ch == ord("r"):
            last_load = 0.0
        elif ch in (curses.KEY_ENTER, 10, 13) and records:
            _copy_path(records[selected].get("cwd", ""))
        else:
            time.sleep(0.05)


def main(argv=None, env=None):
    env = os.environ if env is None else env
    directory = default_dir(env)
    try:
        curses.wrapper(_loop, directory)
    except KeyboardInterrupt:
        pass
    except Exception:
        return 0   # 永不崩潰：離開時 curses.wrapper 已還原終端機
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: 確認純函式測試仍綠（import 不應因新增 curses 殼而壞）**

Run: `python3 -m unittest tests.test_sessions -v`
Expected: PASS（全部）

- [ ] **Step 3: 手動煙霧測試**

Run:
```bash
tmp=$(mktemp -d)
printf '{"session_id":"a","cli":"claude","status":"waiting","cwd":"/Users/x/alpha","started_at":1,"updated_at":%s}' "$(date +%s)" > "$tmp/a.json"
printf '{"session_id":"b","cli":"codex","status":"idle","cwd":"/Users/x/beta","started_at":1,"updated_at":1}' > "$tmp/b.json"
AI_SESSIONS_DIR="$tmp" ./sessions/dashboard.py
```
Expected: 開出 TUI，`alpha`（waiting）置頂、`beta`（idle, stale）在下；`j/k` 可移動、`q` 離開、終端機正常還原。

- [ ] **Step 4: Commit**

```bash
git add sessions/dashboard.py
git commit -m "feat: [sessions] dashboard curses 主迴圈（唯讀總覽）"
```

---

## Task 9: 文件、頂層整合與全測試

**Files:**
- Create: `sessions/README.md`, `sessions/README.en.md`
- Modify: `README.md`, `README.en.md`（頂層總覽加第五元件）、`CHANGELOG.md`、`CLAUDE.md`

- [ ] **Step 1: 寫 `sessions/README.md`（繁中）**

內容須涵蓋：定位（多 session 總覽，與其他元件差異）、架構圖（hook→狀態檔→TUI）、
需求（macOS `/usr/bin/python3`；Claude/Codex）、安裝（`./sessions/install.sh`，含
`CLAUDE_CONFIG_DIR`/`CODEX_HOME`/`AI_SESSIONS_DIR` 覆寫）、狀態模型表（事件→狀態）、
**Codex 狀態粒度限制**、**永不崩潰原則**、TUI 鍵位、**Codex notify 合併派發器（選項 A）**
與「uninstall 會整個移除 Codex notify、需重跑 bell/install.sh 還原」、測試指令、
**階段二（tmux 切換/預覽）為後續** 的說明。

```bash
# 內容定稿後：
$EDITOR sessions/README.md
```

- [ ] **Step 2: 寫 `sessions/README.en.md`（英文對照，內容同步）**

- [ ] **Step 3: 更新頂層 `README.md` / `README.en.md`**

在四工具總覽加入第五個元件 `sessions/`（一段描述 + 連到 `sessions/README.md`），
並在「各元件監看的資料不同」對照段落補一句：sessions 看的是「**跨 session 的即時狀態總覽**」。

- [ ] **Step 4: 更新 `CHANGELOG.md` 與 `CLAUDE.md`**

`CHANGELOG.md` 新增條目（新增第五元件 sessions：多 session 總覽儀表板、階段一）。
`CLAUDE.md` 在「專案概述」列出第五元件、在「開發指令」加：

```bash
# sessions 多 session 總覽
./sessions/install.sh
AI_SESSIONS_DIR=$(mktemp -d) ./sessions/dashboard.py
python3 -m unittest tests.test_sessions -v
```

並把 `bash -n` / `shellcheck` 的檔案清單補上 `sessions/install.sh sessions/uninstall.sh sessions/track.sh sessions/notify.sh`。

- [ ] **Step 5: 全測試 + shell 檢查**

Run:
```bash
python3 -m unittest discover -s tests -v
bash -n sessions/install.sh sessions/uninstall.sh sessions/track.sh sessions/notify.sh
shellcheck sessions/install.sh sessions/uninstall.sh sessions/track.sh sessions/notify.sh
```
Expected: 全測試 PASS；`bash -n` 無輸出；shellcheck 無警告（或僅可接受的 info）。

- [ ] **Step 6: Commit**

```bash
git add sessions/README.md sessions/README.en.md README.md README.en.md CHANGELOG.md CLAUDE.md
git commit -m "docs: [sessions] 雙語文件、頂層總覽、CHANGELOG 與 CLAUDE.md 更新"
```

---

## 自我檢視（已完成）

- **Spec 覆蓋**：狀態模型（Task 1-2）、track 永不崩潰（Task 3）、狀態檔規格（Task 2）、
  Codex 合併派發器選項 A（Task 3, 5）、安裝編排沿用 bell 策略（Task 4-6）、
  curses 寬版 TUI 與排序/色盲雙重編碼（Task 7-8）、測試策略（各 Task）、
  雙語文件與限制聲明（Task 9）。階段二明確劃為後續，未排入本計畫。✓
- **Placeholder 掃描**：無 TBD/TODO；所有程式步驟均含完整可複製的程式碼。
  Task 9 文件步驟以「須涵蓋的要點清單」描述而非整篇貼出，因 README 為散文；要點具體可執行。✓
- **型別/命名一致**：`track` 模組（`event_to_status`/`sanitize_id`/`derive_codex_id`/
  `merge_record`/`write_record`/`delete_record`/`default_dir`/`main`）、`setup` 模組
  （`apply_claude_hooks`/`remove_claude_hooks`/`apply_codex_dispatch`/`remove_codex_dispatch`/
  `run_install`/`run_uninstall`/`MARKER`/`CLAUDE_EVENTS`）、`dashboard`（`load_records`/
  `is_stale`/`sort_key`/`humanize`/`format_row`/`default_dir`）跨 Task 引用一致。✓
```
