# Native Menu Bar Icon Remaining UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the native macOS menu bar text summary with compact provider icon chips that show remaining quota, while preserving a safe text fallback and detailed dropdown semantics.

**Architecture:** Add pure remaining-quota presentation helpers to `AIUsageMonitorCore` so behavior can be tested without AppKit. Add an AppKit-only renderer in `AIUsageMonitorApp` that draws a retina-safe `NSImage` status item using researched icon language. Update `StatusMenuController` to use the renderer for the menu bar and the presenter for dropdown copy.

**Tech Stack:** Swift 6 package, macOS 14, AppKit `NSStatusItem`/`NSImage`, Swift Testing, no new dependencies.

---

## File structure

- Create `macos/AIUsageMonitor/Sources/AIUsageMonitorCore/RemainingQuotaPresenter.swift`
  - Pure presentation logic: remaining percent, fallback text, dropdown detail text.
- Create `macos/AIUsageMonitor/Tests/AIUsageMonitorCoreTests/RemainingQuotaPresenterTests.swift`
  - Test-first coverage for remaining calculations, fallback text, and dropdown row copy.
- Create `macos/AIUsageMonitor/Sources/AIUsageMonitorApp/StatusMenuImageRenderer.swift`
  - AppKit drawing for icon + number chips.
  - Local vector approximations: Claude Spark, OpenAI/Codex monochrome mark language, Antigravity gradient arch based on official site asset.
- Modify `macos/AIUsageMonitor/Sources/AIUsageMonitorApp/StatusMenuController.swift`
  - Replace raw `menuTitle` usage with image-first status presentation and remaining fallback.
  - Replace dropdown window rows with remaining-aware strings.
- No changes to parser files.

---

### Task 1: Add remaining-quota presenter tests

**Files:**
- Create: `macos/AIUsageMonitor/Tests/AIUsageMonitorCoreTests/RemainingQuotaPresenterTests.swift`
- Create after test fails: `macos/AIUsageMonitor/Sources/AIUsageMonitorCore/RemainingQuotaPresenter.swift`

- [ ] **Step 1: Write the failing test file**

Create `macos/AIUsageMonitor/Tests/AIUsageMonitorCoreTests/RemainingQuotaPresenterTests.swift`:

```swift
import Foundation
import Testing
@testable import AIUsageMonitorCore

@Suite("Remaining quota presenter")
struct RemainingQuotaPresenterTests {
    @Test("calculates remaining quota from used and available windows")
    func calculatesRemainingQuota() {
        #expect(RemainingQuotaPresenter.remainingPercent(for: UsageWindow(label: "5h", percent: 3, kind: .used)) == 97)
        #expect(RemainingQuotaPresenter.remainingPercent(for: UsageWindow(label: "5h", percent: 100, kind: .used)) == 0)
        #expect(RemainingQuotaPresenter.remainingPercent(for: UsageWindow(label: "Model", percent: 75, kind: .available)) == 75)
        #expect(RemainingQuotaPresenter.remainingPercent(for: UsageWindow(label: "clamped", percent: -5, kind: .used)) == 100)
        #expect(RemainingQuotaPresenter.remainingPercent(for: UsageWindow(label: "clamped", percent: 120, kind: .available)) == 100)
    }

    @Test("uses provider names and remaining values for fallback title")
    func fallbackTitleUsesRemainingValues() {
        let snapshots = [
            ProviderSnapshot(
                name: "Claude Code",
                shortName: "CC",
                windows: [UsageWindow(label: "5h", percent: 3, kind: .used)]
            ),
            ProviderSnapshot(
                name: "Codex",
                shortName: "CX",
                windows: [UsageWindow(label: "5h", percent: 1, kind: .used)]
            ),
            ProviderSnapshot(
                name: "Antigravity",
                shortName: "AG",
                windows: [UsageWindow(label: "Gemini", percent: 100, kind: .available)]
            )
        ]

        let title = RemainingQuotaPresenter.fallbackTitle(for: snapshots)

        #expect(title == "Claude Code 97 Codex 99 Antigravity 100")
        #expect(!title.contains("CC"))
        #expect(!title.contains("CX"))
        #expect(!title.contains("AG"))
        #expect(!title.contains("3%"))
        #expect(!title.contains("1%"))
    }

    @Test("falls back safely for empty and unavailable snapshots")
    func fallbackTitleHandlesEmptyAndUnavailableSnapshots() {
        #expect(RemainingQuotaPresenter.fallbackTitle(for: []) == "AI —")

        let unavailable = ProviderSnapshot(
            name: "Codex",
            shortName: "CX",
            windows: [],
            isAvailable: false
        )

        #expect(RemainingQuotaPresenter.fallbackTitle(for: [unavailable]) == "Codex —")
    }

    @Test("builds dropdown details with remaining and source semantics")
    func dropdownDetailsDescribeRemainingAndSourceSemantics() {
        let reset = Date(timeIntervalSince1970: 1_800_000_000)
        let used = UsageWindow(label: "5h", percent: 3, kind: .used, resetAt: reset)
        let available = UsageWindow(label: "Gemini 3.5 Flash", percent: 75, kind: .available)

        #expect(
            RemainingQuotaPresenter.detailTitle(for: used) ==
                "5h: 97% remaining · used 3% · reset \(reset.formatted(date: .omitted, time: .shortened))"
        )
        #expect(
            RemainingQuotaPresenter.detailTitle(for: available) ==
                "Gemini 3.5 Flash: 75% remaining · available"
        )
    }
}
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
cd macos/AIUsageMonitor
swift test --filter RemainingQuotaPresenterTests
```

Expected: FAIL at compile time with `Cannot find 'RemainingQuotaPresenter' in scope`.

- [ ] **Step 3: Commit the RED test**

```bash
git add macos/AIUsageMonitor/Tests/AIUsageMonitorCoreTests/RemainingQuotaPresenterTests.swift
git commit -m "Specify remaining quota presentation behavior

Constraint: Menu bar now displays remaining quota, not raw provider usage.
Confidence: high
Scope-risk: narrow
Tested: swift test --filter RemainingQuotaPresenterTests fails because presenter is not implemented.
Not-tested: Implementation not started."
```

---

### Task 2: Implement remaining-quota presenter

**Files:**
- Create: `macos/AIUsageMonitor/Sources/AIUsageMonitorCore/RemainingQuotaPresenter.swift`
- Test: `macos/AIUsageMonitor/Tests/AIUsageMonitorCoreTests/RemainingQuotaPresenterTests.swift`

- [ ] **Step 1: Write the minimal presenter implementation**

Create `macos/AIUsageMonitor/Sources/AIUsageMonitorCore/RemainingQuotaPresenter.swift`:

```swift
import Foundation

public enum RemainingQuotaPresenter {
    public static func remainingPercent(for window: UsageWindow) -> Int {
        let remaining: Double
        switch window.kind {
        case .used:
            remaining = 100 - window.percent
        case .available:
            remaining = window.percent
        }
        return Int(max(0, min(100, remaining)).rounded())
    }

    public static func primaryRemainingPercent(for snapshot: ProviderSnapshot) -> Int? {
        guard let firstWindow = snapshot.windows.first else { return nil }
        return remainingPercent(for: firstWindow)
    }

    public static func fallbackTitle(for snapshots: [ProviderSnapshot]) -> String {
        guard !snapshots.isEmpty else { return "AI —" }

        return snapshots.map { snapshot in
            guard let remaining = primaryRemainingPercent(for: snapshot) else {
                return "\(snapshot.name) —"
            }
            return "\(snapshot.name) \(remaining)"
        }.joined(separator: " ")
    }

    public static func detailTitle(for window: UsageWindow) -> String {
        let remaining = remainingPercent(for: window)
        let resetText = window.resetAt.map { " · reset \($0.formatted(date: .omitted, time: .shortened))" } ?? ""

        switch window.kind {
        case .used:
            return "\(window.label): \(remaining)% remaining · used \(Int(window.percent.rounded()))%\(resetText)"
        case .available:
            return "\(window.label): \(remaining)% remaining · available\(resetText)"
        }
    }
}
```

- [ ] **Step 2: Run the focused tests and verify GREEN**

Run:

```bash
cd macos/AIUsageMonitor
swift test --filter RemainingQuotaPresenterTests
```

Expected: PASS for all `RemainingQuotaPresenterTests` tests.

- [ ] **Step 3: Run all package tests**

Run:

```bash
cd macos/AIUsageMonitor
swift test
```

Expected: PASS for parser tests and remaining presenter tests.

- [ ] **Step 4: Commit the presenter**

```bash
git add macos/AIUsageMonitor/Sources/AIUsageMonitorCore/RemainingQuotaPresenter.swift macos/AIUsageMonitor/Tests/AIUsageMonitorCoreTests/RemainingQuotaPresenterTests.swift
git commit -m "Project provider usage into remaining quota UI text

Constraint: Preserve parser percent semantics and add only presentation-level remaining calculations.
Rejected: Rewriting parser outputs to remaining values | parser source semantics must stay unchanged.
Confidence: high
Scope-risk: narrow
Tested: cd macos/AIUsageMonitor && swift test
Not-tested: AppKit menu bar image rendering not implemented yet."
```

---

### Task 3: Add AppKit status menu image renderer

**Files:**
- Create: `macos/AIUsageMonitor/Sources/AIUsageMonitorApp/StatusMenuImageRenderer.swift`
- Uses: `macos/AIUsageMonitor/Sources/AIUsageMonitorCore/RemainingQuotaPresenter.swift`

- [ ] **Step 1: Create the renderer with deterministic image output and fallback summary**

Create `macos/AIUsageMonitor/Sources/AIUsageMonitorApp/StatusMenuImageRenderer.swift`:

```swift
import AIUsageMonitorCore
import AppKit
import Foundation

@MainActor
enum StatusMenuImageRenderer {
    struct RenderedStatus {
        let image: NSImage?
        let fallbackTitle: String
        let accessibilityTitle: String
    }

    static func renderStatus(for snapshots: [ProviderSnapshot]) -> RenderedStatus {
        let fallbackTitle = RemainingQuotaPresenter.fallbackTitle(for: snapshots)
        let entries = snapshots.compactMap { snapshot -> Entry? in
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

    private struct Entry {
        let providerName: String
        let remaining: Int
    }

    private static func draw(entries: [Entry]) -> NSImage {
        let scale = NSScreen.main?.backingScaleFactor ?? 2
        let font = NSFont.monospacedDigitSystemFont(ofSize: 11, weight: .semibold)
        let chipHeight: CGFloat = 18
        let iconSize: CGFloat = 14
        let horizontalPadding: CGFloat = 7
        let iconNumberGap: CGFloat = 5
        let chipGap: CGFloat = 5

        let numberAttributes: [NSAttributedString.Key: Any] = [
            .font: font,
            .foregroundColor: NSColor.white
        ]

        let chipWidths = entries.map { entry in
            let numberWidth = NSString(string: "\(entry.remaining)").size(withAttributes: numberAttributes).width
            return ceil(horizontalPadding * 2 + iconSize + iconNumberGap + numberWidth)
        }
        let totalWidth = chipWidths.reduce(0, +) + chipGap * CGFloat(max(0, chipWidths.count - 1))
        let canvasSize = NSSize(width: totalWidth, height: chipHeight)
        let image = NSImage(size: canvasSize)
        image.isTemplate = false

        image.lockFocus()
        NSGraphicsContext.current?.imageInterpolation = .high

        var x: CGFloat = 0
        for (index, entry) in entries.enumerated() {
            let chipWidth = chipWidths[index]
            let chipRect = NSRect(x: x, y: 0, width: chipWidth, height: chipHeight)
            drawChipBackground(in: chipRect)

            let iconRect = NSRect(
                x: x + horizontalPadding,
                y: (chipHeight - iconSize) / 2,
                width: iconSize,
                height: iconSize
            )
            drawIcon(for: entry.providerName, in: iconRect)

            let number = NSString(string: "\(entry.remaining)")
            let numberSize = number.size(withAttributes: numberAttributes)
            let numberRect = NSRect(
                x: iconRect.maxX + iconNumberGap,
                y: (chipHeight - numberSize.height) / 2 - 0.5,
                width: numberSize.width,
                height: numberSize.height
            )
            number.draw(in: numberRect, withAttributes: numberAttributes)

            x += chipWidth + chipGap
        }

        image.unlockFocus()
        image.size = NSSize(width: canvasSize.width / scale * scale, height: canvasSize.height)
        return image
    }

    private static func drawChipBackground(in rect: NSRect) {
        let path = NSBezierPath(roundedRect: rect, xRadius: rect.height / 2, yRadius: rect.height / 2)
        NSColor.white.withAlphaComponent(0.17).setFill()
        path.fill()
        NSColor.white.withAlphaComponent(0.23).setStroke()
        path.lineWidth = 1
        path.stroke()
    }

    private static func drawIcon(for providerName: String, in rect: NSRect) {
        let lowercased = providerName.lowercased()
        if lowercased.contains("claude") {
            drawClaudeSpark(in: rect)
        } else if lowercased.contains("codex") {
            drawOpenAIMark(in: rect)
        } else if lowercased.contains("antigravity") {
            drawAntigravityArch(in: rect)
        } else {
            drawGenericDot(in: rect)
        }
    }

    private static func drawClaudeSpark(in rect: NSRect) {
        NSColor(calibratedRed: 0.85, green: 0.45, blue: 0.31, alpha: 1).setFill()
        let center = NSPoint(x: rect.midX, y: rect.midY)
        let longRadius = rect.width * 0.48
        let shortRadius = rect.width * 0.16
        let path = NSBezierPath()
        for index in 0..<8 {
            let angle = CGFloat(index) * .pi / 4 - .pi / 2
            let radius = index.isMultiple(of: 2) ? longRadius : shortRadius
            let point = NSPoint(x: center.x + cos(angle) * radius, y: center.y + sin(angle) * radius)
            if index == 0 { path.move(to: point) } else { path.line(to: point) }
        }
        path.close()
        path.fill()
    }

    private static func drawOpenAIMark(in rect: NSRect) {
        NSColor.white.setStroke()
        let path = NSBezierPath(ovalIn: rect.insetBy(dx: 1.5, dy: 1.5))
        path.lineWidth = 1.4
        path.stroke()

        for angle in stride(from: CGFloat(0), to: CGFloat.pi * 2, by: CGFloat.pi / 3) {
            let center = NSPoint(x: rect.midX, y: rect.midY)
            let inner = NSPoint(x: center.x + cos(angle) * 2.0, y: center.y + sin(angle) * 2.0)
            let outer = NSPoint(x: center.x + cos(angle) * 5.0, y: center.y + sin(angle) * 5.0)
            let spoke = NSBezierPath()
            spoke.move(to: inner)
            spoke.line(to: outer)
            spoke.lineWidth = 1.2
            spoke.stroke()
        }
    }

    private static func drawAntigravityArch(in rect: NSRect) {
        let path = NSBezierPath()
        path.move(to: NSPoint(x: rect.minX + 1, y: rect.minY + 1))
        path.curve(
            to: NSPoint(x: rect.maxX - 1, y: rect.minY + 1),
            controlPoint1: NSPoint(x: rect.midX - 2, y: rect.maxY - 1),
            controlPoint2: NSPoint(x: rect.midX + 2, y: rect.maxY - 1)
        )
        path.lineWidth = 3.0
        NSColor.systemBlue.setStroke()
        path.stroke()

        let warmDot = NSBezierPath(ovalIn: NSRect(x: rect.midX - 2, y: rect.maxY - 5, width: 4, height: 4))
        NSColor.systemOrange.setFill()
        warmDot.fill()
    }

    private static func drawGenericDot(in rect: NSRect) {
        NSColor.white.withAlphaComponent(0.85).setFill()
        NSBezierPath(ovalIn: rect.insetBy(dx: 3, dy: 3)).fill()
    }
}
```

- [ ] **Step 2: Build the app target**

Run:

```bash
cd macos/AIUsageMonitor
swift build
```

Expected: PASS with `Build complete!` and no Swift compile errors.

- [ ] **Step 3: Commit the renderer**

```bash
git add macos/AIUsageMonitor/Sources/AIUsageMonitorApp/StatusMenuImageRenderer.swift
git commit -m "Render icon-first remaining quota menu bar image

Constraint: Use researched provider identity cues without adding dependencies or runtime asset fetching.
Rejected: Continuing plain CC/CX/AG text | user approved icon-first chips instead.
Confidence: medium
Scope-risk: moderate
Tested: cd macos/AIUsageMonitor && swift build
Not-tested: Manual macOS menu bar visual pass pending."
```

---

### Task 4: Wire image-first status presentation into the controller

**Files:**
- Modify: `macos/AIUsageMonitor/Sources/AIUsageMonitorApp/StatusMenuController.swift`
- Uses: `macos/AIUsageMonitor/Sources/AIUsageMonitorApp/StatusMenuImageRenderer.swift`
- Uses: `macos/AIUsageMonitor/Sources/AIUsageMonitorCore/RemainingQuotaPresenter.swift`

- [ ] **Step 1: Replace title-only status updates with image-first presentation**

In `StatusMenuController.swift`, replace the existing `refresh`, `menuTitle`, and `setStatusTitle` pieces with this code:

```swift
    private func refresh() async {
        guard !isRefreshing else { return }
        isRefreshing = true
        setStatusTitle("AI")
        snapshots = await provider.snapshots()
        isRefreshing = false
        setStatusPresentation(for: snapshots)
        rebuildMenu()
    }

    private func setStatusTitle(_ title: String) {
        statusItem.button?.image = nil
        statusItem.button?.title = title
        statusItem.button?.toolTip = title == "AI" ? "AI Usage Monitor" : title
    }

    private func setStatusPresentation(for snapshots: [ProviderSnapshot]) {
        let rendered = StatusMenuImageRenderer.renderStatus(for: snapshots)
        if let image = rendered.image {
            statusItem.button?.title = ""
            statusItem.button?.image = image
            statusItem.button?.imagePosition = .imageOnly
            statusItem.button?.toolTip = rendered.accessibilityTitle
        } else {
            setStatusTitle(rendered.fallbackTitle)
        }
    }
```

Delete the old `private var menuTitle: String` computed property entirely.

- [ ] **Step 2: Build and fix mechanical errors only**

Run:

```bash
cd macos/AIUsageMonitor
swift build
```

Expected: PASS. If the build fails because the old `menuTitle` reference remains, remove the stale reference and rerun.

- [ ] **Step 3: Run all tests**

Run:

```bash
cd macos/AIUsageMonitor
swift test
```

Expected: PASS.

- [ ] **Step 4: Commit controller status presentation wiring**

```bash
git add macos/AIUsageMonitor/Sources/AIUsageMonitorApp/StatusMenuController.swift
git commit -m "Use image-first remaining quota status item

Constraint: Status item must never go blank when image rendering is unavailable.
Rejected: Text-only menu bar summary | approved UI uses icon chips with a text fallback.
Confidence: medium
Scope-risk: moderate
Tested: cd macos/AIUsageMonitor && swift build && swift test
Not-tested: Manual menu bar screenshot verification pending."
```

---

### Task 5: Update dropdown rows to show remaining semantics

**Files:**
- Modify: `macos/AIUsageMonitor/Sources/AIUsageMonitorApp/StatusMenuController.swift`
- Test already covers: `macos/AIUsageMonitor/Tests/AIUsageMonitorCoreTests/RemainingQuotaPresenterTests.swift`

- [ ] **Step 1: Replace dropdown window row title generation**

In `StatusMenuController.swift`, replace this existing block inside `for window in snapshot.windows`:

```swift
                    let resetText = window.resetAt.map { " · reset \($0.formatted(date: .omitted, time: .shortened))" } ?? ""
                    let item = NSMenuItem(
                        title: "  \(window.label): \(Int(window.percent.rounded()))% \(window.kind.menuLabel)\(resetText)",
                        action: nil,
                        keyEquivalent: ""
                    )
```

with:

```swift
                    let item = NSMenuItem(
                        title: "  \(RemainingQuotaPresenter.detailTitle(for: window))",
                        action: nil,
                        keyEquivalent: ""
                    )
```

Then delete the private `QuotaKind.menuLabel` extension at the bottom of the file because it is no longer used.

- [ ] **Step 2: Run all tests**

Run:

```bash
cd macos/AIUsageMonitor
swift test
```

Expected: PASS, including dropdown copy tests in `RemainingQuotaPresenterTests`.

- [ ] **Step 3: Build app target**

Run:

```bash
cd macos/AIUsageMonitor
swift build
```

Expected: PASS.

- [ ] **Step 4: Commit dropdown semantics**

```bash
git add macos/AIUsageMonitor/Sources/AIUsageMonitorApp/StatusMenuController.swift
git commit -m "Explain remaining quota in menu details

Constraint: Menu bar is compact, while dropdown must preserve full used/available semantics.
Rejected: Showing raw used percent in dropdown only | user requested remaining-first semantics.
Confidence: high
Scope-risk: narrow
Tested: cd macos/AIUsageMonitor && swift test && swift build
Not-tested: Manual menu interaction pending."
```

---

### Task 6: Manual app smoke verification

**Files:**
- Read/execute: `macos/AIUsageMonitor/README.md`
- No source edits expected unless smoke reveals a bug.

- [ ] **Step 1: Build the local app bundle using the existing README instructions**

Run:

```bash
cd macos/AIUsageMonitor
swift build
```

Expected: PASS.

If the README includes an app-bundle wrapper command, run that exact command next. If it only documents `swift run`, run:

```bash
cd macos/AIUsageMonitor
swift run AIUsageMonitorApp
```

Expected: The app launches as an accessory/menu bar app.

- [ ] **Step 2: Visually verify the menu bar**

Expected visual result with demo data:

- Menu bar shows three soft chips.
- No `CC`, `CX`, or `AG` text appears in the menu bar.
- Values are remaining values: Claude Code `93` for demo `7% used`, Codex `99` for demo `1% used`, Antigravity `100` for demo `100% available`.
- The status item tooltip uses the readable fallback summary with provider names and remaining values.

- [ ] **Step 3: Verify dropdown copy**

Click the status item.

Expected dropdown rows include copy shaped like:

```text
5h: 93% remaining · used 7% · reset <time>
5h: 99% remaining · used 1% · reset <time>
Gemini 3.5 Flash (Medium): 100% remaining · available
```

- [ ] **Step 4: If a visual bug appears, write a focused failing test where possible before editing**

For presenter/copy bugs, add a Swift Testing assertion to `RemainingQuotaPresenterTests.swift` and follow RED/GREEN.

For renderer-only pixel issues that cannot be unit tested, make the smallest visual fix in `StatusMenuImageRenderer.swift`, then rerun:

```bash
cd macos/AIUsageMonitor
swift build
swift test
```

Expected: PASS.

- [ ] **Step 5: Commit smoke fixes or verification note**

If source changed:

```bash
git add macos/AIUsageMonitor/Sources macos/AIUsageMonitor/Tests
git commit -m "Polish native menu bar icon chip rendering

Constraint: Manual menu bar smoke test exposed small visual defects.
Confidence: medium
Scope-risk: narrow
Tested: cd macos/AIUsageMonitor && swift build && swift test; manual app launch and menu bar visual check.
Not-tested: Automated pixel snapshot comparison."
```

If no source changed, do not create an empty commit. Record the verification in the final report.

---

## Final verification checklist

Run:

```bash
cd macos/AIUsageMonitor
swift test
swift build
```

Expected:

- All Swift tests pass.
- App target builds.
- Manual launch shows icon + remaining quota chips.
- Dropdown rows show remaining-first semantics.
- Menu bar has no `CC`, `CX`, or `AG` abbreviation text.
- No new third-party dependency was added.

## Self-review

- Spec coverage: Tasks 1-2 cover remaining projection and fallback; Task 3 covers icon chip rendering; Task 4 wires image-first status presentation; Task 5 covers dropdown semantics; Task 6 covers manual menu bar verification and trademark/runtime-asset risk by using local vector rendering.
- Placeholder scan: no `TBD`, `TODO`, or unspecified implementation steps remain.
- Type consistency: `RemainingQuotaPresenter.remainingPercent`, `primaryRemainingPercent`, `fallbackTitle`, and `detailTitle` are introduced before all later uses; `StatusMenuImageRenderer.renderStatus` is introduced before controller wiring.
