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

    @Test("agy /usage text wins and is shown as available quota")
    func textPathWins() async {
        let usageText = """
        └ Model Quota

          Gemini 3.5 Flash (Medium)
          ███████████ 92%
          Quota available
        """
        let provider = AntigravityUsageProvider(
            captureText: { usageText },
            loadAccounts: { Data() }, // must be ignored when text parses
            now: { self.now }
        )

        let snapshot = await provider.snapshot()

        #expect(snapshot.name == "Antigravity")
        #expect(snapshot.shortName == "AG")
        #expect(snapshot.isAvailable)
        #expect(snapshot.plan == "agy /usage")
        #expect(snapshot.windows.map(\.label) == ["Gemini 3.5 Flash (Medium)"])
        #expect(snapshot.windows[0].kind == .available)
    }

    @Test("falls back to accounts cooldown when text capture is empty")
    func accountsFallback() async {
        let provider = AntigravityUsageProvider(
            captureText: { nil },
            loadAccounts: { self.accountsData(claudeOffset: 3_600) },
            now: { self.now }
        )

        let snapshot = await provider.snapshot()

        #expect(snapshot.isAvailable)
        #expect(snapshot.plan == "1 acct")
        #expect(snapshot.windows.map(\.label) == ["Claude"])
        #expect(snapshot.windows[0].kind == .used)
    }

    @Test("accounts present but no cooldown is available with no windows (ready)")
    func readyState() async {
        let provider = AntigravityUsageProvider(
            captureText: { nil },
            loadAccounts: { self.accountsData(claudeOffset: -60) },
            now: { self.now }
        )

        let snapshot = await provider.snapshot()

        #expect(snapshot.isAvailable)
        #expect(snapshot.windows.isEmpty)
    }

    @Test("no text and no accounts is unavailable")
    func unavailable() async {
        let provider = AntigravityUsageProvider(
            captureText: { nil },
            loadAccounts: { nil },
            now: { self.now }
        )

        let snapshot = await provider.snapshot()

        #expect(!snapshot.isAvailable)
        #expect(snapshot.windows.isEmpty)
    }

    @Test("blank text capture is treated as no data")
    func blankText() async {
        let provider = AntigravityUsageProvider(
            captureText: { "   \n  " },
            loadAccounts: { nil },
            now: { self.now }
        )

        let snapshot = await provider.snapshot()

        #expect(!snapshot.isAvailable)
    }
}
