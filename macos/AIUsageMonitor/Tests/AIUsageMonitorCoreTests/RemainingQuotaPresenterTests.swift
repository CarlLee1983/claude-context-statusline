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

    @Test("merges Antigravity model variants into the binding (lowest remaining) window")
    func mergesAntigravityVariantsIntoBindingWindow() {
        let reset = Date(timeIntervalSince1970: 1_800_000_000)
        let windows = [
            UsageWindow(label: "Gemini 3.5 Flash (Medium)", percent: 60, kind: .available, resetAt: reset),
            UsageWindow(label: "Gemini 3.1 Pro (High)", percent: 60, kind: .available, resetAt: reset),
            UsageWindow(label: "Gemini 2.0 Flash", percent: 100, kind: .available)
        ]

        let merged = RemainingQuotaPresenter.mergedAntigravityWindow(from: windows)

        #expect(merged?.label == "Gemini")
        #expect(merged.map { RemainingQuotaPresenter.remainingPercent(for: $0) } == 60)
        // Carries the binding model's reset instant, not the 100% (no-reset) one.
        #expect(merged?.resetAt == reset)
    }

    @Test("merged Antigravity window is 100% when all variants are full, and nil when empty")
    func mergedAntigravityWindowEdgeCases() {
        let allReady = [
            UsageWindow(label: "Gemini 3.5 Flash (Medium)", percent: 100, kind: .available),
            UsageWindow(label: "Gemini 3.1 Pro (High)", percent: 100, kind: .available)
        ]
        let merged = RemainingQuotaPresenter.mergedAntigravityWindow(from: allReady)
        #expect(merged.map { RemainingQuotaPresenter.remainingPercent(for: $0) } == 100)

        #expect(RemainingQuotaPresenter.mergedAntigravityWindow(from: []) == nil)
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

        // Same-day reset: time only, no date.
        #expect(
            RemainingQuotaPresenter.detailTitle(for: used, now: reset) ==
                "5h: 97% remaining · used 3% · reset \(reset.formatted(date: .omitted, time: .shortened))"
        )
        #expect(
            RemainingQuotaPresenter.detailTitle(for: available, now: reset) ==
                "Gemini 3.5 Flash: 75% remaining · available"
        )
    }

    @Test("includes the date when the reset is not on the current day")
    func dropdownDetailsAddDateForNonCurrentDayReset() {
        let reset = Date(timeIntervalSince1970: 1_800_000_000)
        let used = UsageWindow(label: "7d", percent: 13, kind: .used, resetAt: reset)
        // `now` is 10 days before the reset — a different calendar day in any tz.
        let now = reset.addingTimeInterval(-10 * 86_400)

        #expect(
            RemainingQuotaPresenter.detailTitle(for: used, now: now) ==
                "7d: 87% remaining · used 13% · reset \(reset.formatted(date: .abbreviated, time: .shortened))"
        )
    }

    @Test("parses fixed window duration from the window label")
    func parsesWindowDurationFromLabel() {
        #expect(RemainingQuotaPresenter.windowDuration(forLabel: "5h") == TimeInterval(5 * 3600))
        #expect(RemainingQuotaPresenter.windowDuration(forLabel: "7d") == TimeInterval(7 * 86_400))
        #expect(RemainingQuotaPresenter.windowDuration(forLabel: "2w") == TimeInterval(2 * 604_800))
        // case-insensitive and tolerant of an interior space
        #expect(RemainingQuotaPresenter.windowDuration(forLabel: "7D") == TimeInterval(7 * 86_400))
        #expect(RemainingQuotaPresenter.windowDuration(forLabel: "5 h") == TimeInterval(5 * 3600))
        // month unit maps to a 30-day window
        #expect(RemainingQuotaPresenter.windowDuration(forLabel: "1m") == TimeInterval(2_592_000))
        // unparseable labels yield nil (Antigravity model names, free-form, empty)
        #expect(RemainingQuotaPresenter.windowDuration(forLabel: "Gemini 3.5 Flash (Medium)") == nil)
        #expect(RemainingQuotaPresenter.windowDuration(forLabel: "Requests") == nil)
        #expect(RemainingQuotaPresenter.windowDuration(forLabel: "") == nil)
        #expect(RemainingQuotaPresenter.windowDuration(forLabel: "abc") == nil)
    }

    @Test("flags a window as expiring-unused only when quota is high and reset is imminent")
    func flagsExpiringUnusedWindows() {
        let now = Date(timeIntervalSince1970: 1_800_000_000)
        // helper: a used window resetting `seconds` from now
        func window(_ label: String, used: Double, resetIn seconds: TimeInterval) -> UsageWindow {
            UsageWindow(label: label, percent: used, kind: .used, resetAt: now.addingTimeInterval(seconds))
        }

        // 5h window, 55% remaining (used 45%), reset in 30 min → within 45-min tail → true
        #expect(RemainingQuotaPresenter.isExpiringUnused(for: window("5h", used: 45, resetIn: 30 * 60), now: now) == true)
        // 5h window, same quota, reset in 2 h → outside the 15% tail → false
        #expect(RemainingQuotaPresenter.isExpiringUnused(for: window("5h", used: 45, resetIn: 2 * 3600), now: now) == false)
        // 7d window, 55% remaining, reset in 20 h → within ~25.2 h tail → true
        #expect(RemainingQuotaPresenter.isExpiringUnused(for: window("7d", used: 45, resetIn: 20 * 3600), now: now) == true)
        // remaining 30% (< 40 threshold), reset imminent → false
        #expect(RemainingQuotaPresenter.isExpiringUnused(for: window("5h", used: 70, resetIn: 10 * 60), now: now) == false)
        // boundary: exactly 40% remaining (used 60) → true (>=)
        #expect(RemainingQuotaPresenter.isExpiringUnused(for: window("5h", used: 60, resetIn: 10 * 60), now: now) == true)
        // boundary: reset exactly at duration*0.15 (5h → 2700s) → true (<=)
        #expect(RemainingQuotaPresenter.isExpiringUnused(for: window("5h", used: 45, resetIn: 2700), now: now) == true)
        // reset already passed → false
        #expect(RemainingQuotaPresenter.isExpiringUnused(for: window("5h", used: 45, resetIn: -600), now: now) == false)
        // no resetAt → false
        #expect(RemainingQuotaPresenter.isExpiringUnused(for: UsageWindow(label: "5h", percent: 45, kind: .used), now: now) == false)
        // unparseable label (Antigravity model name) → false
        #expect(RemainingQuotaPresenter.isExpiringUnused(for: UsageWindow(label: "Gemini 3.5 Flash (Medium)", percent: 40, kind: .available, resetAt: now.addingTimeInterval(60)), now: now) == false)
        // .available kind: 55% available (already remaining), reset imminent → true
        #expect(RemainingQuotaPresenter.isExpiringUnused(
            for: UsageWindow(label: "5h", percent: 55, kind: .available, resetAt: now.addingTimeInterval(20 * 60)),
            now: now) == true)
    }
}
