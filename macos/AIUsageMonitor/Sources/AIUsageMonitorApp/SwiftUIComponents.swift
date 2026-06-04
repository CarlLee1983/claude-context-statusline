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
