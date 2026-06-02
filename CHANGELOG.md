# Changelog

本檔記錄所有值得注意的變更，格式依循 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)，
版本號採 [語意化版本](https://semver.org/lang/zh-TW/)。

All notable changes are documented here, following
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added 新增
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
- 安裝/移除腳本強化前置檢查與錯誤處理（檢查 `python3` 與來源檔、容忍非法 JSON、印出備份路徑）。
  Hardened installer/uninstaller (preflight checks, invalid-JSON tolerance, backup paths).

## [0.1.0]

### Added 新增
- 初版：Claude Code context 用量常駐狀態列（模型名 + 彩色進度條 + token 數）。
  Initial release: persistent Claude Code context-usage statusline.
