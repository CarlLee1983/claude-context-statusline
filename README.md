# claude-context-statusline

在 [Claude Code](https://docs.anthropic.com/en/docs/claude-code) 的狀態列常駐顯示目前 session 的 context window 佔用程度，一眼掌握還剩多少空間。

```
Opus 4.8 · [████░░░░░░] 39% · 78k/200k
```

- **模型名**（淡色）· **彩色進度條** · **已用 % · 已用/上限 token**
- 警示色：綠 `<70%`、黃 `70–85%`、紅 `≥85%`
- Context 上限自動判斷：`model.id` 含 `1m` → 1,000,000，否則 200,000
- 只反映主 session 用量（過濾 subagent / sidechain 訊息，與 `/context` 一致）
- 純標準庫、單檔、零相依；任何錯誤都不會中斷狀態列

## 需求

- macOS（使用系統內建的 `/usr/bin/python3`，免安裝）
- Claude Code

## 安裝

```bash
git clone https://github.com/CarlLee1983/claude-context-statusline.git
cd claude-context-statusline
./install.sh
```

安裝腳本會：

1. 複製 `ctx-statusline.py` 到 `~/.claude/hooks/`
2. 把 `statusLine` 區塊併進 `~/.claude/settings.json`（改動前自動備份成 `settings.json.bak.*`，並保留其他既有設定）

完成後**重新開啟一個 Claude Code session** 即可看到狀態列。

## 移除

```bash
./uninstall.sh
```

## 運作原理

Claude Code 每次更新狀態列時，會把一段 JSON 從 stdin 餵給狀態列指令，內含 `model.id` 與 `transcript_path`。本腳本：

1. 讀 `transcript_path`（JSONL），**從尾端往前**找第一筆非 sidechain 且含 `message.usage` 的記錄
2. 已用 context = `input_tokens + cache_read_input_tokens + cache_creation_input_tokens`
3. 百分比 = 已用 ÷ 模型上限

## 自訂

編輯 `~/.claude/hooks/ctx-statusline.py` 頂部常數：

| 常數 | 預設 | 說明 |
|------|------|------|
| `BAR_WIDTH` | `10` | 進度條寬度（字元數） |
| `WARN_PCT` | `70` | 達此 % 轉黃 |
| `CRIT_PCT` | `85` | 達此 % 轉紅 |

改完重開 session 生效。

## 授權

MIT
