import AIUsageMonitorCore
import AppKit
import Foundation
import ServiceManagement

@MainActor
final class StatusMenuController {
    /// Auto-refresh cadence in seconds. Deliberately 300s (5 min) to match the
    /// SwiftBar plugin's `FETCH_TTL`: both看的是 5h / 7d 速率限制視窗,5 分鐘僅
    /// 約佔 5h 視窗的 1.7%,粒度足夠,又避開 usage 端點自身的 429 限流。
    /// 需要即時數字時用選單的 "Refresh"。
    static let refreshInterval: Duration = .seconds(300)

    private let provider: UsageSnapshotProviding
    private let statusItem: NSStatusItem
    private var snapshots: [ProviderSnapshot] = []
    private var isRefreshing = false
    private var refreshTask: Task<Void, Never>?

    init(provider: UsageSnapshotProviding) {
        self.provider = provider
        self.statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        self.statusItem.button?.title = "AI"
        self.statusItem.button?.toolTip = "AI Usage Monitor"
    }

    func start() {
        rebuildMenu()
        refreshTask = Task { [weak self] in
            while !Task.isCancelled {
                await self?.refresh()
                try? await Task.sleep(for: Self.refreshInterval)
            }
        }
    }

    private func refresh() async {
        guard !isRefreshing else { return }
        isRefreshing = true
        setStatusTitle("AI")
        snapshots = await provider.snapshots()
        isRefreshing = false
        setStatusPresentation(for: snapshots)
        rebuildMenu()
    }

    private func setStatusTitle(_ title: String) {
        statusItem.button?.imagePosition = .noImage
        statusItem.button?.image = nil
        statusItem.button?.title = title
        statusItem.button?.toolTip = title == "AI" ? "AI Usage Monitor" : title
    }

    private func setStatusPresentation(for snapshots: [ProviderSnapshot]) {
        let rendered = StatusMenuImageRenderer.renderStatus(for: snapshots)
        if let image = rendered.image {
            statusItem.button?.title = ""
            statusItem.button?.image = image
            statusItem.button?.imagePosition = .imageOnly
            statusItem.button?.toolTip = rendered.accessibilityTitle
        } else {
            setStatusTitle(rendered.fallbackTitle)
        }
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

                if let emptyDetailTitle = RemainingQuotaPresenter.emptyDetailTitle(for: snapshot) {
                    let item = NSMenuItem(title: "  \(emptyDetailTitle)", action: nil, keyEquivalent: "")
                    item.isEnabled = false
                    menu.addItem(item)
                }

                for window in snapshot.windows {
                    let item = NSMenuItem(
                        title: "  \(RemainingQuotaPresenter.detailTitle(for: window))",
                        action: nil,
                        keyEquivalent: ""
                    )
                    item.isEnabled = false
                    menu.addItem(item)
                }
            }
        }

        menu.addItem(.separator())

        let loginItem = NSMenuItem(title: "Launch at Login", action: #selector(toggleLaunchAtLogin), keyEquivalent: "")
        loginItem.target = self
        loginItem.state = (SMAppService.mainApp.status == .enabled) ? .on : .off
        menu.addItem(loginItem)

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

    /// Toggle the app's "Launch at Login" registration via the native
    /// ServiceManagement API. Reflects/updates the menu checkmark. Never crashes:
    /// any registration error is logged and swallowed (e.g. when running from a
    /// non-bundle dev build via `swift run`).
    @objc private func toggleLaunchAtLogin() {
        do {
            if SMAppService.mainApp.status == .enabled {
                try SMAppService.mainApp.unregister()
            } else {
                try SMAppService.mainApp.register()
            }
        } catch {
            NSLog("AIUsageMonitor: Launch at Login toggle failed: \(error)")
        }
        rebuildMenu()
    }

    @objc private func quitMenuItemSelected() {
        refreshTask?.cancel()
        NSApplication.shared.terminate(nil)
    }
}
