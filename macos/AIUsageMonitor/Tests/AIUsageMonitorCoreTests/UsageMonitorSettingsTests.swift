import Foundation
import Testing
@testable import AIUsageMonitorCore

@Suite("Usage monitor settings")
struct UsageMonitorSettingsTests {
    @Test("defaults keep every provider visible and queried")
    func defaultsKeepEveryProviderEnabled() {
        let settings = UsageMonitorSettings.default
        let ids = Set(UsageProviderID.allCases)

        #expect(settings.menuBarProviderIDs == ids)
        #expect(settings.queriedProviderIDs == ids)
    }

    @Test("filters menu bar snapshots without removing dropdown data")
    func filtersMenuBarSnapshots() {
        let snapshots = [
            ProviderSnapshot(name: "Claude Code", shortName: "CC", windows: []),
            ProviderSnapshot(name: "Codex", shortName: "CX", windows: []),
            ProviderSnapshot(name: "Antigravity", shortName: "AG", windows: [])
        ]
        let settings = UsageMonitorSettings(
            menuBarProviderIDs: [.codex],
            queriedProviderIDs: Set(UsageProviderID.allCases)
        )

        #expect(settings.menuBarSnapshots(from: snapshots).map(\.shortName) == ["CX"])

        let iconOnly = UsageMonitorSettings(
            menuBarProviderIDs: [],
            queriedProviderIDs: Set(UsageProviderID.allCases)
        )
        #expect(iconOnly.menuBarSnapshots(from: snapshots).isEmpty)
    }

    @Test("live provider only calls selected usage sources")
    func liveProviderOnlyCallsSelectedSources() async {
        let claude = CountingProvider(snapshot: ProviderSnapshot(name: "Claude Code", shortName: "CC", windows: []))
        let codex = CountingProvider(snapshot: ProviderSnapshot(name: "Codex", shortName: "CX", windows: []))
        let antigravity = CountingProvider(snapshot: ProviderSnapshot(name: "Antigravity", shortName: "AG", windows: []))

        let provider = LiveUsageSnapshotProvider(
            claude: claude,
            codex: codex,
            antigravity: antigravity,
            enabledProviderIDs: [.codex]
        )

        let snapshots = await provider.snapshots()

        #expect(snapshots.map(\.shortName) == ["CX"])
        #expect(await claude.callCount == 0)
        #expect(await codex.callCount == 1)
        #expect(await antigravity.callCount == 0)
    }
}

private actor CountingProvider: ProviderSnapshotProviding {
    private let storedSnapshot: ProviderSnapshot
    private(set) var callCount = 0

    init(snapshot: ProviderSnapshot) {
        self.storedSnapshot = snapshot
    }

    func snapshot() async -> ProviderSnapshot {
        callCount += 1
        return storedSnapshot
    }
}
