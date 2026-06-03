import AIUsageMonitorCore
import AppKit
import Foundation

@MainActor
enum StatusMenuImageRenderer {
    struct RenderedStatus {
        let image: NSImage?
        let fallbackTitle: String
        let accessibilityTitle: String
    }

    static func renderStatus(for snapshots: [ProviderSnapshot]) -> RenderedStatus {
        let fallbackTitle = RemainingQuotaPresenter.fallbackTitle(for: snapshots)
        let entries = snapshots.compactMap { snapshot -> Entry? in
            guard let remaining = RemainingQuotaPresenter.primaryRemainingPercent(for: snapshot) else { return nil }
            return Entry(providerName: snapshot.name, remaining: remaining)
        }

        guard !entries.isEmpty else {
            return RenderedStatus(image: nil, fallbackTitle: fallbackTitle, accessibilityTitle: fallbackTitle)
        }

        return RenderedStatus(
            image: draw(entries: entries),
            fallbackTitle: fallbackTitle,
            accessibilityTitle: fallbackTitle
        )
    }

    private struct Entry {
        let providerName: String
        let remaining: Int
    }

    private static func draw(entries: [Entry]) -> NSImage {
        let scale = NSScreen.main?.backingScaleFactor ?? 2
        let font = NSFont.monospacedDigitSystemFont(ofSize: 11, weight: .semibold)
        let chipHeight: CGFloat = 18
        let iconSize: CGFloat = 14
        let horizontalPadding: CGFloat = 7
        let iconNumberGap: CGFloat = 5
        let chipGap: CGFloat = 5

        let numberAttributes: [NSAttributedString.Key: Any] = [
            .font: font,
            .foregroundColor: NSColor.white
        ]

        let chipWidths = entries.map { entry in
            let numberWidth = NSString(string: "\(entry.remaining)").size(withAttributes: numberAttributes).width
            return ceil(horizontalPadding * 2 + iconSize + iconNumberGap + numberWidth)
        }
        let totalWidth = chipWidths.reduce(0, +) + chipGap * CGFloat(max(0, chipWidths.count - 1))
        let canvasSize = NSSize(width: totalWidth, height: chipHeight)
        let image = NSImage(size: canvasSize)
        image.isTemplate = false

        image.lockFocus()
        NSGraphicsContext.current?.imageInterpolation = .high

        var x: CGFloat = 0
        for (index, entry) in entries.enumerated() {
            let chipWidth = chipWidths[index]
            let chipRect = NSRect(x: x, y: 0, width: chipWidth, height: chipHeight)
            drawChipBackground(in: chipRect)

            let iconRect = NSRect(
                x: x + horizontalPadding,
                y: (chipHeight - iconSize) / 2,
                width: iconSize,
                height: iconSize
            )
            drawIcon(for: entry.providerName, in: iconRect)

            let number = NSString(string: "\(entry.remaining)")
            let numberSize = number.size(withAttributes: numberAttributes)
            let numberRect = NSRect(
                x: iconRect.maxX + iconNumberGap,
                y: (chipHeight - numberSize.height) / 2 - 0.5,
                width: numberSize.width,
                height: numberSize.height
            )
            number.draw(in: numberRect, withAttributes: numberAttributes)

            x += chipWidth + chipGap
        }

        image.unlockFocus()
        image.size = NSSize(width: canvasSize.width / scale * scale, height: canvasSize.height)
        return image
    }

    private static func drawChipBackground(in rect: NSRect) {
        let path = NSBezierPath(roundedRect: rect, xRadius: rect.height / 2, yRadius: rect.height / 2)
        NSColor.white.withAlphaComponent(0.17).setFill()
        path.fill()
        NSColor.white.withAlphaComponent(0.23).setStroke()
        path.lineWidth = 1
        path.stroke()
    }

    private static func drawIcon(for providerName: String, in rect: NSRect) {
        let lowercased = providerName.lowercased()
        if lowercased.contains("claude") {
            drawClaudeSpark(in: rect)
        } else if lowercased.contains("codex") {
            drawOpenAIMark(in: rect)
        } else if lowercased.contains("antigravity") {
            drawAntigravityArch(in: rect)
        } else {
            drawGenericDot(in: rect)
        }
    }

    private static func drawClaudeSpark(in rect: NSRect) {
        NSColor(calibratedRed: 0.85, green: 0.45, blue: 0.31, alpha: 1).setFill()
        let center = NSPoint(x: rect.midX, y: rect.midY)
        let longRadius = rect.width * 0.48
        let shortRadius = rect.width * 0.16
        let path = NSBezierPath()
        for index in 0..<8 {
            let angle = CGFloat(index) * .pi / 4 - .pi / 2
            let radius = index.isMultiple(of: 2) ? longRadius : shortRadius
            let point = NSPoint(x: center.x + cos(angle) * radius, y: center.y + sin(angle) * radius)
            if index == 0 { path.move(to: point) } else { path.line(to: point) }
        }
        path.close()
        path.fill()
    }

    private static func drawOpenAIMark(in rect: NSRect) {
        NSColor.white.setStroke()
        let path = NSBezierPath(ovalIn: rect.insetBy(dx: 1.5, dy: 1.5))
        path.lineWidth = 1.4
        path.stroke()

        for angle in stride(from: CGFloat(0), to: CGFloat.pi * 2, by: CGFloat.pi / 3) {
            let center = NSPoint(x: rect.midX, y: rect.midY)
            let inner = NSPoint(x: center.x + cos(angle) * 2.0, y: center.y + sin(angle) * 2.0)
            let outer = NSPoint(x: center.x + cos(angle) * 5.0, y: center.y + sin(angle) * 5.0)
            let spoke = NSBezierPath()
            spoke.move(to: inner)
            spoke.line(to: outer)
            spoke.lineWidth = 1.2
            spoke.stroke()
        }
    }

    private static func drawAntigravityArch(in rect: NSRect) {
        let path = NSBezierPath()
        path.move(to: NSPoint(x: rect.minX + 1, y: rect.minY + 1))
        path.curve(
            to: NSPoint(x: rect.maxX - 1, y: rect.minY + 1),
            controlPoint1: NSPoint(x: rect.midX - 2, y: rect.maxY - 1),
            controlPoint2: NSPoint(x: rect.midX + 2, y: rect.maxY - 1)
        )
        path.lineWidth = 3.0
        NSColor.systemBlue.setStroke()
        path.stroke()

        let warmDot = NSBezierPath(ovalIn: NSRect(x: rect.midX - 2, y: rect.maxY - 5, width: 4, height: 4))
        NSColor.systemOrange.setFill()
        warmDot.fill()
    }

    private static func drawGenericDot(in rect: NSRect) {
        NSColor.white.withAlphaComponent(0.85).setFill()
        NSBezierPath(ovalIn: rect.insetBy(dx: 3, dy: 3)).fill()
    }
}
