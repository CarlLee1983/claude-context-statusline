import AIUsageMonitorCore
import AppKit
import SwiftUI

@MainActor
final class UsageMenuModel: ObservableObject {
    @Published private(set) var snapshots: [ProviderSnapshot] = []
    @Published private(set) var isRefreshing = false

    private let provider: UsageSnapshotProviding

    init(provider: UsageSnapshotProviding) {
        self.provider = provider
    }

    var menuTitle: String {
        if snapshots.isEmpty { return "AI —" }

        let parts = snapshots.map { snapshot in
            guard let first = snapshot.windows.first else { return "\(snapshot.shortName) —" }
            return "\(snapshot.shortName) \(Int(first.percent.rounded()))%"
        }
        return "AI " + parts.joined(separator: " ")
    }

    func refresh() async {
        isRefreshing = true
        snapshots = await provider.snapshots()
        isRefreshing = false
    }
}

struct UsageMenuView: View {
    @ObservedObject var model: UsageMenuModel

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("AI Usage Monitor")
                    .font(.headline)
                Spacer()
                Button(model.isRefreshing ? "Refreshing…" : "Refresh") {
                    Task { await model.refresh() }
                }
                .disabled(model.isRefreshing)
            }

            if model.snapshots.isEmpty {
                Text("No usage data yet.")
                    .foregroundStyle(.secondary)
            } else {
                ForEach(model.snapshots) { snapshot in
                    VStack(alignment: .leading, spacing: 6) {
                        HStack(spacing: 4) {
                            Text(snapshot.name)
                                .font(.subheadline.bold())
                            if let plan = snapshot.plan {
                                Text("· \(plan)")
                                    .foregroundStyle(.secondary)
                            }
                            Spacer()
                        }

                        ForEach(snapshot.windows) { window in
                            UsageWindowRow(window: window)
                        }
                    }
                    Divider()
                }
            }

            Button("Quit") {
                NSApplication.shared.terminate(nil)
            }
        }
        .padding()
        .frame(width: 420)
    }
}

private struct UsageWindowRow: View {
    let window: UsageWindow

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack {
                Text(window.label)
                    .lineLimit(1)
                Spacer()
                Text("\(Int(window.percent.rounded()))% \(window.kind.label)")
                    .foregroundStyle(.secondary)
            }
            ProgressView(value: window.percent, total: 100)
                .tint(window.kind.color(for: window.percent))
            if let resetAt = window.resetAt {
                Text("Reset \(resetAt.formatted(date: .omitted, time: .shortened))")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }
}

private extension QuotaKind {
    var label: String {
        switch self {
        case .used:
            "used"
        case .available:
            "available"
        }
    }

    func color(for percent: Double) -> Color {
        switch self {
        case .used:
            if percent >= 90 { return .red }
            if percent >= 70 { return .yellow }
            return .green
        case .available:
            if percent <= 10 { return .red }
            if percent <= 30 { return .yellow }
            return .green
        }
    }
}
