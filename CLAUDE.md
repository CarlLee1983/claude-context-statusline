# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 專案概述

讓 AI CLI 用量隨時可見、跑完有提示、多 session 一眼掌握的 macOS 小工具集，目前有四個元件：

1. **`ctx-statusline.py`**（原始核心）：Claude Code 狀態列工具，常駐顯示目前 session 的 context window 佔用程度。純標準庫、零相依，搭配 `install.sh` / `uninstall.sh` 與 `tests/test_ctx_statusline.py`。
2. **`macos/AIUsageMonitor`**：純 Swift 的 macOS 原生選單列 App，原生抓取 Claude 與 Codex 的速率限制（5h / 7d），每 5 分鐘自動刷新。
3. **`bell/`**：AI CLI 完成提示——AI CLI 跑完一輪時透過終端機 BEL 觸發 Ghostty 分頁/視窗標記。含 `bell/notify.sh`（BEL 發送器）、`bell/bell-setup`（合併邏輯）、`bell/install.sh` / `bell/uninstall.sh`；測試在 `tests/test_bell.py`。
4. **`sessions/`**：多 session 總覽儀表板——Claude Code hooks、Codex notify 與 Antigravity plugin 觸發 `sessions/track.sh` 寫 per-session JSON；`sessions/dashboard.py`（stdlib curses）每秒輪詢並渲染跨 session 的即時狀態（running / waiting / idle）。含 `sessions/notify.sh`（合併派發器，兼容 bell）、`sessions/install.sh` / `sessions/uninstall.sh`；測試在 `tests/test_sessions.py`。

> 各元件監看的資料不同：**ctx-statusline** 看的是單一 session 的 **context window** 用量；**原生 App** 看的是訂閱方案的 **速率限制（5h / 7d）剩餘額度**；**bell** 看的是「完成事件 → 終端機分頁標記」，不讀用量數字；**sessions** 看的是「所有 AI CLI session 目前的執行狀態」，不讀用量也不讀速率限制。

## 開發指令

```bash
# 跑測試（純標準庫 unittest，無需安裝相依）
python3 -m unittest discover -s tests -v

# 用模擬的 statusline JSON 餵入腳本，觀察輸出（會帶 ANSI 色碼）
echo '{"model":{"id":"claude-opus-4-8","display_name":"Opus 4.8"},"transcript_path":"/path/to/transcript.jsonl"}' | ./ctx-statusline.py

# 檢查 shell 腳本（注意：zsh 下別用未加引號的變數展開多檔，會不分詞；直接列檔最穩）
bash -n install.sh uninstall.sh bell/install.sh bell/uninstall.sh sessions/install.sh sessions/uninstall.sh sessions/track.sh sessions/notify.sh macos/AIUsageMonitor/Scripts/*.sh
shellcheck install.sh uninstall.sh bell/install.sh bell/uninstall.sh sessions/install.sh sessions/uninstall.sh sessions/track.sh sessions/notify.sh macos/AIUsageMonitor/Scripts/*.sh

# 安裝到 ~/.claude/（複製腳本 + 併入 settings.json，會自動備份）
# 可用 CLAUDE_CONFIG_DIR 指定其他設定目錄（測試安裝時很有用）
CLAUDE_CONFIG_DIR=$(mktemp -d) ./install.sh

# 移除
./uninstall.sh

# bell 完成提示：安裝（三邊設定：Claude / Codex / Ghostty）
./bell/install.sh
# bell 完成提示：個別測試
python3 -m unittest tests.test_bell -v

# sessions 多 session 總覽：安裝（兩邊設定：Claude / Codex）
./sessions/install.sh
# sessions 儀表板：以暫存目錄啟動（不讀真實狀態檔）
AI_SESSIONS_DIR=$(mktemp -d) ./sessions/dashboard.py
# sessions 個別測試
python3 -m unittest tests.test_sessions -v

# macOS 原生 App：測試與建置
cd macos/AIUsageMonitor && swift test
cd macos/AIUsageMonitor && ./Scripts/build-app.sh && open .build/AIUsageMonitor.app
```

驗證改動後，需**重新開啟一個 Claude Code session** 才會載入更新後的狀態列。`tests/` 因腳本名含連字號，用 `importlib` 依路徑載入模組（見測試檔開頭）。

## 架構重點

**資料流**：Claude Code 每次刷新狀態列時，把一段 JSON 從 **stdin** 餵給此腳本，內含 `model.id`、`model.display_name`、`transcript_path`。腳本算出 context 用量百分比，將一行字串寫到 **stdout** 即為狀態列內容。

**核心邏輯（`ctx-statusline.py`）**：
- `used_tokens()` 從 transcript（JSONL）**尾端往前**掃，找第一筆「非 sidechain 且含 `message.usage`」的記錄。已用 context = `input_tokens + cache_read_input_tokens + cache_creation_input_tokens`。
- 效率：大型 transcript 只讀尾端 `TAIL_BYTES`（預設 2MB）；尾端找不到且檔案曾被截斷時，才整檔回掃（涵蓋「近期全是 sidechain」的邊界）。
- 過濾 `isSidechain` 是刻意設計：只反映主 session 用量，與 Claude Code 內建 `/context` 的數字對齊。subagent 訊息不計入。
- `context_limit()` 以 `model.id` 是否含 `1m` 或 Fable 5 判斷上限（1,000,000 vs 200,000）。

**永不崩潰原則（關鍵不變量）**：狀態列指令絕不能拋例外或噴錯，否則會污染使用者畫面。因此每層都有防線——檔案讀取、JSON parse、`main()` 外層 try/except 全部 fallback 到「0% / 空進度條」。修改時務必維持這個性質：新增邏輯要包在防護內，不要讓任何路徑能逸出未捕捉的例外。

**安裝腳本的合併策略**：`install.sh` / `uninstall.sh` 不依賴 `jq`，而是內嵌 `/usr/bin/python3` heredoc 來安全地讀寫 `~/.claude/settings.json`——只增刪 `statusLine` 一個 key，**保留其餘既有設定**，且改動前一律備份成 `settings.json.bak.<timestamp>`。若 settings.json 不是合法 JSON 則中止不動。

### macOS 原生 App（`macos/AIUsageMonitor`）

- Swift Package（`swift-tools-version: 6.0`，macOS 14+），分兩個目標：可測試的純邏輯庫 `AIUsageMonitorCore` 與 AppKit 外殼 `AIUsageMonitorApp`。
- provider 各自負責一個來源：`ClaudeUsageProvider`（Keychain token → Anthropic usage 端點）、`CodexUsageProvider`（`codex app-server` JSON-RPC）、`AntigravityUsageProvider`（先 PTY 驅動 `agy /usage`，退回讀帳號檔 cooldown），由 `LiveUsageSnapshotProvider` 彙整成快照。
- `RemainingQuotaPresenter` 一律以「**剩餘**額度」決定顯示文字與狀態分級（非已用量）。
- Antigravity 取數：`AntigravityUsageTextCapture`（PTY thin boundary，不單測）+ `AntigravityUsageParser`（去 ANSI 解析面板）+ `AntigravityAccountsParser`（pure，帳號檔 cooldown）。注意 `AntigravityUsageParser.stripANSI` 必須用真實 ESC byte（`"\u{1B}"`）餵 ICU regex，不能用 raw string `\u{001B}`（ICU 不認得）。
- 開發指令：`cd macos/AIUsageMonitor && swift test`（測試）、`./Scripts/build-app.sh`（產 `.app` bundle，含 `LSUIElement`）、`./Scripts/install-app.sh`（build + 複製到 `/Applications`，可用 `APP_INSTALL_DIR` 覆寫、`APP_INSTALL_OPEN=0` 不自動開）。
- 開機啟動：選單的 **Launch at Login** 用原生 `SMAppService.mainApp`（macOS 13+）註冊登入項目；需安裝到固定路徑（`/Applications`）才穩定，故先 `install-app.sh` 再開。

### sessions 儀表板（`sessions/`）

- 兩層分離：hook 觸發層（`sessions/track.sh`，薄殼，永不崩潰）與顯示層（`sessions/dashboard.py`，stdlib curses，每秒輪詢）互不耦合。
- 狀態模型：`SessionStart → idle`、`UserPromptSubmit → running`、`Notification → waiting`、`Stop → idle`、`SessionEnd → 刪除記錄`；Codex `agent-turn-complete → idle`。排序 waiting > running > idle，30 分鐘未更新標 `(stale)`。
- `sessions/notify.sh`（合併派發器）：同時觸發 bell（BEL）與 sessions（寫狀態），可升級已有的 bell-only Codex notify。
- 階段二（Ghostty 原生）：`sessions/ghostty.py` 以 macOS `osascript` 橋接 Ghostty 1.3+
  AppleScript 字典——`pick_terminal`（純函式，cwd + 標題啟發式選分頁，單測）+
  `list_terminals` / `focus_terminal`（subprocess 薄邊界，不單測）。dashboard 的 `Enter`
  懶載入 `ghostty` 並 focus 到對應分頁；`c` 複製路徑。不做即時預覽（Ghostty 字典無對應指令）。
- 階段三（Antigravity）：`sessions-track` 新增 `antigravity` 來源（`PostToolUse`→`running`、
  `Stop`→`idle`；payload 取 `conversationId`/`workspacePaths[0]`）；`sessions-setup` 安裝一個
  專屬 agy plugin `~/.gemini/config/plugins/ai-sessions/`（plugin.json + hooks.json），
  解除即刪該目錄。gemini config 目錄可用 `GEMINI_CONFIG_DIR` 覆寫。

## 慣例

- 目標執行環境是 macOS 系統內建的 `/usr/bin/python3`（免額外安裝）；避免引入第三方套件或非標準庫相依。測試亦只用標準庫 `unittest`。
- 可調參數集中在 `ctx-statusline.py` 頂部常數：`BAR_WIDTH`、`WARN_PCT`(轉黃)、`CRIT_PCT`(轉紅)、`TAIL_BYTES`(尾端讀取量)。
- 文件採中英雙語：每處 `README.md`（繁中為主）都搭一份 `README.en.md`（英文）並同步更新——含頂層、`macos/AIUsageMonitor/`、`bell/` 與 `sessions/`。頂層 README 為四工具總覽，細節連到各子目錄 README。變更記於 `CHANGELOG.md`，貢獻規範見 `CONTRIBUTING.md`。
- 安裝/移除腳本支援 `CLAUDE_CONFIG_DIR` 覆寫設定目錄（預設 `~/.claude`）。
