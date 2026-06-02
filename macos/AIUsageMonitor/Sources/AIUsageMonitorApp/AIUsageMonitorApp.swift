import AIUsageMonitorCore
import AppKit
import Foundation

@main
struct AIUsageMonitorMain {
    static func main() {
        let app = NSApplication.shared
        let delegate = AIUsageMonitorAppDelegate()
        app.delegate = delegate
        app.setActivationPolicy(.accessory)
        app.run()
        _ = delegate
    }
}

@MainActor
final class AIUsageMonitorAppDelegate: NSObject, NSApplicationDelegate {
    private var statusMenuController: StatusMenuController?

    func applicationDidFinishLaunching(_ notification: Notification) {
        statusMenuController = StatusMenuController(provider: DemoUsageSnapshotProvider())
        statusMenuController?.start()
    }
}
