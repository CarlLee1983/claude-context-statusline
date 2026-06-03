import Foundation
import Testing
@testable import AIUsageMonitorCore

@Suite("Antigravity usage parser")
struct AntigravityUsageParserTests {
    @Test("captures the 'Refreshes in' countdown as an absolute reset instant")
    func capturesRefreshCountdown() throws {
        let now = Date(timeIntervalSince1970: 1_000_000)
        let text = """
        └ Model Quota

          Gemini 3.5 Flash (Medium)
          ███████████ ███████████ 80%
          80% remaining · Refreshes in 2h 46m

          Claude Opus 4.6 (Thinking)
          ███████████ ███████████ 100%
          Quota available
        """

        let windows = AntigravityUsageParser.parse(text, now: now)

        #expect(windows.count == 2)
        // Gemini window carries a refresh countdown -> absolute reset = now + 2h46m.
        #expect(windows[0].label == "Gemini 3.5 Flash (Medium)")
        #expect(windows[0].resetAt == now.addingTimeInterval(2 * 3600 + 46 * 60))
        // Claude window is full ("Quota available") -> no reset instant.
        #expect(windows[1].label == "Claude Opus 4.6 (Thinking)")
        #expect(windows[1].resetAt == nil)
    }

    @Test("parses minute-only and day/hour refresh phrasings")
    func parsesVariedRefreshPhrasings() throws {
        let now = Date(timeIntervalSince1970: 2_000_000)
        let text = """
        └ Model Quota

          Gemini A
          ███████████ 40%
          40% remaining · Refreshes in 46m

          Gemini B
          ███████████ 10%
          10% remaining · Refreshes in 1d 3h
        """

        let windows = AntigravityUsageParser.parse(text, now: now)

        #expect(windows[0].resetAt == now.addingTimeInterval(46 * 60))
        #expect(windows[1].resetAt == now.addingTimeInterval(24 * 3600 + 3 * 3600))
    }

    @Test("parses agy usage output as available quota")
    func parsesAvailableQuota() throws {
        let text = """
        └ Model Quota

          Gemini 3.5 Flash (Medium)
          ███████████ ███████████ 92%
          Quota available

          Claude Opus 4.6 (Thinking)
          ███████████ ███████████ 75%
          Quota available
        """

        let windows = AntigravityUsageParser.parse(text)

        #expect(windows.count == 2)
        #expect(windows[0].label == "Gemini 3.5 Flash (Medium)")
        #expect(windows[0].percent == 92)
        #expect(windows[0].kind == .available)
        #expect(windows[1].label == "Claude Opus 4.6 (Thinking)")
        #expect(windows[1].percent == 75)
        #expect(windows[1].kind == .available)
    }

    @Test("strips real ANSI escape sequences from labels and bars")
    func stripsRealANSI() throws {
        // Mirrors what the live `agy /usage` TUI emits: SGR color codes (\u{1B}[1m,
        // \u{1B}[m) and erase-line codes (\u{1B}[K) wrapped around every cell.
        let esc = "\u{1B}"
        let text = """
        \(esc)[1mModel Quota\(esc)[m\(esc)[K
        \(esc)[1mGemini 3.5 Flash (Medium)\(esc)[m\(esc)[K
        ███████████ 80%\(esc)[K
        Quota available\(esc)[K
        \(esc)[1mClaude Opus 4.6 (Thinking)\(esc)[m\(esc)[K
        ███████████ 100%\(esc)[K
        Quota available\(esc)[K
        """

        let windows = AntigravityUsageParser.parse(text)

        #expect(windows.map(\.label) == ["Gemini 3.5 Flash (Medium)", "Claude Opus 4.6 (Thinking)"])
        #expect(windows.map(\.percent) == [80, 100])
        #expect(windows.allSatisfy { $0.kind == .available })
    }

    @Test("ignores prompt chrome before model quota heading")
    func ignoresPromptChrome() throws {
        let text = """
        ? for shortcutsGemini 3.5 Flash (Medium)
        └ Model Quota
        Gemini 3.5 Flash (Medium)
        ███████████ 100%
        Quota available
        esc Close
        """

        let windows = AntigravityUsageParser.parse(text)

        #expect(windows.map(\.label) == ["Gemini 3.5 Flash (Medium)"])
        #expect(windows[0].percent == 100)
    }
}
