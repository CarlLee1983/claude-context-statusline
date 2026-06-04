# 設計：用不完就浪費（expiring-unused）提示

**日期**：2026-06-04
**範圍**：`macos/AIUsageMonitor`（原生選單列 App）
**狀態**：已通過設計確認，待 spec 過目

## 背景與動機

目前選單列 App 的狀態分級（`RemainingQuotaPresenter.tier`）**只看剩餘量**：剩越少越紅。這漏掉了另一個維度——**離 reset 還多久**。

使用者實際痛點（尤其週用量 7d）：「我額度還剩很多，但快 reset 了。」對訂閱制速率限制而言，window 一到 reset 就回滿，**這期沒用掉的剩餘額度等於白白浪費**。使用者希望在這種「用不完就浪費」的情境被特別提醒，趁 reset 前多跑一些。

這是與既有嚴重度**正交**的新訊號：嚴重度講「快不夠用」，這個提示講「快浪費掉」。

## 目標

- 當一個窗口「剩很多 + 快 reset」時，在該窗口的進度條上給出明確視覺提示。
- 純邏輯可單元測試、永不崩潰、不污染既有紅黃綠語意。

## 非目標（YAGNI）

- 不做 SwiftBar 外掛的對齊（列為後續第二階段）。
- 不做通用 reset 倒數（使用者只要「用不完就浪費」這一種情境）。
- 不在進度條上細分「正常會用掉 vs. 超出」的子區段——觸發時整段剩餘一律視為「快過期」。
- 不改 `UsageWindow` model，不動任何 provider/parser。

## 觸發條件（核心邏輯）

一個 `UsageWindow` 被標記為 **expiring-unused** 當且僅當以下三者**同時**成立：

1. **label 解得出週期**：從 label 解析固定窗口長度。
2. **剩餘量 ≥ 40%**：`RemainingQuotaPresenter.remainingPercent(for:) >= 40`。
3. **快 reset**：`0 < (resetAt − now) ≤ 週期 × 0.15`。reset 必須在未來；已過或無 `resetAt` 則不觸發。

實際門檻換算：
- `5h` 窗口：距 reset < 45 分鐘（5h × 0.15 = 0.75h）。
- `7d` 窗口：距 reset < 約 25.2 小時（7d × 0.15）。

常數集中宣告，便於調整：
- `EXPIRING_REMAINING_THRESHOLD = 40`（百分比）
- `EXPIRING_WINDOW_FRACTION = 0.15`

## 窗口長度偵測（方法 A：解析 label）

從 label 以 regex 解析「數字 + 單位」推出週期，純函式：

- 格式：`^(\d+)\s*([hdwm])$`，大小寫不敏感。
- 單位對應：`h` = 小時、`d` = 天、`w` = 週、`m` = 月（30 天近似）。
- 對應結果（`TimeInterval`，秒）：`"5h"` → 18000、`"7d"` → 604800。
- 解不出（如 Antigravity 的模型名 `"Gemini 3.5 Flash (Medium)"`、或 `"Requests"`）→ 回傳 `nil`，該窗口**靜默不觸發**。

**選此方法的理由**：剛好覆蓋使用者在意的 Claude/Codex 5h、7d 窗口（兩者皆以 `"5h"`/`"7d"` 為 label，且 `resetAt` 可靠）；零 model/provider 改動；Antigravity（共用冷卻池、無固定週期）天生不適用，優雅降級。

被否決的替代方案：
- (B) 在 `UsageWindow` 加 `windowDuration` 欄位並由各 provider 填值：最明確，但要動 model + 兩個 parser，且 Antigravity 無對應值，成本不划算。
- (C) 寫死 label→週期對照表：與 A 類似但較不彈性。

## 元件與介面

### Core：`RemainingQuotaPresenter`（既有，純邏輯，新增）

```swift
// 從 label 解析固定窗口長度；解不出回傳 nil。純函式、total。
static func windowDuration(forLabel label: String) -> TimeInterval?

// 判斷某窗口是否「剩很多 + 快 reset」。任何缺資料/不可解情況一律回傳 false。
static func isExpiringUnused(for window: UsageWindow, now: Date = .now) -> Bool
```

`RemainingTier` **不變**。expiring 狀態獨立，不併進嚴重度列舉。

### App：`UsageProgressBarView`（既有，調整渲染）

- 新增一個布林狀態（`isExpiringUnused`），於 `init(window:now:)` 由 `RemainingQuotaPresenter.isExpiringUnused` 計算。手動 `init` 維持可注入。
- 新增「快過期色」靛藍常數 `expiringColor`（Apple system indigo 系，例如 `Color(red: 88/255, green: 86/255, blue: 214/255)`），與紅/黃/綠不衝突。
- 渲染分支：
  - **未觸發**：完全維持現狀（依 `tier` 上紅/黃/綠，實心填滿）。
  - **觸發**：
    - 剩餘（填滿）區段底色 → `expiringColor`。
    - 在填滿區段上**疊對角斜線**紋理（clip 到同一圓角矩形）。
    - 右上「`% remaining`」文字顏色 → `expiringColor`。
    - 斜線為紋理線索，與顏色雙重編碼（色盲友善，呼應專案既有形狀角標慣例）。
- `detailText`（reset 時間那行）維持現狀，本期不加文字後綴。

### App：`DiagonalStripes`（新增，`SwiftUIComponents.swift`）

可重用的 `Shape`，在給定 rect 內畫等距平行對角線；以 `expiringColor` 的提亮/壓暗變體 `stroke`，疊在剩餘區段上。參數：線距、線寬、角度（預設 45°）。

## 資料流

`LiveUsageSnapshotProvider` 產生 `ProviderSnapshot` →（不變）→ `StatusMenuView` → `ProviderCardView` → 每個 `UsageWindow` 建 `UsageProgressBarView`。新增邏輯只發生在 `UsageProgressBarView.init(window:)` 呼叫 presenter 取得 `isExpiringUnused`，再據此切換渲染。無新增資料來源、無新增非同步路徑。

## 錯誤處理（永不崩潰不變量）

- `windowDuration` / `isExpiringUnused` 皆 total：label 不可解、`resetAt` 為 nil、時間為負，一律回傳 `nil` / `false`，不拋例外。
- 渲染分支在任何狀態下都有有效輸出，沿用既有「永不崩潰」設計。

## 測試（`RemainingQuotaPresenterTests`）

純邏輯單元測試（stdlib XCTest / swift test）：

`windowDuration(forLabel:)`：
- `"5h"` → 18000、`"7d"` → 604800、`"2w"` → 1209600。
- 大小寫 / 空白：`"7D"`、`"5 h"` 可解。
- 不可解：`"Gemini 3.5 Flash (Medium)"`、`"Requests"`、`""`、`"abc"` → `nil`。

`isExpiringUnused(for:now:)`：
- 5h 窗口、剩餘 55%、reset 在 30 分後 → `true`。
- 5h 窗口、剩餘 55%、reset 在 2 小時後 → `false`（未進末段 15%）。
- 7d 窗口、剩餘 55%、reset 在 20 小時後 → `true`。
- 剩餘 30%、reset 在 10 分後 → `false`（未達 40% 門檻）。
- **邊界**：剛好剩餘 40% → `true`（`>=`）；剛好距 reset = 週期 × 15% → `true`（`<=`）。
- reset 已過（時間為負）→ `false`。
- `resetAt == nil` → `false`。
- label 不可解（Antigravity 模型名）→ `false`。

`UsageProgressBarView` 的視覺渲染不單測（沿用專案 PTY/渲染薄邊界不單測的慣例）。

## 後續（不在本期）

- **SwiftBar 外掛對齊**：在 `swiftbar/ai-usage.60s.py` 對齊同一觸發邏輯，以文字/emoji 標記（如 `⏳ expiring`）呈現，符合「SwiftBar 對齊 presenter」慣例。
- 文件雙語更新（`macos/AIUsageMonitor/README.md` + `README.en.md`）、`CHANGELOG.md`。
