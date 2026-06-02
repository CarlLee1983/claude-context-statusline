import Foundation
import Testing
@testable import AIUsageMonitorCore

@Suite("Codex rate limit parser")
struct CodexRateLimitParserTests {
    @Test("parses primary and secondary windows")
    func parsesRateLimits() throws {
        let json = """
        {
          "rateLimits": {
            "planType": "plus",
            "primary": { "usedPercent": 7, "resetsAt": 1800000000 },
            "secondary": { "usedPercent": 25, "resetsAt": 1800003600 }
          }
        }
        """.data(using: .utf8)!

        let snapshot = try CodexRateLimitParser.parse(json)

        #expect(snapshot.name == "Codex")
        #expect(snapshot.shortName == "CX")
        #expect(snapshot.plan == "plus")
        #expect(snapshot.windows.map(\.label) == ["5h", "7d"])
        #expect(snapshot.windows.map(\.percent) == [7, 25])
        #expect(snapshot.windows.allSatisfy { $0.kind == .used })
        #expect(snapshot.windows[0].resetAt == Date(timeIntervalSince1970: 1_800_000_000))
    }

    @Test("returns unavailable snapshot when rateLimits node is missing")
    func missingRateLimits() throws {
        let snapshot = try CodexRateLimitParser.parse(#"{}"#.data(using: .utf8)!)
        #expect(snapshot.isAvailable == false)
        #expect(snapshot.windows.isEmpty)
    }
}
