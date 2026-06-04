import Foundation

/// Produces the Antigravity snapshot. Mirrors the reference SwiftBar
/// `provider_antigravity`: prefer the live `agy /usage` panel (real available-quota
/// percentages); if that can't be captured, fall back to the local accounts file
/// (cooldown detection / ready state); otherwise report unavailable.
///
/// The data-fetching boundaries are injected so the orchestration is unit tested
/// without driving a real TUI or touching the filesystem.
public struct AntigravityUsageProvider: ProviderSnapshotProviding {
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

    public func snapshot() async -> ProviderSnapshot {
        let unavailable = ProviderSnapshot(
            name: "Antigravity", shortName: "AG", windows: [], isAvailable: false
        )

        // The TUI capture blocks (up to ~12s); keep it off the cooperative pool.
        let capture = captureText
        let text = await Task.detached(priority: .utility) { capture() }.value
        if let text {
            let windows = AntigravityUsageParser.parse(text, now: now())
            if !windows.isEmpty {
                return ProviderSnapshot(
                    name: "Antigravity", shortName: "AG", plan: "agy /usage", windows: windows
                )
            }
        }

        guard let data = loadAccounts() else { return unavailable }
        let result = AntigravityAccountsParser.parse(data, now: now())
        guard result.hasAccounts else { return unavailable }
        return ProviderSnapshot(
            name: "Antigravity", shortName: "AG", plan: result.plan, windows: result.windows
        )
    }
}
