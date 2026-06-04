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

    static func renderIconOnly() -> RenderedStatus {
        RenderedStatus(
            image: drawIconOnly(),
            fallbackTitle: "AI",
            accessibilityTitle: "AI Usage Monitor"
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

        // The number stays white; status severity is shown by a corner badge on
        // the icon (warn/critical), not by the number color.
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
            drawChipBackground(in: chipRect, remaining: entry.remaining)

            let iconRect = NSRect(
                x: x + horizontalPadding,
                y: (chipHeight - iconSize) / 2,
                width: iconSize,
                height: iconSize
            )
            drawIcon(for: entry.providerName, in: iconRect)
            drawStatusBadge(forRemaining: entry.remaining, iconRect: iconRect)

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

    private static func drawIconOnly() -> NSImage {
        let size = NSSize(width: 18, height: 18)
        let image = NSImage(size: size)
        image.isTemplate = false

        image.lockFocus()
        NSGraphicsContext.current?.imageInterpolation = .high

        let rect = NSRect(origin: .zero, size: size).insetBy(dx: 1, dy: 1)
        let background = NSBezierPath(ovalIn: rect)
        NSColor.white.withAlphaComponent(0.16).setFill()
        background.fill()
        NSColor.white.withAlphaComponent(0.28).setStroke()
        background.lineWidth = 1
        background.stroke()

        let attributes: [NSAttributedString.Key: Any] = [
            .font: NSFont.systemFont(ofSize: 9, weight: .bold),
            .foregroundColor: NSColor.white
        ]
        let title = NSString(string: "AI")
        let titleSize = title.size(withAttributes: attributes)
        title.draw(
            in: NSRect(
                x: (size.width - titleSize.width) / 2,
                y: (size.height - titleSize.height) / 2 - 0.5,
                width: titleSize.width,
                height: titleSize.height
            ),
            withAttributes: attributes
        )

        image.unlockFocus()
        return image
    }

    /// Status badge in the icon's lower-left corner: a yellow caution triangle for
    /// warn, a red circle with a white exclamation for critical, nothing for good.
    /// Shape plus color keeps it legible and colorblind-friendly.
    private static func drawStatusBadge(forRemaining remaining: Int, iconRect: NSRect) {
        let tier = RemainingQuotaPresenter.tier(forRemaining: remaining)
        let size = iconRect.width * 0.68
        let badgeRect = NSRect(
            x: iconRect.minX - size * 0.28,
            y: iconRect.minY - size * 0.16,
            width: size,
            height: size
        )

        switch tier {
        case .good:
            return
        case .warn:
            drawWarnTriangle(in: badgeRect)
        case .critical:
            drawCriticalExclamation(in: badgeRect)
        }
    }

    private static func drawWarnTriangle(in rect: NSRect) {
        let inset = rect.width * 0.04
        let triangle = NSBezierPath()
        triangle.move(to: NSPoint(x: rect.midX, y: rect.maxY - inset))
        triangle.line(to: NSPoint(x: rect.minX + inset, y: rect.minY + inset))
        triangle.line(to: NSPoint(x: rect.maxX - inset, y: rect.minY + inset))
        triangle.close()
        triangle.lineJoinStyle = .round
        // White ring first so the badge reads against any icon, then fill
        // (matches the critical badge treatment).
        NSColor.white.withAlphaComponent(0.92).setStroke()
        triangle.lineWidth = rect.width * 0.24
        triangle.stroke()
        NSColor(calibratedRed: 255 / 255, green: 204 / 255, blue: 0 / 255, alpha: 1).setFill()
        triangle.fill()
        // Dark exclamation inside the triangle.
        NSColor.black.withAlphaComponent(0.72).setFill()
        let barWidth = rect.width * 0.12
        NSBezierPath(
            roundedRect: NSRect(
                x: rect.midX - barWidth / 2, y: rect.minY + rect.height * 0.36,
                width: barWidth, height: rect.height * 0.26
            ),
            xRadius: barWidth / 2, yRadius: barWidth / 2
        ).fill()
        let dot = rect.width * 0.13
        NSBezierPath(ovalIn: NSRect(
            x: rect.midX - dot / 2, y: rect.minY + rect.height * 0.24, width: dot, height: dot
        )).fill()
    }

    private static func drawCriticalExclamation(in rect: NSRect) {
        let circle = NSBezierPath(ovalIn: rect)
        // White outer ring first so the badge reads against any icon, then fill.
        NSColor.white.withAlphaComponent(0.92).setStroke()
        circle.lineWidth = rect.width * 0.12
        circle.stroke()
        NSColor(calibratedRed: 255 / 255, green: 59 / 255, blue: 48 / 255, alpha: 1).setFill()
        circle.fill()
        NSColor.white.setFill()
        let barWidth = rect.width * 0.15
        NSBezierPath(
            roundedRect: NSRect(
                x: rect.midX - barWidth / 2, y: rect.minY + rect.height * 0.38,
                width: barWidth, height: rect.height * 0.30
            ),
            xRadius: barWidth / 2, yRadius: barWidth / 2
        ).fill()
        let dot = barWidth * 1.1
        NSBezierPath(ovalIn: NSRect(
            x: rect.midX - dot / 2, y: rect.minY + rect.height * 0.20, width: dot, height: dot
        )).fill()
    }

    private static func drawChipBackground(in rect: NSRect, remaining: Int) {
        let path = NSBezierPath(roundedRect: rect, xRadius: rect.height / 2, yRadius: rect.height / 2)
        
        if let context = NSGraphicsContext.current {
            context.saveGraphicsState()
            path.addClip()
            
            // 1. Unfilled background (10% opacity)
            NSColor.white.withAlphaComponent(0.10).setFill()
            path.fill()
            
            // 2. Remaining progress (24% opacity)
            let progressWidth = rect.width * CGFloat(remaining) / 100.0
            let progressRect = NSRect(x: rect.minX, y: rect.minY, width: progressWidth, height: rect.height)
            NSColor.white.withAlphaComponent(0.24).setFill()
            let progressPath = NSBezierPath(rect: progressRect)
            progressPath.fill()
            
            context.restoreGraphicsState()
        }
        
        // 3. Border (23% opacity)
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
            drawAntigravityLogo(in: rect)
        } else {
            drawGenericDot(in: rect)
        }
    }

    /// Draw the official Claude starburst (matches the SwiftBar plugin's brand
    /// path) filled in brand orange, instead of an approximate procedural star.
    private static func drawClaudeSpark(in rect: NSRect) {
        ClaudeLogo.brandColor.setFill()
        ClaudeLogo.bezierPath(in: rect).fill()
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

    /// Draw the official Antigravity brand logo (matches the SwiftBar plugin),
    /// scaled to fit the icon rect with aspect ratio preserved and centered.
    /// Falls back to the drawn arch if the embedded PNG can't be decoded.
    private static func drawAntigravityLogo(in rect: NSRect) {
        guard
            let image = AntigravityLogo.image,
            image.size.width > 0, image.size.height > 0
        else {
            drawAntigravityArch(in: rect)
            return
        }
        let scale = min(rect.width / image.size.width, rect.height / image.size.height)
        let width = image.size.width * scale
        let height = image.size.height * scale
        let fitted = NSRect(
            x: rect.midX - width / 2,
            y: rect.midY - height / 2,
            width: width,
            height: height
        )
        image.draw(in: fitted, from: .zero, operation: .sourceOver, fraction: 1)
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
