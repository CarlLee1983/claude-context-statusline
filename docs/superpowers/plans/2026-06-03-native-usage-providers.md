# Native Usage Providers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the menu bar app's demo data with real Claude + Codex usage fetched natively in Swift.

**Architecture:** Pure parsing core (unit-tested) plus thin I/O boundaries (Keychain, URLSession, subprocess — untested). Claude and Codex are fetched concurrently; either failing only marks that provider unavailable. A 5-minute async refresh loop drives updates.

**Tech Stack:** Swift 6.2, Swift Package Manager, Swift `Testing`, AppKit `NSStatusItem`, Foundation `Process` / `URLSession`.

All commands run from `macos/AIUsageMonitor`. Reference spec: `docs/superpowers/specs/2026-06-03-native-usage-providers-design.md`.

---

## Task 1: Claude usage parser (pure)

**Files:**
- Create: `Sources/AIUsageMonitorCore/ClaudeUsageParser.swift`
- Test: `Tests/AIUsageMonitorCoreTests/ClaudeUsageParserTests.swift`

- [ ] **Step 1: Write the failing test**

Create `Tests/AIUsageMonitorCoreTests/ClaudeUsageParserTests.swift`:

```swift
import Foundation
import Testing
@testable import AIUsageMonitorCore

@Suite("Claude usage parser")
struct ClaudeUsageParserTests {
    @Test("parses five-hour and seven-day utilization windows")
    func parsesWindows() {
        let json = """
        {
          "five_hour": { "utilization": 7, "resets_at": "2027-01-15T08:30:00Z" },
          "seven_day": { "utilization": 25, "resets_at": "2027-01-20T08:30:00Z" }
        }
        """.data(using: .utf8)!

        let windows = ClaudeUsageParser.parse(json)

        #expect(windows.map(\.label) == ["5h", "7d"])
        #expect(windows.map(\.percent) == [7, 25])
        #expect(windows.allSatisfy { $0.kind == .used })
    }

    @Test("skips a missing window safely")
    func partial() {
        let json = #"{ "five_hour": { "utilization": 50, "resets_at": "2027-01-15T08:30:00Z" } }"#
            .data(using: .utf8)!
        let windows = ClaudeUsageParser.parse(json)
        #expect(windows.map(\.label) == ["5h"])
        #expect(windows[0].percent == 50)
    }

    @Test("returns empty for malformed json")
    func malformed() {
        #expect(ClaudeUsageParser.parse(Data("nonsense".utf8)).isEmpty)
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `swift test --filter ClaudeUsageParserTests`
Expected: FAIL — compile error, `ClaudeUsageParser` is not defined.

- [ ] **Step 3: Write minimal implementation**

Create `Sources/AIUsageMonitorCore/ClaudeUsageParser.swift`:

```swift
import Foundation

/// Parses the Anthropic OAuth usage endpoint payload into `.used` usage windows.
/// Pure and total: any malformed or missing data yields an empty array.
public enum ClaudeUsageParser {
    public static func parse(_ data: Data) -> [UsageWindow] {
        guard let decoded = try? JSONDecoder().decode(Response.self, from: data) else {
            return []
        }
        var windows: [UsageWindow] = []
        if let window = makeWindow(label: "5h", node: decoded.fiveHour) { windows.append(window) }
        if let window = makeWindow(label: "7d", node: decoded.sevenDay) { windows.append(window) }
        return windows
    }

    private static func makeWindow(label: String, node: Window?) -> UsageWindow? {
        guard let node else { return nil }
        return UsageWindow(
            label: label,
            percent: node.utilization,
            kind: .used,
            resetAt: ISO8601DateFormatter().date(from: node.resetsAt)
        )
    }

    private struct Response: Decodable {
        let fiveHour: Window?
        let sevenDay: Window?

        enum CodingKeys: String, CodingKey {
            case fiveHour = "five_hour"
            case sevenDay = "seven_day"
        }
    }

    private struct Window: Decodable {
        let utilization: Double
        let resetsAt: String

        enum CodingKeys: String, CodingKey {
            case utilization
            case resetsAt = "resets_at"
        }
    }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `swift test --filter ClaudeUsageParserTests`
Expected: PASS — 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add Sources/AIUsageMonitorCore/ClaudeUsageParser.swift Tests/AIUsageMonitorCoreTests/ClaudeUsageParserTests.swift
git commit -m "feat: [macos] Add Claude usage parser"
```

---

## Task 2: Claude usage provider (boundary)

**Files:**
- Create: `Sources/AIUsageMonitorCore/ClaudeUsageProvider.swift`

No unit test: this is thin I/O (Keychain + network) verified end-to-end in Task 7.

- [ ] **Step 1: Write the implementation**

Create `Sources/AIUsageMonitorCore/ClaudeUsageProvider.swift`:

```swift
import Foundation

/// Reads the Claude Code OAuth token from the macOS Keychain and queries the
/// Anthropic usage endpoint. All failures collapse to an unavailable snapshot.
/// The access token is only held in memory and never logged or rendered.
public struct ClaudeUsageProvider: Sendable {
    public init() {}

    public func snapshot() async -> ProviderSnapshot {
        let unavailable = ProviderSnapshot(
            name: "Claude Code", shortName: "CC", windows: [], isAvailable: false
        )
        guard let token = Self.readAccessToken() else { return unavailable }
        guard let data = await Self.fetchUsage(token: token) else { return unavailable }
        let windows = ClaudeUsageParser.parse(data)
        guard !windows.isEmpty else { return unavailable }
        return ProviderSnapshot(name: "Claude Code", shortName: "CC", windows: windows)
    }

    private static func readAccessToken() -> String? {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/security")
        process.arguments = ["find-generic-password", "-s", "Claude Code-credentials", "-w"]
        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = FileHandle.nullDevice
        do { try process.run() } catch { return nil }
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        guard
            let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
            let oauth = object["claudeAiOauth"] as? [String: Any],
            let token = oauth["accessToken"] as? String
        else { return nil }
        return token
    }

    private static func fetchUsage(token: String) async -> Data? {
        guard let url = URL(string: "https://api.anthropic.com/api/oauth/usage") else { return nil }
        var request = URLRequest(url: url)
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("oauth-2025-04-20", forHTTPHeaderField: "anthropic-beta")
        request.timeoutInterval = 8
        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            guard
                let http = response as? HTTPURLResponse,
                (200..<300).contains(http.statusCode)
            else { return nil }
            return data
        } catch {
            return nil
        }
    }
}
```

- [ ] **Step 2: Verify it compiles**

Run: `swift build`
Expected: `Build complete!` with no errors.

- [ ] **Step 3: Commit**

```bash
git add Sources/AIUsageMonitorCore/ClaudeUsageProvider.swift
git commit -m "feat: [macos] Add Claude usage provider boundary"
```

---

## Task 3: Codex executable resolver (pure selection + boundary lookup)

**Files:**
- Create: `Sources/AIUsageMonitorCore/CodexExecutableResolver.swift`
- Test: `Tests/AIUsageMonitorCoreTests/CodexExecutableResolverTests.swift`

- [ ] **Step 1: Write the failing test**

Create `Tests/AIUsageMonitorCoreTests/CodexExecutableResolverTests.swift`:

```swift
import Foundation
import Testing
@testable import AIUsageMonitorCore

@Suite("Codex executable resolver")
struct CodexExecutableResolverTests {
    @Test("selects the newest versioned path by sort order")
    func newest() {
        let candidates = [
            "/Users/x/.nvm/versions/node/v18.20.0/bin/codex",
            "/Users/x/.nvm/versions/node/v20.10.0/bin/codex",
            "/Users/x/.nvm/versions/node/v18.9.0/bin/codex",
        ]
        #expect(
            CodexExecutableResolver.selectNewest(from: candidates)
                == "/Users/x/.nvm/versions/node/v20.10.0/bin/codex"
        )
    }

    @Test("returns nil when there are no candidates")
    func none() {
        #expect(CodexExecutableResolver.selectNewest(from: []) == nil)
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `swift test --filter CodexExecutableResolverTests`
Expected: FAIL — compile error, `CodexExecutableResolver` is not defined.

- [ ] **Step 3: Write minimal implementation**

Create `Sources/AIUsageMonitorCore/CodexExecutableResolver.swift`:

```swift
import Foundation

/// Locates the `codex` executable across PATH, common install dirs, and
/// versioned node-manager directories. The version-selection step is pure and
/// unit tested; the filesystem probing is a thin boundary.
public enum CodexExecutableResolver {
    /// Pure: pick the newest versioned candidate (lexicographic sort, last wins).
    /// Mirrors the reference Python `sorted(hits)[-1]` behaviour.
    static func selectNewest(from candidates: [String]) -> String? {
        candidates.sorted().last
    }

    /// Resolve the absolute path to `codex`, or nil if not found.
    public static func resolve() -> String? {
        let fileManager = FileManager.default
        let home = NSHomeDirectory()

        for dir in ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin"] {
            let path = dir + "/codex"
            if fileManager.isExecutableFile(atPath: path) { return path }
        }

        let globRoots = [
            home + "/.nvm/versions/node",
            home + "/Library/Application Support/Herd/config/nvm/versions/node",
        ]
        var hits: [String] = []
        for root in globRoots {
            guard let entries = try? fileManager.contentsOfDirectory(atPath: root) else { continue }
            for entry in entries {
                let path = root + "/" + entry + "/bin/codex"
                if fileManager.isExecutableFile(atPath: path) { hits.append(path) }
            }
        }
        for fixed in [home + "/.volta/bin/codex", home + "/.local/bin/codex"] {
            if fileManager.isExecutableFile(atPath: fixed) { hits.append(fixed) }
        }
        if let newest = selectNewest(from: hits) { return newest }

        return loginShellLookup()
    }

    private static func loginShellLookup() -> String? {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/zsh")
        process.arguments = ["-lc", "command -v codex"]
        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = FileHandle.nullDevice
        do { try process.run() } catch { return nil }
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        let path = String(decoding: data, as: UTF8.self).trimmingCharacters(in: .whitespacesAndNewlines)
        return path.isEmpty ? nil : path
    }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `swift test --filter CodexExecutableResolverTests`
Expected: PASS — 2 tests pass.

- [ ] **Step 5: Commit**

```bash
git add Sources/AIUsageMonitorCore/CodexExecutableResolver.swift Tests/AIUsageMonitorCoreTests/CodexExecutableResolverTests.swift
git commit -m "feat: [macos] Add Codex executable resolver"
```

---

## Task 4: Codex usage provider (boundary)

**Files:**
- Create: `Sources/AIUsageMonitorCore/CodexUsageProvider.swift`

No unit test: thin subprocess I/O. JSON parsing is already covered by `CodexRateLimitParserTests`. Verified end-to-end in Task 7.

- [ ] **Step 1: Write the implementation**

Create `Sources/AIUsageMonitorCore/CodexUsageProvider.swift`:

```swift
import Foundation

/// Drives `codex app-server` over JSON-RPC to read account rate limits, then
/// feeds the `result` payload to `CodexRateLimitParser`. A watchdog guarantees
/// the subprocess is terminated so this never hangs. Failures collapse to an
/// unavailable snapshot.
public struct CodexUsageProvider: Sendable {
    public init() {}

    public func snapshot() async -> ProviderSnapshot {
        let unavailable = ProviderSnapshot(
            name: "Codex", shortName: "CX", windows: [], isAvailable: false
        )
        guard let result = Self.readRateLimitsResult() else { return unavailable }
        return (try? CodexRateLimitParser.parse(result)) ?? unavailable
    }

    /// Returns the JSON-encoded `result` object (containing `rateLimits`) or nil.
    private static func readRateLimitsResult() -> Data? {
        guard let codex = CodexExecutableResolver.resolve() else { return nil }

        let process = Process()
        process.executableURL = URL(fileURLWithPath: codex)
        process.arguments = ["app-server"]
        var environment = ProcessInfo.processInfo.environment
        let binDir = (codex as NSString).deletingLastPathComponent
        environment["PATH"] = binDir + ":" + (environment["PATH"] ?? "")
        process.environment = environment

        let inPipe = Pipe()
        let outPipe = Pipe()
        process.standardInput = inPipe
        process.standardOutput = outPipe
        process.standardError = FileHandle.nullDevice
        do { try process.run() } catch { return nil }

        // Watchdog: guarantee termination so availableData reaches EOF.
        let watchdog = DispatchWorkItem { if process.isRunning { process.terminate() } }
        DispatchQueue.global().asyncAfter(deadline: .now() + 8, execute: watchdog)

        func send(_ object: [String: Any]) {
            guard let data = try? JSONSerialization.data(withJSONObject: object) else { return }
            inPipe.fileHandleForWriting.write(data)
            inPipe.fileHandleForWriting.write(Data("\n".utf8))
        }

        send([
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": ["clientInfo": [
                "name": "ai-usage-monitor", "title": "AI Usage Monitor", "version": "0.1",
            ]],
        ])
        send(["jsonrpc": "2.0", "id": 2, "method": "account/rateLimits/read", "params": [:]])

        let handle = outPipe.fileHandleForReading
        var buffer = Data()
        var result: Data?
        while true {
            let chunk = handle.availableData
            if chunk.isEmpty { break } // EOF (process exited or watchdog fired)
            buffer.append(chunk)
            while let newline = buffer.firstIndex(of: 0x0A) {
                let lineData = buffer.subdata(in: buffer.startIndex..<newline)
                buffer.removeSubrange(buffer.startIndex...newline)
                guard
                    let message = try? JSONSerialization.jsonObject(with: lineData) as? [String: Any],
                    (message["id"] as? Int) == 2,
                    let resultObject = message["result"]
                else { continue }
                result = try? JSONSerialization.data(withJSONObject: resultObject)
            }
            if result != nil { break }
        }

        watchdog.cancel()
        if process.isRunning { process.terminate() }
        return result
    }
}
```

- [ ] **Step 2: Verify it compiles**

Run: `swift build`
Expected: `Build complete!` with no errors.

- [ ] **Step 3: Commit**

```bash
git add Sources/AIUsageMonitorCore/CodexUsageProvider.swift
git commit -m "feat: [macos] Add Codex usage provider boundary"
```

---

## Task 5: Live snapshot provider (composition)

**Files:**
- Create: `Sources/AIUsageMonitorCore/LiveUsageSnapshotProvider.swift`

No unit test: pure composition of two boundary providers; verified in Task 7.

- [ ] **Step 1: Write the implementation**

Create `Sources/AIUsageMonitorCore/LiveUsageSnapshotProvider.swift`:

```swift
import Foundation

/// Production provider: fetches Claude and Codex concurrently and returns both
/// snapshots in a stable order. A failed provider is surfaced as unavailable
/// rather than dropped, so the menu shows it exists.
public struct LiveUsageSnapshotProvider: UsageSnapshotProviding {
    private let claude = ClaudeUsageProvider()
    private let codex = CodexUsageProvider()

    public init() {}

    public func snapshots() async -> [ProviderSnapshot] {
        async let claudeSnapshot = claude.snapshot()
        async let codexSnapshot = codex.snapshot()
        return await [claudeSnapshot, codexSnapshot]
    }
}
```

- [ ] **Step 2: Verify it compiles**

Run: `swift build`
Expected: `Build complete!` with no errors.

- [ ] **Step 3: Commit**

```bash
git add Sources/AIUsageMonitorCore/LiveUsageSnapshotProvider.swift
git commit -m "feat: [macos] Add live usage snapshot provider"
```

---

## Task 6: Wire the app to live data with a 5-minute refresh loop

**Files:**
- Modify: `Sources/AIUsageMonitorApp/AIUsageMonitorApp.swift:11`
- Modify: `Sources/AIUsageMonitorApp/StatusMenuController.swift` (`start()`, quit handler, add property)

- [ ] **Step 1: Swap the demo provider for the live provider**

In `Sources/AIUsageMonitorApp/AIUsageMonitorApp.swift`, change the controller construction:

```swift
        Runtime.controller = StatusMenuController(provider: LiveUsageSnapshotProvider())
```

(was `DemoUsageSnapshotProvider()`.)

- [ ] **Step 2: Add the refresh-task property**

In `Sources/AIUsageMonitorApp/StatusMenuController.swift`, add a stored property alongside the existing `private var isRefreshing = false`:

```swift
    private var refreshTask: Task<Void, Never>?
```

- [ ] **Step 3: Replace `start()` with an auto-refresh loop**

Replace the existing `start()` method:

```swift
    func start() {
        rebuildMenu()
        refreshTask = Task { [weak self] in
            while !Task.isCancelled {
                await self?.refresh()
                try? await Task.sleep(for: .seconds(300))
            }
        }
    }
```

- [ ] **Step 4: Cancel the loop on quit**

Replace the existing `quitMenuItemSelected()` method:

```swift
    @objc private func quitMenuItemSelected() {
        refreshTask?.cancel()
        NSApplication.shared.terminate(nil)
    }
```

- [ ] **Step 5: Build and run the full test suite**

Run: `swift build && swift test`
Expected: `Build complete!` and all tests pass (Claude parser, Codex parser, Codex resolver, Antigravity parser, RemainingQuotaPresenter).

- [ ] **Step 6: Commit**

```bash
git add Sources/AIUsageMonitorApp/AIUsageMonitorApp.swift Sources/AIUsageMonitorApp/StatusMenuController.swift
git commit -m "feat: [macos] Use live providers with 5-minute auto-refresh"
```

---

## Task 7: End-to-end verification and docs

**Files:**
- Modify: `README.md` (the `macos/AIUsageMonitor/README.md` "Current coverage" section)
- Modify: `../../CHANGELOG.md` (repository root changelog)

- [ ] **Step 1: Rebuild the app bundle and launch it**

```bash
./Scripts/build-app.sh
pkill -f AIUsageMonitor.app/Contents/MacOS/AIUsageMonitor 2>/dev/null || true
open .build/AIUsageMonitor.app
```

- [ ] **Step 2: Confirm real values render**

Capture the menu bar and confirm the Claude (CC) and Codex (CX) chips show plausible
real percentages (not the demo 93/99), and that Antigravity no longer appears:

```bash
screencapture -x -R1470,0,1920,30 /tmp/menubar-live.png
```

Open `/tmp/menubar-live.png` and verify two chips with real numbers. Cross-check against
the reference plugin output:

```bash
python3 ../../experiments/usage-probe.py
```

The CC/CX percentages in the menu bar should match `usage-probe.py`'s 5h numbers.

- [ ] **Step 3: Update the macOS app README**

In `README.md`, replace the `## Current coverage` section with:

```markdown
## Current coverage

- Live Claude Code usage (Keychain OAuth token → Anthropic usage endpoint), 5h / 7d windows.
- Live Codex usage (`codex app-server` JSON-RPC rate limits), 5h / 7d windows.
- Native AppKit menu bar UI with 5-minute auto-refresh plus a manual Refresh action.
- Antigravity is temporarily removed and will return in a later round.
```

Also update the intro paragraph that begins "This first MVP uses demo provider data" to:

```markdown
This MVP fetches live Claude and Codex usage natively (no Python runtime dependency). It
runs as an accessory menu bar app through AppKit `NSStatusItem` and does not require
signing or notarization for local development.
```

- [ ] **Step 4: Update the repository CHANGELOG**

Add an entry near the top of `../../CHANGELOG.md` under an Unreleased/dated heading:

```markdown
- macOS app: native live Claude + Codex usage in the menu bar with 5-minute auto-refresh
  (replaces demo data). Antigravity temporarily removed.
```

- [ ] **Step 5: Commit**

```bash
git add README.md ../../CHANGELOG.md
git commit -m "docs: [macos] Document live Claude+Codex usage coverage"
```

---

## Self-Review

- **Spec coverage:**
  - Full native Swift, no runtime Python → Tasks 1–5 (Process/URLSession/Keychain in Swift).
  - Claude provider (Keychain + URLSession + parser) → Tasks 1–2.
  - Codex provider (app-server JSON-RPC + node-path resolution + existing parser) → Tasks 3–4.
  - Concurrent composition, failed provider shown unavailable → Task 5.
  - Swap demo → live, 5-minute refresh, Antigravity removed → Task 6.
  - Never-crash invariant → every provider returns an unavailable snapshot on failure (Tasks 2, 4, 5).
  - Token never logged → only held in memory in `ClaudeUsageProvider` (Task 2).
  - Pure-core/thin-edge testing split → Tasks 1 & 3 tested; boundaries (Tasks 2, 4, 5) verified in Task 7.
  - YAGNI: no disk cache/backoff, no Antigravity → reflected by their absence.
- **Placeholder scan:** No TBD/TODO; every code step contains full code and exact commands.
- **Type consistency:** `ClaudeUsageParser.parse(Data) -> [UsageWindow]`, `CodexRateLimitParser.parse(Data) throws -> ProviderSnapshot` (existing, shortName "CX"), `CodexExecutableResolver.selectNewest(from:)` / `.resolve()`, `ClaudeUsageProvider.snapshot()`, `CodexUsageProvider.snapshot()`, `LiveUsageSnapshotProvider.snapshots()` are used consistently across tasks. `ProviderSnapshot(name:shortName:plan:windows:isAvailable:)` and `UsageWindow(label:percent:kind:resetAt:)` match the existing `UsageModels.swift` initializers.
