import Foundation
import Testing
@testable import AIUsageMonitorCore

@Suite("Live usage snapshot provider")
struct LiveUsageSnapshotProviderTests {
    private struct FakeSingle: ProviderSnapshotProviding {
        let snap: ProviderSnapshot
        func snapshot() async -> ProviderSnapshot { snap }
    }

    private struct FakeMulti: UsageSnapshotProviding {
        let snaps: [ProviderSnapshot]
        func snapshots() async -> [ProviderSnapshot] { snaps }
    }

    @Test("flattens the antigravity group snapshots after claude and codex, in order")
    func flattensAntigravityGroups() async {
        let cc = ProviderSnapshot(name: "Claude Code", shortName: "CC", windows: [])
        let cx = ProviderSnapshot(name: "Codex", shortName: "CX", windows: [])
        let agg = ProviderSnapshot(name: "Antigravity · Gemini", shortName: "AGg", windows: [])
        let agc = ProviderSnapshot(name: "Antigravity · Claude & GPT", shortName: "AGc", windows: [])

        let provider = LiveUsageSnapshotProvider(
            claude: FakeSingle(snap: cc),
            codex: FakeSingle(snap: cx),
            antigravity: FakeMulti(snaps: [agg, agc]),
            enabledProviderIDs: Set(UsageProviderID.allCases)
        )

        let result = await provider.snapshots()

        #expect(result.map(\.shortName) == ["CC", "CX", "AGg", "AGc"])
    }
}
