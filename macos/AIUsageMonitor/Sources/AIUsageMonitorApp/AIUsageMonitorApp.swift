import AIUsageMonitorCore
import AppKit
import SwiftUI

@main
struct AIUsageMonitorApp: App {
    @StateObject private var model = UsageMenuModel(provider: DemoUsageSnapshotProvider())

    init() {
        NSApp.setActivationPolicy(.accessory)
    }

    var body: some Scene {
        MenuBarExtra {
            UsageMenuView(model: model)
                .task { await model.refresh() }
        } label: {
            Text(model.menuTitle)
        }
        .menuBarExtraStyle(.window)
    }
}
