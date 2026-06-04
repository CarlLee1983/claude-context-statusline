# 多 session 儀表板階段二（Ghostty 原生一鍵切換）實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `sessions/dashboard.py` 選一列按 `Enter`，直接 focus 到該 AI session 所在的 Ghostty 分頁/視窗（零工作流改動、不需 tmux）。

**Architecture:** 新增薄邊界模組 `sessions/ghostty.py`——純函式 `pick_terminal`（cwd + 標題啟發式選分頁，單測）+ 兩個 `osascript` subprocess 邊界 `list_terminals`/`focus_terminal`（不單測，對齊 repo 既有 PTY 邊界慣例）。`dashboard.py` 只在按鍵時懶載入並呼叫 `ghostty`，輪詢迴圈不變。狀態檔格式、track、install 全部不動。

**Tech Stack:** Python 3 標準庫（`subprocess`/`shutil`/`re`/`os`）、`curses`、macOS `osascript`、Ghostty 1.3+ AppleScript 字典。

**設計來源：** `docs/superpowers/specs/2026-06-04-ai-session-dashboard-phase2-design.md`

---

## 檔案結構

- **新增** `sessions/ghostty.py`：Ghostty AppleScript 橋接。純函式 `pick_terminal` + 邊界 `list_terminals`/`focus_terminal`。
- **修改** `sessions/dashboard.py`：`Enter`=跳轉、`c`=複製路徑、加狀態訊息行；懶載入 `ghostty`。
- **修改** `tests/test_sessions.py`：載入 `ghostty` 模組 + `pick_terminal` 純函式測試。
- **修改** 文件：`sessions/README.md`、`sessions/README.en.md`、`README.md`、`README.en.md`、`CHANGELOG.md`、`CLAUDE.md`。

---

## Task 1: `ghostty.py` 純函式 `pick_terminal`（cwd + 標題啟發式）

**Files:**
- Create: `sessions/ghostty.py`
- Test: `tests/test_sessions.py`（新增載入器行 + 新 TestCase）

- [ ] **Step 1: 寫失敗測試**

在 `tests/test_sessions.py` 第 28 行（`dashboard = _load(...)` 之後）新增一行模組載入：

```python
ghostty = _load("sessions_ghostty", "ghostty.py")
```

在檔案結尾（最後一個 class 之後、`if __name__ == "__main__":` 之前；若無該行則直接接在最後）新增：

```python
class PickTerminalTest(unittest.TestCase):
    def test_single_cwd_match_returns_id(self):
        terms = [{"id": "A", "cwd": "/a/b/proj", "title": "anything"}]
        rec = {"cwd": "/a/b/proj", "cli": "claude"}
        self.assertEqual(ghostty.pick_terminal(rec, terms), "A")

    def test_prefers_cli_like_title_over_shell(self):
        terms = [
            {"id": "SH", "cwd": "/a/b/proj", "title": "…/a/b/proj"},
            {"id": "CLI", "cwd": "/a/b/proj", "title": "⠂ Review task"},
            {"id": "DEV", "cwd": "/a/b/proj", "title": "proj"},
        ]
        rec = {"cwd": "/a/b/proj", "cli": "claude"}
        self.assertEqual(ghostty.pick_terminal(rec, terms), "CLI")

    def test_all_shell_like_returns_first_match(self):
        terms = [
            {"id": "SH1", "cwd": "/a/b/proj", "title": "…/a/b/proj"},
            {"id": "SH2", "cwd": "/a/b/proj", "title": "admin@host: ~"},
        ]
        rec = {"cwd": "/a/b/proj", "cli": "claude"}
        self.assertEqual(ghostty.pick_terminal(rec, terms), "SH1")

    def test_trailing_slash_normalized(self):
        terms = [{"id": "A", "cwd": "/a/b/proj/", "title": "x"}]
        rec = {"cwd": "/a/b/proj", "cli": "claude"}
        self.assertEqual(ghostty.pick_terminal(rec, terms), "A")

    def test_no_match_returns_none(self):
        terms = [{"id": "A", "cwd": "/other", "title": "x"}]
        rec = {"cwd": "/a/b/proj", "cli": "claude"}
        self.assertIsNone(ghostty.pick_terminal(rec, terms))

    def test_bad_input_returns_none(self):
        self.assertIsNone(ghostty.pick_terminal(None, []))
        self.assertIsNone(ghostty.pick_terminal({"cli": "claude"}, []))
        self.assertIsNone(ghostty.pick_terminal({"cwd": ""}, [{"id": "A", "cwd": "", "title": "x"}]))
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python3 -m unittest tests.test_sessions -v 2>&1 | tail -20`
Expected: FAIL —— 載入 `ghostty.py` 失敗（檔案不存在）或 `AttributeError: module has no attribute 'pick_terminal'`。

- [ ] **Step 3: 建立 `sessions/ghostty.py`（純函式部分）**

```python
#!/usr/bin/env python3
"""ghostty.py — Ghostty AppleScript 橋接（階段二一鍵切換）。

純函式 pick_terminal（cwd + 標題啟發式選分頁）可單測；
list_terminals / focus_terminal 為 osascript subprocess 薄邊界，不單測
（對齊 repo 既有 PTY 邊界慣例）。永不崩潰：所有失敗回安全值。
"""
import os
import re
import shutil
import subprocess


def _norm_cwd(path):
    """正規化 cwd：去尾斜線，root 保留為 '/'；非字串回 ''。"""
    if not isinstance(path, str):
        return ""
    p = path.rstrip("/")
    if not p:
        return "/" if path else ""
    return p


def _title_is_pathlike(title, cwd):
    """shell 分頁標題通常是路徑（縮寫 / user@host: ~ / 純 basename）；
    CLI session 標題是任務摘要。回 True 代表像 shell，去歧義時降權。"""
    if not isinstance(title, str):
        return True
    t = title.strip()
    if not t:
        return True
    if t.startswith("/") or t.startswith("~") or "…/" in t or ": ~" in t:
        return True
    base = os.path.basename(_norm_cwd(cwd))
    if base and t == base:
        return True
    return False


def pick_terminal(record, terminals):
    """從 Ghostty terminals 選出最符合該 session 的 terminal id（best-effort）。
    純函式、不改輸入。無 cwd 對應回 None。"""
    if not isinstance(record, dict):
        return None
    target = _norm_cwd(record.get("cwd", ""))
    if not target:
        return None
    matches = [t for t in terminals
               if isinstance(t, dict) and _norm_cwd(t.get("cwd", "")) == target]
    if not matches:
        return None
    cli_like = [t for t in matches
                if not _title_is_pathlike(t.get("title", ""), target)]
    chosen = cli_like[0] if cli_like else matches[0]
    return chosen.get("id") or None
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python3 -m unittest tests.test_sessions -v 2>&1 | tail -20`
Expected: PASS（含既有測試與 6 個新 `PickTerminalTest`）。

- [ ] **Step 5: Commit**

```bash
git add sessions/ghostty.py tests/test_sessions.py
git commit -m "feat: [sessions] ghostty pick_terminal 純函式（cwd + 標題啟發式）"
```

---

## Task 2: `ghostty.py` osascript 薄邊界 `list_terminals` / `focus_terminal`

**Files:**
- Modify: `sessions/ghostty.py`（append）

此 task 為 subprocess 邊界，**不寫單測**（對齊 repo 慣例），以手動指令驗證。

- [ ] **Step 1: append 邊界到 `sessions/ghostty.py`**

接在 `pick_terminal` 之後新增：

```python
# ---- osascript 薄邊界（不單測；永不崩潰）-----------------------------------

_LIST_SCRIPT = (
    'tell application "Ghostty"\n'
    '  set out to ""\n'
    '  repeat with t in terminals\n'
    '    try\n'
    '      set out to out & (id of t) & tab & (working directory of t) '
    '& tab & (name of t) & linefeed\n'
    '    end try\n'
    '  end repeat\n'
    '  return out\n'
    'end tell'
)

_ID_RE = re.compile(r"^[A-Za-z0-9-]+$")


def _run_osascript(script, timeout=3):
    """跑 osascript；失敗（無 osascript / 非 0 / 例外）回 None，成功回 stdout 字串。"""
    osa = shutil.which("osascript")
    if not osa:
        return None
    try:
        proc = subprocess.run([osa, "-e", script],
                              capture_output=True, timeout=timeout)
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    try:
        return proc.stdout.decode("utf-8", "replace")
    except Exception:
        return None


def list_terminals():
    """列舉 Ghostty terminals → [{"id","cwd","title"}]。失敗回 []。"""
    raw = _run_osascript(_LIST_SCRIPT)
    if not raw:
        return []
    out = []
    for line in raw.splitlines():
        if not line:
            continue
        parts = line.split("\t", 2)
        if len(parts) < 2:
            continue
        out.append({
            "id": parts[0],
            "cwd": parts[1],
            "title": parts[2] if len(parts) > 2 else "",
        })
    return out


def focus_terminal(term_id):
    """focus 指定 terminal 並把 Ghostty 帶到最前。成功回 True，否則 False。"""
    if not isinstance(term_id, str) or not _ID_RE.match(term_id):
        return False
    script = (
        'tell application "Ghostty"\n'
        '  focus (first terminal whose id is "%s")\n'
        '  activate\n'
        'end tell' % term_id
    )
    return _run_osascript(script) is not None
```

- [ ] **Step 2: 語法檢查**

Run: `python3 -c "import importlib.util,importlib.machinery; l=importlib.machinery.SourceFileLoader('g','sessions/ghostty.py'); s=importlib.util.spec_from_file_location('g','sessions/ghostty.py',loader=l); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); print(type(m.list_terminals()))"`
Expected: 印出 `<class 'list'>`（在無 Ghostty / 非 macOS 環境回 `[]`，不報錯）。

- [ ] **Step 3: 手動驗證（macOS + Ghostty 開著時）**

Run: `python3 -c "import importlib.util,importlib.machinery; l=importlib.machinery.SourceFileLoader('g','sessions/ghostty.py'); s=importlib.util.spec_from_file_location('g','sessions/ghostty.py',loader=l); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); [print(t) for t in m.list_terminals()]"`
Expected: 印出各 Ghostty terminal 的 `{"id":..., "cwd":..., "title":...}`（首次可能跳自動化授權；核准後重跑即有輸出）。

- [ ] **Step 4: 跑全部測試確認未回歸**

Run: `python3 -m unittest discover -s tests 2>&1 | tail -5`
Expected: OK（測試數 = 既有 + 6）。

- [ ] **Step 5: Commit**

```bash
git add sessions/ghostty.py
git commit -m "feat: [sessions] ghostty osascript 邊界 list_terminals/focus_terminal"
```

---

## Task 3: `dashboard.py` 整合（Enter=跳轉、c=複製、狀態訊息行）

**Files:**
- Modify: `sessions/dashboard.py`

curses 互動層**不寫單測**；以語法檢查 + 手動 smoke 驗證。

- [ ] **Step 1: 改 HELP 常數與懶載入器**

把 `sessions/dashboard.py:86` 的 `HELP` 行：

```python
HELP = "  j/k 移動 · r 刷新 · Enter 複製路徑 · q 離開"
```

改為：

```python
HELP = "  j/k 移動 · r 刷新 · Enter 跳到 · c 複製 · q 離開"
```

在 `_copy_path`（`sessions/dashboard.py:89`）之前新增懶載入器與跳轉函式：

```python
def _load_ghostty():
    """懶載入同目錄的 ghostty 模組（dashboard 被 importlib 以非標準名載入時，
    sys.path 可能沒有 sessions/，故顯式補上）。"""
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import ghostty
    return ghostty


def _jump(record):
    """focus 到該 session 的 Ghostty 分頁。回提示訊息（成功為空字串）。永不崩潰。"""
    try:
        gh = _load_ghostty()
        terms = gh.list_terminals()
        if not terms:
            return "找不到 Ghostty 分頁（需 Ghostty 1.3+ 並核准自動化權限）"
        tid = gh.pick_terminal(record, terms)
        if not tid:
            return "找不到對應分頁"
        if gh.focus_terminal(tid):
            return ""
        return "切換失敗（檢查 系統設定›隱私權›自動化）"
    except Exception:
        return "切換失敗"
```

- [ ] **Step 2: `_draw` 支援狀態訊息行**

把 `_draw` 的簽名與最後的 HELP 繪製改為支援 `message`。
將 `sessions/dashboard.py:96` 的：

```python
def _draw(stdscr, records, selected, now):
```

改為：

```python
def _draw(stdscr, records, selected, now, message=""):
```

並把 `sessions/dashboard.py:111` 的：

```python
    stdscr.addnstr(height - 1, 0, HELP[:width - 1], width - 1, curses.A_DIM)
```

改為：

```python
    footer = message or HELP
    stdscr.addnstr(height - 1, 0, footer[:width - 1], width - 1, curses.A_DIM)
```

- [ ] **Step 3: `_loop` 改按鍵綁定（Enter=跳、c=複製、訊息生命週期）**

把 `_loop`（`sessions/dashboard.py:115-143`）整段替換為：

```python
def _loop(stdscr, directory):
    curses.curs_set(0)
    stdscr.nodelay(True)
    selected = 0
    last_load = 0.0
    records = []
    message = ""
    while True:
        now = time.time()
        if now - last_load >= REFRESH_SEC:
            records = sorted(load_records(directory), key=sort_key)
            last_load = now
            selected = max(0, min(selected, len(records) - 1))
        _draw(stdscr, records, selected, int(now), message)
        try:
            ch = stdscr.getch()
        except curses.error:
            ch = -1
        if ch in (ord("q"), 27):
            return
        if ch in (ord("j"), curses.KEY_DOWN):
            selected = min(selected + 1, max(0, len(records) - 1))
            message = ""
        elif ch in (ord("k"), curses.KEY_UP):
            selected = max(selected - 1, 0)
            message = ""
        elif ch == ord("r"):
            last_load = 0.0
            message = ""
        elif ch == ord("c") and records:
            _copy_path(records[selected].get("cwd", ""))
            message = "已複製路徑"
        elif ch in (curses.KEY_ENTER, 10, 13) and records:
            message = _jump(records[selected])
        else:
            time.sleep(0.05)
```

- [ ] **Step 4: 語法檢查 + 既有測試未回歸**

Run: `python3 -c "import importlib.util,importlib.machinery; l=importlib.machinery.SourceFileLoader('d','sessions/dashboard.py'); s=importlib.util.spec_from_file_location('d','sessions/dashboard.py',loader=l); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); print('ok')"`
Expected: 印出 `ok`（模組載入不因新增 `import ghostty` 而失敗——因為是懶載入）。

Run: `python3 -m unittest discover -s tests 2>&1 | tail -5`
Expected: OK。

- [ ] **Step 5: 手動 smoke（macOS + Ghostty）**

Run: `./sessions/dashboard.py`
Expected: TUI 顯示 session 清單；`j/k` 移動、`c` 顯示「已複製路徑」、`Enter` 跳到對應 Ghostty 分頁（或在底列顯示「找不到對應分頁」等提示，不崩潰）、`q` 離開。

- [ ] **Step 6: Commit**

```bash
git add sessions/dashboard.py
git commit -m "feat: [sessions] dashboard Enter 一鍵切換 Ghostty 分頁（c 複製、狀態訊息）"
```

---

## Task 4: 文件雙語更新

**Files:**
- Modify: `sessions/README.md`、`sessions/README.en.md`、`README.md`、`README.en.md`、`CHANGELOG.md`、`CLAUDE.md`

- [ ] **Step 1: `sessions/README.md`（繁中）新增階段二段落**

在現有「鍵盤操作 / 互動」相關段落更新按鍵說明，並新增一節（接在儀表板說明之後）：

```markdown
## 階段二：一鍵切換（Ghostty 原生）

在儀表板選一列按 `Enter`，直接 focus 到該 AI session 所在的 Ghostty 分頁/視窗。
`c` 鍵複製路徑。

- **需求**：Ghostty 1.3+（使用其內建 AppleScript 字典）。首次切換會跳出 macOS
  自動化授權（「Ghostty 想控制 Ghostty」），核准一次即可。
- **配對方式**：以 session 的工作目錄（cwd）對應 Ghostty 分頁；同一目錄有多個分頁時，
  以標題啟發式優先選出 CLI session 分頁（best-effort）。
- **限制**：不提供即時預覽分頁內容（Ghostty 字典無對應指令，刻意取捨）。
- **永不崩潰**：找不到分頁、權限被拒、Ghostty 沒開等情況只在底列顯示提示，不中斷 TUI。
```

- [ ] **Step 2: `sessions/README.en.md`（英文）同步**

新增對應英文節：

```markdown
## Phase 2: One-key switch (native Ghostty)

Select a row in the dashboard and press `Enter` to focus the Ghostty tab/window
where that AI session runs. Press `c` to copy the path.

- **Requires** Ghostty 1.3+ (uses its built-in AppleScript dictionary). The first
  switch triggers a macOS Automation permission prompt ("Ghostty wants to control
  Ghostty"); approve it once.
- **Matching**: maps a session to a Ghostty tab by working directory (cwd); when a
  directory has several tabs, a title heuristic prefers the CLI session tab
  (best-effort).
- **Limitation**: no live preview of tab contents (no equivalent command in the
  Ghostty dictionary — a deliberate trade-off).
- **Never crashes**: missing tab, denied permission, or Ghostty not running only
  shows a footer hint; the TUI keeps running.
```

- [ ] **Step 3: 頂層 `README.md` / `README.en.md` sessions 段落各補一句**

繁中（`README.md` 的 sessions 介紹處）加：

```markdown
> 在 Ghostty 下還能於儀表板按 `Enter` 一鍵切到目標 session 的分頁（階段二，原生 AppleScript）。
```

英文（`README.en.md` 對應處）加：

```markdown
> On Ghostty, press `Enter` in the dashboard to jump straight to a session's tab
> (Phase 2, native AppleScript).
```

- [ ] **Step 4: `CHANGELOG.md` 記錄**

在最新版本區塊（或新增 Unreleased 區塊）的 Added 下加：

```markdown
- **sessions 階段二**：儀表板 `Enter` 一鍵切到目標 AI session 的 Ghostty 分頁
  （Ghostty 1.3+ 原生 AppleScript；`c` 改為複製路徑）。配對以 cwd + 標題啟發式，
  永不崩潰；不含即時預覽（刻意取捨）。
```

- [ ] **Step 5: `CLAUDE.md` 補元件說明**

在 `sessions/` 架構說明段落補一句（描述新增的 `ghostty.py` 與階段二）：

```markdown
階段二（Ghostty 原生）：`sessions/ghostty.py` 以 macOS `osascript` 橋接 Ghostty 1.3+
AppleScript 字典——`pick_terminal`（純函式，cwd + 標題啟發式選分頁，單測）+
`list_terminals` / `focus_terminal`（subprocess 薄邊界，不單測）。dashboard 的 `Enter`
懶載入 `ghostty` 並 focus 到對應分頁；`c` 複製路徑。不做即時預覽（Ghostty 字典無對應指令）。
```

- [ ] **Step 6: 跑全部測試 + Commit**

Run: `python3 -m unittest discover -s tests 2>&1 | tail -5`
Expected: OK。

```bash
git add sessions/README.md sessions/README.en.md README.md README.en.md CHANGELOG.md CLAUDE.md
git commit -m "docs: [sessions] 階段二雙語文件、頂層總覽、CHANGELOG、CLAUDE.md"
```

---

## 完成標準

- `python3 -m unittest discover -s tests` 全綠（既有 + 6 個 `PickTerminalTest`）。
- `./sessions/dashboard.py` 在 Ghostty 下 `Enter` 能切到對應分頁；`c` 複製；各失敗路徑只顯示提示不崩潰。
- 狀態檔格式、`track.sh`/`sessions-track`、`install.sh`/`sessions-setup` 皆未改動。
- 文件雙語同步、CHANGELOG / CLAUDE.md 已更新。
