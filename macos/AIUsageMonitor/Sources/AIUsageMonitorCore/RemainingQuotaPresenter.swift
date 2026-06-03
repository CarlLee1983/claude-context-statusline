import Foundation

/// Status severity for a remaining-quota value. Lower remaining is worse.
public enum RemainingTier: Equatable, Sendable {
    case good
    case warn
    case critical
}

public enum RemainingQuotaPresenter {
    /// Map a remaining percent (0...100) to a status tier using the repository
    /// convention (mirrors WARN_PCT=70 / CRIT_PCT=90 from the SwiftBar plugin,
    /// expressed as remaining): <= 10 critical, <= 30 warn, otherwise good.
    public static func tier(forRemaining remaining: Int) -> RemainingTier {
        if remaining <= 10 { return .critical }
        if remaining <= 30 { return .warn }
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

    public static func detailTitle(for window: UsageWindow) -> String {
        let remaining = remainingPercent(for: window)
        let resetText = window.resetAt.map { " · reset \($0.formatted(date: .omitted, time: .shortened))" } ?? ""

        switch window.kind {
        case .used:
            return "\(window.label): \(remaining)% remaining · used \(Int(window.percent.rounded()))%\(resetText)"
        case .available:
            return "\(window.label): \(remaining)% remaining · available\(resetText)"
        }
    }
}
