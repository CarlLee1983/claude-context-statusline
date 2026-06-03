import Foundation

/// Production provider: fetches Claude, Codex and Antigravity concurrently and
/// returns the snapshots in a stable order. A failed provider is surfaced as
/// unavailable rather than dropped, so the menu shows it exists.
public struct LiveUsageSnapshotProvider: UsageSnapshotProviding {
    private let claude = ClaudeUsageProvider()
    private let codex = CodexUsageProvider()
    private let antigravity = AntigravityUsageProvider()

    public init() {}

    public func snapshots() async -> [ProviderSnapshot] {
        async let claudeSnapshot = claude.snapshot()
        async let codexSnapshot = codex.snapshot()
        async let antigravitySnapshot = antigravity.snapshot()
        return await [claudeSnapshot, codexSnapshot, antigravitySnapshot]
    }
}
