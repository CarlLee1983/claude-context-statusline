# SwiftUI Dropdown Menu Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the macOS status bar app's plain-text dropdown menu with a beautiful custom SwiftUI view containing visual progress bars, official brand logos, and collapsed Antigravity models.

**Architecture:** Use `NSHostingView` to embed a single custom SwiftUI view `StatusMenuView` inside the first `NSMenuItem` of the status bar `NSMenu`. Standard controls (Launch at Login, Refresh, Quit) remain at the bottom as native items.

**Tech Stack:** Swift 5.9+, SwiftUI, AppKit (NSHostingView)

---

### Task 1: SwiftUI Brand Icons & Shapes

**Files:**
- Create: `macos/AIUsageMonitor/Sources/AIUsageMonitorApp/SwiftUIComponents.swift`

- [ ] **Step 1: Write the brand logo shapes and vector drawing code in SwiftUI**

```swift
import SwiftUI
import AIUsageMonitorCore

// 1. Claude Spark Shape
struct ClaudeLogoShape: Shape {
    func path(in rect: CGRect) -> Path {
        let viewBox: CGFloat = 24
        let scale = min(rect.width, rect.height) / viewBox
        let drawn = viewBox * scale
        let offsetX = rect.minX + (rect.width - drawn) / 2
        let offsetY = rect.minY + (rect.height - drawn) / 2

        func map(_ point: CGPoint) -> CGPoint {
            CGPoint(
                x: offsetX + point.x * scale,
                y: offsetY + point.y * scale
            )
        }

        var path = Path()
        let segments = SVGPathParser.parse(ClaudeLogo.svgPath)
        for segment in segments {
            switch segment {
            case let .move(point):
                path.move(to: map(point))
            case let .line(point):
                path.addLine(to: map(point))
            case let .curve(to: end, control1: c1, control2: c2):
                path.addCurve(to: map(end), control1: map(c1), control2: map(c2))
            case .close:
                path.closeSubpath()
            }
        }
        return path
    }
}

// 2. OpenAI Petal Shape for Codex
struct OpenAIPetalShape: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        let cx = rect.midX
        let cy = rect.midY
        let r = min(rect.width, rect.height) / 2
        
        path.move(to: CGPoint(x: cx, y: cy))
        path.addLine(to: CGPoint(x: cx, y: cy - r * 0.5))
        path.addArc(
            center: CGPoint(x: cx + r * 0.18, y: cy - r * 0.5),
            radius: r * 0.18,
            startAngle: .radians(.pi),
            endAngle: .radians(0),
            clockwise: false
        )
        path.addQuadCurve(
            to: CGPoint(x: cx, y: cy),
            control: CGPoint(x: cx + r * 0.38, y: cy - r * 0.18)
        )
        return path
    }
}

struct OpenAILogoView: View {
    let color: Color
    
    var body: some View {
        GeometryReader { geo in
            ZStack {
                ForEach(0..<6) { i in
                    OpenAIPetalShape()
                        .stroke(color, lineWidth: geo.size.width * 0.08)
                        .rotationEffect(.degrees(Double(i) * 60))
                }
            }
        }
    }
}

// 3. Gemini Sparkle Shape (four-pointed star)
struct GeminiSparkleShape: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        let cx = rect.midX
        let cy = rect.midY
        let w = rect.width
        let h = rect.height
        
        path.move(to: CGPoint(x: cx, y: rect.minY))
        path.addQuadCurve(to: CGPoint(x: rect.maxX, y: cy), control: CGPoint(x: cx + w * 0.15, y: cy - h * 0.15))
        path.addQuadCurve(to: CGPoint(x: cx, y: rect.maxY), control: CGPoint(x: cx + w * 0.15, y: cy + h * 0.15))
        path.addQuadCurve(to: CGPoint(x: rect.minX, y: cy), control: CGPoint(x: cx - w * 0.15, y: cy + h * 0.15))
        path.addQuadCurve(to: CGPoint(x: cx, y: rect.minY), control: CGPoint(x: cx - w * 0.15, y: cy - h * 0.15))
        path.closeSubpath()
        return path
    }
}

struct GeminiLogoView: View {
    var body: some View {
        GeminiSparkleShape()
            .fill(
                LinearGradient(
                    colors: [Color(red: 155/255, green: 197/255, blue: 255/255),
                             Color(red: 225/255, green: 161/255, blue: 255/255),
                             Color(red: 255/255, green: 207/255, blue: 180/255)],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
            )
    }
}

// 4. Antigravity Logo View
struct AntigravityLogoView: View {
    var body: some View {
        if let data = Data(base64Encoded: AntigravityLogo.base64),
           let nsImage = NSImage(data: data) {
            Image(nsImage: nsImage)
                .resizable()
                .aspectRatio(contentMode: .fit)
        } else {
            // Fallback arch
            Canvas { context, size in
                let rect = CGRect(origin: .zero, size: size)
                var path = Path()
                path.move(to: CGPoint(x: rect.minX + 2, y: rect.maxY - 2))
                path.addQuadCurve(
                    to: CGPoint(x: rect.maxX - 2, y: rect.maxY - 2),
                    control: CGPoint(x: rect.midX, y: rect.minY + 2)
                )
                context.stroke(path, with: .color(.blue), lineWidth: 3)
                context.fill(Path(ellipseIn: CGRect(x: rect.midX - 2, y: rect.minY + 4, width: 4, height: 4)), with: .color(.orange))
            }
        }
    }
}
```

- [ ] **Step 2: Commit files**

```bash
git add macos/AIUsageMonitor/Sources/AIUsageMonitorApp/SwiftUIComponents.swift
git commit -m "feat: add vector brand logo shapes and views in SwiftUI"
```

---

### Task 2: Brand Icon Switcher & Progress Bar

**Files:**
- Modify: `macos/AIUsageMonitor/Sources/AIUsageMonitorApp/SwiftUIComponents.swift`

- [ ] **Step 1: Implement the icon factory switcher and standard progress bar component**

Add to `SwiftUIComponents.swift`:
```swift
// Icon factory picker
struct BrandIconView: View {
    let name: String
    
    var body: some View {
        let lower = name.lowercased()
        Group {
            if lower.contains("claude") {
                ClaudeLogoShape()
                    .fill(Color(nsColor: ClaudeLogo.brandColor))
            } else if lower.contains("codex") {
                OpenAILogoView(color: Color(red: 25/255, green: 195/255, blue: 125/255))
            } else if lower.contains("antigravity") {
                AntigravityLogoView()
            } else if lower.contains("gemini") {
                GeminiLogoView()
            } else {
                Circle()
                    .fill(Color.secondary)
            }
        }
        .frame(width: 16, height: 16)
    }
}

// Progress Bar with severity tier color
struct UsageProgressBarView: View {
    let label: String
    let remainingPercent: Int
    let usedPercent: Int
    let detailText: String
    
    private var tierColor: Color {
        if remainingPercent <= 10 {
            return .red
        } else if remainingPercent <= 40 {
            return .orange
        } else {
            return .green
        }
    }
    
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(label)
                    .font(.system(size: 11, weight: .medium))
                    .foregroundColor(.primary)
                Spacer()
                Text("\(remainingPercent)% remaining")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(tierColor)
            }
            
            // Progress Bar Track & Fill
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 3)
                        .fill(Color.primary.opacity(0.08))
                    RoundedRectangle(cornerRadius: 3)
                        .fill(tierColor)
                        .frame(width: max(0, min(geo.size.width, geo.size.width * CGFloat(remainingPercent) / 100.0)))
                }
            }
            .frame(height: 6)
            
            HStack {
                Text("used \(usedPercent)%")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
                Spacer()
                Text(detailText)
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
            }
        }
    }
}
```

- [ ] **Step 2: Commit files**

```bash
git add macos/AIUsageMonitor/Sources/AIUsageMonitorApp/SwiftUIComponents.swift
git commit -m "feat: add BrandIconView factory and UsageProgressBarView"
```

---

### Task 3: Dropdown Layout & Models Grouping

**Files:**
- Create: `macos/AIUsageMonitor/Sources/AIUsageMonitorApp/StatusMenuView.swift`

- [ ] **Step 1: Implement card views and main container layout**

```swift
import SwiftUI
import AIUsageMonitorCore

struct ProviderCardView: View {
    let snapshot: ProviderSnapshot
    
    // Grouping helper for Antigravity models
    private var isAntigravity: Bool {
        snapshot.name.lowercased().contains("antigravity")
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
                
                // Active status or Unavailable label
                if !snapshot.isAvailable {
                    Text("Unavailable")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundColor(.red)
                }
            }
            .padding(.bottom, 2)
            
            if snapshot.windows.isEmpty {
                Text(snapshot.isAvailable ? "No quota data available" : "Service offline")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
            } else if isAntigravity {
                // Grouping logic for Antigravity Models:
                // 1. Cooldown models (< 100% quota) -> show detailed progress rows.
                // 2. Ready models (100% quota) -> collapse into a single text summary.
                let cooldownModels = snapshot.windows.filter { RemainingQuotaPresenter.remainingPercent(for: $0) < 100 }
                let readyModels = snapshot.windows.filter { RemainingQuotaPresenter.remainingPercent(for: $0) == 100 }
                
                VStack(alignment: .leading, spacing: 10) {
                    ForEach(cooldownModels) { window in
                        let remaining = RemainingQuotaPresenter.remainingPercent(for: window)
                        let resets = window.resetAt.map { "resets \($0.formatted(date: .omitted, time: .shortened))" } ?? ""
                        UsageProgressBarView(
                            label: window.label,
                            remainingPercent: remaining,
                            usedPercent: 100 - remaining,
                            detailText: resets
                        )
                    }
                    
                    if !readyModels.isEmpty {
                        let names = readyModels.map { $0.label }.joined(separator: ", ")
                        HStack(spacing: 4) {
                            BrandIconView(name: "gemini")
                                .frame(width: 10, height: 10)
                            Text("\(names) are ")
                                .font(.system(size: 10))
                                .foregroundColor(.secondary) +
                            Text("100% available")
                                .font(.system(size: 10, weight: .semibold))
                                .foregroundColor(.green)
                        }
                        .padding(.top, 4)
                        .frame(maxWidth: .infinity, alignment: .center)
                    }
                }
            } else {
                // Standard windows (Claude, Codex)
                VStack(spacing: 12) {
                    ForEach(snapshot.windows) { window in
                        let remaining = RemainingQuotaPresenter.remainingPercent(for: window)
                        let resets = window.resetAt.map { "resets \($0.formatted(date: .omitted, time: .shortened))" } ?? ""
                        UsageProgressBarView(
                            label: window.label,
                            remainingPercent: remaining,
                            usedPercent: Int(window.percent.rounded()),
                            detailText: resets
                        )
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
```

- [ ] **Step 2: Commit files**

```bash
git add macos/AIUsageMonitor/Sources/AIUsageMonitorApp/StatusMenuView.swift
git commit -m "feat: add main StatusMenuView container with card components"
```

---

### Task 4: Integrate SwiftUI View inside Menu Item

**Files:**
- Modify: `macos/AIUsageMonitor/Sources/AIUsageMonitorApp/StatusMenuController.swift`

- [ ] **Step 1: Replace plain-text items in `rebuildMenu` with the SwiftUI hosting view**

Replace target lines ~66-120:
```swift
<<<<
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
====
    private func rebuildMenu() {
        let menu = NSMenu()

        // 1. SwiftUI Custom View wrapping the snapshots
        let view = StatusMenuView(snapshots: snapshots)
        let hostingView = NSHostingView(rootView: view)
        // Autolayout allows SwiftUI view to size the NSHostingView frame automatically
        hostingView.translatesAutoresizingMaskIntoConstraints = false
        
        let customItem = NSMenuItem()
        customItem.view = hostingView
        menu.addItem(customItem)

        // 2. Standard Native Options
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
>>>>
```

- [ ] **Step 2: Compile & Build the project to verify changes**

Run command: `swift build` (under Cwd `macos/AIUsageMonitor`)
Expected output: Build complete! (0.13s)

- [ ] **Step 3: Run existing unit tests to make sure no core tests are broken**

Run command: `swift test` (under Cwd `macos/AIUsageMonitor`)
Expected output: All tests passed.

- [ ] **Step 4: Commit changes**

```bash
git add macos/AIUsageMonitor/Sources/AIUsageMonitorApp/StatusMenuController.swift
git commit -m "feat: embed SwiftUI hosting view inside NSMenuItem and simplify rebuildMenu"
```
