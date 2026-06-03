import Foundation

/// Production provider: fetches Claude and Codex concurrently and returns both
/// snapshots in a stable order. A failed provider is surfaced as unavailable
/// rather than dropped, so the menu shows it exists.
public struct LiveUsageSnapshotProvider: UsageSnapshotProviding {
    private let claude = ClaudeUsageProvider()
    private let codex = CodexUsageProvider()

    public init() {}

    public func snapshots() async -> [ProviderSnapshot] {
        async let claudeSnapshot = claude.snapshot()
        async let codexSnapshot = codex.snapshot()
        return await [claudeSnapshot, codexSnapshot]
    }
}
