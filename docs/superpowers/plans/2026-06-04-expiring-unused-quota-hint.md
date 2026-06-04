# Expiring-Unused Quota Hint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 macOS 原生選單列 App 的進度條上，對「剩很多 + 快 reset」的窗口加上靛藍 + 對角斜線的「用不完就浪費」提示。

**Architecture:** 純判斷邏輯（從 label 解析窗口週期 + 觸發判斷）放進既有的 `RemainingQuotaPresenter`，可單元測試且 total（永不拋例外）。`UsageProgressBarView` 依一個獨立的 `isExpiringUnused` 布林切換渲染，與既有 `RemainingTier` 嚴重度正交。新增一個可重用的 `DiagonalStripes` SwiftUI Shape 畫斜線紋理。

**Tech Stack:** Swift 6 / SwiftPM、swift-testing（`@Test` / `#expect`）、SwiftUI（AppKit menu bar app）。

---

## File Structure

- `macos/AIUsageMonitor/Sources/AIUsageMonitorCore/RemainingQuotaPresenter.swift`（修改）— 新增 `windowDuration(forLabel:)`、`isExpiringUnused(for:now:)` 與兩個常數。純邏輯。
- `macos/AIUsageMonitor/Tests/AIUsageMonitorCoreTests/RemainingQuotaPresenterTests.swift`（修改）— 新增上述兩函式的測試。
- `macos/AIUsageMonitor/Sources/AIUsageMonitorApp/SwiftUIComponents.swift`（修改）— 新增 `DiagonalStripes` Shape、`UsageProgressBarView` 加 `isExpiringUnused` 狀態與渲染分支。

所有指令在 repo 根目錄執行；Swift 測試/建置需先進入 `macos/AIUsageMonitor`（指令已內含 `cd`）。

---

### Task 1: `windowDuration(forLabel:)` — 從 label 解析窗口週期

**Files:**
- Modify: `macos/AIUsageMonitor/Sources/AIUsageMonitorCore/RemainingQuotaPresenter.swift`
- Test: `macos/AIUsageMonitor/Tests/AIUsageMonitorCoreTests/RemainingQuotaPresenterTests.swift`

- [ ] **Step 1: Write the failing test**

在 `RemainingQuotaPresenterTests.swift` 的 `struct RemainingQuotaPresenterTests {` 內、最後一個 `}` 之前，加入：

```swift
    @Test("parses fixed window duration from the window label")
    func parsesWindowDurationFromLabel() {
        #expect(RemainingQuotaPresenter.windowDuration(forLabel: "5h") == 5 * 3600)
        #expect(RemainingQuotaPresenter.windowDuration(forLabel: "7d") == 7 * 86_400)
        #expect(RemainingQuotaPresenter.windowDuration(forLabel: "2w") == 2 * 604_800)
        // case-insensitive and tolerant of an interior space
        #expect(RemainingQuotaPresenter.windowDuration(forLabel: "7D") == 7 * 86_400)
        #expect(RemainingQuotaPresenter.windowDuration(forLabel: "5 h") == 5 * 3600)
        // unparseable labels yield nil (Antigravity model names, free-form, empty)
        #expect(RemainingQuotaPresenter.windowDuration(forLabel: "Gemini 3.5 Flash (Medium)") == nil)
        #expect(RemainingQuotaPresenter.windowDuration(forLabel: "Requests") == nil)
        #expect(RemainingQuotaPresenter.windowDuration(forLabel: "") == nil)
        #expect(RemainingQuotaPresenter.windowDuration(forLabel: "abc") == nil)
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd macos/AIUsageMonitor && swift test --filter parsesWindowDurationFromLabel`
Expected: 編譯失敗 / FAIL — `windowDuration` 尚未定義（`type 'RemainingQuotaPresenter' has no member 'windowDuration'`）。

- [ ] **Step 3: Write minimal implementation**

在 `RemainingQuotaPresenter.swift` 的 `public enum RemainingQuotaPresenter {` 之後、`tier(forRemaining:)` 之前插入：

```swift
    /// Remaining-quota threshold (percent) above which an imminent reset is
    /// treated as "use it or lose it". See `isExpiringUnused`.
    public static let expiringRemainingThreshold = 40

    /// Fraction of the window length that counts as "soon to reset".
    public static let expiringWindowFraction = 0.15

    /// Parses a fixed window length from a label like "5h" / "7d" / "2w".
    /// Pure and total: free-form labels (e.g. Antigravity model names) and
    /// anything unrecognized yield nil. Unit map: h=hour, d=day, w=week,
    /// m=30-day month.
    public static func windowDuration(forLabel label: String) -> TimeInterval? {
        let unitSeconds: [Character: TimeInterval] = [
            "h": 3600, "d": 86_400, "w": 604_800, "m": 2_592_000
        ]
        let trimmed = label.trimmingCharacters(in: .whitespaces).lowercased()
        guard let unit = trimmed.last, let seconds = unitSeconds[unit] else { return nil }
        let numberPart = trimmed.dropLast().trimmingCharacters(in: .whitespaces)
        guard let value = Int(numberPart), value > 0 else { return nil }
        return Double(value) * seconds
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd macos/AIUsageMonitor && swift test --filter parsesWindowDurationFromLabel`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add macos/AIUsageMonitor/Sources/AIUsageMonitorCore/RemainingQuotaPresenter.swift macos/AIUsageMonitor/Tests/AIUsageMonitorCoreTests/RemainingQuotaPresenterTests.swift
git commit -m "feat: 解析窗口 label 推算固定週期長度"
```

---

### Task 2: `isExpiringUnused(for:now:)` — 觸發判斷

**Files:**
- Modify: `macos/AIUsageMonitor/Sources/AIUsageMonitorCore/RemainingQuotaPresenter.swift`
- Test: `macos/AIUsageMonitor/Tests/AIUsageMonitorCoreTests/RemainingQuotaPresenterTests.swift`

- [ ] **Step 1: Write the failing test**

在 `RemainingQuotaPresenterTests.swift` 的 `struct` 內、最後一個 `}` 之前，加入：

```swift
    @Test("flags a window as expiring-unused only when quota is high and reset is imminent")
    func flagsExpiringUnusedWindows() {
        let now = Date(timeIntervalSince1970: 1_800_000_000)
        // helper: a used window resetting `seconds` from now
        func window(_ label: String, used: Double, resetIn seconds: TimeInterval) -> UsageWindow {
            UsageWindow(label: label, percent: used, kind: .used, resetAt: now.addingTimeInterval(seconds))
        }

        // 5h window, 55% remaining (used 45%), reset in 30 min → within 45-min tail → true
        #expect(RemainingQuotaPresenter.isExpiringUnused(for: window("5h", used: 45, resetIn: 30 * 60), now: now) == true)
        // 5h window, same quota, reset in 2 h → outside the 15% tail → false
        #expect(RemainingQuotaPresenter.isExpiringUnused(for: window("5h", used: 45, resetIn: 2 * 3600), now: now) == false)
        // 7d window, 55% remaining, reset in 20 h → within ~25.2 h tail → true
        #expect(RemainingQuotaPresenter.isExpiringUnused(for: window("7d", used: 45, resetIn: 20 * 3600), now: now) == true)
        // remaining 30% (< 40 threshold), reset imminent → false
        #expect(RemainingQuotaPresenter.isExpiringUnused(for: window("5h", used: 70, resetIn: 10 * 60), now: now) == false)
        // boundary: exactly 40% remaining (used 60) → true (>=)
        #expect(RemainingQuotaPresenter.isExpiringUnused(for: window("5h", used: 60, resetIn: 10 * 60), now: now) == true)
        // boundary: reset exactly at duration*0.15 (5h → 2700s) → true (<=)
        #expect(RemainingQuotaPresenter.isExpiringUnused(for: window("5h", used: 45, resetIn: 2700), now: now) == true)
        // reset already passed → false
        #expect(RemainingQuotaPresenter.isExpiringUnused(for: window("5h", used: 45, resetIn: -600), now: now) == false)
        // no resetAt → false
        #expect(RemainingQuotaPresenter.isExpiringUnused(for: UsageWindow(label: "5h", percent: 45, kind: .used), now: now) == false)
        // unparseable label (Antigravity model name) → false
        #expect(RemainingQuotaPresenter.isExpiringUnused(for: UsageWindow(label: "Gemini 3.5 Flash (Medium)", percent: 40, kind: .available, resetAt: now.addingTimeInterval(60)), now: now) == false)
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd macos/AIUsageMonitor && swift test --filter flagsExpiringUnusedWindows`
Expected: 編譯失敗 / FAIL — `isExpiringUnused` 尚未定義。

- [ ] **Step 3: Write minimal implementation**

在 `RemainingQuotaPresenter.swift` 內、`windowDuration(forLabel:)`（Task 1 新增）之後插入：

```swift
    /// True when a window has lots of quota left AND resets soon — the unused
    /// quota will roll over (be "wasted") on reset. Orthogonal to `RemainingTier`.
    /// Total: missing reset, past reset, or unparseable window length → false.
    public static func isExpiringUnused(for window: UsageWindow, now: Date = .now) -> Bool {
        guard let duration = windowDuration(forLabel: window.label) else { return false }
        guard remainingPercent(for: window) >= expiringRemainingThreshold else { return false }
        guard let resetAt = window.resetAt else { return false }
        let timeUntilReset = resetAt.timeIntervalSince(now)
        guard timeUntilReset > 0 else { return false }
        return timeUntilReset <= duration * expiringWindowFraction
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd macos/AIUsageMonitor && swift test --filter flagsExpiringUnusedWindows`
Expected: PASS。

- [ ] **Step 5: Run the full Core suite to confirm no regressions**

Run: `cd macos/AIUsageMonitor && swift test`
Expected: 全部 PASS（含既有的 presenter / parser 測試）。

- [ ] **Step 6: Commit**

```bash
git add macos/AIUsageMonitor/Sources/AIUsageMonitorCore/RemainingQuotaPresenter.swift macos/AIUsageMonitor/Tests/AIUsageMonitorCoreTests/RemainingQuotaPresenterTests.swift
git commit -m "feat: 新增 expiring-unused 觸發判斷(高剩餘+快reset)"
```

---

### Task 3: `UsageProgressBarView` 渲染 + `DiagonalStripes` Shape

此任務為 SwiftUI 渲染，沿用專案「渲染薄邊界不單測」慣例，以 `swift build` + 預覽/實機目視驗證。

**Files:**
- Modify: `macos/AIUsageMonitor/Sources/AIUsageMonitorApp/SwiftUIComponents.swift`（新增 `DiagonalStripes`，改寫 `UsageProgressBarView` lines 173-264）

- [ ] **Step 1: 新增 `DiagonalStripes` Shape**

在 `SwiftUIComponents.swift` 檔尾（最後一個 `}` 之後）加入：

```swift
// 7. Diagonal stripe texture — overlaid on an "expiring-unused" quota segment.
// A pattern cue (color-blind friendly) that pairs with the indigo at-risk color.
struct DiagonalStripes: Shape {
    var spacing: CGFloat = 5

    func path(in rect: CGRect) -> Path {
        var path = Path()
        // 45° lines sweeping bottom-left → top-right, stepping across the rect.
        var x = rect.minX - rect.height
        while x < rect.maxX {
            path.move(to: CGPoint(x: x, y: rect.maxY))
            path.addLine(to: CGPoint(x: x + rect.height, y: rect.minY))
            x += spacing
        }
        return path
    }
}
```

- [ ] **Step 2: 改寫 `UsageProgressBarView` — 加入 `isExpiringUnused` 狀態與 at-risk 色**

將現有的 `public struct UsageProgressBarView: View { ... }`（檔案中 `// 6. Usage Progress Bar View` 之後整段）完整替換為：

```swift
// 6. Usage Progress Bar View
public struct UsageProgressBarView: View {
    public let label: String
    public let remainingPercent: Int
    public let usedPercent: Int
    public let tier: RemainingTier
    public let detailText: String
    public let isExpiringUnused: Bool

    public init(
        label: String,
        remainingPercent: Int,
        usedPercent: Int,
        tier: RemainingTier,
        detailText: String,
        isExpiringUnused: Bool = false
    ) {
        self.label = label
        self.remainingPercent = remainingPercent
        self.usedPercent = usedPercent
        self.tier = tier
        self.detailText = detailText
        self.isExpiringUnused = isExpiringUnused
    }

    public init(window: UsageWindow, now: Date = .now) {
        self.label = window.label
        let remaining = RemainingQuotaPresenter.remainingPercent(for: window)
        self.remainingPercent = remaining
        self.usedPercent = window.kind == .used ? Int(window.percent.rounded()) : (100 - remaining)
        self.tier = RemainingQuotaPresenter.tier(forRemaining: remaining)
        self.isExpiringUnused = RemainingQuotaPresenter.isExpiringUnused(for: window, now: now)

        let resetText = window.resetAt.map { resetAt in
            if Calendar.current.isDate(resetAt, inSameDayAs: now) {
                return "reset " + resetAt.formatted(date: .omitted, time: .shortened)
            } else {
                return "reset " + resetAt.formatted(date: .abbreviated, time: .shortened)
            }
        }

        if let reset = resetText {
            self.detailText = reset
        } else {
            self.detailText = "No reset scheduled"
        }
    }

    // Indigo "expiring" color — distinct from the red/yellow/green severity scale.
    private static let expiringColor = Color(red: 88 / 255, green: 86 / 255, blue: 214 / 255)

    private var tierColor: Color {
        switch tier {
        case .good:
            return Color(red: 52 / 255, green: 199 / 255, blue: 89 / 255) // Apple Green
        case .warn:
            return Color(red: 255 / 255, green: 204 / 255, blue: 0 / 255) // Apple Yellow/Amber
        case .critical:
            return Color(red: 255 / 255, green: 59 / 255, blue: 48 / 255) // Apple Red
        }
    }

    // When expiring-unused, the filled (remaining) segment switches to indigo
    // and gains a diagonal-stripe overlay; otherwise it follows the severity tier.
    private var barColor: Color {
        isExpiringUnused ? Self.expiringColor : tierColor
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(label)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(.primary)
                Spacer()
                Text("\(remainingPercent)% remaining")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundColor(barColor)
            }

            // Progress Bar
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 3)
                        .fill(Color.primary.opacity(0.1))

                    RoundedRectangle(cornerRadius: 3)
                        .fill(barColor)
                        .frame(width: max(0, min(geo.size.width, geo.size.width * CGFloat(remainingPercent) / 100.0)))
                        .overlay {
                            if isExpiringUnused {
                                DiagonalStripes(spacing: 5)
                                    .stroke(Color.white.opacity(0.55), lineWidth: 1.5)
                            }
                        }
                        .clipShape(RoundedRectangle(cornerRadius: 3))
                }
            }
            .frame(height: 6)

            HStack {
                Text("Used \(usedPercent)%")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
                Spacer()
                Text(detailText)
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
            }
        }
        .padding(.vertical, 4)
    }
}
```

- [ ] **Step 3: Build to verify it compiles**

Run: `cd macos/AIUsageMonitor && swift build`
Expected: Build complete，無錯誤。

- [ ] **Step 4: 目視驗證（建 .app 並開啟）**

Run: `cd macos/AIUsageMonitor && ./Scripts/build-app.sh && open .build/AIUsageMonitor.app`
Expected: 選單列出現圖示。點開下拉，當有窗口符合「剩餘 ≥ 40% 且快 reset」時，該條呈靛藍底 + 對角斜線、`% remaining` 文字為靛藍；其餘窗口維持紅/黃/綠實心。
（若當下沒有自然符合的真實資料，可暫時在 `StatusMenuView.swift` 的 `#Preview` 把某個 window 的 `resetAt` 改成 `Date().addingTimeInterval(1800)` 用 Xcode 預覽確認，確認後還原。此步驟不提交任何預覽改動。）

- [ ] **Step 5: Commit**

```bash
git add macos/AIUsageMonitor/Sources/AIUsageMonitorApp/SwiftUIComponents.swift
git commit -m "feat: 進度條對 expiring-unused 窗口加靛藍斜線提示"
```

---

## Self-Review

**Spec coverage:**
- 觸發條件（label 可解 + 剩餘 ≥ 40% + 0 < 距reset ≤ 週期×0.15）→ Task 2 `isExpiringUnused` 實作 + 測試涵蓋全部邊界。✅
- 窗口長度方法 A（解析 label，解不出靜默不觸發）→ Task 1。✅
- 常數 `EXPIRING_REMAINING_THRESHOLD=40`、`EXPIRING_WINDOW_FRACTION=0.15` → Task 1 以 `expiringRemainingThreshold` / `expiringWindowFraction` 集中宣告。✅
- 視覺：剩餘區段換靛藍 + 斜線、`% remaining` 同步靛藍、未觸發維持現狀、`detailText` 不變 → Task 3。✅
- `RemainingTier` 不動、新增獨立 `isExpiringUnused` bool → Task 3 view 狀態，Core 不改 enum。✅
- 永不崩潰 / total → Task 1、2 函式皆以 guard 回傳 nil/false，無拋出。✅
- 測試涵蓋 5h/7d 解析、剛好 40%、reset 已過、不可解 label、剛好 15% 邊界 → Task 1、2。✅
- 範圍只做原生 App（SwiftBar 後續）→ 計畫無 SwiftBar 任務。✅

**Placeholder scan:** 無 TBD / TODO；每個 code step 皆含完整可貼上的程式碼與確切指令/預期輸出。✅

**Type consistency:** `windowDuration(forLabel:)`、`isExpiringUnused(for:now:)`、`expiringRemainingThreshold`、`expiringWindowFraction`、`isExpiringUnused`（view 屬性）、`barColor`、`expiringColor`、`DiagonalStripes(spacing:)` 在各任務間命名一致；`UsageProgressBarView` 兩個 init 與既有 `StatusMenuView`/`ProviderCardView` 呼叫的 `init(window:)` 相容（新增參數皆有預設值）。✅
