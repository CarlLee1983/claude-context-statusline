# 多 session 總覽 — sessions/

**繁體中文** · [English](README.en.md)

同時跑多個 Ghostty 分頁的 AI CLI 時，隨時掌握「哪個 session 正在跑、哪個在等你輸入、哪個閒著」——搭配各 session 的工作目錄，以寬版 curses TUI 呈現。

> **與其他元件的差別**：`ctx-statusline` 看的是「目前 session 把 context window 用了多少」；
> 原生 App 與 SwiftBar 外掛看的是「訂閱方案的 5h/7d 速率限制還剩多少」；
> `bell` 看的是「完成事件 → 終端機分頁標記」；
> 本元件（sessions）看的是**跨 session 的即時狀態總覽**，不讀用量數字，也不讀速率限制。

## 架構

```
[Claude Code hooks]      [Codex notify]        [Antigravity plugin]
  SessionStart             agent-turn-complete    PostToolUse
  UserPromptSubmit               │                Stop
  Notification                   │                  │
  Stop / SessionEnd              │                  │
         │                       ▼                  ▼
         └────────────→  sessions/track.sh  (薄殼，永不崩潰)
                         │
                         ▼
              ~/.cache/ai-sessions/<id>.json   (可用 AI_SESSIONS_DIR 覆寫)
                         │
                         ▼
              sessions/dashboard.py  (stdlib curses，每秒輪詢)
```

**兩層分離**：hook 觸發層（各 CLI 的 hook/notify 配置）與顯示層（curses TUI）互不耦合。

## 狀態模型

| 事件 | 狀態變更 |
|------|----------|
| `SessionStart` | 建立記錄 → `idle` |
| `UserPromptSubmit` | → `running`（你在等 AI 回答） |
| `Notification` | → `waiting`（AI 在等你輸入） |
| `Stop` | → `idle` |
| `SessionEnd` | 刪除記錄 |
| Codex `agent-turn-complete` | → `idle` |
| Antigravity `PostToolUse` | → `running` |
| Antigravity `Stop` | → `idle` |

TUI 依此順序排列：`waiting`（最上）→ `running` → `idle`（最下）；同狀態內再依最新更新時間倒序。
超過 30 分鐘未更新的 session 標示為 `(stale)`。

## Codex 限制

Codex 只發出一種 notify 事件（`agent-turn-complete`），所以 Codex session 永遠只會顯示 `idle` + 最後完成時間，**不會有** `running` / `waiting` 狀態。

## Antigravity 支援與限制

Antigravity（`agy`，gemini-cli 系）以一個專屬 agy plugin 追蹤：安裝會建立
`~/.gemini/config/plugins/ai-sessions/`（`plugin.json` + `hooks.json`），把 `PostToolUse`
（工作中→`running`）與 `Stop`（完成→`idle`）導到 `track.sh`。

- **狀態粒度**：只有 `running` / `idle`，**沒有** `waiting`（agy 不送對應事件）。
- **無建檔/刪檔事件**：記錄於首個事件延遲建立，靠 `(stale)` 逾時清理（同 Codex）。
- **需求**：agy 支援 plugin hooks（`~/.gemini/config/plugins/*/hooks.json`）。
- **同步 hook**：`PostToolUse` 為同步（`async: false`），每次工具呼叫會等 `track.sh` 跑完（約 30ms）。

## 需求

- macOS，系統內建 `/usr/bin/python3`（免額外安裝）
- Claude Code、Codex 和/或 Antigravity（至少其一）

> tmux 不是必要條件（屬於階段二計畫，見下方）。

## 安裝

```bash
./sessions/install.sh
```

安裝腳本會做三件事（皆先備份、只增不刪、可重複執行）：

1. **Claude Code** `~/.claude/settings.json` — 在 `hooks.SessionStart`、`hooks.UserPromptSubmit`、`hooks.Stop`、`hooks.Notification`、`hooks.SessionEnd` 各加入 `sessions/track.sh claude`（以 command 比對，冪等；SessionEnd 觸發時會清除該 session 的狀態檔）
2. **Codex** `~/.codex/config.toml` — 在頂層加 `notify = ["/path/to/sessions/notify.sh", "codex"]`（詳見下方「Codex notify 合併派發器」）
3. **Antigravity** `~/.gemini/config/plugins/ai-sessions/` — 建立專屬 agy plugin（`plugin.json` + `hooks.json`），把 `PostToolUse`→`running`、`Stop`→`idle` 導到 `track.sh`（詳見上方「Antigravity 支援與限制」）

完成後：
- **重新開啟 Claude Code session** 讓 hooks 生效
- 開啟儀表板：`./sessions/dashboard.py`

覆寫設定目錄（測試/非標準路徑）：

```bash
CLAUDE_CONFIG_DIR=/path/to/claude ./sessions/install.sh
CODEX_HOME=/path/to/codex ./sessions/install.sh
GEMINI_CONFIG_DIR=/path/to/gemini ./sessions/install.sh
AI_SESSIONS_DIR=/path/to/state ./sessions/install.sh
```

## 移除

```bash
./sessions/uninstall.sh
```

從 Claude settings 移除五個事件的 hook，從 Codex config.toml 移除 notify 設定（皆留備份），並刪除 Antigravity 的 agy plugin 目錄 `~/.gemini/config/plugins/ai-sessions/`。

> **注意**：移除後 Codex 的 `notify` 整個消失，連 bell 的 BEL 提示也不再觸發。
> 若仍想保留 bell，移除後重跑 `./bell/install.sh` 還原 bell-only notify。

## Codex notify 合併派發器（選項 A）

Codex 的 `config.toml` 頂層只有一個 `notify` 槽，若你已裝 bell，那個槽被 `bell/notify.sh` 佔用。
`sessions/install.sh` 會以 `sessions/notify.sh` 取代它——這個腳本會**同時**呼叫 bell（送 BEL）與 sessions（寫狀態）。

| 安裝時的既有情況 | 安裝後行為 |
|-----------------|------------|
| 無 `notify` | 新增 `sessions/notify.sh` |
| `bell/notify.sh`（bell 元件管理的） | 升級為 `sessions/notify.sh`（兼容 bell 功能） |
| 其他自訂 `notify` | **略過**，提示手動指向 `sessions/notify.sh` |

移除時：Codex `notify` **整個移除**，而非還原為 `bell/notify.sh`。若要繼續使用 bell 的 Codex 提示，事後執行：

```bash
./bell/install.sh
```

## TUI 鍵位

| 鍵 | 動作 |
|----|------|
| `j` / `↓` | 往下移動 |
| `k` / `↑` | 往上移動 |
| `r` | 立即刷新 |
| `Enter` | 跳到選取 session 所在的 Ghostty 分頁（階段二，見下方） |
| `c` | 複製選取 session 的工作目錄路徑（`pbcopy`） |
| `q` | 離開 |

TUI 每秒自動輪詢狀態目錄；r 可強制立刻重讀。狀態欄用 **emoji + 形狀角標**雙重編碼（色盲友善）。

## 永不崩潰原則

- **`track.sh`**：任何失敗（含 `python3` 缺席、壞 JSON、磁碟錯誤）都吞掉並 `exit 0`，絕不讓狀態追蹤弄崩 host CLI。
- **`dashboard.py`**：用 `curses.wrapper` 包裹，任何例外離開前均還原終端機；`KeyboardInterrupt` 亦靜默吸收。

## 測試

```bash
python3 -m unittest tests.test_sessions -v
```

或一次跑全部測試：

```bash
python3 -m unittest discover -s tests -v
```

測試涵蓋：事件 → 狀態映射、`sanitize_id`、`merge_record`、`write_record` / `delete_record`、
Claude hook 合併（空檔/既有/冪等）、Codex dispatch 合併（無 notify / bell notify 升級 / 外來 notify 略過）、
dashboard 純邏輯（`load_records`、`sort_key`、`format_row`、`is_stale`、`humanize`）。

## 階段二：一鍵切換（Ghostty 原生）

在儀表板選一列按 `Enter`，直接 focus 到該 AI session 所在的 Ghostty 分頁/視窗。
`c` 鍵複製路徑。

- **需求**：Ghostty 1.3+（使用其內建 AppleScript 字典）。首次切換會跳出 macOS
  自動化授權（「Ghostty 想控制 Ghostty」），核准一次即可。
- **配對方式**：以 session 的工作目錄（cwd）對應 Ghostty 分頁；同一目錄有多個分頁時，
  以標題啟發式優先選出 CLI session 分頁（best-effort）。
- **限制**：不提供即時預覽分頁內容（Ghostty 字典無對應指令，刻意取捨）。
- **永不崩潰**：找不到分頁、權限被拒、Ghostty 沒開等情況只在底列顯示提示，不中斷 TUI。
