# Changelog

本檔記錄所有值得注意的變更，格式依循 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)，
版本號採 [語意化版本](https://semver.org/lang/zh-TW/)。

All notable changes are documented here, following
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added 新增
- **sessions 階段三**：納入 Antigravity（`agy`）。安裝一個專屬 agy plugin
  （`~/.gemini/config/plugins/ai-sessions/`）把 `PostToolUse`→`running`、`Stop`→`idle`
  導到 `track.sh`。狀態粒度為 running/idle（無 waiting），靠 stale 逾時清理。
  **sessions phase 3**: add Antigravity (`agy`) tracking via a dedicated agy plugin
  (`~/.gemini/config/plugins/ai-sessions/`), routing `PostToolUse`→`running` and
  `Stop`→`idle` to `track.sh`. Status granularity is running/idle only (no waiting);
  cleaned up by the stale timeout.
- **sessions 階段二**：儀表板 `Enter` 一鍵切到目標 AI session 的 Ghostty 分頁
  （Ghostty 1.3+ 原生 AppleScript；`c` 改為複製路徑）。配對以 cwd + 標題啟發式，
  永不崩潰；不含即時預覽（刻意取捨）。
  **sessions phase 2**: dashboard `Enter` focuses the target AI session's Ghostty tab
  (Ghostty 1.3+ native AppleScript; `c` now copies the path). Matching uses cwd +
  title heuristic, never crashes; no live preview (deliberate trade-off).
- 第五元件 `sessions/`：多 session 總覽儀表板（階段一）。
  Claude Code hooks（SessionStart/UserPromptSubmit/Stop/Notification）與 Codex notify（agent-turn-complete）
  → `sessions/track.sh` 寫 per-session JSON 至 `~/.cache/ai-sessions/`（支援 `AI_SESSIONS_DIR` 覆寫）
  → `sessions/dashboard.py`（stdlib curses）每秒輪詢並渲染，狀態排序 waiting > running > idle，
  超過 30 分鐘未更新標 `(stale)`；j/k 移動、r 刷新、Enter 複製工作目錄（pbcopy）、q 離開。
  `sessions/notify.sh`（合併派發器）同時觸發 bell 與狀態追蹤，可升級已有的 bell-only Codex notify。
  `sessions/install.sh` / `sessions/uninstall.sh`（備份、只增不刪、冪等，支援 `CLAUDE_CONFIG_DIR` /
  `CODEX_HOME` / `AI_SESSIONS_DIR` 覆寫）；永不崩潰（track.sh 任何錯誤靜默 exit 0；curses 離開前還原終端機）；
  雙語 README（`sessions/README.md` / `sessions/README.en.md`）。
  tmux 階段二（tab 切換、capture-pane 預覽）列為後續。
  Fifth component `sessions/`: multi-session overview dashboard (phase 1).
  Claude Code hooks (SessionStart / UserPromptSubmit / Stop / Notification) and Codex notify
  (agent-turn-complete) → `sessions/track.sh` writes per-session JSON to `~/.cache/ai-sessions/`
  (`AI_SESSIONS_DIR` override supported) → `sessions/dashboard.py` (stdlib curses) polls every
  second and renders, sorting waiting > running > idle, marking entries stale after 30 min;
  j/k to move, r to refresh, Enter to copy working dir (pbcopy), q to quit.
  `sessions/notify.sh` (combined dispatcher) fans out to both bell and session tracking,
  and can upgrade an existing bell-only Codex notify.
  `sessions/install.sh` / `sessions/uninstall.sh` (backup, additive-only, idempotent;
  `CLAUDE_CONFIG_DIR` / `CODEX_HOME` / `AI_SESSIONS_DIR` overrides); never-crash guarantee
  (track.sh swallows all errors, exit 0; curses restores terminal on exit);
  bilingual READMEs. tmux phase 2 (tab switch, capture-pane preview) deferred.
- 第四元件 `bell/`：AI CLI 完成提示（Ghostty 分頁標記）。
  Claude Code Stop hook + Codex notify（過濾 `agent-turn-complete`）+ Ghostty `bell-features = title,attention`；
  `bell/notify.sh`（BEL 發送器，永不崩潰）、`bell/bell-setup`（純函式合併邏輯）、`bell/install.sh`／`bell/uninstall.sh`
  （三邊設定，備份、只增不刪、冪等，支援 `CLAUDE_CONFIG_DIR` / `CODEX_HOME` / `XDG_CONFIG_HOME` 覆寫）；
  27 項新增單元測試（`tests/test_bell.py`；全套 70 項）；雙語 README（`bell/README.md` / `bell/README.en.md`）。
  Antigravity 尚未支援，列為後續。
  Fourth component `bell/`: AI CLI completion bell (Ghostty tab marker).
  Claude Code Stop hook + Codex notify (filtering `agent-turn-complete`) + Ghostty `bell-features = title,attention`;
  `bell/notify.sh` (BEL emitter, never crashes), `bell/bell-setup` (pure-function merge logic),
  `bell/install.sh` / `bell/uninstall.sh` (three-way config: backup, additive-only, idempotent;
  `CLAUDE_CONFIG_DIR` / `CODEX_HOME` / `XDG_CONFIG_HOME` overrides);
  27 new unit tests (`tests/test_bell.py`; 70 total); bilingual READMEs. Antigravity support deferred.
- Homebrew tap 一鍵安裝：`brew tap CarlLee1983/tap` 後可 `brew install` 三個元件
  （`ctx-statusline` / `ai-usage-monitor` / `swiftbar-ai-usage`）。三者皆從源碼 build，
  無需簽章/公證；安裝期間不改使用者設定，改由 `ctx-statusline-setup`、`ai-usage-monitor`
  啟動器與 caveats 完成。新增 `ctx-statusline-setup`、`packaging/homebrew/Formula/*.rb`、
  `Scripts/release.sh`，並把 `build-app.sh` 參數化（`CONFIGURATION` / `APP_VERSION`）。
  One-shot Homebrew install: `brew tap CarlLee1983/tap` then `brew install` the three
  components. All build from source (no signing/notarization); install never touches user
  config — wiring is done by `ctx-statusline-setup`, the `ai-usage-monitor` launcher, and
  caveats. Adds `ctx-statusline-setup`, `packaging/homebrew/Formula/*.rb`, `Scripts/release.sh`,
  and parameterizes `build-app.sh` (`CONFIGURATION` / `APP_VERSION`).
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
- 原生 App 的 Claude 選單列圖示改用官方品牌 starburst（解析與 SwiftBar 外掛相同的 `CLAUDE_PATH`
  SVG 路徑，填暖橘 `(217,115,79)`），取代先前以八角星近似的程序化火花。新增可測試的純
  `SVGPathParser`（Core）+ `ClaudeLogo`（App）。
  Native app's Claude menu-bar icon now renders the official brand starburst (parsing the same
  `CLAUDE_PATH` SVG as the SwiftBar plugin, filled brand orange `(217,115,79)`), replacing the
  approximate 8-point procedural star. Adds a unit-tested pure `SVGPathParser` (Core) + `ClaudeLogo`
  (App).
- 原生 App 的 Antigravity 選單列圖示改用官方品牌 logo（彩色漸層拱形，與 SwiftBar 外掛同一張
  base64 PNG），取代先前手繪的拱形近似。
  Native app's Antigravity menu-bar icon now uses the official brand logo (the same base64 PNG as
  the SwiftBar plugin), replacing the hand-drawn arch approximation.
- 原生 App 展開 Antigravity 區改為合併成單一一條 Gemini 用量，不再逐一列出每個模型變體
  （Flash/Pro 各推理強度）。Antigravity 額度目前為通算共用池，故取剩餘最少的變體為代表
  （帶其 reset 時間）；全部 100% 時維持「All models ready」訊息。新增可測試的純
  `RemainingQuotaPresenter.mergedAntigravityWindow`。
  Native app's expanded Antigravity section now collapses into a single Gemini usage bar instead of
  listing every model variant (Flash/Pro reasoning tiers). Antigravity quota is currently a shared
  pool, so the binding (lowest-remaining) variant represents the group, carrying its reset instant;
  the "All models ready" line stays when every variant is full. Adds a unit-tested pure
  `RemainingQuotaPresenter.mergedAntigravityWindow`.
- 安裝/移除腳本強化前置檢查與錯誤處理（檢查 `python3` 與來源檔、容忍非法 JSON、印出備份路徑）。
  Hardened installer/uninstaller (preflight checks, invalid-JSON tolerance, backup paths).

### Fixed 修正
- Antigravity `agy /usage` 面板的「Refreshes in 2h 46m」倒數先前被整行丟棄，導致未滿額視窗
  在 dropdown 看不到刷新時間；現在解析倒數並換算成絕對 `resetAt`，選單會顯示刷新時間
  （滿額顯示 `Quota available` 仍無時間）。原生 App（`AntigravityUsageParser`）與 SwiftBar
  外掛（`_parse_antigravity_usage`）同步修正。
  The Antigravity `agy /usage` panel's "Refreshes in 2h 46m" countdown was being dropped, so
  partially-used windows showed no refresh time in the dropdown; it's now parsed into an absolute
  `resetAt`, surfacing the reset time in the menu (full windows still read `Quota available`).
  Fixed in both the native app (`AntigravityUsageParser`) and the SwiftBar plugin
  (`_parse_antigravity_usage`).
- `AntigravityUsageParser` 的 ANSI 去除實際無效（raw string `\u{001B}` 不被 ICU regex 認得），
  導致真實 `agy /usage` 輸出夾帶逸出碼；改用真實 ESC byte 後可正確解析。
  `AntigravityUsageParser` ANSI stripping was a no-op (ICU doesn't read the raw-string
  `\u{001B}`); fixed to feed a real ESC byte so live `agy /usage` output parses cleanly.

## [0.1.0]

### Added 新增
- 初版：Claude Code context 用量常駐狀態列（模型名 + 彩色進度條 + token 數）。
  Initial release: persistent Claude Code context-usage statusline.
