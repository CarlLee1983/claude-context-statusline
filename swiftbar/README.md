# AI Usage — SwiftBar 外掛

**繁體中文** · [English](README.en.md)

單檔 Python 的 [SwiftBar](https://github.com/swiftbar/SwiftBar) 外掛，在 macOS 選單列常駐顯示
各 AI CLI 的速率限制剩餘額度（5h / 7d）。與 [原生選單列 App](../macos/AIUsageMonitor/README.md)
看的是同一類資料，差別只在這個版本透過 SwiftBar 執行、用單一 `.py` 檔散布。

目前內建三個 provider：

- **Claude Code** — 讀 Keychain 內的 OAuth token，呼叫 Anthropic usage 端點，取 5h / 7d 用量。
- **Codex** — 透過 `codex app-server` 的 JSON-RPC（`account/rateLimits/read`）取 5h / 7d 用量。
- **Antigravity** — 沒有公開用量端點；讀本機 opencode 帳號檔，偵測到尚未過期的 rate-limit
  cooldown 時，以 100% 顯示該 quota pool 直到 reset；否則標示 `ready`。

> **永不崩潰、絕不外洩**：任一 provider 失敗只標記為「無法取得」，不影響其他工具與整體輸出；
> 任何路徑都不會把 token 印到選單列。

## 顯示方式

- **選單列**：若環境有 Pillow，渲染成膠囊圖示（扁平工具圖示 + 左下角狀態角標 + 剩餘 %）；
  否則退回純文字（例如 `AI  CC 61%  Cx 88%`）。
- **下拉選單**：每個工具一段，列出各視窗的進度條、剩餘 %、距 reset 倒數與 reset 絕對時間，
  最底下有「立即刷新」。
- **狀態色（依「剩餘」額度判斷，與原生 App 的 `RemainingQuotaPresenter` 對齊）**：
  綠（正常）、黃（剩餘 ≤ `WARN_REMAINING`）、紅（剩餘 ≤ `CRIT_REMAINING`）。
  狀態同時用形狀角標編碼（黃三角 / 紅驚嘆號），對色盲友善。
- **用不完就浪費（expiring-unused）提示**：當某視窗**剩很多卻快 reset**（剩餘
  ≥ `EXPIRING_REMAINING_THRESHOLD` 且距 reset ≤ 週期的 `EXPIRING_WINDOW_FRACTION`），該列轉**靛藍**
  並加 `⏳ 即將重置` 標記，提醒趁 reset 前用掉額度（週用量最常遇到）。週期由視窗 label（`5h`/`7d`）
  解析，Antigravity 模型名解不出故不觸發。與[原生 App](../macos/AIUsageMonitor/README.md) 同一邏輯。

## 需求

- [SwiftBar](https://github.com/swiftbar/SwiftBar)：`brew install --cask swiftbar`
- `python3`（系統內建的 `/usr/bin/python3` 即可）
- **選用**：[Pillow](https://pypi.org/project/Pillow/) — 用來在選單列畫膠囊圖示；
  沒有也能跑，只是退回文字模式。需安裝到「實際執行外掛的那個 `python3`」。
- 各 provider 視你實際使用而定：登入過的 Claude Code、可執行的 `codex`、opencode Antigravity 帳號檔。

## 安裝

> 用 Homebrew：`brew install CarlLee1983/tap/swiftbar-ai-usage`，再依 caveats 把外掛 symlink
> 進 SwiftBar 的 plugins 目錄。以下為手動安裝方式。

先安裝並啟動 SwiftBar（`brew install --cask swiftbar`），首次啟動時指定一個 **plugins 資料夾**。

### 一鍵安裝（建議）

```bash
./swiftbar/install.sh
```

腳本會自動讀取 SwiftBar 偏好裡的 plugin 目錄 → 把外掛 **symlink** 進去（方便日後 `git pull` 更新）
→ `chmod +x` → 請 SwiftBar 立即刷新。若讀不到目錄，會退回 `~/.config/swiftbar` 並提示你在
SwiftBar 設定中把 Plugin Folder 指向該處。

覆寫目錄或改用「複製」：

```bash
./swiftbar/install.sh /path/to/plugins          # 指定目錄（位置參數）
SWIFTBAR_PLUGIN_DIR=/path ./swiftbar/install.sh # 同上，用環境變數
SWIFTBAR_INSTALL_COPY=1 ./swiftbar/install.sh   # 用複製而非 symlink（分享到沒有本 repo 的機器）
```

### 手動安裝

```bash
ln -s "$PWD/swiftbar/ai-usage.60s.py" ~/.config/swiftbar/ai-usage.60s.py
chmod +x swiftbar/ai-usage.60s.py
```

放好後在 SwiftBar 選單按 **Refresh All**（或重開 SwiftBar）。

> 檔名中的 `60s` 是 SwiftBar 的刷新間隔慣例（每 60 秒重跑一次）。要改頻率就改檔名，
> 例如 `ai-usage.5m.py`。實際對端點的呼叫另有節流（見下方快取），不會因此猛打。

## 快取與節流

為避免每次刷新都打端點（甚至被回 429），每個 provider 有兩段式快取，存於 `~/.cache/ai-usage/`：

- **節流**：距上次嘗試未滿 `FETCH_TTL`（預設 300 秒）就直接用快取，不碰網路 / 子程序。
- **退避保值**：抓取失敗時，沿用「上次成功值」並標記「N 分前」，而不是直接顯示「—」。

## 自訂

編輯外掛頂部常數：

| 常數 | 預設 | 說明 |
|------|------|------|
| `WARN_REMAINING` | `40` | 剩餘額度 ≤ 此值轉黃 |
| `CRIT_REMAINING` | `10` | 剩餘額度 ≤ 此值轉紅 |
| `BAR_WIDTH` | `10` | 下拉選單進度條格數 |
| `FETCH_TTL` | `300` | 每個來源最短重抓間隔（秒） |
| `CACHE_DIR` | `~/.cache/ai-usage` | 快取目錄 |
| `TZ_OFFSET_HOURS` | `8` | 顯示 reset 絕對時間用的時區（預設 Asia/Taipei，UTC+8） |

## 新增 provider

外掛刻意設計成可擴充：每個工具就是一個 provider 函式，回傳「正規化」紀錄
（`name` / `short` / `icon` / `ok` / `five_hour` / `seven_day` 等）。要新增工具，
寫一個同樣形狀的函式並加進檔尾的 `PROVIDERS` 清單即可。

## 疑難排解

- **選單列只有文字、沒有膠囊圖示**：表示找不到 Pillow。把 Pillow 裝到實際執行外掛的
  `python3`（用 `head -1` 看 shebang，或在 SwiftBar 設定確認），或就接受文字模式。
- **Codex 顯示「無法取得」**：SwiftBar 的 PATH 較精簡，外掛已會嘗試 Homebrew、nvm/Volta/Herd
  等常見路徑與登入 shell 來找 `codex`；若仍找不到，確認 `codex` 可在終端機執行。
- **Claude 顯示「無法取得」**：確認已登入 Claude Code（Keychain 內有
  `Claude Code-credentials`），且網路可連 `api.anthropic.com`。
- **顯示「N 分前」**：代表正在沿用上次成功值（目前抓取失敗或仍在 `FETCH_TTL` 節流內），屬正常退避行為。
