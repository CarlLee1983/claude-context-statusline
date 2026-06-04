import SwiftUI
import AIUsageMonitorCore

struct ProviderCardView: View {
    let snapshot: ProviderSnapshot
    
    private var isAntigravity: Bool {
        snapshot.name.lowercased() == "antigravity" || snapshot.shortName.lowercased() == "antigravity"
    }
    
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            // Header
            HStack(spacing: 8) {
                BrandIconView(name: snapshot.name)
                
                Text(snapshot.name)
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(.primary)
                
                if let plan = snapshot.plan {
                    Text(plan)
                        .font(.system(size: 10, weight: .medium))
                        .padding(.horizontal, 5)
                        .padding(.vertical, 1)
                        .background(Color.primary.opacity(0.08))
                        .cornerRadius(4)
                        .foregroundColor(.secondary)
                }
                
                Spacer()
                
                if !snapshot.isAvailable {
                    Text("Unavailable")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundColor(.red)
                } else {
                    Text(snapshot.updatedAt.formatted(date: .omitted, time: .shortened))
                        .font(.system(size: 10))
                        .foregroundColor(.secondary)
                }
            }
            .padding(.bottom, 2)
            
            if snapshot.windows.isEmpty {
                Text(snapshot.isAvailable ? "No quota data available" : "Service offline")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
            } else if isAntigravity {
                let cooldownModels = snapshot.windows.filter { RemainingQuotaPresenter.remainingPercent(for: $0) < 100 }
                let readyModels = snapshot.windows.filter { RemainingQuotaPresenter.remainingPercent(for: $0) == 100 }
                
                VStack(alignment: .leading, spacing: 10) {
                    ForEach(cooldownModels) { window in
                        UsageProgressBarView(window: window)
                    }
                    
                    if !readyModels.isEmpty {
                        HStack(spacing: 4) {
                            BrandIconView(name: "gemini")
                                .frame(width: 10, height: 10)
                            Text("+ \(readyModels.count) \(readyModels.count == 1 ? "other model" : "other models") available with ")
                                .font(.system(size: 10))
                                .foregroundColor(.secondary) +
                            Text("100% quota")
                                .font(.system(size: 10, weight: .semibold))
                                .foregroundColor(.green)
                        }
                        .padding(.top, 4)
                        .frame(maxWidth: .infinity, alignment: .center)
                    }
                }
            } else {
                VStack(spacing: 12) {
                    ForEach(snapshot.windows) { window in
                        UsageProgressBarView(window: window)
                    }
                }
            }
        }
        .padding(12)
        .background(Color(nsColor: .windowBackgroundColor).opacity(0.12))
        .cornerRadius(8)
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(Color.primary.opacity(0.06), lineWidth: 1)
        )
    }
}

public struct StatusMenuView: View {
    let snapshots: [ProviderSnapshot]
    
    public init(snapshots: [ProviderSnapshot]) {
        self.snapshots = snapshots
    }
    
    public var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // App Header
            HStack {
                Text("AI Usage Monitor")
                    .font(.system(size: 11, weight: .bold))
                    .foregroundColor(.secondary)
                    .textCase(.uppercase)
                Spacer()
            }
            .padding(.horizontal, 4)
            
            if snapshots.isEmpty {
                Text("No usage data available")
                    .font(.system(size: 12))
                    .foregroundColor(.secondary)
                    .frame(maxWidth: .infinity, alignment: .center)
                    .padding(.vertical, 16)
            } else {
                ForEach(snapshots) { snapshot in
                    ProviderCardView(snapshot: snapshot)
                }
            }
        }
        .padding(16)
        .frame(width: 320)
    }
}

#Preview {
    StatusMenuView(snapshots: [
        ProviderSnapshot(
            name: "Claude Code",
            shortName: "CC",
            plan: "Pro",
            windows: [
                UsageWindow(label: "5h", percent: 45, kind: .used, resetAt: Date().addingTimeInterval(3600)),
                UsageWindow(label: "7d", percent: 12, kind: .used, resetAt: Date().addingTimeInterval(86400 * 2))
            ]
        ),
        ProviderSnapshot(
            name: "Codex",
            shortName: "CX",
            plan: nil,
            windows: [
                UsageWindow(label: "Requests", percent: 8, kind: .used, resetAt: Date().addingTimeInterval(60))
            ]
        ),
        ProviderSnapshot(
            name: "Antigravity",
            shortName: "AG",
            plan: "agy /usage",
            windows: [
                UsageWindow(label: "Gemini 1.5 Pro", percent: 60, kind: .used, resetAt: Date().addingTimeInterval(120)),
                UsageWindow(label: "Gemini 1.5 Flash", percent: 100, kind: .available),
                UsageWindow(label: "Claude 3.5 Sonnet", percent: 100, kind: .available),
                UsageWindow(label: "Claude 3 Opus", percent: 95, kind: .used, resetAt: Date().addingTimeInterval(300))
            ]
        )
    ])
}
