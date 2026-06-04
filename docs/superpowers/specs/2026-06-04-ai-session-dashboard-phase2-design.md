# 設計：`sessions/` 階段二 — Ghostty 原生「一鍵切換」

> **狀態**：已核可，待寫實作計畫。
> **前置**：階段一（多 session 總覽儀表板）已完成並合併。
> **設計來源**：取代 `2026-06-04-ai-session-dashboard-design.md` 第 11 節的 tmux 方向（見 §8）。

## 1. 背景與決策

階段一交付了唯讀的多 session 總覽儀表板（`sessions/dashboard.py`，curses，每秒輪詢狀態檔）。
原設計的階段二假設「AI CLI 跑在 **tmux** 內」，靠 `select-window` 切換、`capture-pane` 預覽。

**但實際工作流是純 Ghostty 分頁、不經 tmux**，該前提不成立。重新探勘後發現：

- **Ghostty 1.3.1 內建完整 AppleScript 字典**（`/Applications/Ghostty.app/Contents/Resources/Ghostty.sdef`），
  開放列舉 terminal、讀每個 terminal 的 `working directory`，以及 `focus`（focus 一個 terminal
  並把它的視窗帶到最前）。
- 實測 `osascript` 能列出全部 terminal 的 `id` / `working directory` / `name`(標題)，且 `focus`
  指令一步完成「帶視窗到最前 + 選分頁 + focus surface」。

因此階段二改採 **Ghostty 原生 AppleScript** 路線：**零工作流改動**即可拿到階段二最核心的
「一鍵跳到正在等我的 session」。

**唯一取捨**：Ghostty 字典**無 `capture-pane` 對等指令**，故**不做即時預覽分頁內容**（次要功能，刻意捨棄）。

## 2. 範圍

**本 spec 的實作目標**：在 dashboard 選一列按 `Enter`，直接 focus 到該 AI session 所在的
Ghostty 分頁/視窗。

**不動既有資產**：

- 狀態檔格式與 `sessions/track.sh`、`sessions/sessions-track` **完全不動**（配對只用既有的
  `cwd` + `cli` 欄位，不新增欄位）。
- `sessions/install.sh`、`sessions/uninstall.sh`、`sessions/sessions-setup` **不動**
  （dashboard 仍手動啟動，階段二無新增安裝步驟）。

**範圍外（YAGNI，明確不納入）**：

- 即時預覽分頁內容（Ghostty 字典無對應指令）。
- 孤兒狀態檔清理強化（沿用階段一的時間戳 `stale` 標記即可）。
- tmux 底座（見 §8）。
- dashboard 啟動快捷鍵 / popup 整合。

## 3. 架構

新增薄邊界模組 `sessions/ghostty.py`，比照 repo 既有慣例（如 macOS App 的
`AntigravityUsageTextCapture` PTY 邊界 + 純解析分離）：subprocess 邊界不單測、純邏輯單測。

| 部分 | 職責 | 單測 |
|------|------|------|
| `list_terminals()` | 跑 `osascript` 列舉 Ghostty terminals → `[{"id","cwd","title"}]` | ❌ subprocess 邊界 |
| `focus_terminal(term_id)` | 跑 `osascript`：focus 該 terminal + activate Ghostty App | ❌ subprocess 邊界 |
| `pick_terminal(record, terminals)` | **純函式**：依 cwd + 標題啟發式選出最佳 terminal id（或 `None`） | ✅ |

`dashboard.py` 只在按 `Enter` 時呼叫一次 osascript（**不進 1 秒輪詢迴圈**，無效能負擔）。
輪詢迴圈維持階段一行為（只讀狀態檔）。

### 資料流

```
使用者在 dashboard 選一列，按 Enter
        │
        ▼
ghostty.list_terminals()  ──osascript──>  Ghostty AppleScript（列舉 terminal + cwd + 標題）
        │
        ▼
ghostty.pick_terminal(選中的 session record, terminals)   ← 純函式：cwd 過濾 + 標題啟發式
        │  回傳 terminal id（或 None）
        ▼
ghostty.focus_terminal(id) ──osascript──> Ghostty 把目標視窗帶到最前並 focus
        │
        ▼
dashboard 退到背景（仍續跑，可切回來）；失敗則狀態列顯示短訊息，不崩潰
```

## 4. 配對邏輯（`pick_terminal`，純函式）

輸入：一筆 session record（含 `cwd`、`cli`）、`list_terminals()` 回傳的 terminal 清單。
輸出：最佳 terminal `id` 字串，或 `None`。

步驟：

1. **cwd 過濾**：保留 `working directory` 等於 `record.cwd` 的 terminal（正規化尾斜線後比對）。
2. **標題啟發式去歧義**（同 cwd 多筆時）：把「標題看起來像路徑的」視為 shell 並**降權**——
   例如標題形如 `…/Dev/CMG/arcade-report`、`user@host: ~`、或等於 cwd 的縮寫/basename。
   偏好標題不像路徑的（Claude/Codex 會把任務摘要寫進標題，可與 shell / dev-server 區分）。
3. **回傳**：取最高分的 terminal id。若選不出明確 CLI 分頁（同分或全是 shell），**回傳同 cwd 的
   第一個**——focus 它等於把對的「視窗」帶到最前，仍是 90% 價值。
4. **無命中**：完全沒有 cwd 對應的 terminal → 回傳 `None`。

> 啟發式是 best-effort，文件須標明限制。配對鍵刻意只用 cwd + 標題（Ghostty 未在 terminal
> 環境變數注入可讀回的 surface id，且字典的 terminal 無 pid 屬性，故無精準鍵）。

## 5. 互動與「永不崩潰」

按鍵（dashboard）：

| 鍵 | 行為 | 變更 |
|----|------|------|
| `Enter` | **跳到該 session**：list → pick → focus；focus 後 dashboard 退背景（續跑） | 新增（取代原 Enter） |
| `c` | 複製路徑（`pbcopy`） | 由原 `Enter` 移來 |
| `j`/`k`/方向 | 移動游標 | 不變 |
| `q` | 離開 | 不變 |
| `r` | 手動刷新 | 不變 |

**永不崩潰鐵則**（對齊現有 dashboard 與 repo 全元件慣例）——下列情況**只在狀態列顯示一行
短訊息，絕不讓 TUI 崩潰或污染畫面**：

- `osascript` 不存在 / 非 macOS / Ghostty 沒開。
- **TCC 自動化權限被拒**：顯示「需到 系統設定›隱私權與安全性›自動化 授權」。
- `pick_terminal` 回 `None`（找不到對應分頁）：顯示「找不到對應分頁」。
- osascript 逾時或回傳非預期格式：吞掉並提示。

**權限**：首次跳轉觸發 macOS 自動化授權（「Ghostty 想控制 Ghostty」），核准一次即可；
拒絕則降級為提示訊息，不影響 dashboard 其餘功能。

## 6. 測試策略

沿用 repo 慣例（純標準庫 `unittest`，`tests/test_sessions.py` 以 `importlib` 載入連字號檔名模組）。

`pick_terminal` 純函式單測：

- 精準 cwd 命中（單一 terminal）→ 回該 id。
- 同 cwd 多 terminal、其中一個標題像 CLI 任務、其餘像 shell → 回 CLI 那個。
- 同 cwd 全是 shell-like 標題 → 回第一個（不崩潰、仍給可 focus 的 id）。
- 尾斜線 / 路徑正規化：`/foo` vs `/foo/` 視為相同。
- 無任何 cwd 對應 → 回 `None`。

osascript 邊界（`list_terminals` / `focus_terminal`）**不單測**（subprocess thin boundary，
對齊 `AntigravityUsageTextCapture` 不單測的慣例）。

## 7. 文件

雙語更新：

- `sessions/README.md`（繁中）+ `sessions/README.en.md`（英文）：新增階段二「一鍵切換」說明，標明
  **需 Ghostty 1.3+**、**首次需核准 macOS 自動化權限**、**無即時預覽（刻意取捨）**、
  **配對為 best-effort（cwd + 標題啟發式）**。
- 頂層 `README.md` / `README.en.md`：sessions 段落補一句「可一鍵切到目標 session（Ghostty 原生）」。
- `CHANGELOG.md`：記錄階段二。
- `CLAUDE.md`：sessions 元件說明補階段二與 `ghostty.py` 邊界。

## 8. 已評估、未採用：tmux 底座

原設計（`2026-06-04-ai-session-dashboard-design.md` §11）的 tmux 方向（`list-panes` 配對、
`select-window` 切換、`capture-pane` 預覽、tmux↔Ghostty BEL passthrough）**已評估但未採用**：

- 需把所有 AI CLI 改跑在 tmux 內，**改變每日工作流**，代價大於它多給的（pid 精準配對 + 預覽）。
- Ghostty 原生路線零工作流改動即覆蓋核心價值；唯一少的「即時預覽」屬次要。

保留此段為決策紀錄；未來若工作流改用 tmux，可另立 spec 重啟該路線。

## 9. 永不崩潰原則（重申，跨元件鐵則）

dashboard 與所有新增路徑**絕不拋出未捕捉例外**：osascript 呼叫、權限、配對、focus 全包在防護內，
任何失敗都 fallback 到「狀態列短訊息 + 繼續運作」，且 `curses.wrapper` 確保離開時還原終端機。
