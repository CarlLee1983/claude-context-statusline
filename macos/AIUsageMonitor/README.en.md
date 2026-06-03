# AI Usage Monitor (native menu bar app)

[繁體中文](README.md) · **English**

A pure-Swift macOS menu bar app that natively fetches live AI CLI usage, runs locally, and needs no
Python runtime. It shows the same kind of "rate-limit headroom" data as the
[SwiftBar plugin](../../swiftbar/README.en.md) — the difference is this is a standalone native app
that lives in the menu bar through AppKit `NSStatusItem`.

## Run

For reliable menu bar visibility, build and open the local `.app` bundle:

```bash
cd macos/AIUsageMonitor
./Scripts/build-app.sh
open .build/AIUsageMonitor.app
```

To debug the executable directly:

```bash
swift run AIUsageMonitorApp
```

The app runs as an accessory (`LSUIElement`) menu bar app — no Dock icon — and needs no signing or
notarization for local development.

## Install & launch at login

The bundle in `.build/` is wiped on every rebuild, so it's a poor persistent target. For regular use, build and install into `/Applications`:

```bash
cd macos/AIUsageMonitor
./Scripts/install-app.sh
```

The script: builds → quits any running instance → copies to `/Applications/AIUsageMonitor.app` → opens it.
Override the install location (e.g. if you can't write to `/Applications`):

```bash
APP_INSTALL_DIR="$HOME/Applications" ./Scripts/install-app.sh
```

**Launch at login**: click the menu bar icon → check **Launch at Login**. This registers a login item
via the native `SMAppService` API (it also appears in System Settings → General → Login Items, where you
can toggle it). Installing to `/Applications` first gives a stable path so the registration sticks.

## Current coverage

- **Live Claude Code usage**: Keychain OAuth token → Anthropic usage endpoint, 5h / 7d windows.
- **Live Codex usage**: `codex app-server` JSON-RPC rate limits, 5h / 7d windows.
- **Live Antigravity usage**: drives `agy /usage` over a pseudo-TTY for per-model available quota;
  falls back to the local `~/.config/opencode/antigravity-accounts.json` cooldown / ready state when
  that can't be captured. Mirrors the [SwiftBar plugin](../../swiftbar/README.en.md) approach.
- **Native AppKit menu bar UI**: 5-minute auto-refresh plus a manual Refresh action.

## Architecture

```
Sources/
├── AIUsageMonitorApp/          # Executable target (AppKit shell)
│   ├── AIUsageMonitorApp.swift        # App entry point
│   ├── StatusMenuController.swift     # NSStatusItem, menu, refresh, Launch at Login
│   ├── StatusMenuImageRenderer.swift  # Menu bar image (remaining % + status badge)
│   ├── ClaudeLogo.swift               # Official Claude brand starburst (SVG path, same as SwiftBar)
│   └── AntigravityLogo.swift          # Official Antigravity brand logo (base64, same as SwiftBar)
└── AIUsageMonitorCore/         # Pure logic library (unit-testable)
    ├── UsageModels.swift              # Normalized usage data models
    ├── UsageSnapshotProvider.swift    # Provider protocol
    ├── LiveUsageSnapshotProvider.swift# Aggregates providers into a live snapshot
    ├── ClaudeUsageProvider.swift      # Claude: Keychain token → usage endpoint
    ├── ClaudeUsageParser.swift        # Parses the Anthropic usage response
    ├── CodexUsageProvider.swift       # Codex: app-server JSON-RPC
    ├── CodexExecutableResolver.swift  # Locates the codex executable on a minimal PATH
    ├── CodexRateLimitParser.swift     # Parses the Codex rate-limit response
    ├── AntigravityUsageProvider.swift # Antigravity: agy /usage first, accounts cooldown fallback
    ├── AntigravityUsageTextCapture.swift # PTY-drives agy /usage for panel text (thin I/O boundary)
    ├── AntigravityUsageParser.swift   # Parses the agy /usage panel (strip ANSI → available windows)
    ├── AntigravityAccountsParser.swift # Parses the accounts-file cooldown (pure)
    ├── SVGPathParser.swift            # Parses SVG path data (brand starburst → segments, pure)
    └── RemainingQuotaPresenter.swift  # Turns remaining headroom into display text + status tier
```

All testable logic lives in `AIUsageMonitorCore`; the AppKit shell (`AIUsageMonitorApp`) only does
UI and scheduling. Status tiers are computed from **remaining** headroom (not used amount),
consistent with the SwiftBar plugin.

## Tests

```bash
cd macos/AIUsageMonitor
swift test
```

Tests live in `Tests/AIUsageMonitorCoreTests/` and cover the parsers, Codex executable resolution,
and `RemainingQuotaPresenter`.

## Troubleshooting

- **No menu bar icon**: make sure you launched the `.app` bundle (the `build-app.sh` output includes
  `LSUIElement`); a bare `swift run` can be flaky for menu bar visibility.
- **No Claude data**: confirm you're logged into Claude Code (the Keychain holds
  `Claude Code-credentials`) and can reach `api.anthropic.com`.
- **No Codex data**: confirm `codex` runs from your terminal; the app tries common install paths to
  locate the executable.

## Requirements

- macOS 14+
- Swift 6 toolchain (Xcode or a Swift toolchain)
