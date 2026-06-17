import Foundation

/// Produces Antigravity snapshots: prefer the live `agy /usage` panel — now split
/// into model groups (Gemini / Claude & GPT), one snapshot per group — and fall
/// back to the local accounts file (a single snapshot) when capture fails.
///
/// The data-fetching boundaries are injected so the orchestration is unit tested
/// without driving a real TUI or touching the filesystem.
public struct AntigravityUsageProvider: UsageSnapshotProviding {
    private let captureText: @Sendable () -> String?
    private let loadAccounts: @Sendable () -> Data?
    private let now: @Sendable () -> Date

    static let accountsURL = URL(fileURLWithPath: NSHomeDirectory())
        .appendingPathComponent(".config/opencode/antigravity-accounts.json")

    public init() {
        self.init(
            captureText: { AntigravityUsageTextCapture.capture() },
            loadAccounts: { try? Data(contentsOf: AntigravityUsageProvider.accountsURL) },
            now: { Date() }
        )
    }

    init(
        captureText: @escaping @Sendable () -> String?,
        loadAccounts: @escaping @Sendable () -> Data?,
        now: @escaping @Sendable () -> Date
    ) {
        self.captureText = captureText
        self.loadAccounts = loadAccounts
        self.now = now
    }

    public func snapshots() async -> [ProviderSnapshot] {
        let unavailable = ProviderSnapshot(
            providerID: .antigravity, name: "Antigravity", shortName: "AG", windows: [], isAvailable: false
        )

        // The TUI capture blocks (up to ~12s); keep it off the cooperative pool.
        let capture = captureText
        let text = await Task.detached(priority: .utility) { capture() }.value
        if let text {
            let groups = AntigravityUsageParser.parse(text, now: now())
            if !groups.isEmpty {
                return AntigravityUsageProvider.snapshots(from: groups)
            }
        }

        guard let data = loadAccounts() else { return [unavailable] }
        let result = AntigravityAccountsParser.parse(data, now: now())
        guard result.hasAccounts else { return [unavailable] }
        return [ProviderSnapshot(
            providerID: .antigravity, name: "Antigravity", shortName: "AG", plan: result.plan, windows: result.windows
        )]
    }

    /// One independent card per group. Identity is carried by `providerID`
    /// (`.antigravity`); shortName is a display-only label, "AG" + the group's
    /// first alphanumeric (lowercased), with collisions falling back to the group
    /// index so the snapshot ids (== shortName) stay unique for SwiftUI's ForEach.
    static func snapshots(from groups: [AntigravityUsageParser.ParsedGroup]) -> [ProviderSnapshot] {
        var used: Set<String> = []
        return groups.enumerated().map { index, group in
            let initial = group.title.first(where: { $0.isLetter || $0.isNumber })
                .map { String($0).lowercased() } ?? "\(index)"
            var short = "AG" + initial
            if used.contains(short) { short = "AG\(index)" }
            used.insert(short)
            return ProviderSnapshot(
                providerID: .antigravity,
                name: "Antigravity · \(group.title)",
                shortName: short,
                plan: "agy /usage",
                windows: group.windows
            )
        }
    }
}
