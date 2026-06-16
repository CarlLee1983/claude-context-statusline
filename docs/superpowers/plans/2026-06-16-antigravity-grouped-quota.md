# Antigravity 分區額度顯示 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 解析改版後的 `agy /usage` 兩群組面板，在下拉選單拆成兩張獨立 Antigravity 卡片（Gemini / Claude & GPT），menu bar 仍合併為單一最差 chip，且共用一個 Antigravity 開關。

**Architecture:** `AntigravityUsageParser.parse` 改回傳 `[ParsedGroup]`（群組感知）；`AntigravityUsageProvider` 改實作既有的 `UsageSnapshotProviding`（`snapshots() -> [ProviderSnapshot]`），每組一張 snapshot；`LiveUsageSnapshotProvider` 攤平。`UsageProviderID(shortName:)` 讓 `AG` 前綴都對應 `.antigravity`（共用開關）。下拉卡片移除 AG 合併特例改逐條列出；menu bar 透過新增的 `RemainingQuotaPresenter.collapsedForMenuBar` 合併兩區取最差。

**Tech Stack:** Swift 6 / SwiftPM、swift-testing（`@Test` / `#expect`）、AppKit、SwiftUI。測試以 `swift test` 執行，工作目錄 `macos/AIUsageMonitor`。

---

## File Structure

- `Sources/AIUsageMonitorCore/AntigravityUsageParser.swift` — 改寫：`ParsedGroup` 型別 + 群組感知 `parse`。
- `Sources/AIUsageMonitorCore/AntigravityUsageProvider.swift` — 改實作 `UsageSnapshotProviding`，群組→多張 snapshot，保留帳號檔後備。
- `Sources/AIUsageMonitorCore/LiveUsageSnapshotProvider.swift` — antigravity 槽改持 `any UsageSnapshotProviding` 並攤平。
- `Sources/AIUsageMonitorCore/UsageMonitorSettings.swift` — `UsageProviderID(shortName:)` 對 `AG` 前綴對應 `.antigravity`。
- `Sources/AIUsageMonitorCore/RemainingQuotaPresenter.swift` — 新增 `collapsedForMenuBar`；移除 `mergedAntigravityWindow`。
- `Sources/AIUsageMonitorApp/StatusMenuView.swift` — 移除 AG 合併特例；更新 `#Preview` 範例。
- `Sources/AIUsageMonitorApp/StatusMenuImageRenderer.swift` — menu bar 先 collapse 再產圖/文字。
- 測試：`AntigravityUsageParserTests`、`AntigravityUsageProviderTests`、新增 `LiveUsageSnapshotProviderTests`、`UsageMonitorSettingsTests`、`RemainingQuotaPresenterTests`、`StatusMenuImageRendererTests`。
- 文件：`macos/AIUsageMonitor/README.md` / `README.en.md`、頂層 `CHANGELOG.md`。

---

### Task 1: Parser、Provider、Aggregator 群組化（核心編譯單元）

這三者型別相依，需一起改才能編譯通過。全程在 `macos/AIUsageMonitor`。

**Files:**
- Modify: `Sources/AIUsageMonitorCore/AntigravityUsageParser.swift`（整檔改寫）
- Modify: `Sources/AIUsageMonitorCore/AntigravityUsageProvider.swift`
- Modify: `Sources/AIUsageMonitorCore/LiveUsageSnapshotProvider.swift`
- Test: `Tests/AIUsageMonitorCoreTests/AntigravityUsageParserTests.swift`（改寫）
- Test: `Tests/AIUsageMonitorCoreTests/AntigravityUsageProviderTests.swift`（改寫）
- Test: `Tests/AIUsageMonitorCoreTests/LiveUsageSnapshotProviderTests.swift`（新建）

- [ ] **Step 1: 改寫 parser 測試（失敗的測試）**

把 `Tests/AIUsageMonitorCoreTests/AntigravityUsageParserTests.swift` 整檔換成：

```swift
import Foundation
import Testing
@testable import AIUsageMonitorCore

@Suite("Antigravity usage parser")
struct AntigravityUsageParserTests {
    @Test("parses the two-group panel into named limit windows")
    func parsesTwoGroups() throws {
        let now = Date(timeIntervalSince1970: 1_000_000)
        let text = """
        Models & Quota

          Account: user@example.com

        GEMINI MODELS
          Models within this group: Gemini Flash, Gemini Pro

          Weekly Limit
            [███████████████████████░░░░░░░] 77.05%
            77% remaining · Refreshes in 59h 6m

          Five Hour Limit
            [██████████████████████████████] 100.00%
            Quota available


        CLAUDE AND GPT MODELS
          Models within this group: Claude Opus, Claude Sonnet, GPT-OSS

          Weekly Limit
            [░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░] 0.00%
            Refreshes in 40h 55m
        """

        let groups = AntigravityUsageParser.parse(text, now: now)

        #expect(groups.count == 2)

        #expect(groups[0].title == "Gemini")
        #expect(groups[0].windows.map(\.label) == ["Weekly Limit", "Five Hour Limit"])
        #expect(groups[0].windows[0].percent == 77.05)
        #expect(groups[0].windows[0].kind == .available)
        #expect(groups[0].windows[0].resetAt == now.addingTimeInterval(59 * 3600 + 6 * 60))
        #expect(groups[0].windows[1].percent == 100)
        #expect(groups[0].windows[1].resetAt == nil)

        #expect(groups[1].title == "Claude & GPT")
        #expect(groups[1].windows.map(\.label) == ["Weekly Limit"])
        #expect(groups[1].windows[0].percent == 0)
        #expect(groups[1].windows[0].resetAt == now.addingTimeInterval(40 * 3600 + 55 * 60))
    }

    @Test("does not mistake group headers or subtitles for limit windows")
    func ignoresHeadersAndSubtitles() throws {
        let text = """
        Models & Quota
        GEMINI MODELS
          Models within this group: Gemini Flash, Gemini Pro
          Weekly Limit
            [██████] 50.00%
            50% remaining · Refreshes in 1h
        """

        let groups = AntigravityUsageParser.parse(text)

        #expect(groups.count == 1)
        #expect(groups[0].title == "Gemini")
        #expect(groups[0].windows.map(\.label) == ["Weekly Limit"])
        #expect(groups[0].windows[0].percent == 50)
    }

    @Test("title-cases unknown group headers as a fallback")
    func titleCasesUnknownGroups() throws {
        let text = """
        Models & Quota
        FOO BAR MODELS
          Weekly Limit
            [██] 12.00%
            Refreshes in 2h
        """

        let groups = AntigravityUsageParser.parse(text)

        #expect(groups.map(\.title) == ["Foo Bar"])
    }

    @Test("strips real ANSI escape sequences from labels and bars")
    func stripsRealANSI() throws {
        let esc = "\u{1B}"
        let text = """
        \(esc)[1mModels & Quota\(esc)[m\(esc)[K
        \(esc)[1mGEMINI MODELS\(esc)[m\(esc)[K
        \(esc)[1mWeekly Limit\(esc)[m\(esc)[K
        [██████████] 80.00%\(esc)[K
        Quota available\(esc)[K
        """

        let groups = AntigravityUsageParser.parse(text)

        #expect(groups.count == 1)
        #expect(groups[0].title == "Gemini")
        #expect(groups[0].windows.map(\.label) == ["Weekly Limit"])
        #expect(groups[0].windows[0].percent == 80)
    }

    @Test("returns no groups when the panel has no model groups")
    func returnsEmptyWhenNoGroups() throws {
        #expect(AntigravityUsageParser.parse("? for shortcuts\nesc Close").isEmpty)
    }
}
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd macos/AIUsageMonitor && swift test --filter AntigravityUsageParserTests`
Expected: 編譯失敗（`ParsedGroup` 未定義 / `parse` 回傳型別不符）。

- [ ] **Step 3: 改寫 parser 實作**

把 `Sources/AIUsageMonitorCore/AntigravityUsageParser.swift` 整檔換成：

```swift
import Foundation

public enum AntigravityUsageParser {
    /// One model group in the `agy /usage` panel (e.g. "Gemini",
    /// "Claude & GPT") with its named limit windows (Weekly / Five Hour).
    public struct ParsedGroup: Equatable, Sendable {
        public let title: String
        public let windows: [UsageWindow]

        public init(title: String, windows: [UsageWindow]) {
            self.title = title
            self.windows = windows
        }
    }

    public static func parse(_ rawText: String, now: Date = .now) -> [ParsedGroup] {
        var text = rawText.replacingOccurrences(of: "\r", with: "\n")
        // Anchor at the panel heading; tolerate the legacy "Model Quota" wording.
        if let range = text.range(of: "Models & Quota", options: .backwards) {
            text = String(text[range.lowerBound...])
        } else if let range = text.range(of: "Model Quota", options: .backwards) {
            text = String(text[range.lowerBound...])
        }

        let lines = text
            .components(separatedBy: .newlines)
            .map { stripANSI($0).trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }

        var groups: [ParsedGroup] = []
        var currentTitle: String?
        var currentWindows: [UsageWindow] = []

        func flush() {
            if let title = currentTitle, !currentWindows.isEmpty {
                groups.append(ParsedGroup(title: title, windows: currentWindows))
            }
            currentWindows = []
        }

        for (index, line) in lines.enumerated() {
            if let groupName = groupTitle(from: line) {
                flush()
                currentTitle = groupName
                continue
            }
            // Limit windows only exist inside a group.
            guard currentTitle != nil else { continue }
            if shouldSkip(line) || isBarOrPercentLine(line) { continue }

            // The bar line ("[…] 77.05%") sits immediately below the limit name;
            // the "… Refreshes in" countdown is the line after it.
            let lookahead = Array(lines.dropFirst(index + 1).prefix(2))
            guard let percent = firstPercent(in: lookahead) else { continue }
            let resetAt = firstRefreshInterval(in: lookahead).map { now.addingTimeInterval($0) }
            currentWindows.append(
                UsageWindow(label: line, percent: percent, kind: .available, resetAt: resetAt)
            )
        }
        flush()
        return groups
    }

    /// A group header is an all-caps line (with letters) ending in "MODELS".
    /// Maps the two known headers to friendly names; title-cases the rest.
    private static func groupTitle(from line: String) -> String? {
        guard
            line == line.uppercased(),
            line.rangeOfCharacter(from: .letters) != nil,
            line.hasSuffix("MODELS")
        else { return nil }

        switch line {
        case "GEMINI MODELS":
            return "Gemini"
        case "CLAUDE AND GPT MODELS":
            return "Claude & GPT"
        default:
            let stripped = line.replacingOccurrences(of: "MODELS", with: "")
                .trimmingCharacters(in: .whitespaces)
            return (stripped.isEmpty ? line : stripped).capitalized
        }
    }

    private static func isBarOrPercentLine(_ line: String) -> Bool {
        line.contains("█") || line.contains("░") || line.contains("%")
            || line.contains("[") || line.contains("]")
    }

    /// Parses an Antigravity "Refreshes in …" countdown into seconds. Accepts the
    /// `1d 3h 46m 30s` token style (any subset, in any order); returns nil when no
    /// countdown is present (e.g. a "Quota available" line).
    private static func firstRefreshInterval<S: Sequence>(in lines: S) -> TimeInterval?
    where S.Element == String {
        for line in lines {
            guard let range = line.range(of: "Refreshes in", options: .caseInsensitive) else { continue }
            let tail = line[range.upperBound...]
            let units: [(suffix: String, seconds: Double)] = [
                ("d", 86_400), ("h", 3_600), ("m", 60), ("s", 1),
            ]
            var total: TimeInterval = 0
            var matched = false
            for (suffix, seconds) in units {
                let pattern = "(\\d+(?:\\.\\d+)?)\\s*" + suffix + "\\b"
                if let match = tail.range(of: pattern, options: .regularExpression) {
                    let number = tail[match].replacingOccurrences(
                        of: "[^0-9.]", with: "", options: .regularExpression
                    )
                    if let value = Double(number) {
                        total += value * seconds
                        matched = true
                    }
                }
            }
            if matched { return total }
        }
        return nil
    }

    private static func shouldSkip(_ line: String) -> Bool {
        line == "Model Quota"
            || line == "Models & Quota"
            || line == "Quota available"
            || line.hasSuffix("Model Quota")
            || line.hasSuffix("Models & Quota")
            || line.localizedCaseInsensitiveContains("models within this group")
            || line.localizedCaseInsensitiveContains("account:")
            || line.localizedCaseInsensitiveContains("shortcuts")
            || line.localizedCaseInsensitiveContains("scroll")
            || line.localizedCaseInsensitiveContains("esc")
    }

    private static func firstPercent<S: Sequence>(in lines: S) -> Double? where S.Element == String {
        for line in lines {
            if let match = line.range(of: #"(\d+(?:\.\d+)?)\s*%"#, options: .regularExpression) {
                let token = line[match]
                    .replacingOccurrences(of: "%", with: "")
                    .trimmingCharacters(in: .whitespaces)
                return Double(token)
            }
        }
        return nil
    }

    // ESC char built via Swift escape so the literal ESC byte (not the text
    // "\u{001B}") reaches the ICU regex engine. Covers CSI sequences (colors,
    // erase-line), private-mode sets, and a catch-all for 2-byte escapes.
    private static let ansiPattern =
        "\u{1B}\\[[0-?]*[ -/]*[@-~]|\u{1B}[>=][^A-Za-z]*[A-Za-z]?|\u{1B}\\\\?."

    private static func stripANSI(_ line: String) -> String {
        line.replacingOccurrences(of: ansiPattern, with: "", options: .regularExpression)
    }
}
```

- [ ] **Step 4: 改寫 provider 實作**

把 `Sources/AIUsageMonitorCore/AntigravityUsageProvider.swift` 整檔換成：

```swift
import Foundation

/// Produces Antigravity snapshots: prefer the live `agy /usage` panel — now split
/// into model groups (Gemini / Claude & GPT), one snapshot per group — and fall
/// back to the local accounts file (a single snapshot) when capture fails.
///
/// The data-fetching boundaries are injected so the orchestration is unit tested
/// without driving a real TUI or touching the filesystem.
public struct AntigravityUsageProvider: UsageSnapshotProviding {
    private let captureText: @Sendable () -> String?
    private let loadAccounts: @Sendable () -> Data?
    private let now: @Sendable () -> Date

    static let accountsURL = URL(fileURLWithPath: NSHomeDirectory())
        .appendingPathComponent(".config/opencode/antigravity-accounts.json")

    public init() {
        self.init(
            captureText: { AntigravityUsageTextCapture.capture() },
            loadAccounts: { try? Data(contentsOf: AntigravityUsageProvider.accountsURL) },
            now: { Date() }
        )
    }

    init(
        captureText: @escaping @Sendable () -> String?,
        loadAccounts: @escaping @Sendable () -> Data?,
        now: @escaping @Sendable () -> Date
    ) {
        self.captureText = captureText
        self.loadAccounts = loadAccounts
        self.now = now
    }

    public func snapshots() async -> [ProviderSnapshot] {
        let unavailable = ProviderSnapshot(
            name: "Antigravity", shortName: "AG", windows: [], isAvailable: false
        )

        // The TUI capture blocks (up to ~12s); keep it off the cooperative pool.
        let capture = captureText
        let text = await Task.detached(priority: .utility) { capture() }.value
        if let text {
            let groups = AntigravityUsageParser.parse(text, now: now())
            if !groups.isEmpty {
                return AntigravityUsageProvider.snapshots(from: groups)
            }
        }

        guard let data = loadAccounts() else { return [unavailable] }
        let result = AntigravityAccountsParser.parse(data, now: now())
        guard result.hasAccounts else { return [unavailable] }
        return [ProviderSnapshot(
            name: "Antigravity", shortName: "AG", plan: result.plan, windows: result.windows
        )]
    }

    /// One independent card per group. shortName = "AG" + the group's first
    /// alphanumeric (lowercased); collisions fall back to the group index so the
    /// snapshot ids (== shortName) stay unique for SwiftUI's ForEach.
    static func snapshots(from groups: [AntigravityUsageParser.ParsedGroup]) -> [ProviderSnapshot] {
        var used: Set<String> = []
        return groups.enumerated().map { index, group in
            let initial = group.title.first(where: { $0.isLetter || $0.isNumber })
                .map { String($0).lowercased() } ?? "\(index)"
            var short = "AG" + initial
            if used.contains(short) { short = "AG\(index)" }
            used.insert(short)
            return ProviderSnapshot(
                name: "Antigravity · \(group.title)",
                shortName: short,
                plan: "agy /usage",
                windows: group.windows
            )
        }
    }
}
```

- [ ] **Step 5: 更新 aggregator 攤平 antigravity**

在 `Sources/AIUsageMonitorCore/LiveUsageSnapshotProvider.swift`：

把欄位與兩個 init 參數的 antigravity 型別從 `any ProviderSnapshotProviding` 改成 `any UsageSnapshotProviding`：

```swift
    private let antigravity: any UsageSnapshotProviding
```
```swift
    public init(
        claude: any ProviderSnapshotProviding,
        codex: any ProviderSnapshotProviding,
        antigravity: any UsageSnapshotProviding,
        enabledProviderIDs: Set<UsageProviderID>
    ) {
```

把 `snapshots()` 整個方法換成（每個 provider 改回傳陣列、antigravity 直接攤平）：

```swift
    public func snapshots() async -> [ProviderSnapshot] {
        await withTaskGroup(of: (UsageProviderID, [ProviderSnapshot]).self) { group in
            if enabledProviderIDs.contains(.claudeCode) {
                group.addTask { (.claudeCode, [await claude.snapshot()]) }
            }
            if enabledProviderIDs.contains(.codex) {
                group.addTask { (.codex, [await codex.snapshot()]) }
            }
            if enabledProviderIDs.contains(.antigravity) {
                group.addTask { (.antigravity, await antigravity.snapshots()) }
            }

            var results: [UsageProviderID: [ProviderSnapshot]] = [:]
            for await (providerID, snapshots) in group {
                results[providerID] = snapshots
            }

            return UsageProviderID.allCases.flatMap { results[$0] ?? [] }
        }
    }
```

- [ ] **Step 6: 改寫 provider 測試**

把 `Tests/AIUsageMonitorCoreTests/AntigravityUsageProviderTests.swift` 整檔換成：

```swift
import Foundation
import Testing
@testable import AIUsageMonitorCore

@Suite("Antigravity usage provider")
struct AntigravityUsageProviderTests {
    private let now = Date(timeIntervalSince1970: 1_700_000_000)

    private func accountsData(claudeOffset: Double) -> Data {
        let resetMs = Int((now.timeIntervalSince1970 + claudeOffset) * 1000)
        return try! JSONSerialization.data(withJSONObject: [
            "accounts": [["rateLimitResetTimes": ["claude": resetMs]]]
        ])
    }

    @Test("live panel yields one snapshot per model group")
    func textPathSplitsGroups() async {
        let usageText = """
        Models & Quota
        GEMINI MODELS
          Weekly Limit
            [██████] 92.00%
            Quota available
        CLAUDE AND GPT MODELS
          Weekly Limit
            [███] 30.00%
            Refreshes in 5h
        """
        let provider = AntigravityUsageProvider(
            captureText: { usageText },
            loadAccounts: { Data() }, // must be ignored when text parses
            now: { self.now }
        )

        let snapshots = await provider.snapshots()

        #expect(snapshots.map(\.name) == ["Antigravity · Gemini", "Antigravity · Claude & GPT"])
        #expect(snapshots.map(\.shortName) == ["AGg", "AGc"])
        #expect(snapshots.allSatisfy { $0.plan == "agy /usage" && $0.isAvailable })
        #expect(snapshots[0].windows.map(\.label) == ["Weekly Limit"])
        #expect(snapshots[0].windows[0].percent == 92)
        #expect(snapshots[1].windows[0].percent == 30)
    }

    @Test("falls back to a single accounts-cooldown snapshot when capture is empty")
    func accountsFallback() async {
        let provider = AntigravityUsageProvider(
            captureText: { nil },
            loadAccounts: { self.accountsData(claudeOffset: 3_600) },
            now: { self.now }
        )

        let snapshots = await provider.snapshots()

        #expect(snapshots.count == 1)
        #expect(snapshots[0].name == "Antigravity")
        #expect(snapshots[0].shortName == "AG")
        #expect(snapshots[0].plan == "1 acct")
        #expect(snapshots[0].windows.map(\.label) == ["Claude"])
        #expect(snapshots[0].windows[0].kind == .used)
    }

    @Test("accounts present but no cooldown is available with no windows (ready)")
    func readyState() async {
        let provider = AntigravityUsageProvider(
            captureText: { nil },
            loadAccounts: { self.accountsData(claudeOffset: -60) },
            now: { self.now }
        )

        let snapshots = await provider.snapshots()

        #expect(snapshots.count == 1)
        #expect(snapshots[0].isAvailable)
        #expect(snapshots[0].windows.isEmpty)
    }

    @Test("no text and no accounts is a single unavailable snapshot")
    func unavailable() async {
        let provider = AntigravityUsageProvider(
            captureText: { nil },
            loadAccounts: { nil },
            now: { self.now }
        )

        let snapshots = await provider.snapshots()

        #expect(snapshots.count == 1)
        #expect(!snapshots[0].isAvailable)
        #expect(snapshots[0].windows.isEmpty)
    }

    @Test("colliding group initials fall back to a unique index-based shortName")
    func collidingShortNames() {
        let groups = [
            AntigravityUsageParser.ParsedGroup(
                title: "Gemini", windows: [UsageWindow(label: "Weekly Limit", percent: 50, kind: .available)]
            ),
            AntigravityUsageParser.ParsedGroup(
                title: "Gpt", windows: [UsageWindow(label: "Weekly Limit", percent: 10, kind: .available)]
            )
        ]

        let snapshots = AntigravityUsageProvider.snapshots(from: groups)

        #expect(snapshots.map(\.shortName) == ["AGg", "AG1"])
        #expect(Set(snapshots.map(\.shortName)).count == 2)
    }
}
```

- [ ] **Step 7: 新建 aggregator 攤平測試**

建立 `Tests/AIUsageMonitorCoreTests/LiveUsageSnapshotProviderTests.swift`：

```swift
import Foundation
import Testing
@testable import AIUsageMonitorCore

@Suite("Live usage snapshot provider")
struct LiveUsageSnapshotProviderTests {
    private struct FakeSingle: ProviderSnapshotProviding {
        let snap: ProviderSnapshot
        func snapshot() async -> ProviderSnapshot { snap }
    }

    private struct FakeMulti: UsageSnapshotProviding {
        let snaps: [ProviderSnapshot]
        func snapshots() async -> [ProviderSnapshot] { snaps }
    }

    @Test("flattens the antigravity group snapshots after claude and codex, in order")
    func flattensAntigravityGroups() async {
        let cc = ProviderSnapshot(name: "Claude Code", shortName: "CC", windows: [])
        let cx = ProviderSnapshot(name: "Codex", shortName: "CX", windows: [])
        let agg = ProviderSnapshot(name: "Antigravity · Gemini", shortName: "AGg", windows: [])
        let agc = ProviderSnapshot(name: "Antigravity · Claude & GPT", shortName: "AGc", windows: [])

        let provider = LiveUsageSnapshotProvider(
            claude: FakeSingle(snap: cc),
            codex: FakeSingle(snap: cx),
            antigravity: FakeMulti(snaps: [agg, agc]),
            enabledProviderIDs: Set(UsageProviderID.allCases)
        )

        let result = await provider.snapshots()

        #expect(result.map(\.shortName) == ["CC", "CX", "AGg", "AGc"])
    }
}
```

- [ ] **Step 8: 跑測試確認全綠**

Run: `cd macos/AIUsageMonitor && swift test --filter AntigravityUsage`
Run: `cd macos/AIUsageMonitor && swift test --filter LiveUsageSnapshotProviderTests`
Expected: 全數 PASS。

- [ ] **Step 9: Commit**

```bash
git add macos/AIUsageMonitor/Sources/AIUsageMonitorCore/AntigravityUsageParser.swift \
        macos/AIUsageMonitor/Sources/AIUsageMonitorCore/AntigravityUsageProvider.swift \
        macos/AIUsageMonitor/Sources/AIUsageMonitorCore/LiveUsageSnapshotProvider.swift \
        macos/AIUsageMonitor/Tests/AIUsageMonitorCoreTests/AntigravityUsageParserTests.swift \
        macos/AIUsageMonitor/Tests/AIUsageMonitorCoreTests/AntigravityUsageProviderTests.swift \
        macos/AIUsageMonitor/Tests/AIUsageMonitorCoreTests/LiveUsageSnapshotProviderTests.swift
git commit -m "feat: [macos] parse grouped agy /usage into per-group Antigravity snapshots"
```

---

### Task 2: 共用單一 Antigravity 開關（shortName 前綴對應）

**Files:**
- Modify: `Sources/AIUsageMonitorCore/UsageMonitorSettings.swift:56-63`
- Test: `Tests/AIUsageMonitorCoreTests/UsageMonitorSettingsTests.swift`

- [ ] **Step 1: 新增失敗的測試**

在 `Tests/AIUsageMonitorCoreTests/UsageMonitorSettingsTests.swift` 的 `struct` 內新增測試（放在最後一個 `}` 之前）：

```swift
    @Test("any AG-prefixed shortName resolves to the antigravity provider")
    func agPrefixResolvesToAntigravity() {
        #expect(UsageProviderID(shortName: "AG") == .antigravity)
        #expect(UsageProviderID(shortName: "AGg") == .antigravity)
        #expect(UsageProviderID(shortName: "AGc") == .antigravity)
        #expect(UsageProviderID(shortName: "AG1") == .antigravity)
        #expect(UsageProviderID(shortName: "CC") == .claudeCode)
        #expect(UsageProviderID(shortName: "CX") == .codex)
        #expect(UsageProviderID(shortName: "ZZ") == nil)
    }

    @Test("a single antigravity toggle controls both grouped cards")
    func singleToggleControlsBothAntigravityCards() {
        let settings = UsageMonitorSettings(
            menuBarProviderIDs: [.claudeCode, .antigravity],
            queriedProviderIDs: Set(UsageProviderID.allCases)
        )
        let snapshots = [
            ProviderSnapshot(name: "Antigravity · Gemini", shortName: "AGg", windows: []),
            ProviderSnapshot(name: "Antigravity · Claude & GPT", shortName: "AGc", windows: []),
            ProviderSnapshot(name: "Codex", shortName: "CX", windows: [])
        ]

        let shown = settings.menuBarSnapshots(from: snapshots)

        #expect(shown.map(\.shortName) == ["AGg", "AGc"])
    }
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd macos/AIUsageMonitor && swift test --filter UsageMonitorSettingsTests`
Expected: 新測試 FAIL（`AGg` 目前回傳 nil → 被過濾掉）。

- [ ] **Step 3: 改 `UsageProviderID(shortName:)`**

在 `Sources/AIUsageMonitorCore/UsageMonitorSettings.swift` 把 init 換成：

```swift
public extension UsageProviderID {
    init?(shortName: String) {
        // Antigravity surfaces as multiple grouped cards ("AGg", "AGc", …); any
        // "AG"-prefixed shortName maps back to the single antigravity provider so
        // one toggle controls them all.
        if shortName.hasPrefix("AG") {
            self = .antigravity
            return
        }
        guard let provider = Self.allCases.first(where: { $0.shortName == shortName }) else {
            return nil
        }
        self = provider
    }
}
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd macos/AIUsageMonitor && swift test --filter UsageMonitorSettingsTests`
Expected: 全數 PASS。

- [ ] **Step 5: Commit**

```bash
git add macos/AIUsageMonitor/Sources/AIUsageMonitorCore/UsageMonitorSettings.swift \
        macos/AIUsageMonitor/Tests/AIUsageMonitorCoreTests/UsageMonitorSettingsTests.swift
git commit -m "feat: [macos] map AG-prefixed shortNames to the single antigravity toggle"
```

---

### Task 3: menu bar 合併取最差（`collapsedForMenuBar`）

**Files:**
- Modify: `Sources/AIUsageMonitorCore/RemainingQuotaPresenter.swift`
- Test: `Tests/AIUsageMonitorCoreTests/RemainingQuotaPresenterTests.swift`

- [ ] **Step 1: 新增失敗的測試**

在 `Tests/AIUsageMonitorCoreTests/RemainingQuotaPresenterTests.swift` 的 `struct` 內新增：

```swift
    @Test("collapses AG-prefixed snapshots into one worst-remaining menu-bar entry")
    func collapsesAntigravityForMenuBar() {
        let reset = Date(timeIntervalSince1970: 1_800_000_000)
        let snapshots = [
            ProviderSnapshot(name: "Claude Code", shortName: "CC",
                             windows: [UsageWindow(label: "5h", percent: 3, kind: .used)]),
            ProviderSnapshot(name: "Antigravity · Gemini", shortName: "AGg", plan: "agy /usage",
                             windows: [UsageWindow(label: "Weekly Limit", percent: 77, kind: .available)]),
            ProviderSnapshot(name: "Antigravity · Claude & GPT", shortName: "AGc", plan: "agy /usage",
                             windows: [UsageWindow(label: "Weekly Limit", percent: 0, kind: .available, resetAt: reset)])
        ]

        let collapsed = RemainingQuotaPresenter.collapsedForMenuBar(snapshots)

        // CC untouched, the two AG cards become one "Antigravity" entry.
        #expect(collapsed.map(\.shortName) == ["CC", "AG"])
        #expect(collapsed[1].name == "Antigravity")
        // Worst (lowest remaining) of the two AG windows represents the entry.
        #expect(RemainingQuotaPresenter.primaryRemainingPercent(for: collapsed[1]) == 0)
        // fallback title reflects the collapsed entries.
        #expect(RemainingQuotaPresenter.fallbackTitle(for: collapsed) == "Claude Code 97 Antigravity 0")
    }

    @Test("collapse leaves non-AG snapshots and a lone AG snapshot unchanged in order")
    func collapsePreservesOthers() {
        let snapshots = [
            ProviderSnapshot(name: "Antigravity", shortName: "AG",
                             windows: [UsageWindow(label: "Claude", percent: 100, kind: .used)]),
            ProviderSnapshot(name: "Codex", shortName: "CX",
                             windows: [UsageWindow(label: "5h", percent: 1, kind: .used)])
        ]

        let collapsed = RemainingQuotaPresenter.collapsedForMenuBar(snapshots)

        #expect(collapsed.map(\.shortName) == ["AG", "CX"])
        #expect(RemainingQuotaPresenter.primaryRemainingPercent(for: collapsed[0]) == 0)
    }
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd macos/AIUsageMonitor && swift test --filter RemainingQuotaPresenterTests`
Expected: 編譯失敗（`collapsedForMenuBar` 未定義）。

- [ ] **Step 3: 新增 `collapsedForMenuBar`**

在 `Sources/AIUsageMonitorCore/RemainingQuotaPresenter.swift` 的 `enum RemainingQuotaPresenter { … }` 內新增（放在 `fallbackTitle` 之前）：

```swift
    /// Collapses the (possibly multiple) AG-prefixed snapshots into a single
    /// "Antigravity" entry for the compact menu bar, keeping it to one chip. The
    /// representative window is the worst (lowest remaining) across all AG groups,
    /// so the tightest pool surfaces. Non-AG snapshots keep their position; the AG
    /// entry takes the slot of the first AG snapshot seen.
    public static func collapsedForMenuBar(_ snapshots: [ProviderSnapshot]) -> [ProviderSnapshot] {
        var result: [ProviderSnapshot] = []
        var agWindows: [UsageWindow] = []
        var agPlan: String?
        var agAvailable = false
        var agSlot: Int?

        for snapshot in snapshots {
            if snapshot.shortName.hasPrefix("AG") {
                if agSlot == nil {
                    agSlot = result.count
                    agPlan = snapshot.plan
                }
                agAvailable = agAvailable || snapshot.isAvailable
                agWindows.append(contentsOf: snapshot.windows)
            } else {
                result.append(snapshot)
            }
        }

        guard let slot = agSlot else { return result }

        let worst = agWindows.min(by: { remainingPercent(for: $0) < remainingPercent(for: $1) })
        let collapsed = ProviderSnapshot(
            name: "Antigravity",
            shortName: "AG",
            plan: agPlan,
            windows: worst.map { [$0] } ?? [],
            isAvailable: agAvailable
        )
        result.insert(collapsed, at: min(slot, result.count))
        return result
    }
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd macos/AIUsageMonitor && swift test --filter RemainingQuotaPresenterTests`
Expected: 全數 PASS（既有 `mergedAntigravityWindow` 測試此時仍在，也應通過）。

- [ ] **Step 5: Commit**

```bash
git add macos/AIUsageMonitor/Sources/AIUsageMonitorCore/RemainingQuotaPresenter.swift \
        macos/AIUsageMonitor/Tests/AIUsageMonitorCoreTests/RemainingQuotaPresenterTests.swift
git commit -m "feat: [macos] collapse grouped Antigravity into one worst-remaining menu-bar entry"
```

---

### Task 4: menu bar 渲染套用 collapse

**Files:**
- Modify: `Sources/AIUsageMonitorApp/StatusMenuImageRenderer.swift:13-29`
- Test: `Tests/AIUsageMonitorAppTests/StatusMenuImageRendererTests.swift`

- [ ] **Step 1: 新增失敗的測試**

在 `Tests/AIUsageMonitorAppTests/StatusMenuImageRendererTests.swift` 的 `struct` 內新增：

```swift
    @Test("two grouped Antigravity snapshots render as one combined fallback entry")
    func combinesAntigravityInStatus() {
        let snapshots = [
            ProviderSnapshot(name: "Antigravity · Gemini", shortName: "AGg", plan: "agy /usage",
                             windows: [UsageWindow(label: "Weekly Limit", percent: 77, kind: .available)]),
            ProviderSnapshot(name: "Antigravity · Claude & GPT", shortName: "AGc", plan: "agy /usage",
                             windows: [UsageWindow(label: "Weekly Limit", percent: 0, kind: .available)])
        ]

        let rendered = StatusMenuImageRenderer.renderStatus(for: snapshots)

        #expect(rendered.fallbackTitle == "Antigravity 0")
        #expect(rendered.image != nil)
    }
```

需要 import `AIUsageMonitorCore` —— 檔案頂端 `@testable import AIUsageMonitorApp` 之外再加 `import AIUsageMonitorCore`。

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd macos/AIUsageMonitor && swift test --filter StatusMenuImageRendererTests`
Expected: FAIL（目前回傳 `"Antigravity · Gemini 77 Antigravity · Claude & GPT 0"`）。

- [ ] **Step 3: renderStatus 先 collapse**

在 `Sources/AIUsageMonitorApp/StatusMenuImageRenderer.swift` 把 `renderStatus(for:)` 換成：

```swift
    static func renderStatus(for snapshots: [ProviderSnapshot]) -> RenderedStatus {
        // Grouped Antigravity cards collapse to one chip in the compact menu bar.
        let collapsed = RemainingQuotaPresenter.collapsedForMenuBar(snapshots)
        let fallbackTitle = RemainingQuotaPresenter.fallbackTitle(for: collapsed)
        let entries = collapsed.compactMap { snapshot -> Entry? in
            guard let remaining = RemainingQuotaPresenter.primaryRemainingPercent(for: snapshot) else { return nil }
            return Entry(providerName: snapshot.name, remaining: remaining)
        }

        guard !entries.isEmpty else {
            return RenderedStatus(image: nil, fallbackTitle: fallbackTitle, accessibilityTitle: fallbackTitle)
        }

        return RenderedStatus(
            image: draw(entries: entries),
            fallbackTitle: fallbackTitle,
            accessibilityTitle: fallbackTitle
        )
    }
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd macos/AIUsageMonitor && swift test --filter StatusMenuImageRendererTests`
Expected: 全數 PASS。

- [ ] **Step 5: Commit**

```bash
git add macos/AIUsageMonitor/Sources/AIUsageMonitorApp/StatusMenuImageRenderer.swift \
        macos/AIUsageMonitor/Tests/AIUsageMonitorAppTests/StatusMenuImageRendererTests.swift
git commit -m "feat: [macos] collapse Antigravity groups into one menu-bar chip"
```

---

### Task 5: 下拉卡片移除 AG 合併特例 + 更新 Preview

純 SwiftUI view 變更，無單元測試（沿用既有慣例：view 不單測）。以 `swift build` 確認編譯。

**Files:**
- Modify: `Sources/AIUsageMonitorApp/StatusMenuView.swift:4-88`（移除 `isAntigravity` 與合併分支）
- Modify: `Sources/AIUsageMonitorApp/StatusMenuView.swift:134-165`（更新 `#Preview`）

- [ ] **Step 1: 移除 `isAntigravity` 屬性與合併分支**

把 `struct ProviderCardView` 從 `private var isAntigravity` 到 `body` 結尾換成（保留 header 區塊不動，只改 `body` 內容判斷）。將整個 `ProviderCardView` 換成：

```swift
struct ProviderCardView: View {
    let snapshot: ProviderSnapshot

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            // Header
            HStack(spacing: 8) {
                BrandIconView(name: snapshot.name)

                Text(snapshot.name)
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(.primary)

                if let plan = snapshot.plan {
                    Text(plan)
                        .font(.system(size: 10, weight: .medium))
                        .padding(.horizontal, 5)
                        .padding(.vertical, 1)
                        .background(Color.primary.opacity(0.08))
                        .cornerRadius(4)
                        .foregroundColor(.secondary)
                }

                Spacer()

                if !snapshot.isAvailable {
                    Text("Unavailable")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundColor(.red)
                } else {
                    Text(snapshot.updatedAt.formatted(date: .omitted, time: .shortened))
                        .font(.system(size: 10))
                        .foregroundColor(.secondary)
                }
            }
            .padding(.bottom, 2)

            if snapshot.windows.isEmpty {
                Text(snapshot.isAvailable ? "No quota data available" : "Service offline")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
            } else {
                VStack(spacing: 12) {
                    ForEach(snapshot.windows) { window in
                        UsageProgressBarView(window: window)
                    }
                }
            }
        }
        .padding(12)
        .background(Color(nsColor: .windowBackgroundColor).opacity(0.12))
        .cornerRadius(8)
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(Color.primary.opacity(0.06), lineWidth: 1)
        )
    }
}
```

- [ ] **Step 2: 更新 `#Preview` 的 AG 範例為兩張群組卡**

把 `#Preview { … }` 內最後一個 Antigravity `ProviderSnapshot(...)` 換成兩張：

```swift
        ProviderSnapshot(
            name: "Antigravity · Gemini",
            shortName: "AGg",
            plan: "agy /usage",
            windows: [
                UsageWindow(label: "Weekly Limit", percent: 77, kind: .available, resetAt: Date().addingTimeInterval(59 * 3600)),
                UsageWindow(label: "Five Hour Limit", percent: 100, kind: .available)
            ]
        ),
        ProviderSnapshot(
            name: "Antigravity · Claude & GPT",
            shortName: "AGc",
            plan: "agy /usage",
            windows: [
                UsageWindow(label: "Weekly Limit", percent: 0, kind: .available, resetAt: Date().addingTimeInterval(40 * 3600))
            ]
        )
```

- [ ] **Step 3: 編譯確認**

Run: `cd macos/AIUsageMonitor && swift build`
Expected: 編譯成功，無 `isAntigravity` / `mergedAntigravityWindow` 相關錯誤。

- [ ] **Step 4: Commit**

```bash
git add macos/AIUsageMonitor/Sources/AIUsageMonitorApp/StatusMenuView.swift
git commit -m "feat: [macos] render each Antigravity group as its own dropdown card"
```

---

### Task 6: 移除已無用的 `mergedAntigravityWindow`

完成 Task 5 後，`mergedAntigravityWindow` 已無生產端使用者，移除以精簡（DRY/YAGNI）。

**Files:**
- Modify: `Sources/AIUsageMonitorCore/RemainingQuotaPresenter.swift:69-89`（刪除函式）
- Modify: `Tests/AIUsageMonitorCoreTests/RemainingQuotaPresenterTests.swift`（刪除兩個對應測試）

- [ ] **Step 1: 確認已無生產端引用**

Run: `cd macos/AIUsageMonitor && grep -rn "mergedAntigravityWindow" Sources/`
Expected: 無輸出（僅測試引用）。

- [ ] **Step 2: 刪除函式**

在 `Sources/AIUsageMonitorCore/RemainingQuotaPresenter.swift` 刪掉整個 `mergedAntigravityWindow(from:label:)` 方法（含其上方註解 block，從 `/// Collapses Antigravity's per-model windows…` 到該函式結尾的 `}`）。

- [ ] **Step 3: 刪除對應測試**

在 `Tests/AIUsageMonitorCoreTests/RemainingQuotaPresenterTests.swift` 刪除這兩個測試方法（含其上方 `@Test(...)`）：
- `mergesAntigravityVariantsIntoBindingWindow()`
- `mergedAntigravityWindowEdgeCases()`

- [ ] **Step 4: 跑全套測試確認通過**

Run: `cd macos/AIUsageMonitor && swift test`
Expected: 全數 PASS、無編譯錯誤。

- [ ] **Step 5: Commit**

```bash
git add macos/AIUsageMonitor/Sources/AIUsageMonitorCore/RemainingQuotaPresenter.swift \
        macos/AIUsageMonitor/Tests/AIUsageMonitorCoreTests/RemainingQuotaPresenterTests.swift
git commit -m "refactor: [macos] drop unused mergedAntigravityWindow"
```

---

### Task 7: 更新 Demo 範例資料

讓 `swift build` 的預覽/示範資料反映新的兩群組樣貌（非測試但用於 demo provider）。

**Files:**
- Modify: `Sources/AIUsageMonitorCore/UsageSnapshotProvider.swift:53-61`

- [ ] **Step 1: 更新 `DemoUsageSnapshotProvider` 的 AG 項**

把 `DemoUsageSnapshotProvider.snapshots()` 陣列中最後一個 Antigravity `ProviderSnapshot(...)` 換成兩張：

```swift
            ProviderSnapshot(
                name: "Antigravity · Gemini",
                shortName: "AGg",
                plan: "agy /usage",
                windows: [
                    UsageWindow(label: "Weekly Limit", percent: 77, kind: .available, resetAt: Date().addingTimeInterval(59 * 3_600)),
                    UsageWindow(label: "Five Hour Limit", percent: 100, kind: .available)
                ]
            ),
            ProviderSnapshot(
                name: "Antigravity · Claude & GPT",
                shortName: "AGc",
                plan: "agy /usage",
                windows: [
                    UsageWindow(label: "Weekly Limit", percent: 0, kind: .available, resetAt: Date().addingTimeInterval(40 * 3_600))
                ]
            )
```

- [ ] **Step 2: 編譯確認**

Run: `cd macos/AIUsageMonitor && swift build`
Expected: 編譯成功。

- [ ] **Step 3: Commit**

```bash
git add macos/AIUsageMonitor/Sources/AIUsageMonitorCore/UsageSnapshotProvider.swift
git commit -m "chore: [macos] update demo data to grouped Antigravity snapshots"
```

---

### Task 8: 全套驗證 + 文件雙語更新

**Files:**
- Modify: `macos/AIUsageMonitor/README.md`
- Modify: `macos/AIUsageMonitor/README.en.md`
- Modify: `CHANGELOG.md`（頂層）

- [ ] **Step 1: 跑完整測試套件**

Run: `cd macos/AIUsageMonitor && swift test`
Expected: 全數 PASS。

- [ ] **Step 2: 更新 `macos/AIUsageMonitor/README.md`（繁中）**

在描述 Antigravity provider 取數的段落，補一句說明新行為（依實際文句插入，重點包含）：

> Antigravity 的 `agy /usage` 面板已分成模型群組（Gemini 與 Claude/GPT）。選單會把兩群組拆成**兩張獨立卡片**分開顯示各自的 Weekly / Five Hour 額度；選單列 (menu bar) 仍合併為單一 Antigravity 圖示，數字取兩區剩餘量最低者。兩張卡共用同一個 Antigravity 開關。

- [ ] **Step 3: 同步更新 `macos/AIUsageMonitor/README.en.md`（英文）**

對應英文：

> Antigravity's `agy /usage` panel is now split into model groups (Gemini and Claude/GPT). The dropdown shows them as **two independent cards**, each listing its own Weekly / Five Hour quota; the menu bar still collapses them into a single Antigravity chip showing the lowest remaining of the two groups. Both cards share one Antigravity toggle.

- [ ] **Step 4: 更新頂層 `CHANGELOG.md`**

在最新版本區塊新增條目（依現有格式）：

```markdown
- Antigravity：解析改版後分群組的 `agy /usage` 面板，下拉選單拆成 Gemini 與 Claude/GPT 兩張獨立卡片，menu bar 合併取最差；共用單一 Antigravity 開關。
```

- [ ] **Step 5: Commit**

```bash
git add macos/AIUsageMonitor/README.md macos/AIUsageMonitor/README.en.md CHANGELOG.md
git commit -m "docs: [macos] document grouped Antigravity quota display"
```

---

## Self-Review

**Spec coverage:**
- Parser 群組化 → Task 1 ✓
- Provider 多張 snapshot + 後備單張 → Task 1 ✓
- Aggregator 攤平 → Task 1 ✓
- shortName 唯一性（碰撞退回 index）→ Task 1 Step 6 測試 + 實作 ✓
- 共用單一開關（AG 前綴對應）→ Task 2 ✓
- 卡片移除合併、逐條列出 → Task 5 ✓
- menu bar collapse 取最差 → Task 3（presenter）+ Task 4（renderer）✓
- 移除 `mergedAntigravityWindow` → Task 6 ✓
- 測試計畫各項 → Task 1–4 涵蓋；Demo → Task 7；文件雙語 + CHANGELOG → Task 8 ✓

**與 spec 的刻意偏差：** spec 提到新增 `MultiProviderSnapshotProviding` 協定；改用既有的 `UsageSnapshotProviding`（簽章相同 `snapshots() -> [ProviderSnapshot]`），避免重複協定。功能等價。

**Placeholder scan:** 無 TBD/TODO；每個改碼步驟均附完整程式碼與預期輸出。

**Type consistency:** `ParsedGroup`（title/windows）、`AntigravityUsageProvider.snapshots()` 與 `snapshots(from:)`、`UsageSnapshotProviding.snapshots()`、`collapsedForMenuBar(_:)`、`UsageProviderID(shortName:)` 在各 Task 間命名一致；shortName 規則（`AGg`/`AGc`/碰撞 `AG{index}`）與 collapse 的 `hasPrefix("AG")` 對應一致。
