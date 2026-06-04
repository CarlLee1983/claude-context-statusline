import AIUsageMonitorCore
import AppKit
import Foundation
import ServiceManagement
import SwiftUI

@MainActor
final class StatusMenuController {
    /// Auto-refresh cadence in seconds. Deliberately 300s (5 min) to match the
    /// SwiftBar plugin's `FETCH_TTL`: both看的是 5h / 7d 速率限制視窗,5 分鐘僅
    /// 約佔 5h 視窗的 1.7%,粒度足夠,又避開 usage 端點自身的 429 限流。
    /// 需要即時數字時用選單的 "Refresh"。
    static let refreshInterval: Duration = .seconds(300)

    private let providerFactory: (Set<UsageProviderID>) -> any UsageSnapshotProviding
    private let settingsStore: any UsageMonitorSettingsStoring
    private let statusItem: NSStatusItem
    private var provider: any UsageSnapshotProviding
    private var settings: UsageMonitorSettings
    private var snapshots: [ProviderSnapshot] = []
    private var isRefreshing = false
    private var refreshTask: Task<Void, Never>?

    private let menu = NSMenu()
    private var loginItem: NSMenuItem?
    private var refreshItem: NSMenuItem?

    init(
        providerFactory: @escaping (Set<UsageProviderID>) -> any UsageSnapshotProviding = {
            LiveUsageSnapshotProvider(enabledProviderIDs: $0)
        },
        settingsStore: any UsageMonitorSettingsStoring = UserDefaultsUsageMonitorSettingsStore()
    ) {
        self.providerFactory = providerFactory
        self.settingsStore = settingsStore
        self.settings = settingsStore.load()
        self.provider = providerFactory(settings.queriedProviderIDs)
        self.statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        self.statusItem.button?.title = "AI"
        self.statusItem.button?.toolTip = "AI Usage Monitor"
    }

    convenience init(provider: any UsageSnapshotProviding) {
        self.init(providerFactory: { _ in provider })
    }

    func start() {
        rebuildMenu()
        refreshTask = Task { [weak self] in
            while !Task.isCancelled {
                guard let self else { break }
                await self.refresh()
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
        updateStatusPresentation()
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
        applyRenderedStatus(rendered)
    }

    private func setIconOnlyPresentation() {
        applyRenderedStatus(StatusMenuImageRenderer.renderIconOnly())
    }

    private func applyRenderedStatus(_ rendered: StatusMenuImageRenderer.RenderedStatus) {
        if let image = rendered.image {
            statusItem.button?.title = ""
            statusItem.button?.image = image
            statusItem.button?.imagePosition = .imageOnly
            statusItem.button?.toolTip = rendered.accessibilityTitle
        } else {
            setStatusTitle(rendered.fallbackTitle)
        }
    }

    private func updateStatusPresentation() {
        if settings.menuBarProviderIDs.isEmpty {
            setIconOnlyPresentation()
        } else {
            setStatusPresentation(for: settings.menuBarSnapshots(from: snapshots))
        }
    }

    private func rebuildMenu() {
        menu.removeAllItems()

        let hv = NSHostingView(rootView: StatusMenuView(
            snapshots: snapshots,
            maximumProviderListHeight: StatusMenuLayout.maximumProviderListHeight
        ))
        hv.frame = NSRect(
            x: 0,
            y: 0,
            width: StatusMenuLayout.width,
            height: StatusMenuLayout.hostingHeight(measuredHeight: hv.fittingSize.height)
        )

        let customHostItem = NSMenuItem()
        customHostItem.view = hv
        menu.addItem(customHostItem)
        menu.addItem(.separator())
        menu.addItem(settingsSubmenu(
            title: "Show in Menu Bar",
            selectedProviderIDs: settings.menuBarProviderIDs,
            action: #selector(toggleMenuBarProvider)
        ))
        menu.addItem(settingsSubmenu(
            title: "Query Usage",
            selectedProviderIDs: settings.queriedProviderIDs,
            action: #selector(toggleQueriedProvider)
        ))
        menu.addItem(.separator())

        let loginItem = NSMenuItem(title: "Launch at Login", action: #selector(toggleLaunchAtLogin), keyEquivalent: "")
        loginItem.target = self
        loginItem.state = (SMAppService.mainApp.status == .enabled) ? .on : .off
        self.loginItem = loginItem
        menu.addItem(loginItem)

        let refreshItem = NSMenuItem(title: isRefreshing ? "Refreshing…" : "Refresh", action: #selector(refreshMenuItemSelected), keyEquivalent: "r")
        refreshItem.target = self
        refreshItem.isEnabled = !isRefreshing
        self.refreshItem = refreshItem
        menu.addItem(refreshItem)

        let quitItem = NSMenuItem(title: "Quit", action: #selector(quitMenuItemSelected), keyEquivalent: "q")
        quitItem.target = self
        menu.addItem(quitItem)

        statusItem.menu = menu
    }

    private func settingsSubmenu(
        title: String,
        selectedProviderIDs: Set<UsageProviderID>,
        action: Selector
    ) -> NSMenuItem {
        let item = NSMenuItem(title: title, action: nil, keyEquivalent: "")
        let submenu = NSMenu(title: title)
        for providerID in UsageProviderID.allCases {
            let providerItem = NSMenuItem(
                title: providerID.displayName,
                action: action,
                keyEquivalent: ""
            )
            providerItem.target = self
            providerItem.representedObject = providerID.rawValue
            providerItem.state = selectedProviderIDs.contains(providerID) ? .on : .off
            submenu.addItem(providerItem)
        }
        item.submenu = submenu
        return item
    }

    @objc private func refreshMenuItemSelected() {
        Task { await refresh() }
    }

    @objc private func toggleMenuBarProvider(_ sender: NSMenuItem) {
        guard let providerID = providerID(from: sender) else { return }
        var menuBarProviderIDs = settings.menuBarProviderIDs
        toggle(providerID, in: &menuBarProviderIDs)
        settings = UsageMonitorSettings(
            menuBarProviderIDs: menuBarProviderIDs,
            queriedProviderIDs: settings.queriedProviderIDs
        )
        settingsStore.save(settings)
        updateStatusPresentation()
        rebuildMenu()
    }

    @objc private func toggleQueriedProvider(_ sender: NSMenuItem) {
        guard let providerID = providerID(from: sender) else { return }
        var queriedProviderIDs = settings.queriedProviderIDs
        toggle(providerID, in: &queriedProviderIDs)
        settings = UsageMonitorSettings(
            menuBarProviderIDs: settings.menuBarProviderIDs,
            queriedProviderIDs: queriedProviderIDs
        )
        settingsStore.save(settings)
        provider = providerFactory(settings.queriedProviderIDs)
        rebuildMenu()
        Task { await refresh() }
    }

    private func providerID(from sender: NSMenuItem) -> UsageProviderID? {
        guard let rawValue = sender.representedObject as? String else { return nil }
        return UsageProviderID(rawValue: rawValue)
    }

    private func toggle(_ providerID: UsageProviderID, in providerIDs: inout Set<UsageProviderID>) {
        if providerIDs.contains(providerID) {
            providerIDs.remove(providerID)
        } else {
            providerIDs.insert(providerID)
        }
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
