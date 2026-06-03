import AIUsageMonitorCore
import AppKit
import Foundation

@main
struct AIUsageMonitorMain {
    static func main() {
        let app = NSApplication.shared
        app.setActivationPolicy(.accessory)

        Runtime.controller = StatusMenuController(provider: LiveUsageSnapshotProvider())
        Runtime.controller?.start()

        app.run()
    }
}

@MainActor
private enum Runtime {
    static var controller: StatusMenuController?
}
