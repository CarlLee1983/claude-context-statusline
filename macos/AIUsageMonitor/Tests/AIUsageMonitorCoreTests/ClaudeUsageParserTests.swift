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
        #expect(windows.allSatisfy { $0.resetAt != nil })
    }

    @Test("parses fractional-second timestamps with explicit UTC offset")
    func fractionalSecondResetAt() throws {
        // Real API shape: 6-digit fractional seconds plus a `+00:00` offset,
        // which the default ISO8601 formatter rejects.
        let json = """
        {
          "five_hour": { "utilization": 50, "resets_at": "2026-06-03T06:19:59.866880+00:00" }
        }
        """.data(using: .utf8)!

        let windows = ClaudeUsageParser.parse(json)

        #expect(windows.count == 1)
        let expected = Date(timeIntervalSince1970: 1_780_467_599.86688)
        let resetAt = try #require(windows.first?.resetAt)
        #expect(abs(resetAt.timeIntervalSince1970 - expected.timeIntervalSince1970) < 0.001)
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
