import AIUsageMonitorCore
import Foundation

@MainActor
protocol UsageMonitorSettingsStoring {
    func load() -> UsageMonitorSettings
    func save(_ settings: UsageMonitorSettings)
}

@MainActor
struct UserDefaultsUsageMonitorSettingsStore: UsageMonitorSettingsStoring {
    private let defaults: UserDefaults
    private let menuBarKey = "menuBarProviderIDs"
    private let queriedKey = "queriedProviderIDs"

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
    }

    func load() -> UsageMonitorSettings {
        UsageMonitorSettings(
            menuBarProviderIDs: loadProviderIDs(forKey: menuBarKey),
            queriedProviderIDs: loadProviderIDs(forKey: queriedKey)
        )
    }

    func save(_ settings: UsageMonitorSettings) {
        defaults.set(rawValues(for: settings.menuBarProviderIDs), forKey: menuBarKey)
        defaults.set(rawValues(for: settings.queriedProviderIDs), forKey: queriedKey)
    }

    private func loadProviderIDs(forKey key: String) -> Set<UsageProviderID> {
        guard let rawValues = defaults.object(forKey: key) as? [String] else {
            return Set(UsageProviderID.allCases)
        }
        return Set(rawValues.compactMap(UsageProviderID.init(rawValue:)))
    }

    private func rawValues(for providerIDs: Set<UsageProviderID>) -> [String] {
        UsageProviderID.allCases
            .filter { providerIDs.contains($0) }
            .map(\.rawValue)
    }
}
