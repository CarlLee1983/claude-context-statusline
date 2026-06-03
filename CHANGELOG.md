# Changelog

本檔記錄所有值得注意的變更，格式依循 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)，
版本號採 [語意化版本](https://semver.org/lang/zh-TW/)。

All notable changes are documented here, following
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added 新增
- 原生 App 安裝腳本與開機啟動：`macos/AIUsageMonitor/Scripts/install-app.sh`（build → 關舊版 →
  複製到 `/Applications` → 啟動，可用 `APP_INSTALL_DIR` 覆寫）；選單新增 **Launch at Login** 開關，
  以原生 `SMAppService` 註冊登入項目。
  Native app installer + login launch: `Scripts/install-app.sh` (build → quit → copy to
  `/Applications` → open, `APP_INSTALL_DIR` override) plus a **Launch at Login** menu toggle backed
  by the native `SMAppService` API.
- SwiftBar 外掛一鍵安裝腳本（`swiftbar/install.sh`）：自動讀 SwiftBar 偏好的 plugin 目錄、
  symlink 外掛、`chmod +x` 並刷新；支援以位置參數 / `SWIFTBAR_PLUGIN_DIR` 覆寫目錄、
  `SWIFTBAR_INSTALL_COPY=1` 改用複製。
  One-shot SwiftBar installer (`swiftbar/install.sh`): auto-detects the plugin folder, symlinks
  the plugin, `chmod +x`, refreshes; folder override via arg / `SWIFTBAR_PLUGIN_DIR`, copy mode
  via `SWIFTBAR_INSTALL_COPY=1`.
- 原生 App 接上 Antigravity provider：優先以 pseudo-TTY 驅動 `agy /usage` 取各模型可用 quota，
  取不到時退回讀本機帳號檔 cooldown，做法對齊 SwiftBar 外掛；新增 `AntigravityUsageProvider`、
  `AntigravityUsageTextCapture`、`AntigravityAccountsParser`，並串進 `LiveUsageSnapshotProvider`。
  Wire Antigravity into the native app: drive `agy /usage` over a pseudo-TTY for per-model
  available quota, falling back to the local accounts-file cooldown, mirroring the SwiftBar plugin.
- SwiftBar 外掛（`swiftbar/ai-usage.60s.py`）：單檔 Python 在選單列顯示 Claude、Codex
  （與 Antigravity）的 5h / 7d 速率限制剩餘額度；可選 Pillow 膠囊圖示、兩段式快取退避、
  狀態色與形狀角標皆對齊原生 App。
  SwiftBar plugin (`swiftbar/ai-usage.60s.py`): single-file Python showing Claude,
  Codex (and Antigravity) 5h / 7d rate-limit headroom in the menu bar, with optional
  Pillow capsule icon, two-stage caching/backoff, and status colors aligned with the native app.
- 文件改寫成「工具集」總覽：頂層 `README.md` / `README.en.md` 並列三個工具，
  並為 `macos/AIUsageMonitor` 與 `swiftbar/` 補上中英雙語 README。
  Docs reworked into a toolkit overview: top-level `README` lists all three tools,
  with bilingual READMEs added for `macos/AIUsageMonitor` and `swiftbar/`.
- macOS 原生選單列 app（`macos/AIUsageMonitor`）：以原生 Swift 抓取 Claude 與 Codex 即時用量，
  選單列顯示剩餘額度,每 5 分鐘自動刷新(取代先前的 demo 假資料);Antigravity 暫時移除。
  Native macOS menu bar app: live Claude + Codex usage in native Swift with a
  5-minute auto-refresh (replaces demo data). Antigravity temporarily removed.
- 標準庫單元測試套件（`tests/`，22 個測試），可用 `python3 -m unittest discover -s tests` 執行。
  Stdlib unit-test suite (`tests/`, 22 tests).
- 安裝/移除腳本支援 `CLAUDE_CONFIG_DIR` 環境變數以指定設定目錄。
  Installer/uninstaller honor the `CLAUDE_CONFIG_DIR` env var.
- 大型 transcript 只讀尾端 `TAIL_BYTES`（預設 2MB），找不到才整檔回掃，提升狀態列刷新效率。
  Large transcripts read only the trailing `TAIL_BYTES` (2MB default) with a
  full-scan fallback, speeding up statusline refreshes.
- 英文版說明 `README.en.md`、`CONTRIBUTING.md`、本 `CHANGELOG.md`。
  English `README.en.md`, plus `CONTRIBUTING.md` and this `CHANGELOG.md`.
- 程式碼加入型別註解與 docstring 中英對照。
  Type hints and bilingual docstrings.

### Changed 變更
- 原生 App 的 Antigravity 選單列圖示改用官方品牌 logo（彩色漸層拱形，與 SwiftBar 外掛同一張
  base64 PNG），取代先前手繪的拱形近似。
  Native app's Antigravity menu-bar icon now uses the official brand logo (the same base64 PNG as
  the SwiftBar plugin), replacing the hand-drawn arch approximation.
- 安裝/移除腳本強化前置檢查與錯誤處理（檢查 `python3` 與來源檔、容忍非法 JSON、印出備份路徑）。
  Hardened installer/uninstaller (preflight checks, invalid-JSON tolerance, backup paths).

### Fixed 修正
- `AntigravityUsageParser` 的 ANSI 去除實際無效（raw string `\u{001B}` 不被 ICU regex 認得），
  導致真實 `agy /usage` 輸出夾帶逸出碼；改用真實 ESC byte 後可正確解析。
  `AntigravityUsageParser` ANSI stripping was a no-op (ICU doesn't read the raw-string
  `\u{001B}`); fixed to feed a real ESC byte so live `agy /usage` output parses cleanly.

## [0.1.0]

### Added 新增
- 初版：Claude Code context 用量常駐狀態列（模型名 + 彩色進度條 + token 數）。
  Initial release: persistent Claude Code context-usage statusline.
