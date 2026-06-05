# Spec: AI Usage Monitor Menu Bar Icon Redesign

- **Date:** 2026-06-05
- **Status:** Approved
- **Author:** Antigravity

## Context & Problem Statement
The native macOS application `AIUsageMonitor` has an "icon-only" state. This state occurs when the user chooses to disable all provider metrics/percentages in the menu bar (unchecking them under the "Show in Menu Bar" submenu) and only wants the app to display a clickable trigger to expand the menu panel.
Currently, this icon-only presentation is rendered as a circular badge with the text "AI" inside.
This presentation has two major drawbacks:
1. It is not visually representative of a modern AI tool.
2. It does not look like a native macOS menu bar status item (which typically uses clean, borderless template icons).

## Proposed Solution
We will replace the text-based circular "AI" icon with a **Modern AI Sparkle (four-pointed star)**. 

### Visual Design
- **Shape:** A clean, four-pointed sparkle with curved inner edges.
- **Styling:** Standalone shape, removing the circular frame and background.
- **macOS Integration:** Set `image.isTemplate = true`. This ensures macOS automatically colors the icon black/dark-gray in Light mode, white in Dark mode, and handles selected/active highlighted states correctly.
- **Fallback:** Keep `"AI"` as the accessibility title and fallback text.

### Implementation Details
We will update `drawIconOnly()` in [StatusMenuImageRenderer.swift](file:///Users/carl/Dev/claude-context-statusline/macos/AIUsageMonitor/Sources/AIUsageMonitorApp/StatusMenuImageRenderer.swift) to procedurally draw the sparkle shape using `NSBezierPath` with cubic Bezier curves curving inwards towards the center of the bounding box.

```swift
private static func drawIconOnly() -> NSImage {
    let size = NSSize(width: 18, height: 18)
    let image = NSImage(size: size)
    image.isTemplate = true

    image.lockFocus()
    NSGraphicsContext.current?.imageInterpolation = .high

    let rect = NSRect(origin: .zero, size: size).insetBy(dx: 1.5, dy: 1.5)
    let cx = rect.midX
    let cy = rect.midY
    let center = NSPoint(x: cx, y: cy)

    let path = NSBezierPath()
    path.move(to: NSPoint(x: cx, y: rect.maxY))
    path.curve(to: NSPoint(x: rect.maxX, y: cy), controlPoint1: center, controlPoint2: center)
    path.curve(to: NSPoint(x: cx, y: rect.minY), controlPoint1: center, controlPoint2: center)
    path.curve(to: NSPoint(x: rect.minX, y: cy), controlPoint1: center, controlPoint2: center)
    path.curve(to: NSPoint(x: cx, y: rect.maxY), controlPoint1: center, controlPoint2: center)
    path.close()

    NSColor.black.setFill()
    path.fill()

    image.unlockFocus()
    return image
}
```

## Testing & Verification
1. Run local swift unit tests: `swift test` in `macos/AIUsageMonitor`.
2. Build and launch the app: `./Scripts/build-app.sh && open .build/AIUsageMonitor.app`.
3. In the app settings (dropdown menu), uncheck all options under "Show in Menu Bar".
4. Verify the new Sparkle icon is displayed in the menu bar.
5. Verify that it correctly changes color when switching between Light Mode and Dark Mode, and when clicking/highlighting the menu bar item.
