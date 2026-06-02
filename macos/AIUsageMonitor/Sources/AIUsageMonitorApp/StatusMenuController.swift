import AIUsageMonitorCore
import AppKit
import Foundation

@MainActor
final class StatusMenuController {
    private let provider: UsageSnapshotProviding
    private let statusItem: NSStatusItem
    private var snapshots: [ProviderSnapshot] = []
    private var isRefreshing = false

    init(provider: UsageSnapshotProviding) {
        self.provider = provider
        self.statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        self.statusItem.button?.title = "AI"
        self.statusItem.button?.toolTip = "AI Usage Monitor"
    }

    func start() {
        rebuildMenu()
        Task { await refresh() }
    }

    private func refresh() async {
        guard !isRefreshing else { return }
        isRefreshing = true
        setStatusTitle("AI")
        snapshots = await provider.snapshots()
        isRefreshing = false
        setStatusTitle(menuTitle)
        rebuildMenu()
    }

    private var menuTitle: String {
        guard !snapshots.isEmpty else { return "AI —" }
        return snapshots.map { snapshot in
            guard let first = snapshot.windows.first else { return "\(snapshot.shortName) —" }
            return "\(snapshot.shortName) \(Int(first.percent.rounded()))%"
        }.joined(separator: " ")
    }

    private func setStatusTitle(_ title: String) {
        statusItem.button?.title = title
    }

    private func rebuildMenu() {
        let menu = NSMenu()

        let header = NSMenuItem(title: "AI Usage Monitor", action: nil, keyEquivalent: "")
        header.isEnabled = false
        menu.addItem(header)
        menu.addItem(.separator())

        if snapshots.isEmpty {
            let empty = NSMenuItem(title: isRefreshing ? "Refreshing…" : "No usage data yet", action: nil, keyEquivalent: "")
            empty.isEnabled = false
            menu.addItem(empty)
        } else {
            for snapshot in snapshots {
                let title = [snapshot.name, snapshot.plan].compactMap { $0 }.joined(separator: " · ")
                let providerItem = NSMenuItem(title: title, action: nil, keyEquivalent: "")
                providerItem.isEnabled = false
                menu.addItem(providerItem)

                for window in snapshot.windows {
                    let resetText = window.resetAt.map { " · reset \($0.formatted(date: .omitted, time: .shortened))" } ?? ""
                    let item = NSMenuItem(
                        title: "  \(window.label): \(Int(window.percent.rounded()))% \(window.kind.menuLabel)\(resetText)",
                        action: nil,
                        keyEquivalent: ""
                    )
                    item.isEnabled = false
                    menu.addItem(item)
                }
            }
        }

        menu.addItem(.separator())
        let refreshItem = NSMenuItem(title: isRefreshing ? "Refreshing…" : "Refresh", action: #selector(refreshMenuItemSelected), keyEquivalent: "r")
        refreshItem.target = self
        refreshItem.isEnabled = !isRefreshing
        menu.addItem(refreshItem)

        let quitItem = NSMenuItem(title: "Quit", action: #selector(quitMenuItemSelected), keyEquivalent: "q")
        quitItem.target = self
        menu.addItem(quitItem)

        statusItem.menu = menu
    }

    @objc private func refreshMenuItemSelected() {
        Task { await refresh() }
    }

    @objc private func quitMenuItemSelected() {
        NSApplication.shared.terminate(nil)
    }
}

private extension QuotaKind {
    var menuLabel: String {
        switch self {
        case .used:
            "used"
        case .available:
            "available"
        }
    }
}
