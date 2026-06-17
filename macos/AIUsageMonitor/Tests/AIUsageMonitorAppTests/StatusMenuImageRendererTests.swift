import Testing
import AppKit
@testable import AIUsageMonitorApp
import AIUsageMonitorCore

@Suite("Status menu image renderer")
@MainActor
struct StatusMenuImageRendererTests {
    @Test("icon-only image is a template image of size 18x18")
    func iconOnlyImageIsTemplateAndCorrectSize() throws {
        let rendered = StatusMenuImageRenderer.renderIconOnly()
        let image = try #require(rendered.image)
        #expect(image.size.width == 18)
        #expect(image.size.height == 18)
        #expect(image.isTemplate == true)
        #expect(rendered.fallbackTitle == "AI")
        #expect(rendered.accessibilityTitle == "AI Usage Monitor")
    }

    @Test("two grouped Antigravity snapshots render as one combined fallback entry")
    func combinesAntigravityInStatus() {
        let snapshots = [
            ProviderSnapshot(providerID: .antigravity, name: "Antigravity · Gemini", shortName: "AGg", plan: "agy /usage",
                             windows: [UsageWindow(label: "Weekly Limit", percent: 77, kind: .available)]),
            ProviderSnapshot(providerID: .antigravity, name: "Antigravity · Claude & GPT", shortName: "AGc", plan: "agy /usage",
                             windows: [UsageWindow(label: "Weekly Limit", percent: 0, kind: .available)])
        ]

        let rendered = StatusMenuImageRenderer.renderStatus(for: snapshots)

        #expect(rendered.fallbackTitle == "Antigravity 0")
        #expect(rendered.image != nil)
    }
}
