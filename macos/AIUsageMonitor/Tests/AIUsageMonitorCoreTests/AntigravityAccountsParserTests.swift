import Foundation
import Testing
@testable import AIUsageMonitorCore

@Suite("Antigravity accounts parser")
struct AntigravityAccountsParserTests {
    private let now = Date(timeIntervalSince1970: 1_700_000_000)

    private func ms(_ offsetSeconds: Double) -> Int {
        Int((now.timeIntervalSince1970 + offsetSeconds) * 1000)
    }

    private func json(_ object: [String: Any]) -> Data {
        try! JSONSerialization.data(withJSONObject: object)
    }

    @Test("future claude cooldown becomes a fully-limited window")
    func futureClaudeCooldown() {
        let resetMs = ms(3_600)
        let data = json([
            "accounts": [["rateLimitResetTimes": ["claude": resetMs]]]
        ])

        let result = AntigravityAccountsParser.parse(data, now: now)

        #expect(result.hasAccounts)
        #expect(result.plan == "1 acct")
        #expect(result.windows.count == 1)
        let window = result.windows[0]
        #expect(window.label == "Claude")
        #expect(window.percent == 100)
        #expect(window.kind == .used) // 100% used -> 0% remaining (limited)
        #expect(window.resetAt == Date(timeIntervalSince1970: Double(resetMs) / 1000))
    }

    @Test("claude and gemini cooldowns produce Claude-then-Gemini windows")
    func bothPools() {
        let data = json([
            "accounts": [[
                "rateLimitResetTimes": [
                    "claude": ms(1_800),
                    "gemini-antigravity": ms(7_200),
                ]
            ]]
        ])

        let result = AntigravityAccountsParser.parse(data, now: now)

        #expect(result.windows.map(\.label) == ["Claude", "Gemini"])
    }

    @Test("prefixed reset keys are recognized")
    func prefixedKeys() {
        let data = json([
            "accounts": [[
                "rateLimitResetTimes": [
                    "claude:opus": ms(900),
                    "gemini-antigravity:flash": ms(900),
                ]
            ]]
        ])

        let result = AntigravityAccountsParser.parse(data, now: now)

        #expect(result.windows.map(\.label) == ["Claude", "Gemini"])
    }

    @Test("expired resets are ignored (ready state)")
    func expiredResets() {
        let data = json([
            "accounts": [["rateLimitResetTimes": ["claude": ms(-60)]]]
        ])

        let result = AntigravityAccountsParser.parse(data, now: now)

        #expect(result.hasAccounts)
        #expect(result.plan == "1 acct")
        #expect(result.windows.isEmpty)
    }

    @Test("multiple accounts in the same pool take the latest reset")
    func latestResetWins() {
        let early = ms(1_000)
        let late = ms(5_000)
        let data = json([
            "accounts": [
                ["rateLimitResetTimes": ["claude": early]],
                ["rateLimitResetTimes": ["claude": late]],
            ]
        ])

        let result = AntigravityAccountsParser.parse(data, now: now)

        #expect(result.plan == "2 accts")
        #expect(result.windows.count == 1)
        #expect(result.windows[0].resetAt == Date(timeIntervalSince1970: Double(late) / 1000))
    }

    @Test("empty accounts array is not available")
    func emptyAccounts() {
        let data = json(["accounts": []])

        let result = AntigravityAccountsParser.parse(data, now: now)

        #expect(!result.hasAccounts)
        #expect(result.plan == nil)
        #expect(result.windows.isEmpty)
    }

    @Test("malformed JSON degrades to unavailable")
    func malformedJSON() {
        let result = AntigravityAccountsParser.parse(Data("not json".utf8), now: now)

        #expect(!result.hasAccounts)
        #expect(result.windows.isEmpty)
    }
}
