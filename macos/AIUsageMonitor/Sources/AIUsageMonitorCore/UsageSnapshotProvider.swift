import Foundation

public protocol UsageSnapshotProviding: Sendable {
    func snapshots() async -> [ProviderSnapshot]
}

public protocol ProviderSnapshotProviding: Sendable {
    func snapshot() async -> ProviderSnapshot
}

public struct DemoUsageSnapshotProvider: UsageSnapshotProviding {
    public init() {}

    public func snapshots() async -> [ProviderSnapshot] {
        [
            ProviderSnapshot(
                name: "Claude Code",
                shortName: "CC",
                windows: [
                    UsageWindow(
                        label: "5h",
                        percent: 7,
                        kind: .used,
                        resetAt: Date().addingTimeInterval(3 * 3_600 + 13 * 60)
                    ),
                    UsageWindow(
                        label: "7d",
                        percent: 8,
                        kind: .used,
                        resetAt: Date().addingTimeInterval(75 * 3_600)
                    )
                ]
            ),
            ProviderSnapshot(
                name: "Codex",
                shortName: "CX",
                plan: "plus",
                windows: [
                    UsageWindow(
                        label: "5h",
                        percent: 1,
                        kind: .used,
                        resetAt: Date().addingTimeInterval(4 * 3_600 + 55 * 60)
                    ),
                    UsageWindow(
                        label: "7d",
                        percent: 25,
                        kind: .used,
                        resetAt: Date().addingTimeInterval(130 * 3_600)
                    )
                ]
            ),
            ProviderSnapshot(
                name: "Antigravity · Gemini",
                shortName: "AGg",
                plan: "agy /usage",
                windows: [
                    UsageWindow(label: "Weekly Limit", percent: 77, kind: .available, resetAt: Date().addingTimeInterval(59 * 3_600)),
                    UsageWindow(label: "Five Hour Limit", percent: 100, kind: .available)
                ]
            ),
            ProviderSnapshot(
                name: "Antigravity · Claude & GPT",
                shortName: "AGc",
                plan: "agy /usage",
                windows: [
                    UsageWindow(label: "Weekly Limit", percent: 0, kind: .available, resetAt: Date().addingTimeInterval(40 * 3_600))
                ]
            )
        ]
    }
}
