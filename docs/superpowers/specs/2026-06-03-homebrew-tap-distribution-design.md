# Homebrew tap 一鍵安裝 — 設計文件

- 日期：2026-06-03
- 範圍：為 `claude-context-statusline` 工具集（三個元件）建立 Homebrew tap，讓使用者用
  `brew install` 一鍵安裝，降低散佈與安裝門檻。
- 方案：**全部走「從源碼 build」的 formula**（不簽章、不公證、不需 CI、不需付費帳號）。

## 背景與動機

專案目前有三個元件，安裝方式各自獨立、皆需 clone 原始碼後手動跑腳本：

1. `ctx-statusline.py` — Claude Code context 狀態列（純標準庫 Python）。`./install.sh`。
2. `macos/AIUsageMonitor` — 原生 Swift 選單列 App。`./Scripts/install-app.sh`。
3. `swiftbar/ai-usage.60s.py` — SwiftBar 外掛。`./swiftbar/install.sh`。

目標是讓三者都能透過 Homebrew 安裝，符合使用者「以 Homebrew 為主要套件管理器」的習慣。

### 關鍵約束

- **App 目前未簽章**（debug 組態、bundle ID `local.ai-usage-monitor`），且專案明確不打算處理
  簽章/公證（無 Apple 開發者帳號）。
- **本機從源碼編譯的 binary 不會被加上 Gatekeeper quarantine 旗標**，因此「formula 從源碼 build」
  這條路可從根本繞過 Gatekeeper，不是 workaround。
- Homebrew 慣例：**`brew install` 期間不得修改 prefix 外的檔案**（即不可在安裝時動
  `~/.claude/settings.json` 或 SwiftBar plugin 目錄）。需要動使用者設定的步驟，一律改為
  安裝後由使用者主動執行的 setup 命令，並在 caveats 提示。

## 架構：兩個 repo

### 新 repo `CarlLee1983/homebrew-tap`（formula 權威來源）

```
Formula/ctx-statusline.rb
Formula/ai-usage-monitor.rb
Formula/swiftbar-ai-usage.rb
README.md
```

使用者體驗：

```bash
brew tap CarlLee1983/tap
brew install ctx-statusline ai-usage-monitor swiftbar-ai-usage
```

三個 formula 的 `url` 皆指向本專案 repo 的 **git tag 原始碼 tarball**（GitHub 自動產生，免手動
上傳 artifact）：

```
https://github.com/CarlLee1983/claude-context-statusline/archive/refs/tags/v0.2.0.tar.gz
```

### 本 repo `claude-context-statusline`（被 formula 安裝的工具 + 發版流程）

新增可在本地測試的小工具與發版腳本，formula 安裝時會用到。

## 元件設計

### 1. `ctx-statusline.rb`（純 Python、零相依）

- 安裝：`bin.install "ctx-statusline.py" => "ctx-statusline"`，另安裝新的 `ctx-statusline-setup`
  命令。
- **不在安裝期間改 settings.json**。caveats 提示使用者執行 `ctx-statusline-setup`：
  - 把 `statusLine` 區塊安全併入 `~/.claude/settings.json`，指向 brew 安裝的 `ctx-statusline`
    （`$(brew --prefix)/bin/ctx-statusline`）。
  - 沿用現有 `install.sh` 的安全合併策略：內嵌 `/usr/bin/python3` heredoc、只增刪 `statusLine`
    一個 key、保留其餘設定、改動前備份成 `settings.json.bak.<timestamp>`、非法 JSON 則中止不動。
  - 支援 `--remove`（對應 `uninstall.sh` 行為）。
  - 支援 `CLAUDE_CONFIG_DIR` 覆寫設定目錄。
- `test do`：餵假 statusline JSON 給 `ctx-statusline`，驗證輸出非空、含百分比格式。

### 2. `ai-usage-monitor.rb`（Swift App、build-from-source）

- `depends_on xcode: :build`（swift-tools-version 6.0 需 Xcode 16）。
- 建置：`swift build -c release --product AIUsageMonitorApp`，沿用現有 `build-app.sh` 的 bundle
  組裝邏輯，但改 **release** 組態，且 `CFBundleShortVersionString` 帶入 formula 的 `version`。
  產出 `AIUsageMonitor.app`，`prefix.install "AIUsageMonitor.app"`。
- 安裝 `bin/ai-usage-monitor` 啟動器：
  - 首次執行時把 `#{opt_prefix}/AIUsageMonitor.app` 複製/更新到 **`~/Applications/AIUsageMonitor.app`**
    （使用者可寫、免 sudo、路徑穩定）。`~/Applications` 路徑跨 `brew upgrade` 不變，
    `SMAppService.mainApp` 的 Launch-at-Login 註冊才可靠。
  - 接著 `open ~/Applications/AIUsageMonitor.app`。
  - `brew upgrade` 後重跑 `ai-usage-monitor` 即原地刷新到新版。
- 本機編譯 → 產物不帶 quarantine → 無 Gatekeeper 攔阻。
- caveats：說明執行 `ai-usage-monitor` 啟動（首次會安裝到 `~/Applications`），以及在選單勾
  Launch at Login 開機啟動。
- `test do`：驗證 `.app` bundle 結構存在（`Contents/MacOS/AIUsageMonitor` 可執行）。

### 3. `swiftbar-ai-usage.rb`（SwiftBar 外掛）

- 安裝 `ai-usage.60s.py` 到 prefix（`bin` 或 `libexec` + 提示路徑）。
- Pillow 維持**選用**（無則退回文字輸出），不強制相依。
- `depends_on cask: "swiftbar"` **不**強制；僅在 caveats 提示需要 SwiftBar。
- caveats：說明把外掛 symlink 進 SwiftBar 偏好的 plugin 目錄（沿用 `swiftbar/install.sh` 行為），
  並 `chmod +x` / 刷新。
- `test do`：直接執行外掛，驗證輸出非空且為 SwiftBar 純文字格式。

## 本 repo 的新增交付物

1. **`ctx-statusline-setup`**（新獨立**純標準庫 Python** 腳本，與既有元件的技術選型一致、且可用
   importlib 載入測試）：從現有 `install.sh` 抽出 settings.json 合併/備份/移除邏輯，可被 formula
   安裝、也可獨立執行。`install.sh` 改為呼叫此腳本（`exec` 或委派），共用同一份邏輯以避免重複。
2. **App 啟動器邏輯**：`bin/ai-usage-monitor` 的複製到 `~/Applications` + 啟動行為（可由
   formula 內嵌或抽成小腳本；複用 `install-app.sh` 的「關舊版 → 複製 → 開啟」概念，但來源為
   `opt_prefix`、目的為 `~/Applications`）。
3. **`Scripts/release.sh`**（發版腳本）：
   - 撞版本號：更新 `build-app.sh` / `Info.plist` 版本字串、`CHANGELOG.md`。
   - `git tag vX.Y.Z && git push --tags`。
   - 抓 tag tarball 算 `sha256`，更新 `homebrew-tap` 內三個 formula 的 `url` / `sha256` / `version`
     （透過本地 clone 或 `gh`），commit + push。
4. **文件更新**：見下節。
5. **測試**：`ctx-statusline-setup` 的標準庫 unittest（沿用 `tests/` 的 importlib 載入慣例），
   涵蓋合併、備份、移除、非法 JSON 中止、`CLAUDE_CONFIG_DIR` 覆寫。

## 文件

- 頂層 `README.md` / `README.en.md`：將 `brew tap` + `brew install` 列為**主要**安裝方式；
  現有 `./install.sh` / `install-app.sh` / `swiftbar/install.sh` 保留為「從源碼」替代路徑。
- 各子目錄 README（`macos/AIUsageMonitor/`、`swiftbar/`）同步補上 brew 安裝說明。
- `CHANGELOG.md`：Unreleased 區段新增 Homebrew tap 條目（中英雙語）。
- 新 `homebrew-tap` repo 的 `README.md`：列出三個 formula、安裝指令、回連本專案。

## 測試與驗證策略

- **Formula 層**：每個 formula 具 `test do` 區塊；`brew audit --strict` 與 `brew style` 須過關；
  本地 `brew install --build-from-source` 實測三者可裝、可跑。
- **程式層**：新增的 `ctx-statusline-setup` 以標準庫 unittest 覆蓋；既有 `swift test` 與 Python
  unittest 套件維持綠燈。
- **手動驗收**：在乾淨環境 `brew tap` → `brew install` → 跑 setup → 確認狀態列出現、選單列 App
  啟動、SwiftBar 外掛顯示。

## 不做的事（YAGNI / 明確排除）

- **不**做簽章/公證（無 Apple 開發者帳號；本機編譯已繞過 Gatekeeper）。
- **不**做 CI 預編譯 + cask 下載（方案 B）；保留為未來在取得開發者帳號後的升級路線，本設計不含。
- **不**強制相依 Pillow 或 SwiftBar cask。
- **不**在 `brew install` 期間自動改寫使用者設定檔。

## 待辦前置（實作時需確認）

- `CarlLee1983/homebrew-tap` repo 需先建立（空 repo + `Formula/` 目錄）。
- 需打第一個版本 tag（建議 `v0.2.0`，對應 CHANGELOG 的 Unreleased 內容）。
