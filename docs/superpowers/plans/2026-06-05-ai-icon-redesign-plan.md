# AI Icon Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the circular "AI" text icon in the menu bar with a modern, high-quality, native macOS template sparkle icon when the app runs in icon-only mode.

**Architecture:** Update `StatusMenuImageRenderer.renderIconOnly()` to return a template image (`isTemplate = true`) and procedurally draw the four-pointed sparkle shape using `NSBezierPath` curves. Remove the legacy circular background and text drawing code.

**Tech Stack:** Swift, AppKit, Swift Testing

---

### Task 1: Add a test for StatusMenuImageRenderer.renderIconOnly()

**Files:**
- Create: `macos/AIUsageMonitor/Tests/AIUsageMonitorAppTests/StatusMenuImageRendererTests.swift`

- [ ] **Step 1: Write the failing test**
  Create the test file verifying that the icon-only status image is a template image of size 18x18.
  
  ```swift
  import Testing
  import AppKit
  @testable import AIUsageMonitorApp

  @Suite("Status menu image renderer")
  struct StatusMenuImageRendererTests {
      @Test("icon-only image is a template image of size 18x18")
      func iconOnlyImageIsTemplateAndCorrectSize() {
          let rendered = StatusMenuImageRenderer.renderIconOnly()
          #expect(rendered.image != nil)
          if let image = rendered.image {
              #expect(image.size.width == 18)
              #expect(image.size.height == 18)
              #expect(image.isTemplate == true)
          }
      }
  }
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `cd macos/AIUsageMonitor && swift test --filter StatusMenuImageRendererTests`
  Expected: FAIL (or compilation succeeds but the test fails because `isTemplate` is currently `false` in `StatusMenuImageRenderer.swift`).

- [ ] **Step 3: Modify implementation (set isTemplate = true)**
  Edit `macos/AIUsageMonitor/Sources/AIUsageMonitorApp/StatusMenuImageRenderer.swift` at lines 105-108:
  
  ```swift
  private static func drawIconOnly() -> NSImage {
      let size = NSSize(width: 18, height: 18)
      let image = NSImage(size: size)
      image.isTemplate = true // Set to true to make the test pass
  ```

- [ ] **Step 4: Run test to verify it passes**
  Run: `cd macos/AIUsageMonitor && swift test --filter StatusMenuImageRendererTests`
  Expected: PASS

- [ ] **Step 5: Commit**
  Run:
  ```bash
  git add macos/AIUsageMonitor/Tests/AIUsageMonitorAppTests/StatusMenuImageRendererTests.swift macos/AIUsageMonitor/Sources/AIUsageMonitorApp/StatusMenuImageRenderer.swift
  git commit -m "test: add test for icon-only template image and set isTemplate = true"
  ```

---

### Task 2: Implement the Sparkle icon path in StatusMenuImageRenderer.swift

**Files:**
- Modify: `macos/AIUsageMonitor/Sources/AIUsageMonitorApp/StatusMenuImageRenderer.swift:105-139`

- [ ] **Step 1: Write minimal implementation**
  Replace the entire body of `drawIconOnly()` in `StatusMenuImageRenderer.swift` to draw the sparkle icon with an offset of `rect.width * 0.10` and an inset of `1.0`.

  ```swift
  private static func drawIconOnly() -> NSImage {
      let size = NSSize(width: 18, height: 18)
      let image = NSImage(size: size)
      image.isTemplate = true

      image.lockFocus()
      NSGraphicsContext.current?.imageInterpolation = .high

      let rect = NSRect(origin: .zero, size: size).insetBy(dx: 1.0, dy: 1.0)
      let cx = rect.midX
      let cy = rect.midY
      let offset = rect.width * 0.10

      let path = NSBezierPath()
      path.move(to: NSPoint(x: cx, y: rect.maxY))
      
      // Top to Right
      let cpTR = NSPoint(x: cx + offset, y: cy + offset)
      path.curve(to: NSPoint(x: rect.maxX, y: cy), controlPoint1: cpTR, controlPoint2: cpTR)
      
      // Right to Bottom
      let cpRB = NSPoint(x: cx + offset, y: cy - offset)
      path.curve(to: NSPoint(x: cx, y: rect.minY), controlPoint1: cpRB, controlPoint2: cpRB)
      
      // Bottom to Left
      let cpBL = NSPoint(x: cx - offset, y: cy - offset)
      path.curve(to: NSPoint(x: rect.minX, y: cy), controlPoint1: cpBL, controlPoint2: cpBL)
      
      // Left to Top
      let cpLT = NSPoint(x: cx - offset, y: cy + offset)
      path.curve(to: NSPoint(x: cx, y: rect.maxY), controlPoint1: cpLT, controlPoint2: cpLT)
      
      path.close()

      NSColor.black.setFill()
      path.fill()

      image.unlockFocus()
      return image
  }
  ```

- [ ] **Step 2: Run all tests to verify they pass**
  Run: `cd macos/AIUsageMonitor && swift test`
  Expected: PASS

- [ ] **Step 3: Commit**
  Run:
  ```bash
  git add macos/AIUsageMonitor/Sources/AIUsageMonitorApp/StatusMenuImageRenderer.swift
  git commit -m "feat: implement Sparkle icon drawing in drawIconOnly()"
  ```

---

### Task 3: Build & verify the app visually

**Files:** None

- [ ] **Step 1: Build the app bundle**
  Run: `cd macos/AIUsageMonitor && ./Scripts/build-app.sh`
  Expected: Build successfully completes.

- [ ] **Step 2: Launch the built app**
  Run: `open macos/AIUsageMonitor/.build/AIUsageMonitor.app`
  Expected: The app starts and is visible in the macOS menu bar.

- [ ] **Step 3: Switch to icon-only mode**
  In the app menu dropdown, go to **Show in Menu Bar** and deselect all active providers (e.g. *Claude Code*, *Codex*, *Antigravity*).
  Expected: The display collapses to only show the new Sparkle icon in the menu bar.

- [ ] **Step 4: Verify appearance**
  Verify:
  - The icon matches the dark/light appearance of the system.
  - Clicking the icon turns it into highlighted state properly.
  - The icon looks clear and sharp.

- [ ] **Step 5: Commit any adjustments**
  If any adjustments are needed (e.g., insets, dimensions), commit them, then clean up.
