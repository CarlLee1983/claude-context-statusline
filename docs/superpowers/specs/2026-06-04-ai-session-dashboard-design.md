# 設計：`sessions/` — 多 session 總覽儀表板（tmux 外框架）

- 日期：2026-06-04
- 狀態：設計定案，待寫實作計畫
- 元件：`sessions/`（本 repo 第五個元件）

## 1. 背景與目標

同時開很多 Ghostty 分頁跑 AI CLI 時，看不出「哪個在跑、哪個跑完、哪個在等我、各自在哪個目錄」。
本元件提供一個**寬版總覽儀表板**，並（階段二）能直接切到目標分頁。

Ghostty 本身**沒有對外控制平面（IPC）**，外部腳本無法遠端切分頁。標準解法是
**在底下塞一個多工器**：AI CLI 跑在 **tmux**，Ghostty 當顯示視窗，tmux 當我們能完全
控制的分頁管理層。tmux 提供 `list-panes`、`select-window`、`capture-pane`、
`pane_current_path` 等 IPC。

### 核心洞察：兩種資訊合流

- **狀態語意**（在跑／等輸入／待命）— 只有各 CLI 的 **hook** 知道，tmux 不知道。
- **拓樸與切換**（有哪些分頁、CWD、怎麼切）— 只有 **tmux** 知道。

兩者合流才完整：hook 寫狀態檔，tmux 提供拓樸，儀表板把兩者疊起來。

### 非目標（YAGNI）

- 不改 Ghostty 本體（不 fork、不做原生左側欄）。
- 不做真實畫面縮圖（拿不到他 App 畫面）；「預覽」= `capture-pane` 的文字快照。
- 階段一不納入 Antigravity（待查其完成事件機制）。

## 2. 分階段範圍

| | 階段一（本 spec 的實作目標） | 階段二（後續另立計畫） |
|---|---|---|
| 底座 | 無 tmux 也能用 | tmux |
| 資料 | 純讀 hook 狀態檔 | 狀態檔 + tmux 即時拓樸 |
| 切換 | ❌（`Enter` 複製路徑） | ✅ `select-window` / `switch-client` |
| 預覽 | ❌ | ✅ `capture-pane` |
| 啟動 | 在任一終端直接跑 TUI | 綁 tmux `display-popup` 鍵 |

一份 `dashboard.py` 橋接兩階段：偵測到環境變數 `$TMUX` 時自動開啟階段二功能。
**本 spec 以階段一為可實作單位**，階段二僅描述方向。

## 3. 資料流

```
階段一：
  [Claude hooks: SessionStart/UserPromptSubmit/Stop/Notification]
  [Codex notify: agent-turn-complete]
        │ 呼叫
        ▼
  sessions/track.sh  ──寫──>  ~/.cache/ai-sessions/<session_id>.json
                                      │ 讀（約 1s 輪詢）
                                      ▼
                          sessions/dashboard.py（curses 寬版總覽，唯讀）

階段二（加疊）：
  AI CLI 跑在 tmux ── tmux list-panes/capture-pane ─┐
  狀態檔 ────────────────────────────────────────────┤ 合流
                                                      ▼
              tmux display-popup -E python3 dashboard.py
              → Enter: select-window 切過去；側欄: capture-pane 預覽
```

## 4. 狀態模型

| 事件 | 來源 | 狀態 | 備註 |
|------|------|------|------|
| `SessionStart` | Claude | `idle` | 建檔 |
| `UserPromptSubmit` | Claude | `running` | 正在想 |
| `Notification` | Claude | `waiting` | 等權限/輸入（儀表板置頂） |
| `Stop` | Claude | `idle` | 跑完待命 |
| `SessionEnd` | Claude | （刪檔） | session 結束 |
| `agent-turn-complete` | Codex | `idle` | Codex 只有此單一事件 |

**Codex 限制**：只有一個 `notify` 事件，拿不到 `running`/`waiting`，只能顯示
`idle` + 上次完成時間。文件須標明。

## 5. 元件拆分（單一職責，可獨立測試）

### 5.1 `sessions/track.sh` — 觸發層（純 `/bin/sh`，零相依）

- 用法：`track.sh <source> <event> [payload]`，把事件映射成狀態，寫 `<id>.json`。
- `session_id`／`cwd`／`transcript_path` 來源：Claude hook 由 **stdin JSON** 提供；
  Codex 由 `notify` 的 payload 提供。`track.sh` 以 `/usr/bin/python3` 解析（沿用 repo
  慣例，避免依賴 `jq`）。
- **永不崩潰鐵則**（對齊 `bell/notify.sh`）：任何失敗一律吞掉並 `exit 0`，
  絕不讓 host CLI 因狀態追蹤而報錯或中斷。
- 可用 `AI_SESSIONS_DIR` 覆寫輸出目錄（測試用）。

### 5.2 `sessions/dashboard.py` — 顯示層（stdlib `curses`）

- 讀狀態目錄、渲染表格、約 1s 自動刷新（比對目錄 mtime）。
- 偵測 `$TMUX` → 啟用階段二功能（階段一可先留掛鉤）。
- **永不崩潰**：外層 try/except；`curses.wrapper` 確保離開時還原終端機；
  狀態檔損毀／缺欄位都 fallback，不中斷整體渲染。

### 5.3 `sessions/install.sh` / `uninstall.sh` + `sessions/sessions-setup` — 編排層

- 沿用 bell 的合併策略：**備份（`*.bak.<timestamp>`）、只增不刪、冪等、
  以 MARKER 識別自家區段**，honors `CLAUDE_CONFIG_DIR` / `CODEX_HOME`。
- 純函式（`apply_*` / `remove_*` 不改輸入、回傳新值）+ 薄 I/O，比照 `bell/bell-setup`。

## 6. 狀態檔規格

- 位置：`${AI_SESSIONS_DIR:-~/.cache/ai-sessions}/<session_id>.json`，一 session 一檔。
- 欄位：
  - `session_id`：字串（Claude 給 session_id；Codex 用 payload 提供的 id，缺則以 cwd 衍生）
  - `cli`：`"claude"` | `"codex"`
  - `cwd`：工作目錄絕對路徑
  - `status`：`"running"` | `"waiting"` | `"idle"`
  - `started_at` / `updated_at`：epoch 秒
  - `transcript_path`：字串（Claude 才有，選填）
- **過期判定**：`updated_at` 超過門檻（如 30 分）標 `stale`。階段二以「tmux pane 是否
  存在」作為真實依據校正並清掉孤兒檔。階段一純靠時間戳。
- **清檔**：`SessionEnd` 刪檔；無 `SessionEnd` 時靠過期標記（崩潰留下的孤兒）。

## 7. ⚠️ 整合決定：Codex `notify` 單槽衝突 → 採合併派發器（選項 A）

Codex `config.toml` 只有**一個 `notify` 槽**，而 bell 已佔用它（指向 `bell/notify.sh`）。
解法採**合併派發器**：

- Codex 的單一 notify 入口指向一個派發腳本，`agent-turn-complete` 進來時
  **同時**：① 送 BEL（bell 的職責）② 寫狀態檔（sessions 的職責）。
- **安裝協調**：`sessions/install.sh` 偵測到 bell 已擁有 Codex notify 時，
  將該 notify **升級**為合併派發器（仍以 MARKER 標記、可逆）；移除時還原。
  兩元件共用同一個「完成信號」入口。
- **Claude 無此衝突**：Claude hooks 可多筆並存。bell 的 `Stop` hook 維持不動；
  sessions 另外加自己的 `SessionStart`/`UserPromptSubmit`/`Stop`/`Notification` hook
  指向 `track.sh`，兩者各自獨立。

> 註：派發器的確切落點（改寫 `bell/notify.sh` 為可重用入口，或新增一個薄 wrapper
> 同時呼叫 `bell/notify.sh` 與 `track.sh`）留待實作計畫定，原則是**最小變動 bell、保持兩元件解耦**。

## 8. TUI 行為（階段一）

- 排序：`waiting` 置頂 → `running` → `idle`；同組依 `updated_at`。
- 每列：CLI 圖示、狀態（**顏色 + emoji + 形狀角標**雙重編碼，對齊 repo 既有色盲友善做法）、
  CWD（basename 粗體 + 完整路徑暗色）、停在此狀態多久、`stale` 標記。
- 鍵：`j`/`k`/方向移動、`q` 離開、`r` 手動刷新；`Enter` 複製路徑（`pbcopy`）。
- 空狀態：無任何 session 時顯示提示文字，不報錯。

## 9. 測試策略

沿用 repo 慣例：純標準庫 `unittest`，新增 `tests/test_sessions.py`（連字號檔名以
`importlib` 依路徑載入）。涵蓋：

- `track.sh` 事件→狀態映射（各 Claude 事件、Codex agent-turn-complete、非完成事件忽略）。
- `track.sh` 永不崩潰（壞 JSON、無 stdin、無寫入權限 → 仍 `exit 0`）。
- 狀態檔讀寫與過期判定（`updated_at` 門檻）。
- `sessions-setup` 合併純函式：Claude 四個 hook 的 apply/remove（空檔/既有/冪等/壞 JSON）、
  Codex notify 從 bell 單槽**升級為合併派發器**與還原、`AI_SESSIONS_DIR` 覆寫。
- `dashboard.py` 渲染純邏輯（排序、過期標記、空狀態）可抽純函式單測；curses 繪製層不單測。

## 10. 文件

沿用 repo 雙語慣例：`sessions/README.md`（繁中）+ `sessions/README.en.md`（英文），
頂層 README 總覽加入第五個元件，`CHANGELOG.md` 記錄，`CLAUDE.md` 補元件說明與開發指令。
須標明：**需要 tmux（階段二）**、**Codex 狀態粒度限制**、**永不崩潰原則**。

## 11. 階段二方向（後續另立 spec/計畫，非本次實作）

- 啟動：`tmux display-popup -E python3 dashboard.py`，安裝一個 tmux keybind（如 `prefix + g`）。
- 拓樸合流：`tmux list-panes -a -F '...'` 取 session/window/pane_current_path/pane_current_command/pane_pid，
  與狀態檔以 cwd + cli（或 pid）配對（配對策略為階段二主要難點）。
- 切換：`Enter` → `select-window` / `switch-client` 跳到目標 pane，popup 關閉。
- 預覽：`capture-pane -p -t <pane>` 取末 N 行。
- **tmux↔Ghostty BEL 傳遞**：tmux 內 BEL 需設定（`monitor-bell` / bell-action）讓 BEL
  仍能傳到 Ghostty 觸發 `attention`，否則 bell 在 tmux 下失效。
```
