import SwiftUI
import AIUsageMonitorCore

// 1. Claude Spark Shape
struct ClaudeLogoShape: Shape {
    func path(in rect: CGRect) -> Path {
        let viewBox = ClaudeLogo.viewBox
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
        let segments = ClaudeLogo.parsedSegments
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
        let size = min(rect.width, rect.height)
        let offsetX = rect.minX + (rect.width - size) / 2
        let offsetY = rect.minY + (rect.height - size) / 2
        // Centered square rectangle to enforce 1:1 aspect ratio and prevent stretching
        let squareRect = CGRect(x: offsetX, y: offsetY, width: size, height: size)
        
        var path = Path()
        let cx = squareRect.midX
        let cy = squareRect.midY
        
        path.move(to: CGPoint(x: cx, y: squareRect.minY))
        path.addQuadCurve(to: CGPoint(x: squareRect.maxX, y: cy), control: CGPoint(x: cx + size * 0.15, y: cy - size * 0.15))
        path.addQuadCurve(to: CGPoint(x: cx, y: squareRect.maxY), control: CGPoint(x: cx + size * 0.15, y: cy + size * 0.15))
        path.addQuadCurve(to: CGPoint(x: squareRect.minX, y: cy), control: CGPoint(x: cx - size * 0.15, y: cy + size * 0.15))
        path.addQuadCurve(to: CGPoint(x: cx, y: squareRect.minY), control: CGPoint(x: cx - size * 0.15, y: cy - size * 0.15))
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
        if let nsImage = AntigravityLogo.image {
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

// 5. Brand Icon View Switcher
public struct BrandIconView: View {
    public let name: String
    public let size: CGFloat
    
    public init(name: String, size: CGFloat = 16) {
        self.name = name
        self.size = size
    }
    
    public var body: some View {
        Group {
            let lowercased = name.lowercased()
            if lowercased.contains("claude") {
                ClaudeLogoShape()
                    .fill(Color(nsColor: ClaudeLogo.brandColor))
            } else if lowercased.contains("codex") || lowercased.contains("openai") {
                OpenAILogoView(color: Color(red: 25 / 255, green: 195 / 255, blue: 125 / 255))
            } else if lowercased.contains("antigravity") {
                AntigravityLogoView()
            } else if lowercased.contains("gemini") || lowercased.contains("google") {
                GeminiLogoView()
            } else {
                Circle()
                    .fill(Color.secondary)
            }
        }
        .frame(width: size, height: size)
    }
}

// 6. Usage Progress Bar View
public struct UsageProgressBarView: View {
    public let label: String
    public let remainingPercent: Int
    public let usedPercent: Int
    public let tier: RemainingTier
    public let detailText: String
    public let isExpiringUnused: Bool

    public init(
        label: String,
        remainingPercent: Int,
        usedPercent: Int,
        tier: RemainingTier,
        detailText: String,
        isExpiringUnused: Bool = false
    ) {
        self.label = label
        self.remainingPercent = remainingPercent
        self.usedPercent = usedPercent
        self.tier = tier
        self.detailText = detailText
        self.isExpiringUnused = isExpiringUnused
    }

    public init(window: UsageWindow, now: Date = .now) {
        self.label = window.label
        let remaining = RemainingQuotaPresenter.remainingPercent(for: window)
        self.remainingPercent = remaining
        self.usedPercent = window.kind == .used ? Int(window.percent.rounded()) : (100 - remaining)
        self.tier = RemainingQuotaPresenter.tier(forRemaining: remaining)
        self.isExpiringUnused = RemainingQuotaPresenter.isExpiringUnused(for: window, now: now)

        let resetText = window.resetAt.map { resetAt in
            if Calendar.current.isDate(resetAt, inSameDayAs: now) {
                return "reset " + resetAt.formatted(date: .omitted, time: .shortened)
            } else {
                return "reset " + resetAt.formatted(date: .abbreviated, time: .shortened)
            }
        }

        if let reset = resetText {
            self.detailText = reset
        } else {
            self.detailText = "No reset scheduled"
        }
    }

    // Indigo "expiring" color — distinct from the red/yellow/green severity scale.
    private static let expiringColor = Color(red: 88 / 255, green: 86 / 255, blue: 214 / 255)

    private var tierColor: Color {
        switch tier {
        case .good:
            return Color(red: 52 / 255, green: 199 / 255, blue: 89 / 255) // Apple Green
        case .warn:
            return Color(red: 255 / 255, green: 204 / 255, blue: 0 / 255) // Apple Yellow/Amber
        case .critical:
            return Color(red: 255 / 255, green: 59 / 255, blue: 48 / 255) // Apple Red
        }
    }

    // When expiring-unused, the filled (remaining) segment switches to indigo
    // and gains a diagonal-stripe overlay; otherwise it follows the severity tier.
    private var barColor: Color {
        isExpiringUnused ? Self.expiringColor : tierColor
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(label)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(.primary)
                Spacer()
                Text("\(remainingPercent)% remaining")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundColor(barColor)
            }

            // Progress Bar
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 3)
                        .fill(Color.primary.opacity(0.1))

                    RoundedRectangle(cornerRadius: 3)
                        .fill(barColor)
                        .frame(width: max(0, min(geo.size.width, geo.size.width * CGFloat(remainingPercent) / 100.0)))
                        .overlay {
                            if isExpiringUnused {
                                DiagonalStripes(spacing: 5)
                                    .stroke(Color.white.opacity(0.55), lineWidth: 1.5)
                            }
                        }
                        .clipShape(RoundedRectangle(cornerRadius: 3))
                }
            }
            .frame(height: 6)

            HStack {
                Text("Used \(usedPercent)%")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
                Spacer()
                Text(detailText)
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
            }
        }
        .padding(.vertical, 4)
    }
}

// 7. Diagonal stripe texture — overlaid on an "expiring-unused" quota segment.
// A pattern cue (color-blind friendly) that pairs with the indigo at-risk color.
private struct DiagonalStripes: Shape {
    var spacing: CGFloat = 5

    func path(in rect: CGRect) -> Path {
        guard spacing > 0 else { return Path() }
        var path = Path()
        // 45° lines sweeping bottom-left → top-right, stepping across the rect.
        var x = rect.minX - rect.height
        while x < rect.maxX {
            path.move(to: CGPoint(x: x, y: rect.maxY))
            path.addLine(to: CGPoint(x: x + rect.height, y: rect.minY))
            x += spacing
        }
        return path
    }
}
