# Generic Provider Grouping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the "AG"-prefix string convention with a first-class `providerID` on each `ProviderSnapshot`, and make menu-bar collapse a generic group-by-provider rule — removing the Antigravity special case while keeping behavior identical.

**Architecture:** Each `ProviderSnapshot` carries its canonical `UsageProviderID`. Settings filtering reads that id directly; menu-bar collapse groups snapshots by id and merges any group with >1 snapshot into one chip. The string helpers `UsageProviderID.isAntigravity(shortName:)` and `init?(shortName:)` are deleted.

**Tech Stack:** Swift 6, swift-testing (`@Test`/`#expect`), `swift test` / `swift build` from `macos/AIUsageMonitor`.

---

All commands run from `macos/AIUsageMonitor`. Full suite: `swift test`.

## File Structure

- Modify: `Sources/AIUsageMonitorCore/UsageModels.swift` — add `providerID` field to `ProviderSnapshot`.
- Modify: `Sources/AIUsageMonitorCore/RemainingQuotaPresenter.swift` — generic collapse.
- Modify: `Sources/AIUsageMonitorCore/UsageMonitorSettings.swift` — id-based filter; delete string helpers.
- Modify (call sites gain `providerID:`): `ClaudeUsageProvider.swift`, `CodexUsageProvider.swift`, `CodexRateLimitParser.swift`, `AntigravityUsageProvider.swift`, `UsageSnapshotProvider.swift`, `RemainingQuotaPresenter.swift`, `StatusMenuView.swift`.
- Modify (tests gain `providerID:` / adjusted): all four test files containing `ProviderSnapshot(`.

---

## Task 1: Add `providerID` to `ProviderSnapshot` and update every call site

This is a mechanical "make it compile" task — no behavior change. `providerID` is required (no default) so every snapshot creator declares identity explicitly.

**Files:**
- Modify: `Sources/AIUsageMonitorCore/UsageModels.swift:24-49`
- Modify: all call sites listed in the mapping table below.

- [ ] **Step 1: Add the field and init parameter**

In `Sources/AIUsageMonitorCore/UsageModels.swift`, change the `ProviderSnapshot` struct so it stores and accepts `providerID`. The new struct:

```swift
public struct ProviderSnapshot: Equatable, Identifiable, Sendable {
    public let id: String
    public let providerID: UsageProviderID
    public let name: String
    public let shortName: String
    public let plan: String?
    public let windows: [UsageWindow]
    public let isAvailable: Bool
    public let updatedAt: Date

    public init(
        providerID: UsageProviderID,
        name: String,
        shortName: String,
        plan: String? = nil,
        windows: [UsageWindow],
        isAvailable: Bool = true,
        updatedAt: Date = .now
    ) {
        self.id = shortName
        self.providerID = providerID
        self.name = name
        self.shortName = shortName
        self.plan = plan
        self.windows = windows
        self.isAvailable = isAvailable
        self.updatedAt = updatedAt
    }
}
```

- [ ] **Step 2: Run build to see all the call-site errors**

Run: `swift build`
Expected: FAIL — "missing argument for parameter 'providerID'" at each `ProviderSnapshot(...)` call site.

- [ ] **Step 3: Add `providerID:` as the first argument to every call site**

Insert `providerID: <value>,` as the first argument in each `ProviderSnapshot(...)` below. Value is decided by the snapshot's provider (CC → `.claudeCode`, CX → `.codex`, AG/AGg/AGc/grouped → `.antigravity`).

Production code:

| File | Line | shortName | providerID |
|------|------|-----------|------------|
| `Sources/AIUsageMonitorCore/ClaudeUsageProvider.swift` | 10 | CC | `.claudeCode` |
| `Sources/AIUsageMonitorCore/ClaudeUsageProvider.swift` | 17 | CC | `.claudeCode` |
| `Sources/AIUsageMonitorCore/CodexUsageProvider.swift` | 11 | CX | `.codex` |
| `Sources/AIUsageMonitorCore/CodexRateLimitParser.swift` | 7 | CX | `.codex` |
| `Sources/AIUsageMonitorCore/CodexRateLimitParser.swift` | 32 | CX | `.codex` |
| `Sources/AIUsageMonitorCore/AntigravityUsageProvider.swift` | 36 | AG | `.antigravity` |
| `Sources/AIUsageMonitorCore/AntigravityUsageProvider.swift` | 53 | AG | `.antigravity` |
| `Sources/AIUsageMonitorCore/AntigravityUsageProvider.swift` | 69 | grouped | `.antigravity` |
| `Sources/AIUsageMonitorCore/UsageSnapshotProvider.swift` | 16 | CC | `.claudeCode` |
| `Sources/AIUsageMonitorCore/UsageSnapshotProvider.swift` | 34 | CX | `.codex` |
| `Sources/AIUsageMonitorCore/UsageSnapshotProvider.swift` | 53 | AGg | `.antigravity` |
| `Sources/AIUsageMonitorCore/UsageSnapshotProvider.swift` | 62 | AGc | `.antigravity` |
| `Sources/AIUsageMonitorCore/RemainingQuotaPresenter.swift` | 97 | AG (collapsed) | `.antigravity` |
| `Sources/AIUsageMonitorApp/StatusMenuView.swift` | 109 | CC | `.claudeCode` |
| `Sources/AIUsageMonitorApp/StatusMenuView.swift` | 118 | CX | `.codex` |
| `Sources/AIUsageMonitorApp/StatusMenuView.swift` | 126 | AGg | `.antigravity` |
| `Sources/AIUsageMonitorApp/StatusMenuView.swift` | 135 | AGc | `.antigravity` |

Example (`ClaudeUsageProvider.swift:17`):

```swift
return ProviderSnapshot(providerID: .claudeCode, name: "Claude Code", shortName: "CC", windows: windows)
```

Test code (add `providerID:` as first argument, same CC/CX/AG→id rule):

| File | shortNames present | providerID per shortName |
|------|--------------------|--------------------------|
| `Tests/AIUsageMonitorCoreTests/UsageMonitorSettingsTests.swift` | CC, CX, AG, AGg, AGc | CC→`.claudeCode`, CX→`.codex`, AG/AGg/AGc→`.antigravity` |
| `Tests/AIUsageMonitorCoreTests/LiveUsageSnapshotProviderTests.swift` | CC, CX, AGg, AGc | same rule |
| `Tests/AIUsageMonitorCoreTests/RemainingQuotaPresenterTests.swift` | CC, CX, AG, AGg, AGc | same rule |
| `Tests/AIUsageMonitorAppTests/StatusMenuImageRendererTests.swift` | AGg, AGc | `.antigravity` |

- [ ] **Step 4: Build and run the full suite — behavior unchanged, everything green**

Run: `swift build && swift test`
Expected: PASS — all existing tests pass (collapse and settings still use the old string helpers, which remain in place this task).

- [ ] **Step 5: Commit**

```bash
git add macos/AIUsageMonitor
git commit -m "refactor: [macos] add providerID to ProviderSnapshot"
```

---

## Task 2: Generalize menu-bar collapse to group-by-providerID

Replace the AG-only collapse with a generic rule: group snapshots by `providerID` (first-seen order); a group with one snapshot is kept as-is, a group with >1 snapshots is merged into one chip.

**Files:**
- Modify: `Sources/AIUsageMonitorCore/RemainingQuotaPresenter.swift:69-106`
- Test: `Tests/AIUsageMonitorCoreTests/RemainingQuotaPresenterTests.swift`

- [ ] **Step 1: Write the failing test (a non-Antigravity provider also collapses)**

Add to `RemainingQuotaPresenterTests.swift` inside the suite:

```swift
@Test("collapses any provider that emits multiple snapshots, not just antigravity")
func collapsesAnyMultiSnapshotProvider() {
    let snapshots = [
        ProviderSnapshot(providerID: .codex, name: "Codex A", shortName: "CXa",
                         windows: [UsageWindow(label: "5h", percent: 20, kind: .available)]),
        ProviderSnapshot(providerID: .codex, name: "Codex B", shortName: "CXb",
                         windows: [UsageWindow(label: "5h", percent: 5, kind: .available)])
    ]

    let collapsed = RemainingQuotaPresenter.collapsedForMenuBar(snapshots)

    // Two codex snapshots become one "Codex" chip with the worst remaining window.
    #expect(collapsed.map(\.shortName) == ["CX"])
    #expect(collapsed[0].name == "Codex")
    #expect(collapsed[0].providerID == .codex)
    #expect(RemainingQuotaPresenter.primaryRemainingPercent(for: collapsed[0]) == 5)
}
```

- [ ] **Step 2: Run it to verify it fails**

Run: `swift test --filter collapsesAnyMultiSnapshotProvider`
Expected: FAIL — current code only collapses AG-prefixed snapshots, so the two `CXa`/`CXb` chips stay separate.

- [ ] **Step 3: Rewrite `collapsedForMenuBar` to be generic**

Replace the whole method body (`Sources/AIUsageMonitorCore/RemainingQuotaPresenter.swift:69-106`) with:

```swift
    /// Collapses snapshots so each provider occupies one compact menu-bar chip.
    /// Snapshots are grouped by `providerID`, preserving the order each provider
    /// first appears. A provider with a single snapshot is left untouched. A
    /// provider that emitted multiple snapshots is merged into one chip whose
    /// representative window is the worst (lowest remaining) across the group, so
    /// the tightest pool surfaces. The chip's name/shortName come from the
    /// provider id, keeping the rule free of any per-provider special case.
    public static func collapsedForMenuBar(_ snapshots: [ProviderSnapshot]) -> [ProviderSnapshot] {
        var order: [UsageProviderID] = []
        var groups: [UsageProviderID: [ProviderSnapshot]] = [:]
        for snapshot in snapshots {
            if groups[snapshot.providerID] == nil { order.append(snapshot.providerID) }
            groups[snapshot.providerID, default: []].append(snapshot)
        }

        return order.compactMap { providerID -> ProviderSnapshot? in
            guard let group = groups[providerID] else { return nil }
            if group.count == 1 { return group[0] }

            let windows = group.flatMap(\.windows)
            let worst = windows.min(by: { remainingPercent(for: $0) < remainingPercent(for: $1) })
            return ProviderSnapshot(
                providerID: providerID,
                name: providerID.displayName,
                shortName: providerID.shortName,
                plan: group.first?.plan,
                windows: worst.map { [$0] } ?? [],
                isAvailable: group.contains { $0.isAvailable }
            )
        }
    }
```

- [ ] **Step 4: Run the collapse tests to verify all pass**

Run: `swift test --filter RemainingQuotaPresenter`
Expected: PASS — new generic test plus the existing `collapsesAntigravityForMenuBar` (collapsed name "Antigravity", shortName "AG", worst remaining 0) and `collapsePreservesOthers` (lone AG + CX kept in order).

- [ ] **Step 5: Commit**

```bash
git add macos/AIUsageMonitor
git commit -m "refactor: [macos] collapse menu bar by providerID, drop AG-only path"
```

---

## Task 3: Filter settings by `providerID` and delete the string helpers

`menuBarSnapshots` reads `providerID` directly; the `isAntigravity(shortName:)` / `init?(shortName:)` extension is deleted along with its test.

**Files:**
- Modify: `Sources/AIUsageMonitorCore/UsageMonitorSettings.swift:48-76`
- Test: `Tests/AIUsageMonitorCoreTests/UsageMonitorSettingsTests.swift`

- [ ] **Step 1: Delete the now-obsolete test**

Remove the entire `agPrefixResolvesToAntigravity` test (`UsageMonitorSettingsTests.swift:58-67`, the `@Test("any AG-prefixed shortName resolves to the antigravity provider")` block). Its subject is being deleted.

- [ ] **Step 2: Run the settings suite to confirm it still builds without that test**

Run: `swift test --filter "Usage monitor settings"`
Expected: PASS — remaining tests (`filtersMenuBarSnapshots`, `singleToggleControlsBothAntigravityCards`, etc.) still pass because `menuBarSnapshots` still uses `init?(shortName:)` at this point.

- [ ] **Step 3: Rewrite `menuBarSnapshots` to use `providerID` and delete the extension**

In `Sources/AIUsageMonitorCore/UsageMonitorSettings.swift`, replace the body of `menuBarSnapshots` (lines 48-53):

```swift
    public func menuBarSnapshots(from snapshots: [ProviderSnapshot]) -> [ProviderSnapshot] {
        snapshots.filter { menuBarProviderIDs.contains($0.providerID) }
    }
```

Then delete the entire trailing extension (`UsageMonitorSettings.swift:56-76`):

```swift
public extension UsageProviderID {
    static func isAntigravity(shortName: String) -> Bool { ... }
    init?(shortName: String) { ... }
}
```

- [ ] **Step 4: Run the full suite**

Run: `swift build && swift test`
Expected: PASS — no remaining references to `isAntigravity` or `UsageProviderID(shortName:)`. `singleToggleControlsBothAntigravityCards` passes via the `providerID: .antigravity` set on `AGg`/`AGc` in Task 1.

- [ ] **Step 5: Verify the string convention is fully gone**

Run: `grep -rn "isAntigravity\|hasPrefix(\"AG\")\|UsageProviderID(shortName" Sources Tests`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add macos/AIUsageMonitor
git commit -m "refactor: [macos] filter menu bar by providerID, remove AG string convention"
```

---

## Done-when

- `swift test` green from `macos/AIUsageMonitor`.
- `grep` in Task 3 Step 5 returns nothing.
- Menu bar and dropdown behave exactly as before (Antigravity still one collapsed "AG" chip; Claude/Codex unchanged).
- `CLAUDE.md` mentions `UsageProviderID.isAntigravity` as the AG-prefix convention; update that line to describe the new providerID-based grouping after the refactor lands (docs follow-up, not blocking).
