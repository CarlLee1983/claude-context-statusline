import Foundation

public enum UsageProviderID: String, CaseIterable, Sendable {
    case claudeCode
    case codex
    case antigravity

    public var displayName: String {
        switch self {
        case .claudeCode:
            return "Claude Code"
        case .codex:
            return "Codex"
        case .antigravity:
            return "Antigravity"
        }
    }

    public var shortName: String {
        switch self {
        case .claudeCode:
            return "CC"
        case .codex:
            return "CX"
        case .antigravity:
            return "AG"
        }
    }
}

public struct UsageMonitorSettings: Equatable, Sendable {
    public let menuBarProviderIDs: Set<UsageProviderID>
    public let queriedProviderIDs: Set<UsageProviderID>

    public static let `default` = UsageMonitorSettings(
        menuBarProviderIDs: Set(UsageProviderID.allCases),
        queriedProviderIDs: Set(UsageProviderID.allCases)
    )

    public init(
        menuBarProviderIDs: Set<UsageProviderID>,
        queriedProviderIDs: Set<UsageProviderID>
    ) {
        self.menuBarProviderIDs = menuBarProviderIDs
        self.queriedProviderIDs = queriedProviderIDs
    }

    public func menuBarSnapshots(from snapshots: [ProviderSnapshot]) -> [ProviderSnapshot] {
        snapshots.filter { snapshot in
            guard let providerID = UsageProviderID(shortName: snapshot.shortName) else { return false }
            return menuBarProviderIDs.contains(providerID)
        }
    }
}

public extension UsageProviderID {
    init?(shortName: String) {
        guard let provider = Self.allCases.first(where: { $0.shortName == shortName }) else {
            return nil
        }
        self = provider
    }
}
