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
