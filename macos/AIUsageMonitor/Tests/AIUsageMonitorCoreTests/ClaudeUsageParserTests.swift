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
