import Foundation
import Testing
@testable import AIUsageMonitorCore

@Suite("Claude usage provider")
struct ClaudeUsageProviderTests {
    private let cliResult = #"{"is_error":false,"local_command":"usage","result":"Current session: 27% used · resets Sep 23 at 2:29pm (Asia/Taipei)\nCurrent week (all models): 26% used · resets Sep 26 at 1:59am (Asia/Taipei)"}"#.data(using: .utf8)!
    private let apiResult = #"{"five_hour":{"utilization":12,"resets_at":"2026-09-23T06:29:00Z"}}"#.data(using: .utf8)!
    private let now = ISO8601DateFormatter().date(from: "2026-09-23T04:00:00Z")!

    @Test("uses Claude CLI when the old Keychain token is absent")
    func fallsBackWhenTokenMissing() async {
        let provider = ClaudeUsageProvider(
            readAccessToken: { nil },
            fetchUsage: { _ in
                Issue.record("HTTP should not run without an OAuth token")
                return nil
            },
            captureCLIUsage: { cliResult },
            now: { now }
        )

        let snapshot = await provider.snapshot()

        #expect(snapshot.isAvailable)
        #expect(snapshot.windows.map(\.label) == ["5h", "7d"])
        #expect(snapshot.windows.map(\.percent) == [27, 26])
    }

    @Test("retains the working API path without launching the CLI")
    func prefersAPI() async {
        let provider = ClaudeUsageProvider(
            readAccessToken: { "fixture-token" },
            fetchUsage: { _ in apiResult },
            captureCLIUsage: {
                Issue.record("CLI should not run when API usage is available")
                return nil
            },
            now: { now }
        )

        let snapshot = await provider.snapshot()

        #expect(snapshot.isAvailable)
        #expect(snapshot.windows.map(\.percent) == [12])
    }

    @Test("falls back when the OAuth endpoint cannot provide usage")
    func fallsBackWhenAPIFails() async {
        let provider = ClaudeUsageProvider(
            readAccessToken: { "fixture-token" },
            fetchUsage: { _ in nil },
            captureCLIUsage: { cliResult },
            now: { now }
        )

        let snapshot = await provider.snapshot()

        #expect(snapshot.isAvailable)
        #expect(snapshot.windows.map(\.percent) == [27, 26])
    }
}
