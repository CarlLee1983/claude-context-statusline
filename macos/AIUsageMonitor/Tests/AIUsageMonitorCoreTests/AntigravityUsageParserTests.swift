import Foundation
import Testing
@testable import AIUsageMonitorCore

@Suite("Antigravity usage parser")
struct AntigravityUsageParserTests {
    @Test("parses the two-group panel into named limit windows")
    func parsesTwoGroups() throws {
        let now = Date(timeIntervalSince1970: 1_000_000)
        let text = """
        Models & Quota

          Account: user@example.com

        GEMINI MODELS
          Models within this group: Gemini Flash, Gemini Pro

          Weekly Limit
            [███████████████████████░░░░░░░] 77.05%
            77% remaining · Refreshes in 59h 6m

          Five Hour Limit
            [██████████████████████████████] 100.00%
            Quota available


        CLAUDE AND GPT MODELS
          Models within this group: Claude Opus, Claude Sonnet, GPT-OSS

          Weekly Limit
            [░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░] 0.00%
            Refreshes in 40h 55m
        """

        let groups = AntigravityUsageParser.parse(text, now: now)

        #expect(groups.count == 2)

        #expect(groups[0].title == "Gemini")
        #expect(groups[0].windows.map(\.label) == ["Weekly Limit", "Five Hour Limit"])
        #expect(groups[0].windows[0].percent == 77.05)
        #expect(groups[0].windows[0].kind == .available)
        #expect(groups[0].windows[0].resetAt == now.addingTimeInterval(59 * 3600 + 6 * 60))
        #expect(groups[0].windows[1].percent == 100)
        #expect(groups[0].windows[1].resetAt == nil)

        #expect(groups[1].title == "Claude & GPT")
        #expect(groups[1].windows.map(\.label) == ["Weekly Limit"])
        #expect(groups[1].windows[0].percent == 0)
        #expect(groups[1].windows[0].resetAt == now.addingTimeInterval(40 * 3600 + 55 * 60))
    }

    @Test("does not mistake group headers or subtitles for limit windows")
    func ignoresHeadersAndSubtitles() throws {
        let text = """
        Models & Quota
        GEMINI MODELS
          Models within this group: Gemini Flash, Gemini Pro
          Weekly Limit
            [██████] 50.00%
            50% remaining · Refreshes in 1h
        """

        let groups = AntigravityUsageParser.parse(text)

        #expect(groups.count == 1)
        #expect(groups[0].title == "Gemini")
        #expect(groups[0].windows.map(\.label) == ["Weekly Limit"])
        #expect(groups[0].windows[0].percent == 50)
    }

    @Test("title-cases unknown group headers as a fallback")
    func titleCasesUnknownGroups() throws {
        let text = """
        Models & Quota
        FOO BAR MODELS
          Weekly Limit
            [██] 12.00%
            Refreshes in 2h
        """

        let groups = AntigravityUsageParser.parse(text)

        #expect(groups.map(\.title) == ["Foo Bar"])
    }

    @Test("strips real ANSI escape sequences from labels and bars")
    func stripsRealANSI() throws {
        let esc = "\u{1B}"
        let text = """
        \(esc)[1mModels & Quota\(esc)[m\(esc)[K
        \(esc)[1mGEMINI MODELS\(esc)[m\(esc)[K
        \(esc)[1mWeekly Limit\(esc)[m\(esc)[K
        [██████████] 80.00%\(esc)[K
        Quota available\(esc)[K
        """

        let groups = AntigravityUsageParser.parse(text)

        #expect(groups.count == 1)
        #expect(groups[0].title == "Gemini")
        #expect(groups[0].windows.map(\.label) == ["Weekly Limit"])
        #expect(groups[0].windows[0].percent == 80)
    }

    @Test("returns no groups when the panel has no model groups")
    func returnsEmptyWhenNoGroups() throws {
        #expect(AntigravityUsageParser.parse("? for shortcuts\nesc Close").isEmpty)
    }
}
