# AI Usage Monitor（原生選單列 App）

**繁體中文** · [English](README.en.md)

純 Swift 的 macOS 選單列 App，原生抓取 AI CLI 的即時用量狀態，本機運作、不需 Python runtime。
與 [SwiftBar 外掛](../../swiftbar/README.md) 看的是同一類「速率限制剩餘額度」資料，差別在這是
獨立的原生 App、透過 AppKit `NSStatusItem` 常駐選單列。

## 執行

要在選單列穩定顯示，建議建置並開啟本機 `.app` bundle：

```bash
cd macos/AIUsageMonitor
./Scripts/build-app.sh
open .build/AIUsageMonitor.app
```

只想直接除錯執行檔：

```bash
swift run AIUsageMonitorApp
```

App 以 accessory（`LSUIElement`）形式常駐選單列，不在 Dock 顯示；本機開發無需簽章或公證。

## 安裝與開機啟動

`.build/` 內的 bundle 每次重 build 會被覆蓋，不適合當常駐目標。要長期使用，建置後安裝到 `/Applications`：

```bash
cd macos/AIUsageMonitor
./Scripts/install-app.sh
```

腳本會：build → 關閉執行中的舊版 → 複製到 `/Applications/AIUsageMonitor.app` → 開啟。
覆寫安裝位置（例如沒有 `/Applications` 寫入權限時）：

```bash
APP_INSTALL_DIR="$HOME/Applications" ./Scripts/install-app.sh
```

**開機自動啟動**：點選單列圖示 → 勾選 **Launch at Login**。這用 macOS 原生 `SMAppService`
註冊登入項目（也會出現在 系統設定 → 一般 → 登入項目，可在那裡開關）。安裝到 `/Applications`
後路徑固定，註冊才穩定——所以請先 `install-app.sh` 再開這個開關。

## 目前涵蓋範圍

- **Claude Code 即時用量**：Keychain OAuth token → Anthropic usage 端點，取 5h / 7d 視窗。
- **Codex 即時用量**：`codex app-server` JSON-RPC rate limits，取 5h / 7d 視窗。
- **Antigravity 即時用量**：優先以 pseudo-TTY 驅動 `agy /usage` 取各模型可用 quota；
  取不到時退回讀本機 `~/.config/opencode/antigravity-accounts.json` 的 cooldown / ready 狀態。
  做法對齊 [SwiftBar 外掛](../../swiftbar/README.md)。
- **原生 AppKit 選單列 UI**：每 5 分鐘自動刷新，另提供手動「Refresh」。

## 架構

```
Sources/
├── AIUsageMonitorApp/          # 可執行目標（AppKit 外殼）
│   ├── AIUsageMonitorApp.swift        # App 進入點
│   ├── StatusMenuController.swift     # NSStatusItem、選單、自動刷新、Launch at Login
│   ├── StatusMenuImageRenderer.swift  # 選單列圖示繪製（剩餘 % + 狀態角標）
│   └── AntigravityLogo.swift          # Antigravity 官方品牌 logo（base64，與 SwiftBar 一致）
└── AIUsageMonitorCore/         # 純邏輯函式庫（可單元測試）
    ├── UsageModels.swift              # 正規化用量資料模型
    ├── UsageSnapshotProvider.swift    # provider 介面
    ├── LiveUsageSnapshotProvider.swift# 彙整各 provider 的即時快照
    ├── ClaudeUsageProvider.swift      # Claude：Keychain token → usage 端點
    ├── ClaudeUsageParser.swift        # 解析 Anthropic usage 回應
    ├── CodexUsageProvider.swift       # Codex：app-server JSON-RPC
    ├── CodexExecutableResolver.swift  # 在受限 PATH 下尋找 codex 執行檔
    ├── CodexRateLimitParser.swift     # 解析 Codex rate-limit 回應
    ├── AntigravityUsageProvider.swift # Antigravity：先 agy /usage、退回帳號檔 cooldown
    ├── AntigravityUsageTextCapture.swift # PTY 驅動 agy /usage 取面板文字（thin I/O 邊界）
    ├── AntigravityUsageParser.swift   # 解析 agy /usage 面板（去 ANSI → 可用 quota 視窗）
    ├── AntigravityAccountsParser.swift # 解析帳號檔 cooldown（pure）
    └── RemainingQuotaPresenter.swift  # 由「剩餘」額度決定顯示文字與狀態分級
```

設計上把所有可測試的邏輯放在 `AIUsageMonitorCore`，AppKit 外殼（`AIUsageMonitorApp`）只負責
UI 與排程。狀態分級一律以「**剩餘**額度」計算（而非已用量），與 SwiftBar 外掛的判斷一致。

## 測試

```bash
cd macos/AIUsageMonitor
swift test
```

測試集中在 `Tests/AIUsageMonitorCoreTests/`，涵蓋各 parser、Codex 執行檔解析與
`RemainingQuotaPresenter`。

## 疑難排解

- **選單列沒出現**：確認是以 `.app` bundle 開啟（`build-app.sh` 產出的版本含 `LSUIElement`）；
  直接 `swift run` 在某些情況下選單列圖示可能不穩定。
- **Claude 沒有資料**：確認已登入 Claude Code（Keychain 內有 `Claude Code-credentials`）、
  且可連線 `api.anthropic.com`。
- **Codex 沒有資料**：確認 `codex` 可在終端機執行；App 會嘗試常見安裝路徑來定位執行檔。

## 需求

- macOS 14+
- Swift 6 工具鏈（Xcode 或 Swift toolchain）
