# 通用化 provider 分組/合併機制（移除 Antigravity 特例）

- 日期：2026-06-17
- 範圍：`macos/AIUsageMonitor`（純內部重構，使用者可見行為零變化）

## 背景與問題

目前 provider 的「身分」是靠**字串解析 `ProviderSnapshot.shortName`**（`"AG"` 前綴約定）反推回 `UsageProviderID`，而「把同一 provider 的多張快照合併成一個 menu bar chip」的行為被寫死成只認 Antigravity。這個特例散落在三處：

- `UsageProviderID.isAntigravity(shortName:)` 與 `init?(shortName:)`（`UsageMonitorSettings.swift`）——用 `shortName.hasPrefix("AG")` 還原身分。
- `RemainingQuotaPresenter.collapsedForMenuBar`（`RemainingQuotaPresenter.swift`）——只對 AG-prefixed 快照做合併。
- `ProviderSnapshot`（`UsageModels.swift`）——只帶 `shortName`，不帶正規 provider 身分。

關鍵洞察：Claude/Codex 各只吐 1 張快照、Antigravity 吐 N 張。因此「需不需要合併」**等價於「這個 provider 是不是吐了多張快照」**——可變成通用結構性規則，不必為任何 provider 寫特例。

## 設計

### 1. 快照自帶身分

`ProviderSnapshot` 新增 `providerID: UsageProviderID`（必填）。快照身分明確帶著，不再靠 `shortName` 反推。`shortName` 退回純顯示/子群標籤用途（`"AGg"`、`"AGc"`、`"CC"`、`"CX"`）。`ProviderSnapshot.id` 仍沿用 `shortName`（不動 Identifiable 行為）。

### 2. 三處通用化

**`UsageMonitorSettings.menuBarSnapshots`**：直接讀身分，字串解析消失。
```swift
snapshots.filter { menuBarProviderIDs.contains($0.providerID) }
```

**`UsageProviderID` extension**：`isAntigravity(shortName:)` 與 `init?(shortName:)` **整個刪除**。AG 字串約定不再存在於任何地方。

**`RemainingQuotaPresenter.collapsedForMenuBar`**：改成通用 group-by-`providerID`：
- 依 `providerID` 分組，保留首次出現順序。
- 群只有 1 張 → 原樣保留（維持 CC/CX 兩個 window 都顯示）。
- 群有 >1 張 → 合併成一個 chip：`name`/`shortName` 取自 `providerID.displayName`/`.shortName`、window 取群內**最差**（剩餘最低）那個、`isAvailable` 為 OR、`plan` 取群內第一個。

### 3. 資料來源端設定身分

各 provider 建構快照時帶上 `providerID`：
- `ClaudeUsageProvider` → `.claudeCode`
- `CodexUsageProvider` → `.codex`
- `AntigravityUsageProvider` 每張卡 → `.antigravity`
- `DemoUsageSnapshotProvider` 與各測試的 `ProviderSnapshot(...)` 同步補上

## 測試

- 刪除 `UsageProviderID(shortName:)` 那組 expectation（`UsageMonitorSettingsTests.swift`）。
- `collapsedForMenuBar` 既有斷言不變（行為一致），建構快照補 `providerID`。
- **新增測試**：一個非 AG 的多快照 provider 也會被合併成單一 chip（證明通用性而非寫死 AG）。

## 不變量

- menu bar 與 dropdown 可見行為**完全一致**（純內部重構）。
- 「狀態列/選單列絕不崩潰」原則維持，新邏輯有 fallback。

## 不在本次範圍（YAGNI）

- UI 圖示層（`StatusMenuImageRenderer.drawIcon` / `SwiftUIComponents.BrandIconView`）仍用 `name.contains(...)` 字串判斷。那是獨立的字串耦合且有 generic fallback，留待下次。
- provider 層級的「宣告式合併策略」旗標（結構性規則已足夠）。
