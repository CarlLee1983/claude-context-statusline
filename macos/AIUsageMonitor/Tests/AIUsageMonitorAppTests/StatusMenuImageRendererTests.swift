import Testing
import AppKit
@testable import AIUsageMonitorApp

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
}
