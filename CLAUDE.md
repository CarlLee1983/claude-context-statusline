# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 專案概述

Claude Code 狀態列工具：在狀態列常駐顯示目前 session 的 context window 佔用程度。整個工具是單一檔案 `ctx-statusline.py`，純標準庫、零相依，搭配 `install.sh` / `uninstall.sh` 兩個安裝腳本。

## 開發指令

無 build / lint / test 框架。以實際輸入手動驗證：

```bash
# 用模擬的 statusline JSON 餵入腳本，觀察輸出（會帶 ANSI 色碼）
echo '{"model":{"id":"claude-opus-4-8","display_name":"Opus 4.8"},"transcript_path":"/path/to/transcript.jsonl"}' | ./ctx-statusline.py

# 安裝到 ~/.claude/（複製腳本 + 併入 settings.json，會自動備份）
./install.sh

# 移除
./uninstall.sh
```

驗證改動後，需**重新開啟一個 Claude Code session** 才會載入更新後的狀態列。

## 架構重點

**資料流**：Claude Code 每次刷新狀態列時，把一段 JSON 從 **stdin** 餵給此腳本，內含 `model.id`、`model.display_name`、`transcript_path`。腳本算出 context 用量百分比，將一行字串寫到 **stdout** 即為狀態列內容。

**核心邏輯（`ctx-statusline.py`）**：
- `used_tokens()` 從 transcript（JSONL）**尾端往前**掃，找第一筆「非 sidechain 且含 `message.usage`」的記錄。已用 context = `input_tokens + cache_read_input_tokens + cache_creation_input_tokens`。
- 過濾 `isSidechain` 是刻意設計：只反映主 session 用量，與 Claude Code 內建 `/context` 的數字對齊。subagent 訊息不計入。
- `context_limit()` 以 `model.id` 是否含 `1m` 判斷上限（1,000,000 vs 200,000）。

**永不崩潰原則（關鍵不變量）**：狀態列指令絕不能拋例外或噴錯，否則會污染使用者畫面。因此每層都有防線——檔案讀取、JSON parse、`main()` 外層 try/except 全部 fallback 到「0% / 空進度條」。修改時務必維持這個性質：新增邏輯要包在防護內，不要讓任何路徑能逸出未捕捉的例外。

**安裝腳本的合併策略**：`install.sh` / `uninstall.sh` 不依賴 `jq`，而是內嵌 `/usr/bin/python3` heredoc 來安全地讀寫 `~/.claude/settings.json`——只增刪 `statusLine` 一個 key，**保留其餘既有設定**，且改動前一律備份成 `settings.json.bak.<timestamp>`。若 settings.json 不是合法 JSON 則中止不動。

## 慣例

- 目標執行環境是 macOS 系統內建的 `/usr/bin/python3`（免額外安裝）；避免引入第三方套件或非標準庫相依。
- 可調參數集中在 `ctx-statusline.py` 頂部常數：`BAR_WIDTH`、`WARN_PCT`(轉黃)、`CRIT_PCT`(轉紅)。
