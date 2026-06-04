import Foundation

/// Status severity for a remaining-quota value. Lower remaining is worse.
public enum RemainingTier: Equatable, Sendable {
    case good
    case warn
    case critical
}

public enum RemainingQuotaPresenter {
    /// Map a remaining percent (0...100) to a status tier: <= 10 critical,
    /// <= 40 warn (warns once usage passes 60%), otherwise good.
    public static func tier(forRemaining remaining: Int) -> RemainingTier {
        if remaining <= 10 { return .critical }
        if remaining <= 40 { return .warn }
        return .good
    }

    public static func remainingPercent(for window: UsageWindow) -> Int {
        let remaining: Double
        switch window.kind {
        case .used:
            remaining = 100 - window.percent
        case .available:
            remaining = window.percent
        }
        return Int(max(0, min(100, remaining)).rounded())
    }

    public static func primaryRemainingPercent(for snapshot: ProviderSnapshot) -> Int? {
        guard let firstWindow = snapshot.windows.first else { return nil }
        return remainingPercent(for: firstWindow)
    }

    /// Collapses Antigravity's per-model windows into a single representative
    /// window. Antigravity quota is currently a shared pool across every model
    /// variant (e.g. the Flash/Pro reasoning-effort tiers move together), so the
    /// dropdown shows one bar instead of one row per variant. The binding
    /// constraint — the lowest remaining quota — represents the group and carries
    /// its reset instant, so the soonest cooldown is what surfaces.
    public static func mergedAntigravityWindow(
        from windows: [UsageWindow],
        label: String = "Gemini"
    ) -> UsageWindow? {
        guard let binding = windows.min(by: {
            remainingPercent(for: $0) < remainingPercent(for: $1)
        }) else { return nil }

        return UsageWindow(
            label: label,
            percent: Double(remainingPercent(for: binding)),
            kind: .available,
            resetAt: binding.resetAt
        )
    }

    public static func fallbackTitle(for snapshots: [ProviderSnapshot]) -> String {
        guard !snapshots.isEmpty else { return "AI —" }

        return snapshots.map { snapshot in
            guard let remaining = primaryRemainingPercent(for: snapshot) else {
                return "\(snapshot.name) —"
            }
            return "\(snapshot.name) \(remaining)"
        }.joined(separator: " ")
    }

    public static func emptyDetailTitle(for snapshot: ProviderSnapshot) -> String? {
        guard snapshot.windows.isEmpty else { return nil }
        return snapshot.isAvailable ? "No quota data available" : "Unavailable"
    }

    public static func detailTitle(for window: UsageWindow, now: Date = .now) -> String {
        let remaining = remainingPercent(for: window)
        let resetText = window.resetAt.map { " · reset \(resetLabel(for: $0, now: now))" } ?? ""

        switch window.kind {
        case .used:
            return "\(window.label): \(remaining)% remaining · used \(Int(window.percent.rounded()))%\(resetText)"
        case .available:
            return "\(window.label): \(remaining)% remaining · available\(resetText)"
        }
    }

    /// Formats a reset instant for the dropdown: time only when it falls on the
    /// current day, otherwise prefixed with the date (e.g. a 7d window that
    /// resets days later would be ambiguous as a bare time).
    private static func resetLabel(for resetAt: Date, now: Date) -> String {
        if Calendar.current.isDate(resetAt, inSameDayAs: now) {
            return resetAt.formatted(date: .omitted, time: .shortened)
        }
        return resetAt.formatted(date: .abbreviated, time: .shortened)
    }
}
