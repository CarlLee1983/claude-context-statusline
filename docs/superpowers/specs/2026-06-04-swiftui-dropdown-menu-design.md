# SwiftUI Dropdown Menu Design

Date: 2026-06-04
Status: approved by user, ready for planning

## Goal

Replace the plain-text macOS status bar dropdown menu with a custom SwiftUI view embedded via `NSHostingView`. This addresses the lack of design sense and improves the overall UX by introducing scannable progress bars, accurate brand logos, and a clean, grouped layout.

## User-Approved UI & Layout Direction

The dropdown will be a single custom SwiftUI view presented inside an `NSMenuItem` at the top of the menu, followed by a standard native separator and native system control items at the bottom.

### 1. General Panel Style
- **Width**: `320pt` to `340pt` (fixed/minimum width).
- **Background**: Native macOS translucent menu background (automatic in `NSMenu`).
- **Typography**: Native System font (`SF Pro`), utilizing proper hierarchies and weights (`.headline`, `.subheadline`, `.caption`).
- **Theme Support**: Out-of-the-box light/dark mode adaptation using native semantic colors (`Color.primary`, `Color.secondary`, `Color(nsColor: .separator)`).

### 2. Provider Card Layout
Each AI provider (Claude Code, Codex, Antigravity) will have its own visually isolated card element:
- **Header**:
  - Brand Logo (horizontal alignment, 18x18 size).
  - Provider name (`Claude Code`, `Codex`, `Antigravity`) in bold (`.font(.system(size: 13, weight: .semibold))`).
  - Plan/Subtitle if available (e.g. `plus`, `agy /usage`).
  - Refresh indicator / timestamp on the right side.
- **Usage Windows / Limits**:
  - A horizontal progress bar reflecting the remaining quota percentage (`remaining = 100 - percent` for used; `remaining = percent` for available).
  - Progress bar colors adapt to remaining status tiers (defined in `RemainingQuotaPresenter`):
    - **Green** (good): `remaining > 40%`
    - **Yellow** (warn): `10% < remaining <= 40%`
    - **Red** (critical): `remaining <= 10%`
  - Labels showing the window details (e.g., `5h window: 19% remaining`, `used 81%`, `resets 17:30`).

### 3. Antigravity Model List Grouping
Antigravity CLI reports usage metrics for multiple Gemini/Claude models. To prevent menu clutter:
- **Active / Cooldown Models**: Models with an active cooldown (quota < 100%) are shown as individual compact progress bar rows.
- **Redundant Entries**: Hide redundant "Refreshes in 1m" items (embed cooldown details directly in the model row).
- **100% Available Models**: Models with 100% quota are grouped into a single, clean text summary at the bottom of the card (e.g., `+ 6 other models available with 100% quota`).

---

## Brand Logo Specifications

To match the actual brand identities, we will implement the following icons in SwiftUI:

1. **Claude Code**:
   - **Icon**: Official Anthropic spark/starburst path from `ClaudeLogo.svgPath`.
   - **Color**: Brand Orange (`#D9734F`).
   - **Implementation**: SwiftUI `Shape` built from parsed SVG path coordinates.
2. **OpenAI / Codex**:
   - **Icon**: A custom procedural 6-petal spiral shape representing the OpenAI blossom logo.
   - **Color**: Brand Green (`#19C37D`).
   - **Implementation**: 6 overlapping curved petals rotated by 60 degrees.
3. **Antigravity**:
   - **Icon**: Official Antigravity arch mark from `AntigravityLogo.base64`.
   - **Implementation**: Decoded `NSImage` loaded directly into SwiftUI `Image`.
4. **Google Gemini (under Antigravity)**:
   - **Icon**: Official four-pointed star sparkle.
   - **Color**: Filled with the official Gemini linear gradient (`#9bc5ff` to `#e1a1ff` to `#ffcfb4`).

---

## Architectural Implementation Plan

### 1. `StatusMenuController` Updates
- Rebuild `rebuildMenu()` to:
  - Create a single host menu item: `let customItem = NSMenuItem()`.
  - Instantiate `StatusMenuView(snapshots: snapshots)`.
  - Wrap the SwiftUI view in `NSHostingView(rootView: view)`.
  - Assign the hosting view to `customItem.view`.
  - Append the custom item, a separator, and native items (`Launch at Login`, `Refresh`, `Quit`) to the `NSMenu`.

### 2. New SwiftUI Views (in `AIUsageMonitorApp` target)
- **`StatusMenuView`**: Main container displaying the list of snapshots.
- **`ProviderCardView`**: Renders a card for a single `ProviderSnapshot`.
- **`ProgressBarView`**: Renders a custom colored progress bar.
- **`BrandIconView`**: Factory view returning the correct vector/image logo based on the provider or model name.

---

## Testing & Verification Strategy

1. **Compilation**:
   - Verify the Swift package compiles cleanly after adding SwiftUI components.
2. **Manual Visual Inspection**:
   - Run the updated menu bar app and verify dark/light mode appearance, hover states, and list sizing.
3. **Unit Tests**:
   - Ensure existing logic in `AIUsageMonitorCore` remains 100% untouched and passing.
