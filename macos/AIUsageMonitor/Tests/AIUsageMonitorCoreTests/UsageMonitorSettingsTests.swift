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
            ProviderSnapshot(providerID: .claudeCode, name: "Claude Code", shortName: "CC", windows: []),
            ProviderSnapshot(providerID: .codex, name: "Codex", shortName: "CX", windows: []),
            ProviderSnapshot(providerID: .antigravity, name: "Antigravity", shortName: "AG", windows: [])
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
        let claude = CountingProvider(snapshot: ProviderSnapshot(providerID: .claudeCode, name: "Claude Code", shortName: "CC", windows: []))
        let codex = CountingProvider(snapshot: ProviderSnapshot(providerID: .codex, name: "Codex", shortName: "CX", windows: []))
        let antigravity = CountingProvider(snapshot: ProviderSnapshot(providerID: .antigravity, name: "Antigravity", shortName: "AG", windows: []))

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

    @Test("any AG-prefixed shortName resolves to the antigravity provider")
    func agPrefixResolvesToAntigravity() {
        #expect(UsageProviderID(shortName: "AG") == .antigravity)
        #expect(UsageProviderID(shortName: "AGg") == .antigravity)
        #expect(UsageProviderID(shortName: "AGc") == .antigravity)
        #expect(UsageProviderID(shortName: "AG1") == .antigravity)
        #expect(UsageProviderID(shortName: "CC") == .claudeCode)
        #expect(UsageProviderID(shortName: "CX") == .codex)
        #expect(UsageProviderID(shortName: "ZZ") == nil)
    }

    @Test("a single antigravity toggle controls both grouped cards")
    func singleToggleControlsBothAntigravityCards() {
        let settings = UsageMonitorSettings(
            menuBarProviderIDs: [.claudeCode, .antigravity],
            queriedProviderIDs: Set(UsageProviderID.allCases)
        )
        let snapshots = [
            ProviderSnapshot(providerID: .antigravity, name: "Antigravity · Gemini", shortName: "AGg", windows: []),
            ProviderSnapshot(providerID: .antigravity, name: "Antigravity · Claude & GPT", shortName: "AGc", windows: []),
            ProviderSnapshot(providerID: .codex, name: "Codex", shortName: "CX", windows: [])
        ]

        let shown = settings.menuBarSnapshots(from: snapshots)

        #expect(shown.map(\.shortName) == ["AGg", "AGc"])
    }
}

private actor CountingProvider: ProviderSnapshotProviding, UsageSnapshotProviding {
    private let storedSnapshot: ProviderSnapshot
    private(set) var callCount = 0

    init(snapshot: ProviderSnapshot) {
        self.storedSnapshot = snapshot
    }

    func snapshot() async -> ProviderSnapshot {
        callCount += 1
        return storedSnapshot
    }

    func snapshots() async -> [ProviderSnapshot] {
        callCount += 1
        return [storedSnapshot]
    }
}
