# Antigravity 分區額度顯示

**日期**：2026-06-16
**範圍**：`macos/AIUsageMonitor` — Antigravity provider / parser / 選單渲染

## 背景與動機

Antigravity (`agy`) 的 `/usage` 面板已改版，現在把額度分成**兩個模型群組**，各有獨立的限制視窗：

```
Models & Quota

  Account: yashino538@gmail.com

GEMINI MODELS
  Models within this group: Gemini Flash, Gemini Pro

  Weekly Limit
    [███████████████████████████████████████░░░░░░░░░░░] 77.05%
    77% remaining · Refreshes in 59h 6m

  Five Hour Limit
    [██████████████████████████████████████████████████] 100.00%
    Quota available


CLAUDE AND GPT MODELS
  Models within this group: Claude Opus, Claude Sonnet, GPT-OSS

  Weekly Limit
    [░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░] 0.00%
    Refreshes in 40h 55m
```

兩個問題：

1. **現行 parser 已完全失效**：舊 `AntigravityUsageParser` 找的是 `"Model Quota"` 標題（現為 `"Models & Quota"`），且把每個 model 名稱當成一筆視窗。新格式是「兩群組 × 每組多個具名限制（Weekly / Five Hour）」，舊邏輯還會把 `GEMINI MODELS` 標題行誤判成一筆 77% 的視窗。
2. **使用者需求**：Gemini 模式與 Claude/GPT 兩組額度池**互相獨立**，混在同一條 bar 會誤導。需要在選單裡**拆成兩張獨立卡片**分開查看。

## 目標

- 解析新版 `agy /usage` 面板的兩個群組與各自的具名限制視窗。
- 在下拉選單把 Antigravity 拆成**兩張獨立卡片**（Gemini / Claude & GPT），各自逐條列出限制視窗。
- 選單列 (menu bar) 仍只佔一個 Antigravity chip，數字取兩區**最差（最低剩餘）**者。
- Provider 開關選單仍只有**一個** Antigravity 項目，同時控制兩張卡。

## 非目標 (YAGNI)

- 不為兩區做獨立開關，也不在 menu bar 顯示兩個 AG chip。
- 不改 Claude / Codex provider 的行為。
- 不解析 `Models within this group:` 裡列出的個別模型名稱（只用群組層級的限制視窗）。

## 設計

### 1. Parser 改寫：群組感知（`AntigravityUsageParser`）

`parse()` 回傳值由 `[UsageWindow]` 改為群組結構：

```swift
public struct ParsedGroup: Equatable, Sendable {
    public let title: String          // 顯示用群組名："Gemini" / "Claude & GPT"
    public let windows: [UsageWindow]
}

public static func parse(_ rawText: String, now: Date = .now) -> [ParsedGroup]
```

解析規則：

- **定位面板起點**：找 `"Models & Quota"`（`.backwards`）；找不到則退回對舊 `"Model Quota"` 的相容，再找不到就整段掃。
- **群組切分**：以**全大寫、且以 `MODELS` 結尾**的標題行作為群組邊界（`GEMINI MODELS`、`CLAUDE AND GPT MODELS`）。群組名對應：
  - `GEMINI MODELS` → `"Gemini"`
  - `CLAUDE AND GPT MODELS` → `"Claude & GPT"`
  - 其他 `… MODELS` → 後備：title-case 原文（例：`FOO BAR MODELS` → `"Foo Bar"`）。
- **群組內限制視窗**：在每個群組區段內，把非 bar、非百分比、非略過清單的行（如 `Weekly Limit`、`Five Hour Limit`）當作限制名稱；往後看數行（lookahead）抓：
  - **percent**：bar 行 `[…] 77.05%` 中的數字 = **剩餘**量 → `UsageWindow(percent:, kind: .available)`。
  - **resetAt**：`Refreshes in …` 倒數（沿用既有 `firstRefreshInterval`，支援 `1d 3h 46m 30s` 任意子集）→ `now + interval`；`Quota available` 則 `resetAt = nil`。
- **略過行**：`Account:`、`Models within this group:`、`Models & Quota`/`Model Quota` 標題、shortcuts/scroll/esc chrome、bar 行（含 `█`/`░`/`[`/`]`）、純百分比行。

ANSI 去除沿用既有 `stripANSI`（真實 ESC byte 餵 ICU regex 的既有作法不變）。

### 2. Provider 回傳多張 snapshot（`AntigravityUsageProvider`）

- **live 擷取成功且解析出群組**：每個 `ParsedGroup` 產生一張 `ProviderSnapshot`：
  - `name`：`"Antigravity · Gemini"` / `"Antigravity · Claude & GPT"`（`"Antigravity · " + group.title`）
  - `shortName`：`"AGg"` / `"AGc"`（規則：`"AG" + group.title` 首字小寫，需保證唯一；見下方 shortName 規則）
  - `plan`：`"agy /usage"`
  - `windows`：該組的限制視窗
- **擷取失敗 → 帳號檔後備**：維持現狀，回傳**單張** snapshot（name `"Antigravity"`、shortName `"AG"`、`AntigravityAccountsParser` 的 windows）。
- **完全不可用**：單張 `isAvailable = false` 的 `"AG"` snapshot（現狀）。

介面調整：新增

```swift
public func snapshots() async -> [ProviderSnapshot]
```

`AntigravityUsageProvider` 實作回傳 1～2 張。`LiveUsageSnapshotProvider` 針對 antigravity 槽呼叫 `snapshots()` 並把結果**攤平**進總清單（其餘 provider 仍各 1 張）。

為維持可注入測試，`LiveUsageSnapshotProvider` 持有 antigravity 的型別改為新的小協定：

```swift
public protocol MultiProviderSnapshotProviding: Sendable {
    func snapshots() async -> [ProviderSnapshot]
}
```

`AntigravityUsageProvider` 同時符合既有 `ProviderSnapshotProviding`（`snapshot()` 回傳陣列首張，供既有測試/相容）與 `MultiProviderSnapshotProviding`。

#### shortName 規則與唯一性

- 群組 shortName = `"AG" + 群組 title 的首個英數字元`（`Gemini → "AGg"`、`Claude & GPT → "AGc"`）。
- 若兩組首字碰撞，退回 `"AG" + index`（`"AG0"`、`"AG1"`）確保唯一——因 `ProviderSnapshot.id == shortName`，SwiftUI `ForEach` 需唯一 id。

### 3. 共用單一開關（`UsageMonitorSettings` / `UsageProviderID`）

`UsageProviderID(shortName:)` 解析規則改為：**任何 `"AG"` 開頭的 shortName 都對應 `.antigravity`**（`"AG"`、`"AGg"`、`"AGc"`、`"AG0"`…）。Claude (`"CC"`) / Codex (`"CX"`) 維持精確比對。

效果：

- `UsageMonitorSettings.menuBarSnapshots(from:)` 過濾時兩張 AG 卡同進同出。
- Provider 開關選單仍只列一個「Antigravity」(`.antigravity`)。

### 4. 卡片渲染：拆成兩張獨立卡（`StatusMenuView`）

- 移除 `ProviderCardView` 中 Antigravity 專屬的「合併成單一 bar / All models ready」特例（`isAntigravity` 分支與 `mergedAntigravityWindow` 用法）。
- 兩張 AG 卡各自走一般 provider 的逐條列出分支——`ForEach(snapshot.windows)` 顯示 `Weekly Limit`、`Five Hour Limit` 各一條 `UsageProgressBarView`。
- 品牌圖示：`BrandIconView` / `drawIcon` 既有判斷為 `name` 含 `"antigravity"`，`"Antigravity · Gemini"` 仍正確顯示 AG logo。
- 帳號檔後備那張單卡（name `"Antigravity"`）一樣走逐條列出（Claude / Gemini 兩條 `kind = .used` bar）；不再合併。

`RemainingQuotaPresenter.mergedAntigravityWindow` 若無其他使用者則移除（精簡）。

### 5. Menu bar 合併取最差（`StatusMenuImageRenderer` + `RemainingQuotaPresenter`）

新增 collapse 步驟，把同屬 Antigravity 家族的多張 snapshot 合成**一個** menu-bar 代表：

- 在 `RemainingQuotaPresenter` 新增純函式，例如：
  ```swift
  static func collapsedForMenuBar(_ snapshots: [ProviderSnapshot]) -> [ProviderSnapshot]
  ```
  將所有 `shortName` 以 `"AG"` 開頭者合併為一張代表 snapshot（`name = "Antigravity"`、`shortName = "AG"`），其 windows 取「跨兩區剩餘量最低」的那一個（讓 `primaryRemainingPercent` 反映最差）。其餘 provider 原樣保留、順序不變。
- `StatusMenuImageRenderer.renderStatus(for:)` 與 `RemainingQuotaPresenter.fallbackTitle(for:)` 先套用此 collapse，再產 chip / 文字。
- 結果：menu bar 只出現一個 AG chip，數字為兩區最緊者；warn/critical badge 依該最差值。

> 注意：collapse 只用於 menu bar 呈現；下拉選單仍用未合併的兩張卡。

## 元件邊界與資料流

```
agy /usage (PTY)  ──AntigravityUsageTextCapture──▶ raw text
                                                      │
                              AntigravityUsageParser.parse ─▶ [ParsedGroup]
                                                      │
        AntigravityUsageProvider.snapshots() ─▶ [ProviderSnapshot]  (1~2 張)
                                                      │
            LiveUsageSnapshotProvider.snapshots() ─▶ [ProviderSnapshot]  (攤平)
                                  │                                  │
            (下拉) StatusMenuView：每張 → 一張卡        (menu bar) collapsedForMenuBar → 1 張 AG chip
```

每個單元職責單一、可獨立測試：parser 純文字→群組；provider 群組→snapshot 並處理後備；presenter 純函式合併；view 純渲染。

## 錯誤處理 / 不變量

- Parser 對殘缺輸入（缺標題、缺 bar、缺 reset 行）回傳能解析到的群組，餘者略過，不丟例外。
- live 解析不出任何群組 → 視為擷取失敗，走帳號檔後備。
- 維持 provider「永不阻塞主執行緒」：擷取仍在 `Task.detached`。

## 測試計畫

`AIUsageMonitorCoreTests`：

- **`AntigravityUsageParserTests`（改寫）**：
  - 解析使用者實測樣本（兩群組、`Weekly`/`Five Hour`、`77.05%` + `Refreshes in 59h 6m`、`Quota available`、`0.00%` 純 `Refreshes in 40h 55m` 行）→ 群組數、群組名、各視窗 label/percent/resetAt 正確。
  - `GEMINI MODELS` / `Models within this group:` / `Account:` 不被誤判成視窗。
  - ANSI escape 去除、prompt chrome 略過（沿用既有案例改新格式）。
  - 對舊 `Model Quota` 標題的相容性（若保留）。
- **`AntigravityUsageProviderTests`（擴充）**：
  - live 成功 → 2 張 snapshot、name / shortName / windows 正確。
  - live 失敗 → 帳號檔後備單張。
  - shortName 首字碰撞 → 退回唯一 index。
- **`UsageMonitorSettingsTests`（擴充）**：`AGg`/`AGc` → `.antigravity`；`menuBarSnapshots` 兩卡同進同出。
- **`RemainingQuotaPresenterTests`（擴充）**：`collapsedForMenuBar` 把兩張 AG 併為一張、取最低剩餘；非 AG 不受影響；`fallbackTitle` 反映合併結果。

`AIUsageMonitorAppTests`：`StatusMenuImageRendererTests` 確認兩張 AG snapshot 進來只畫一個 AG chip、數字為最差值。

維持純標準工具鏈：`swift test`。

## 影響檔案

- `Sources/AIUsageMonitorCore/AntigravityUsageParser.swift`（改寫）
- `Sources/AIUsageMonitorCore/AntigravityUsageProvider.swift`（多張 snapshot + 新協定）
- `Sources/AIUsageMonitorCore/LiveUsageSnapshotProvider.swift`（攤平 antigravity）
- `Sources/AIUsageMonitorCore/UsageMonitorSettings.swift`（`UsageProviderID(shortName:)` AG 前綴對應）
- `Sources/AIUsageMonitorCore/RemainingQuotaPresenter.swift`（`collapsedForMenuBar`，移除 `mergedAntigravityWindow`）
- `Sources/AIUsageMonitorApp/StatusMenuView.swift`（移除 AG 合併特例）
- `Sources/AIUsageMonitorApp/StatusMenuImageRenderer.swift`（menu bar 套用 collapse）
- 對應 `Tests/`
- 文件：`macos/AIUsageMonitor/README.md` / `README.en.md`、頂層 `CHANGELOG.md`（雙語同步）
```
