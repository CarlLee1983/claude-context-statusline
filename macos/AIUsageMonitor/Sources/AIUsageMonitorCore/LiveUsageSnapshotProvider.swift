import Foundation

/// Production provider: fetches Claude, Codex and Antigravity concurrently and
/// returns the snapshots in a stable order. A failed provider is surfaced as
/// unavailable rather than dropped, so the menu shows it exists.
public struct LiveUsageSnapshotProvider: UsageSnapshotProviding {
    private let claude: any ProviderSnapshotProviding
    private let codex: any ProviderSnapshotProviding
    private let antigravity: any ProviderSnapshotProviding
    private let enabledProviderIDs: Set<UsageProviderID>

    public init(enabledProviderIDs: Set<UsageProviderID> = Set(UsageProviderID.allCases)) {
        self.init(
            claude: ClaudeUsageProvider(),
            codex: CodexUsageProvider(),
            antigravity: AntigravityUsageProvider(),
            enabledProviderIDs: enabledProviderIDs
        )
    }

    public init(
        claude: any ProviderSnapshotProviding,
        codex: any ProviderSnapshotProviding,
        antigravity: any ProviderSnapshotProviding,
        enabledProviderIDs: Set<UsageProviderID>
    ) {
        self.claude = claude
        self.codex = codex
        self.antigravity = antigravity
        self.enabledProviderIDs = enabledProviderIDs
    }

    public func snapshots() async -> [ProviderSnapshot] {
        await withTaskGroup(of: (UsageProviderID, ProviderSnapshot).self) { group in
            if enabledProviderIDs.contains(.claudeCode) {
                group.addTask { (.claudeCode, await claude.snapshot()) }
            }
            if enabledProviderIDs.contains(.codex) {
                group.addTask { (.codex, await codex.snapshot()) }
            }
            if enabledProviderIDs.contains(.antigravity) {
                group.addTask { (.antigravity, await antigravity.snapshot()) }
            }

            var results: [UsageProviderID: ProviderSnapshot] = [:]
            for await (providerID, snapshot) in group {
                results[providerID] = snapshot
            }

            return UsageProviderID.allCases.compactMap { results[$0] }
        }
    }
}
