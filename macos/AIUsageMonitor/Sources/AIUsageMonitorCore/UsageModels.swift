import Foundation

public enum QuotaKind: Equatable, Sendable {
    case used
    case available
}

public struct UsageWindow: Equatable, Identifiable, Sendable {
    public let id: String
    public let label: String
    public let percent: Double
    public let kind: QuotaKind
    public let resetAt: Date?

    public init(label: String, percent: Double, kind: QuotaKind, resetAt: Date? = nil) {
        self.label = label
        self.percent = max(0, min(100, percent))
        self.kind = kind
        self.resetAt = resetAt
        self.id = "\(label)-\(kind)-\(self.percent)-\(resetAt?.timeIntervalSince1970 ?? 0)"
    }
}

public struct ProviderSnapshot: Equatable, Identifiable, Sendable {
    public let id: String
    public let name: String
    public let shortName: String
    public let plan: String?
    public let windows: [UsageWindow]
    public let isAvailable: Bool
    public let updatedAt: Date

    public init(
        name: String,
        shortName: String,
        plan: String? = nil,
        windows: [UsageWindow],
        isAvailable: Bool = true,
        updatedAt: Date = .now
    ) {
        self.id = shortName
        self.name = name
        self.shortName = shortName
        self.plan = plan
        self.windows = windows
        self.isAvailable = isAvailable
        self.updatedAt = updatedAt
    }
}
