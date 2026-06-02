import Foundation

public protocol UsageSnapshotProviding: Sendable {
    func snapshots() async -> [ProviderSnapshot]
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
                name: "Antigravity",
                shortName: "AG",
                plan: "agy /usage",
                windows: [
                    UsageWindow(label: "Gemini 3.5 Flash (Medium)", percent: 100, kind: .available),
                    UsageWindow(label: "Claude Opus 4.6 (Thinking)", percent: 100, kind: .available)
                ]
            )
        ]
    }
}
