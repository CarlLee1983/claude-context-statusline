import Foundation
import Testing
@testable import AIUsageMonitorCore

@Suite("Remaining quota presenter")
struct RemainingQuotaPresenterTests {
    @Test("calculates remaining quota from used and available windows")
    func calculatesRemainingQuota() {
        #expect(RemainingQuotaPresenter.remainingPercent(for: UsageWindow(label: "5h", percent: 3, kind: .used)) == 97)
        #expect(RemainingQuotaPresenter.remainingPercent(for: UsageWindow(label: "5h", percent: 100, kind: .used)) == 0)
        #expect(RemainingQuotaPresenter.remainingPercent(for: UsageWindow(label: "Model", percent: 75, kind: .available)) == 75)
        #expect(RemainingQuotaPresenter.remainingPercent(for: UsageWindow(label: "clamped", percent: -5, kind: .used)) == 100)
        #expect(RemainingQuotaPresenter.remainingPercent(for: UsageWindow(label: "clamped", percent: 120, kind: .available)) == 100)
    }

    @Test("uses provider names and remaining values for fallback title")
    func fallbackTitleUsesRemainingValues() {
        let snapshots = [
            ProviderSnapshot(
                name: "Claude Code",
                shortName: "CC",
                windows: [UsageWindow(label: "5h", percent: 3, kind: .used)]
            ),
            ProviderSnapshot(
                name: "Codex",
                shortName: "CX",
                windows: [UsageWindow(label: "5h", percent: 1, kind: .used)]
            ),
            ProviderSnapshot(
                name: "Antigravity",
                shortName: "AG",
                windows: [UsageWindow(label: "Gemini", percent: 100, kind: .available)]
            )
        ]

        let title = RemainingQuotaPresenter.fallbackTitle(for: snapshots)

        #expect(title == "Claude Code 97 Codex 99 Antigravity 100")
        #expect(!title.contains("CC"))
        #expect(!title.contains("CX"))
        #expect(!title.contains("AG"))
        #expect(!title.contains("3%"))
        #expect(!title.contains("1%"))
    }

    @Test("falls back safely for empty and unavailable snapshots")
    func fallbackTitleHandlesEmptyAndUnavailableSnapshots() {
        #expect(RemainingQuotaPresenter.fallbackTitle(for: []) == "AI —")

        let unavailable = ProviderSnapshot(
            name: "Codex",
            shortName: "CX",
            windows: [],
            isAvailable: false
        )

        #expect(RemainingQuotaPresenter.fallbackTitle(for: [unavailable]) == "Codex —")
    }

    @Test("builds empty provider dropdown details for unavailable and no data states")
    func emptyProviderDropdownDetails() {
        let unavailable = ProviderSnapshot(name: "Codex", shortName: "CX", windows: [], isAvailable: false)
        let noData = ProviderSnapshot(name: "Claude Code", shortName: "CC", windows: [], isAvailable: true)
        let withData = ProviderSnapshot(
            name: "Antigravity",
            shortName: "AG",
            windows: [UsageWindow(label: "Gemini", percent: 100, kind: .available)]
        )

        #expect(RemainingQuotaPresenter.emptyDetailTitle(for: unavailable) == "Unavailable")
        #expect(RemainingQuotaPresenter.emptyDetailTitle(for: noData) == "No quota data available")
        #expect(RemainingQuotaPresenter.emptyDetailTitle(for: withData) == nil)
    }

    @Test("maps remaining percent to status tiers at the repo thresholds")
    func remainingTiers() {
        // critical: <= 10
        #expect(RemainingQuotaPresenter.tier(forRemaining: 0) == .critical)
        #expect(RemainingQuotaPresenter.tier(forRemaining: 10) == .critical)
        // warn: 11...40
        #expect(RemainingQuotaPresenter.tier(forRemaining: 11) == .warn)
        #expect(RemainingQuotaPresenter.tier(forRemaining: 40) == .warn)
        // good: > 40
        #expect(RemainingQuotaPresenter.tier(forRemaining: 41) == .good)
        #expect(RemainingQuotaPresenter.tier(forRemaining: 100) == .good)
    }

    @Test("builds dropdown details with remaining and source semantics")
    func dropdownDetailsDescribeRemainingAndSourceSemantics() {
        let reset = Date(timeIntervalSince1970: 1_800_000_000)
        let used = UsageWindow(label: "5h", percent: 3, kind: .used, resetAt: reset)
        let available = UsageWindow(label: "Gemini 3.5 Flash", percent: 75, kind: .available)

        #expect(
            RemainingQuotaPresenter.detailTitle(for: used) ==
                "5h: 97% remaining · used 3% · reset \(reset.formatted(date: .omitted, time: .shortened))"
        )
        #expect(
            RemainingQuotaPresenter.detailTitle(for: available) ==
                "Gemini 3.5 Flash: 75% remaining · available"
        )
    }
}
