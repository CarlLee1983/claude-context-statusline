# 多 session 儀表板階段三（納入 Antigravity）實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 Antigravity（`agy`）納入 sessions 流程：agy 的 `PostToolUse`/`Stop` hook → `track.sh antigravity <event>` → 寫狀態檔（`running`/`idle`）→ 既有儀表板顯示。

**Architecture:** 與 Claude/Codex 對稱、純加性。`sessions-track` 新增 antigravity 純函式（事件映射、payload 解析）+ handler + main 分派；`sessions-setup` 安裝一個專屬 agy plugin（`<gemini_config>/plugins/ai-sessions/` 的 plugin.json + hooks.json）。狀態檔格式、`dashboard.py`、階段二 `ghostty.py` 都不改（Antigravity 也跑 Ghostty，`pick_terminal` 靠 cwd 自動適用）。

**Tech Stack:** Python 3 標準庫、`/bin/sh`、agy（gemini-cli 系）plugin hooks（`PostToolUse`/`Stop`，payload 帶 `conversationId`/`workspacePaths`）。

**設計來源：** `docs/superpowers/specs/2026-06-04-ai-session-dashboard-phase3-design.md`

---

## 檔案結構

- **修改** `sessions/sessions-track`：antigravity 事件映射 + payload 解析（純函式）、handler、main 分派。
- **修改** `sessions/sessions-setup`：antigravity plugin 檔內容（純函式）、apply/remove I/O、路徑解析、run_install/run_uninstall 接線、main。
- **修改** `tests/test_sessions.py`：antigravity track + setup 測試。
- **不改** `sessions/track.sh`（已轉發 `$@` 與 stdin）、`sessions/dashboard.py`、`sessions/ghostty.py`、`sessions/install.sh`/`uninstall.sh`（sessions-setup 由 env 解析 gemini 目錄）。
- **修改** 文件：`sessions/README.md`/`.en.md`、`README.md`/`.en.md`、`CHANGELOG.md`、`CLAUDE.md`。

---

## Task 1: Gating 驗證（agy 是否自動載入新 plugin + Stop payload）

**這是純驗證任務（不寫程式碼），但其結論決定 Task 4 是否需加 manifest 註冊。** 必須最先做。

- [ ] **Step 1: 建立暫時的 ai-sessions plugin 並掛 logging hook**

```bash
GP=~/.gemini/config/plugins/ai-sessions
mkdir -p "$GP"
printf '{"name": "ai-sessions"}\n' > "$GP/plugin.json"
cat > /tmp/agy-gate.sh <<'EOF'
#!/bin/sh
{ printf '\n===== EVENT=%s =====\n' "$1"; cat; } >> /tmp/agy-gate.log 2>&1
exit 0
EOF
chmod +x /tmp/agy-gate.sh
python3 - <<'PY'
import json,os
gp=os.path.expanduser("~/.gemini/config/plugins/ai-sessions/hooks.json")
h={"hooks":{e:[{"hooks":[{"type":"command","command":"/tmp/agy-gate.sh "+e,"async":False}]}] for e in ["PostToolUse","Stop"]}}
json.dump(h,open(gp,"w"),indent=2)
print("wrote",gp)
PY
: > /tmp/agy-gate.log
```

- [ ] **Step 2: 跑一次 agy，觸發事件**

```bash
agy -p "Run the shell command 'echo gate-test' once, then reply with just: done" --print-timeout 2m; echo "exit=$?"
```
（若 `agy -p` 卡住超過 ~1 分鐘，另開終端 `pkill -9 -f 'agy -p'`，仍可看 log 與 cli.log。）

- [ ] **Step 3: 判讀三件事並記錄結論**

```bash
echo "=== A) agy 是否載入我們的 plugin hooks ==="
grep -h "plugins/ai-sessions/hooks.json" ~/.gemini/antigravity-cli/log/cli-*.log | tail -3
echo "=== B) 實際 fire 的事件 ==="
grep -hoE 'jsonhook__hooks_(PostToolUse|Stop)' ~/.gemini/antigravity-cli/log/cli-*.log | tail -5
echo "=== C) Stop payload 欄位（是否帶 conversationId / workspacePaths）==="
awk '/EVENT=Stop/{f=1} f' /tmp/agy-gate.log | head -20
```

記錄：
- **A 有出現** `Loaded hooks.json from .../plugins/ai-sessions/hooks.json` → agy **自動載入**新 plugin → Task 4 用「建目錄 + 兩檔」即可。
- **A 沒出現** → agy 需要 manifest 註冊或啟用 → Task 4 採 **contingency**（見 Task 4 末段，加 import_manifest.json entry）。
- **C**：確認 Stop payload 是否含 `conversationId`。若**有**，Task 2 的 `antigravity_fields` 維持以 `conversationId` 為主；若**無**，把 Task 2 的解析改為「一律以 cwd 衍生 id」（Task 2 已含此分支說明）。

- [ ] **Step 4: 還原環境（重要）**

```bash
rm -rf ~/.gemini/config/plugins/ai-sessions
rm -f /tmp/agy-gate.sh /tmp/agy-gate.log
echo "=== 確認已移除 ==="; ls ~/.gemini/config/plugins/ | grep ai-sessions || echo "已移除 ai-sessions"
```

- [ ] **Step 5: 把結論寫進 commit（記錄用，無程式變更）**

```bash
git commit --allow-empty -m "chore: [sessions] 階段三 gating 驗證結論（agy plugin 載入 / Stop payload）"
```
在 commit message body 記下 A/B/C 三點實測結果，供 Task 4 參考。

---

## Task 2: `sessions-track` antigravity 純函式（事件映射 + payload 解析）

**Files:**
- Modify: `sessions/sessions-track`
- Test: `tests/test_sessions.py`

- [ ] **Step 1: 寫失敗測試**

在 `tests/test_sessions.py` 結尾（最後一個 class 之後）新增：

```python
class AntigravityTrackTest(unittest.TestCase):
    def test_event_to_status(self):
        self.assertEqual(track.antigravity_event_to_status("PostToolUse"), "running")
        self.assertEqual(track.antigravity_event_to_status("Stop"), "idle")
        self.assertIsNone(track.antigravity_event_to_status("PreToolUse"))
        self.assertIsNone(track.antigravity_event_to_status(""))

    def test_derive_id_from_cwd(self):
        self.assertEqual(track.derive_antigravity_id("/Users/x/p"), "antigravity:/Users/x/p")

    def test_fields_prefers_conversation_id(self):
        data = {"conversationId": "conv-1",
                "workspacePaths": ["/Users/x/p"],
                "transcriptPath": "/t.jsonl"}
        sid, cwd, tp = track.antigravity_fields(data)
        self.assertEqual(sid, "conv-1")
        self.assertEqual(cwd, "/Users/x/p")
        self.assertEqual(tp, "/t.jsonl")

    def test_fields_falls_back_to_cwd_derived_id(self):
        data = {"workspacePaths": ["/Users/x/p"]}
        sid, cwd, tp = track.antigravity_fields(data)
        self.assertEqual(sid, "antigravity:/Users/x/p")
        self.assertEqual(cwd, "/Users/x/p")
        self.assertIsNone(tp)

    def test_fields_empty_workspacepaths(self):
        sid, cwd, tp = track.antigravity_fields({"conversationId": "c"})
        self.assertEqual(sid, "c")
        self.assertEqual(cwd, "")
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python3 -m unittest tests.test_sessions -v 2>&1 | tail -15`
Expected: FAIL — `AttributeError: module ... has no attribute 'antigravity_event_to_status'`。

- [ ] **Step 3: 在 `sessions/sessions-track` 新增純函式**

在 `CODEX_COMPLETE = "agent-turn-complete"`（第 20 行）之後新增：

```python
_ANTIGRAVITY_EVENT_STATUS = {
    "PostToolUse": "running",
    "Stop": "idle",
}
```

在 `derive_codex_id` 之後新增：

```python
def derive_antigravity_id(cwd):
    """Antigravity 無 conversationId 時以 cwd 衍生（同專案目錄視為同一 session）。"""
    return "antigravity:" + cwd


def antigravity_event_to_status(event):
    """Antigravity (agy) hook 事件 → 狀態字串；非追蹤事件回 None。"""
    return _ANTIGRAVITY_EVENT_STATUS.get(event)


def antigravity_fields(data):
    """從 agy hook payload dict 取 (session_id, cwd, transcript_path)，不改輸入。
    conversationId 優先；缺則以 cwd 衍生。workspacePaths 取第一個字串。"""
    cwd = ""
    wp = data.get("workspacePaths")
    if isinstance(wp, list) and wp and isinstance(wp[0], str):
        cwd = wp[0]
    conv = data.get("conversationId")
    session_id = conv if conv else derive_antigravity_id(cwd)
    tp = data.get("transcriptPath")
    return session_id, cwd, tp
```

> **若 Task 1 的 C 點發現 Stop payload 不含 `conversationId`**：把 `antigravity_fields` 改為一律
> `session_id = derive_antigravity_id(cwd)`（移除 conversationId 優先），並把 `test_fields_prefers_conversation_id`
> 改為預期 cwd 衍生 id。預設（本步驟）採 conversationId 優先。

- [ ] **Step 4: 跑測試確認通過**

Run: `python3 -m unittest tests.test_sessions -v 2>&1 | tail -15`
Expected: PASS（既有 + 5 個 `AntigravityTrackTest`）。

- [ ] **Step 5: Commit**

```bash
git add sessions/sessions-track tests/test_sessions.py
git commit -m "feat: [sessions] track antigravity 純函式（事件映射 + payload 解析）"
```

---

## Task 3: `sessions-track` antigravity handler + main 分派

**Files:**
- Modify: `sessions/sessions-track`
- Test: `tests/test_sessions.py`

- [ ] **Step 1: 寫失敗測試**

在 `tests/test_sessions.py` 結尾新增：

```python
class AntigravityHandlerTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)

    def _records(self):
        out = []
        for n in os.listdir(self.dir):
            if n.endswith(".json"):
                with open(os.path.join(self.dir, n), encoding="utf-8") as f:
                    out.append(json.load(f))
        return out

    def test_posttooluse_writes_running(self):
        payload = json.dumps({"conversationId": "c1", "workspacePaths": ["/p"]})
        track._handle_antigravity(self.dir, "PostToolUse", payload, now=100)
        recs = self._records()
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["cli"], "antigravity")
        self.assertEqual(recs[0]["status"], "running")
        self.assertEqual(recs[0]["cwd"], "/p")
        self.assertEqual(recs[0]["session_id"], "c1")

    def test_stop_writes_idle(self):
        payload = json.dumps({"conversationId": "c1", "workspacePaths": ["/p"]})
        track._handle_antigravity(self.dir, "Stop", payload, now=100)
        self.assertEqual(self._records()[0]["status"], "idle")

    def test_unknown_event_ignored(self):
        payload = json.dumps({"conversationId": "c1", "workspacePaths": ["/p"]})
        track._handle_antigravity(self.dir, "PreToolUse", payload, now=100)
        self.assertEqual(self._records(), [])

    def test_no_identity_ignored(self):
        track._handle_antigravity(self.dir, "Stop", json.dumps({}), now=100)
        self.assertEqual(self._records(), [])

    def test_main_dispatches_antigravity(self):
        payload = json.dumps({"conversationId": "c9", "workspacePaths": ["/q"]})
        track.main(argv=["antigravity", "Stop"], stdin=io.StringIO(payload),
                   env={"AI_SESSIONS_DIR": self.dir}, now=200)
        recs = self._records()
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["session_id"], "c9")
        self.assertEqual(recs[0]["status"], "idle")
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python3 -m unittest tests.test_sessions.AntigravityHandlerTest -v 2>&1 | tail -15`
Expected: FAIL — `_handle_antigravity` 不存在。

- [ ] **Step 3: 新增 handler 與 main 分派**

在 `sessions/sessions-track` 的 `_handle_codex`（第 116 行附近）之後新增：

```python
def _handle_antigravity(directory, event, stdin_text, now):
    status = antigravity_event_to_status(event)
    if status is None:
        return
    data = json.loads(stdin_text)            # 壞 JSON → 例外 → __main__ 靜默吞
    if not isinstance(data, dict):
        return
    session_id, cwd, tp = antigravity_fields(data)
    if not (data.get("conversationId") or cwd):
        return
    fields = {"cli": "antigravity", "status": status, "cwd": cwd}
    if tp:
        fields["transcript_path"] = tp
    write_record(directory, session_id, fields, now)
```

在 `main()` 的 codex 分支之後（`elif src == "codex":` 區塊後）新增：

```python
    elif src == "antigravity":
        event = argv[1] if len(argv) > 1 else ""
        text = (stdin if stdin is not None else sys.stdin).read()
        _handle_antigravity(directory, event, text, now)
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python3 -m unittest tests.test_sessions -v 2>&1 | tail -10`
Expected: PASS。

- [ ] **Step 5: 驗證 track.sh 轉發（無需改動）**

Run: `printf '{"conversationId":"cli-test","workspacePaths":["/tmp/x"]}' | AI_SESSIONS_DIR=$(mktemp -d) sh -c 'd=$AI_SESSIONS_DIR; AI_SESSIONS_DIR=$d ./sessions/track.sh antigravity Stop; ls $d; cat $d/*.json'`
Expected: 印出一個 `cli-test.json`，內含 `"cli": "antigravity"`, `"status": "idle"`。
（track.sh 透傳 `$@` 與 stdin，故不需修改；此步只是確認。）

- [ ] **Step 6: Commit**

```bash
git add sessions/sessions-track tests/test_sessions.py
git commit -m "feat: [sessions] track antigravity handler + main 分派"
```

---

## Task 4: `sessions-setup` antigravity plugin 安裝/移除

**Files:**
- Modify: `sessions/sessions-setup`
- Test: `tests/test_sessions.py`

- [ ] **Step 1: 寫失敗測試**

在 `tests/test_sessions.py` 結尾新增：

```python
class AntigravitySetupTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.plugin_dir = os.path.join(self.root, "plugins", "ai-sessions")
        self.track = "/abs/sessions/track.sh"

    def test_plugin_files_content(self):
        files = setup.antigravity_plugin_files(self.track)
        self.assertIn("plugin.json", files)
        self.assertIn("hooks.json", files)
        self.assertIn('"name": "ai-sessions"', files["plugin.json"])
        hooks = json.loads(files["hooks.json"])["hooks"]
        self.assertEqual(hooks["PostToolUse"][0]["hooks"][0]["command"],
                         "/abs/sessions/track.sh antigravity PostToolUse")
        self.assertEqual(hooks["Stop"][0]["hooks"][0]["command"],
                         "/abs/sessions/track.sh antigravity Stop")

    def test_apply_creates_then_idempotent_then_remove(self):
        r1 = setup._apply_antigravity(self.plugin_dir, self.track)
        self.assertEqual(r1["status"], "ok")
        self.assertTrue(os.path.exists(os.path.join(self.plugin_dir, "plugin.json")))
        self.assertTrue(os.path.exists(os.path.join(self.plugin_dir, "hooks.json")))
        r2 = setup._apply_antigravity(self.plugin_dir, self.track)
        self.assertEqual(r2["status"], "skipped")
        r3 = setup._remove_antigravity(self.plugin_dir)
        self.assertEqual(r3["status"], "ok")
        self.assertFalse(os.path.exists(self.plugin_dir))
        r4 = setup._remove_antigravity(self.plugin_dir)
        self.assertEqual(r4["status"], "skipped")

    def test_run_install_includes_antigravity_when_dir_given(self):
        claude = os.path.join(self.root, "settings.json")
        codex = os.path.join(self.root, "config.toml")
        results = setup.run_install(claude, "/t/track.sh claude", codex,
                                    ["/t/notify.sh", "codex"],
                                    agy_plugin_dir=self.plugin_dir,
                                    track_path="/t/track.sh")
        self.assertEqual(len(results), 3)
        self.assertTrue(os.path.exists(os.path.join(self.plugin_dir, "hooks.json")))
        results_u = setup.run_uninstall(claude, "/t/track.sh claude", codex,
                                        agy_plugin_dir=self.plugin_dir)
        self.assertEqual(len(results_u), 3)
        self.assertFalse(os.path.exists(self.plugin_dir))

    def test_paths_resolves_gemini_dir(self):
        claude, codex, agy = setup._paths({"GEMINI_CONFIG_DIR": "/g"})
        self.assertEqual(agy, "/g/plugins/ai-sessions")
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python3 -m unittest tests.test_sessions.AntigravitySetupTest -v 2>&1 | tail -15`
Expected: FAIL — `antigravity_plugin_files` 不存在。

- [ ] **Step 3: 新增 antigravity plugin 純函式 + I/O**

在 `sessions/sessions-setup` 的 `MARKER = ...`（第 14 行）之後新增常數：

```python
AGY_PLUGIN_NAME = "ai-sessions"
```

在 Codex 區段之後、`# ---- 薄 I/O` 之前新增：

```python
# ---- Antigravity: 專屬 agy plugin（獨立目錄，無需 merge）--------------------
def antigravity_plugin_files(track_path):
    """回傳 ai-sessions agy plugin 的 {相對檔名: 內容字串}（純函式、不做 I/O）。"""
    hooks = {"hooks": {
        "PostToolUse": [{"hooks": [{"type": "command",
            "command": f"{track_path} antigravity PostToolUse", "async": False}]}],
        "Stop": [{"hooks": [{"type": "command",
            "command": f"{track_path} antigravity Stop", "async": False}]}],
    }}
    return {
        "plugin.json": json.dumps({"name": AGY_PLUGIN_NAME}, ensure_ascii=False) + "\n",
        "hooks.json": json.dumps(hooks, indent=2, ensure_ascii=False) + "\n",
    }
```

在 `_apply_text`（薄 I/O 區）之後新增：

```python
def _apply_antigravity(plugin_dir, track_path):
    files = antigravity_plugin_files(track_path)
    try:
        same = all(
            os.path.exists(os.path.join(plugin_dir, rel))
            and _read_text(os.path.join(plugin_dir, rel)) == content
            for rel, content in files.items()
        )
        if same:
            return _result(plugin_dir, "skipped", "已安裝")
        os.makedirs(plugin_dir, exist_ok=True)
        for rel, content in files.items():
            _write_text(os.path.join(plugin_dir, rel), content)
    except Exception as exc:
        return _result(plugin_dir, "error", f"寫入失敗：{exc}")
    return _result(plugin_dir, "ok")


def _remove_antigravity(plugin_dir):
    if not os.path.isdir(plugin_dir):
        return _result(plugin_dir, "skipped", "未安裝")
    try:
        shutil.rmtree(plugin_dir)
    except Exception as exc:
        return _result(plugin_dir, "error", f"移除失敗：{exc}")
    return _result(plugin_dir, "ok")
```

- [ ] **Step 4: 接線 run_install / run_uninstall（agy 參數選用，不破壞既有測試）**

把 `run_install`（第 212 行）整段替換為：

```python
def run_install(claude_path, claude_cmd, codex_path, codex_args,
                agy_plugin_dir=None, track_path=None):
    results = [
        _apply_json(claude_path, lambda d: apply_claude_hooks(d, claude_cmd)),
        _apply_text(codex_path, lambda t: apply_codex_dispatch(t, codex_args), mode=0o600),
    ]
    if agy_plugin_dir is not None and track_path is not None:
        results.append(_apply_antigravity(agy_plugin_dir, track_path))
    return results
```

把 `run_uninstall`（第 219 行）整段替換為：

```python
def run_uninstall(claude_path, claude_cmd, codex_path, agy_plugin_dir=None):
    results = [
        _apply_json(claude_path, lambda d: remove_claude_hooks(d, claude_cmd)[0]),
        _apply_text(codex_path, remove_codex_dispatch, mode=0o600),
    ]
    if agy_plugin_dir is not None:
        results.append(_remove_antigravity(agy_plugin_dir))
    return results
```

- [ ] **Step 5: 路徑解析 + main 接線**

把 `_paths`（第 227 行）整段替換為：

```python
def _paths(env):
    claude = env.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")
    codex = env.get("CODEX_HOME") or os.path.expanduser("~/.codex")
    gemini = env.get("GEMINI_CONFIG_DIR") or os.path.expanduser("~/.gemini/config")
    return (os.path.join(claude, "settings.json"),
            os.path.join(codex, "config.toml"),
            os.path.join(gemini, "plugins", AGY_PLUGIN_NAME))
```

在 `main()` 中，把：

```python
    claude_path, codex_path = _paths(env)
```
改為：
```python
    claude_path, codex_path, agy_plugin_dir = _paths(env)
```

並把 install/uninstall 呼叫改為帶 agy 參數：
```python
    if action == "install":
        results = run_install(claude_path, claude_cmd, codex_path, codex_args,
                              agy_plugin_dir, track)
    else:
        results = run_uninstall(claude_path, claude_cmd, codex_path, agy_plugin_dir)
```

- [ ] **Step 6: 跑全部測試確認通過（含既有 OrchestrationTest 未回歸）**

Run: `python3 -m unittest discover -s tests 2>&1 | tail -5`
Expected: OK。

- [ ] **Step 7: Commit**

```bash
git add sessions/sessions-setup tests/test_sessions.py
git commit -m "feat: [sessions] setup 安裝 antigravity agy plugin（ai-sessions）"
```

- [ ] **Step 8（CONTINGENCY，僅當 Task 1 的 A 點顯示 agy 不自動載入新 plugin）：補 manifest 註冊**

若 Task 1 發現 agy 需要 `~/.gemini/config/import_manifest.json` 註冊才會載入 plugin hooks，於
`_apply_antigravity` 成功後、`_remove_antigravity` 前，額外維護 manifest。新增純函式：

```python
def add_manifest_entry(data, name):
    """在 import_manifest 的 imports 加一筆（冪等，不改輸入）。"""
    imports = list((data or {}).get("imports", []))
    if any(i.get("name") == name for i in imports):
        return data or {"imports": imports}
    entry = {"name": name, "source": "local", "components": ["hooks"]}
    return {**(data or {}), "imports": imports + [entry]}


def remove_manifest_entry(data, name):
    imports = [i for i in (data or {}).get("imports", []) if i.get("name") != name]
    return {**(data or {}), "imports": imports}
```

並在 `_apply_antigravity` / `_remove_antigravity` 內以 `_apply_json` 對
`<gemini_config>/import_manifest.json` 套用上述函式（傳入 manifest 路徑需擴充 `_paths` 回傳）。
對應補測試 `add_manifest_entry` / `remove_manifest_entry` 的冪等與移除。Commit：
`git commit -m "feat: [sessions] setup 補 agy import_manifest 註冊（plugin 載入所需）"`

> 若 Task 1 的 A 點確認**自動載入**，跳過 Step 8。

---

## Task 5: 文件雙語更新

**Files:**
- Modify: `sessions/README.md`、`sessions/README.en.md`、`README.md`、`README.en.md`、`CHANGELOG.md`、`CLAUDE.md`

- [ ] **Step 1: `sessions/README.md`（繁中）—— 狀態模型表加入 Antigravity，並新增安裝說明**

在狀態映射表（含 `Codex agent-turn-complete → idle` 的表格）加入兩列：

```markdown
| Antigravity `PostToolUse` | → `running` |
| Antigravity `Stop` | → `idle` |
```

在「Codex 限制」段落之後新增：

```markdown
## Antigravity 支援與限制

Antigravity（`agy`，gemini-cli 系）以一個專屬 agy plugin 追蹤：安裝會建立
`~/.gemini/config/plugins/ai-sessions/`（`plugin.json` + `hooks.json`），把 `PostToolUse`
（工作中→`running`）與 `Stop`（完成→`idle`）導到 `track.sh`。

- **狀態粒度**：只有 `running` / `idle`，**沒有** `waiting`（agy 不送對應事件）。
- **無建檔/刪檔事件**：記錄於首個事件延遲建立，靠 `(stale)` 逾時清理（同 Codex）。
- **需求**：agy 支援 plugin hooks（`~/.gemini/config/plugins/*/hooks.json`）。
```

- [ ] **Step 2: `sessions/README.en.md`（英文）同步**

狀態表加入：
```markdown
| Antigravity `PostToolUse` | → `running` |
| Antigravity `Stop` | → `idle` |
```
新增節：
```markdown
## Antigravity support and limits

Antigravity (`agy`, gemini-cli family) is tracked via a dedicated agy plugin: install
creates `~/.gemini/config/plugins/ai-sessions/` (`plugin.json` + `hooks.json`) routing
`PostToolUse` (working → `running`) and `Stop` (done → `idle`) to `track.sh`.

- **Status granularity**: only `running` / `idle`, **no** `waiting` (agy emits no such event).
- **No create/delete events**: a record is created lazily on the first event and cleaned up
  by the `(stale)` timeout (like Codex).
- **Requires** agy plugin hooks support (`~/.gemini/config/plugins/*/hooks.json`).
```

- [ ] **Step 3: 頂層 `README.md` / `README.en.md` sessions 段落**

繁中（`README.md`）把 sessions 追蹤來源描述更新為涵蓋三者，例如在 sessions 介紹處加：
```markdown
> 追蹤 Claude Code、Codex 與 Antigravity 三種 AI CLI 的 session 狀態。
```
英文（`README.en.md`）：
```markdown
> Tracks session state across three AI CLIs: Claude Code, Codex, and Antigravity.
```

- [ ] **Step 4: `CHANGELOG.md`**

在最新版本（或 Unreleased）的 Added 下加：
```markdown
- **sessions 階段三**：納入 Antigravity（`agy`）。安裝一個專屬 agy plugin
  （`~/.gemini/config/plugins/ai-sessions/`）把 `PostToolUse`→`running`、`Stop`→`idle`
  導到 `track.sh`。狀態粒度為 running/idle（無 waiting），靠 stale 逾時清理。
```

- [ ] **Step 5: `CLAUDE.md`**

在 `sessions/` 元件說明補一句：
```markdown
階段三（Antigravity）：`sessions-track` 新增 `antigravity` 來源（`PostToolUse`→`running`、
`Stop`→`idle`；payload 取 `conversationId`/`workspacePaths[0]`）；`sessions-setup` 安裝一個
專屬 agy plugin `~/.gemini/config/plugins/ai-sessions/`（plugin.json + hooks.json），
解除即刪該目錄。gemini config 目錄可用 `GEMINI_CONFIG_DIR` 覆寫。
```

- [ ] **Step 6: 跑全部測試 + Commit**

Run: `python3 -m unittest discover -s tests 2>&1 | tail -5`
Expected: OK。

```bash
git add sessions/README.md sessions/README.en.md README.md README.en.md CHANGELOG.md CLAUDE.md
git commit -m "docs: [sessions] 階段三雙語文件、CHANGELOG、CLAUDE.md（Antigravity）"
```

---

## 完成標準

- `python3 -m unittest discover -s tests` 全綠（既有 + antigravity track/setup 新測試）。
- Task 1 gating 結論已記錄；若需 manifest 則 Task 4 Step 8 已實作。
- 真實安裝（`GEMINI_CONFIG_DIR` 預設）後，跑一次 agy 會在 `~/.cache/ai-sessions/` 出現
  `cli=antigravity` 的狀態檔，且儀表板顯示其 running/idle；按 `Enter` 能切到該 agy 分頁。
- 狀態檔格式、`dashboard.py`、`ghostty.py`、`install.sh`/`uninstall.sh` 未改動。
- 文件雙語同步。
