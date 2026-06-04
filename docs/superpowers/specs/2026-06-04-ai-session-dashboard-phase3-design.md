# 設計：`sessions/` 階段三 — 納入 Antigravity

> **狀態**：已核可，待寫實作計畫。
> **前置**：階段一（總覽儀表板）、階段二（Ghostty 原生一鍵切換）已完成並合併。

## 1. 背景與決策

階段一刻意排除 Antigravity，原因是「完成事件機制待查」。本階段先以**實證探針**釐清，
再設計。探針結論（在本機 agy 1.x 實測）：

- **`agy` 是 gemini-cli 系的終端機 CLI**，互動模式跑在 Ghostty 分頁，定位同 Claude Code / Codex。
- **hook 系統與 Claude 相容、採 plugin 制**：hooks 放在 `~/.gemini/config/plugins/<名>/hooks.json`
  （非單一 settings.json）。格式為 `{"hooks": {EventName: [{"hooks":[{"type":"command","command":...,"async":false}]}]}}`。
- **實際會 fire 的事件**：`PostToolUse`（工作中，每次工具呼叫後）與 `Stop`（一輪完成）。
  探測下 **不會** fire `SessionStart` / `UserPromptSubmit` / `Notification` / `SessionEnd`。
- **payload（stdin JSON）欄位**：`conversationId`、`workspacePaths`（陣列）、`transcriptPath`、
  `toolCall`、`stepIdx`、`error`、`artifactDirectoryPath`。
- **payload 不含事件名** → 以 hook 指令參數帶入（`track.sh antigravity PostToolUse` / `… Stop`）。

**狀態粒度決策**：`running`（PostToolUse）+ `idle`（Stop）。無 `waiting`（不 fire Notification）；
無 `SessionStart`→記錄延遲建立；無 `SessionEnd`→靠 stale 逾時清理（同 Codex）。
比 Codex（只有 idle）豐富，比 Claude（完整 running/waiting/idle）少一個 waiting。

## 2. 範圍

把 Antigravity 納入既有 sessions 流程，**與 Claude/Codex 對稱**：hook → `track.sh` 寫狀態檔 →
儀表板顯示。

**不動既有資產**：

- 狀態檔格式不變（沿用 `cli` / `status` / `cwd` / `started_at` / `updated_at` / `session_id` /
  `transcript_path`，`cli` 值新增 `"antigravity"`）。
- `sessions/dashboard.py` 渲染與排序不需改（`format_row` 已泛用；新 cli 值自然顯示）。
- 階段二 `sessions/ghostty.py` 切換不需改（Antigravity 也跑在 Ghostty，`pick_terminal` 靠 cwd 適用）。

**新增**：`sessions-track` 的 antigravity handler；`sessions-setup` 的 antigravity 安裝/移除邏輯；
`track.sh` 的 `antigravity` 分派。

**範圍外（YAGNI）**：

- `pick_terminal` 依 `cli` 精準化（同 cwd 同時有 claude + agy 時可能 focus 錯分頁——這是階段二
  既有的 best-effort 限制，列為未來優化）。
- `waiting` 狀態（agy 不 fire Notification）。
- 即時預覽、孤兒主動清理（非本階段）。

## 3. 元件設計（單一職責、可獨立測試）

### 3.1 `sessions/track.sh` — 分派層

新增 `antigravity` 分支：`track.sh antigravity <event>`，stdin 為 agy hook payload。
比照既有 `claude` / `codex` 分派，永不崩潰（任何失敗 `exit 0`）。

### 3.2 `sessions/sessions-track` — 解析與映射（純函式 + 薄 I/O）

- 新增 antigravity 事件→狀態映射：`PostToolUse → running`、`Stop → idle`、其他 → None（忽略）。
  以獨立純函式實作（如 `antigravity_event_to_status(event)`），不污染既有 `event_to_status`。
- 新增 antigravity payload 解析（純函式）：
  - `session_id = conversationId`；缺則以 cwd 衍生（沿用 `derive_codex_id` 風格，另立
    `derive_antigravity_id(cwd)` 回傳如 `"antigravity:" + cwd`，並經 `sanitize_id`）。
  - `cwd = workspacePaths[0]`（陣列非空時取第一個，否則空字串）。
  - `transcript_path = transcriptPath`（選填）。
- 薄 I/O `_handle_antigravity(directory, event, stdin_text, now)`：解析 → `event_to_status` →
  None 則略過；否則 `write_record(directory, id, {"cli":"antigravity","status":...,"cwd":...,
  "transcript_path":...}, now)`。
- `main()` 的 source 分派新增 `antigravity`。

### 3.3 `sessions/sessions-setup` — 安裝/移除（純函式 + 薄 I/O）

- 裝一個**專屬 agy plugin** `<gemini_config>/plugins/ai-sessions/`：
  - `plugin.json`：`{"name": "ai-sessions"}`
  - `hooks.json`：
    ```json
    {"hooks": {
      "PostToolUse": [{"hooks": [{"type": "command", "command": "<TRACK> antigravity PostToolUse", "async": false}]}],
      "Stop":        [{"hooks": [{"type": "command", "command": "<TRACK> antigravity Stop",        "async": false}]}]
    }}
    ```
    `<TRACK>` 為安裝後 `track.sh` 的絕對路徑。
- **純函式**：`antigravity_plugin_files(track_path)` 回傳 `{相對路徑: 內容字串}`（plugin.json /
  hooks.json），不做 I/O；薄 I/O 負責寫檔/建目錄/刪目錄。
- gemini config 目錄：預設 `~/.gemini/config`，可用環境變數覆寫（測試注入暫存目錄；沿用既有
  setup 以參數傳目錄的形態）。
- **解除安裝**：移除整個 `ai-sessions` plugin 目錄（我們獨有，**不需 merge、不碰其他 plugin**）。
  冪等：目錄不存在則無動作。
- **與 Claude/Codex 安裝獨立**：Antigravity 是獨立 plugin 目錄，與 bell/Codex 的單槽 notify
  無衝突。

## 4. ⚠️ 實作風險與 gating step（計畫第一步必做）

agy 是否會自動載入「不在 `~/.gemini/config/import_manifest.json` 內的新 plugin 目錄」的 hooks，
**尚未證實**（探針是改既有、已註冊的 superpowers plugin 來觀察）。

**計畫第一個任務必須先驗證**：建立 `ai-sessions` plugin 目錄後跑一次 agy，檢查 `~/.gemini/
antigravity-cli/log/cli-*.log` 是否出現 `Loaded hooks.json from .../plugins/ai-sessions/hooks.json`。

- **若自動載入** → 安裝只需建目錄 + 寫兩個檔。
- **若需 manifest 註冊** → 安裝再補一筆 `import_manifest.json` entry（或改用 `agy plugin` 指令），
  解除時一併還原。此分支於該驗證後在計畫中定案。

同一個 gating step 一併確認 **`Stop` 事件的 payload 欄位**：探針已證實 `PostToolUse` payload 帶
`conversationId` / `workspacePaths` / `transcriptPath`，但 `Stop` 的 payload 因 agy 當次卡住未乾淨
捕獲。計畫第一步用一次性 probe hook 確認 `Stop` 同樣帶 `conversationId` + `workspacePaths`；
若 `Stop` 缺 `conversationId`，則 antigravity id 一律改以 cwd 衍生（犧牲同 cwd 多 session 的精確性，
換取 running/idle 能歸屬到同一筆記錄）。

## 5. 永不崩潰（重申）

`track.sh` / `sessions-track` 對 antigravity 的所有路徑（壞 JSON、缺 `conversationId`、
`workspacePaths` 空、缺欄位）都 fallback 並 `exit 0`，絕不讓 agy 因狀態追蹤而報錯或中斷。

## 6. 測試策略

沿用 repo 慣例（純標準庫 `unittest`，`tests/test_sessions.py` 以 `importlib` 載入）。新增：

- antigravity 事件→狀態映射：`PostToolUse→running`、`Stop→idle`、未知→None。
- antigravity payload 解析：`conversationId`→id、`workspacePaths[0]`→cwd、缺 `conversationId` 時
  以 cwd 衍生、`workspacePaths` 為空/缺時 cwd 為空字串、壞 JSON 不拋例外。
- `antigravity_plugin_files(track_path)` 純函式：產出 plugin.json / hooks.json 內容正確、
  指令含 `antigravity PostToolUse` 與 `antigravity Stop`。
- setup apply/remove（薄 I/O）：在暫存 gemini config 目錄建立/移除 `ai-sessions` plugin，冪等。
- `track.sh` 子程序層級永不崩潰（壞輸入 → exit 0）。

## 7. 文件

雙語更新：

- `sessions/README.md` / `.en.md`：Antigravity 列為第三個追蹤來源；標明**狀態粒度（running + idle，
  無 waiting）**、安裝會新增一個 agy plugin（`~/.gemini/config/plugins/ai-sessions/`）、
  需 agy 支援 plugin hooks。
- 頂層 `README.md` / `.en.md`：sessions 段落補一句「支援 Claude / Codex / **Antigravity**」。
- `CHANGELOG.md`：記錄階段三。
- `CLAUDE.md`：sessions 元件說明補 antigravity 來源與 agy plugin 安裝方式。

## 8. 狀態模型（更新後全表）

| 事件 | 來源 | 狀態 | 備註 |
|------|------|------|------|
| `SessionStart` | Claude | `idle` | 建檔 |
| `UserPromptSubmit` | Claude | `running` | |
| `Notification` | Claude | `waiting` | 置頂 |
| `Stop` | Claude | `idle` | |
| `SessionEnd` | Claude | （刪檔） | |
| `agent-turn-complete` | Codex | `idle` | 僅此單一事件 |
| `PostToolUse` | **Antigravity** | `running` | 工作中（每次工具呼叫後） |
| `Stop` | **Antigravity** | `idle` | 一輪完成 |

Antigravity 無 `waiting`、無建檔/刪檔事件：記錄於首個 PostToolUse/Stop 延遲建立，靠 stale 逾時清理。
