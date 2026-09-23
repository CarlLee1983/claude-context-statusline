import Foundation
import Testing
@testable import AIUsageMonitorCore

@Suite("Claude CLI usage parser")
struct ClaudeCLIUsageParserTests {
    @Test("reads the local usage command's session and all-models week")
    func parsesUsage() throws {
        let result = """
        You are currently using your subscription to power your Claude Code usage

        Current session: 27% used · resets Sep 23 at 2:29pm (Asia/Taipei)
        Current week (all models): 26% used · resets Sep 26 at 1:59am (Asia/Taipei)
        Current week (Fable): 20% used · resets Sep 26 at 1:59am (Asia/Taipei)

        97% of your usage came from subagent-heavy sessions
        """
        let payload = try JSONSerialization.data(withJSONObject: [
            "is_error": false, "local_command": "usage", "result": result,
        ])
        let now = try #require(ISO8601DateFormatter().date(from: "2026-09-23T04:00:00Z"))

        let windows = ClaudeCLIUsageParser.parse(payload, now: now)

        #expect(windows.map(\.label) == ["5h", "7d"])
        #expect(windows.map(\.percent) == [27, 26])
        #expect(windows.allSatisfy { $0.kind == .used })
        #expect(windows.first?.resetAt == ISO8601DateFormatter().date(from: "2026-09-23T06:29:00Z"))
        #expect(windows.last?.resetAt == ISO8601DateFormatter().date(from: "2026-09-25T17:59:00Z"))
    }

    @Test("rejects a generated or failed response")
    func rejectsNonLocalResult() {
        let prompt = #"{"is_error":false,"result":"Current session: 27% used"}"#.data(using: .utf8)!
        let error = #"{"is_error":true,"local_command":"usage","result":"Current session: 27% used"}"#.data(using: .utf8)!
        #expect(ClaudeCLIUsageParser.parse(prompt).isEmpty)
        #expect(ClaudeCLIUsageParser.parse(error).isEmpty)
        #expect(ClaudeCLIUsageParser.parse(Data("nonsense".utf8)).isEmpty)
    }

    @Test("keeps a valid percent when the reset text is unavailable")
    func partialWithoutReset() {
        let payload = #"{"is_error":false,"local_command":"usage","result":"Current session: 9.5% used"}"#.data(using: .utf8)!

        let windows = ClaudeCLIUsageParser.parse(payload)

        #expect(windows.map(\.label) == ["5h"])
        #expect(windows.first?.percent == 9.5)
        #expect(windows.first?.resetAt == nil)
    }

    @Test("rolls a December reset into the next year")
    func yearBoundary() throws {
        let payload = #"{"is_error":false,"local_command":"usage","result":"Current session: 5% used · resets Jan 1 at 1:00am (Asia/Taipei)"}"#.data(using: .utf8)!
        let now = try #require(ISO8601DateFormatter().date(from: "2026-12-31T15:00:00Z"))

        let windows = ClaudeCLIUsageParser.parse(payload, now: now)

        #expect(windows.count == 1)
        #expect(windows[0].resetAt == ISO8601DateFormatter().date(from: "2026-12-31T17:00:00Z"))
    }
}
