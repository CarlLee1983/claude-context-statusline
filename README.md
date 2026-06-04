# claude-context-statusline

**繁體中文** · [English](README.en.md)

一組讓 **AI CLI 用量隨時可見、跑完有提示、多 session 一眼掌握** 的 macOS 小工具。從最初的 Claude Code context 狀態列，
延伸出在 macOS 選單列常駐顯示「訂閱速率限制剩餘額度」的原生選單列 App，
讓 AI CLI 跑完一輪時透過終端機 BEL 觸發 Ghostty 分頁標記的完成提示元件，
以及一次掌握所有 AI CLI session 狀態的跨 session 儀表板。

## 四個工具

| 工具 | 顯示位置 | 監看對象 | 相依 | 安裝 |
|------|----------|----------|------|------|
| [**ctx-statusline**](#1-context-狀態列ctx-statuslinepy) | Claude Code 狀態列 | 目前 session 的 **context window** 用量 | 系統 `python3`，零相依 | `brew install CarlLee1983/tap/ctx-statusline`（或 `./install.sh`） |
| [**AI Usage Monitor（原生 App）**](macos/AIUsageMonitor/README.md) | macOS 選單列 | Claude Code + Codex + Antigravity 的 **速率限制**（5h / 7d 剩餘額度） | Swift 6 / macOS 14+ | `brew install CarlLee1983/tap/ai-usage-monitor`（或 `./Scripts/install-app.sh`） |
| [**完成提示（bell/）**](bell/README.md) | Ghostty 分頁 / Dock | **完成事件 → 終端機分頁標記**（BEL） | 系統 `python3`、Ghostty | `./bell/install.sh` |
| [**Session 儀表板（sessions/）**](sessions/README.md) | 終端機 curses TUI | **跨 session 的即時狀態**（running / waiting / idle） | 系統 `python3` | `./sessions/install.sh` |

> 各元件監看的資料不同：**ctx-statusline** 看「單一 session 把 context window 用掉多少」；
> **原生 App** 看「訂閱方案的 5 小時 / 7 天速率限制還剩多少」；
> **bell** 看「AI CLI 何時跑完一輪 → 終端機分頁標記」，不讀用量數字；
> **sessions** 看「所有 AI CLI session 目前的執行狀態」，不讀用量數字也不讀速率限制。

---

## 用 Homebrew 一鍵安裝（推薦）

```bash
brew tap CarlLee1983/tap
brew install ctx-statusline ai-usage-monitor
```

安裝後各自跑一次設定（不會在安裝期間改你的設定檔）：

```bash
ctx-statusline-setup     # 併入 ~/.claude/settings.json，然後重開 Claude Code session
ai-usage-monitor         # 首次執行會把 App 裝到 ~/Applications 並啟動
```

只想裝其中一個？兩個 formula 可單獨 `brew install`。

---

## 1. Context 狀態列（`ctx-statusline.py`）

在 [Claude Code](https://docs.anthropic.com/en/docs/claude-code) 的狀態列常駐顯示目前 session 的 context window 佔用程度，一眼掌握還剩多少空間。

```
Opus 4.8 · [████░░░░░░] 39% · 78k/200k
```

- **模型名**（淡色）· **彩色進度條** · **已用 % · 已用/上限 token**
- 警示色：綠 `<70%`、黃 `70–85%`、紅 `≥85%`
- Context 上限自動判斷：`model.id` 含 `1m` → 1,000,000，否則 200,000
- 只反映主 session 用量（過濾 subagent / sidechain 訊息，與 `/context` 一致）
- 純標準庫、單檔、零相依；任何錯誤都不會中斷狀態列

### 需求

- macOS（使用系統內建的 `/usr/bin/python3`，免安裝）
- Claude Code

### 安裝

```bash
git clone https://github.com/CarlLee1983/claude-context-statusline.git
cd claude-context-statusline
./install.sh
```

安裝腳本會：

1. 複製 `ctx-statusline.py` 到 `~/.claude/hooks/`
2. 把 `statusLine` 區塊併進 `~/.claude/settings.json`（改動前自動備份成 `settings.json.bak.*`，並保留其他既有設定）

完成後**重新開啟一個 Claude Code session** 即可看到狀態列。

> 若你的 Claude Code 設定不在 `~/.claude`，可用 `CLAUDE_CONFIG_DIR` 指定：
> `CLAUDE_CONFIG_DIR=/path/to/config ./install.sh`

### 移除

```bash
./uninstall.sh
```

### 運作原理

Claude Code 每次更新狀態列時，會把一段 JSON 從 stdin 餵給狀態列指令，內含 `model.id` 與 `transcript_path`。本腳本：

1. 讀 `transcript_path`（JSONL），**從尾端往前**找第一筆非 sidechain 且含 `message.usage` 的記錄
2. 已用 context = `input_tokens + cache_read_input_tokens + cache_creation_input_tokens`
3. 百分比 = 已用 ÷ 模型上限

為效率考量，大型 transcript 只讀尾端 ~2MB；若尾端找不到（例如近期訊息全為 sidechain）才退回整檔掃描。

### 自訂

編輯 `~/.claude/hooks/ctx-statusline.py` 頂部常數：

| 常數 | 預設 | 說明 |
|------|------|------|
| `BAR_WIDTH` | `10` | 進度條寬度（字元數） |
| `WARN_PCT` | `70` | 達此 % 轉黃 |
| `CRIT_PCT` | `85` | 達此 % 轉紅 |
| `TAIL_BYTES` | `2_000_000` | 大型 transcript 只讀尾端的位元組數 |

改完重開 session 生效。

---

## 2. 原生選單列 App（`macos/AIUsageMonitor`）

純 Swift 的 macOS 選單列 App，原生抓取 Claude Code、Codex 與 Antigravity 的即時速率限制（5h / 7d），
在選單列顯示剩餘額度，每 5 分鐘自動刷新。不依賴 Python runtime，本機開發無需簽章或公證。

完整建置、架構與疑難排解請見 **[macos/AIUsageMonitor/README.md](macos/AIUsageMonitor/README.md)**。

```bash
cd macos/AIUsageMonitor
./Scripts/install-app.sh          # build + 安裝到 /Applications，並啟動
```

裝好後點選單列圖示 → 勾 **Launch at Login** 即可開機自動啟動（原生 `SMAppService`）。

---

## 3. 完成提示（`bell/`）

AI CLI 跑完一輪時，透過終端機 BEL 觸發 Ghostty 把分頁或視窗標記為「需要注意」——
切去別的 App 等 AI 回答時，Dock 圖示跳動提示你；回到視窗後分頁標題出現 🔔。
支援 Claude Code（Stop hook）與 Codex（notify），靜音純視覺，零相依。

完整安裝與架構說明請見 **[bell/README.md](bell/README.md)**。

```bash
./bell/install.sh
```

---

## 4. Session 儀表板（`sessions/`）

同時跑多個 Ghostty 分頁的 AI CLI 時，以 curses TUI 一次顯示所有 session 的即時狀態
（running / waiting / idle）及各 session 的工作目錄。追蹤 Claude Code、Codex 與
Antigravity 三種 AI CLI 的 session 狀態；純標準庫，不讀用量數字，不讀速率限制。

完整安裝與架構說明請見 **[sessions/README.md](sessions/README.md)**。

> 在 Ghostty 下還能於儀表板按 `Enter` 一鍵切到目標 session 的分頁（階段二，原生 AppleScript）。

```bash
./sessions/install.sh
./sessions/dashboard.py   # 開啟 TUI
```

---

## 開發

ctx-statusline 為純標準庫 Python，無需安裝相依。執行測試：

```bash
python3 -m unittest discover -s tests -v
```

手動驗證 ctx-statusline 輸出（會帶 ANSI 色碼）：

```bash
echo '{"model":{"id":"claude-opus-4-8","display_name":"Opus 4.8"},"transcript_path":"/path/to/transcript.jsonl"}' | ./ctx-statusline.py
```

原生 App 的測試：

```bash
cd macos/AIUsageMonitor && swift test
```

歡迎貢獻，請見 [CONTRIBUTING.md](CONTRIBUTING.md)；版本變更記於 [CHANGELOG.md](CHANGELOG.md)。

## 授權

[MIT](LICENSE)
