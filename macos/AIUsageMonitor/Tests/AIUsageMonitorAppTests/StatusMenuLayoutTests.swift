import Testing
@testable import AIUsageMonitorApp

@Suite("Status menu layout")
struct StatusMenuLayoutTests {
    @Test("keeps empty dropdown details compact")
    func emptyDetailsStayCompact() {
        #expect(StatusMenuLayout.hostingHeight(measuredHeight: 82) == 82)
    }

    @Test("clamps implausibly tall hosting measurements")
    func clampsImplausiblyTallMeasurements() {
        #expect(StatusMenuLayout.hostingHeight(measuredHeight: 1_050) == 580)
    }

    @Test("keeps provider list height below the whole hosted menu section")
    func providerListHeightLeavesRoomForHeader() {
        #expect(StatusMenuLayout.maximumProviderListHeight < StatusMenuLayout.maximumHostingHeight)
    }

    @Test("uses a compact fallback for invalid measurements")
    func usesCompactFallbackForInvalidMeasurements() {
        #expect(StatusMenuLayout.hostingHeight(measuredHeight: 0) == 82)
        #expect(StatusMenuLayout.hostingHeight(measuredHeight: -.infinity) == 82)
    }
}
