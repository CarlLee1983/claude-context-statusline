# claude-context-statusline

**繁體中文** · [English](README.en.md)

一組讓 **AI CLI 用量隨時可見** 的 macOS 小工具。從最初的 Claude Code context 狀態列，
延伸出兩種在 macOS 選單列常駐顯示「訂閱速率限制剩餘額度」的方式：原生選單列 App 與 SwiftBar 外掛。

## 三個工具

| 工具 | 顯示位置 | 監看對象 | 相依 | 安裝 |
|------|----------|----------|------|------|
| [**ctx-statusline**](#1-context-狀態列ctx-statuslinepy) | Claude Code 狀態列 | 目前 session 的 **context window** 用量 | 系統 `python3`，零相依 | `./install.sh` |
| [**AI Usage Monitor（原生 App）**](macos/AIUsageMonitor/README.md) | macOS 選單列 | Claude Code + Codex + Antigravity 的 **速率限制**（5h / 7d 剩餘額度） | Swift 6 / macOS 14+ | `./Scripts/build-app.sh` |
| [**SwiftBar 外掛**](swiftbar/README.md) | macOS 選單列（透過 SwiftBar） | Claude Code + Codex（+ Antigravity）的 **速率限制** | SwiftBar + `python3`（Pillow 選用） | `./swiftbar/install.sh` |

> 兩類資料不同：**ctx-statusline** 看的是「單一 session 把 context window 用掉多少」；
> **原生 App** 與 **SwiftBar 外掛** 看的是「訂閱方案的 5 小時 / 7 天速率限制還剩多少」。

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
./Scripts/build-app.sh
open .build/AIUsageMonitor.app
```

---

## 3. SwiftBar 外掛（`swiftbar/`）

若你已在用 [SwiftBar](https://github.com/swiftbar/SwiftBar)，可用單檔 Python 外掛取得同樣的速率限制資訊：
選單列顯示 Claude Code 與 Codex（以及 Antigravity）的 5h / 7d 剩餘額度，下拉選單附進度條與 reset 時間。

完整安裝與設定請見 **[swiftbar/README.md](swiftbar/README.md)**。

---

## 開發

ctx-statusline 與 SwiftBar 外掛皆為純標準庫 Python，無需安裝相依。執行測試：

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
