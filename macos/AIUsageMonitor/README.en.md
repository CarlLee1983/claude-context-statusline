# AI Usage Monitor (native menu bar app)

[繁體中文](README.md) · **English**

A pure-Swift macOS menu bar app that natively fetches live AI CLI usage, runs locally, and needs no
Python runtime. It shows subscription-plan "rate-limit headroom" data and lives in the menu bar
through AppKit `NSStatusItem`.

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
  that can't be captured.
- **Native AppKit menu bar UI**: 5-minute auto-refresh plus a manual Refresh action.
- **Menu bar and query settings**: **Show in Menu Bar** chooses which providers stay in the menu bar
  summary; when all are unchecked, the app keeps one AI icon and still opens the details menu.
  **Query Usage** chooses which providers are actually queried; unchecked providers are skipped on
  refresh.

> **The refresh interval is 5 minutes.** The `StatusMenuController.refreshInterval` constant controls
> the real cadence of calls to the usage endpoints. The data is a 5h / 7d rate-limit window — 5
> minutes is only ~1.7% of the 5h window, granular enough while avoiding the endpoints' own 429
> throttling. Use the menu's "Refresh" for an instant number; change the constant to adjust the
> cadence.

## Architecture

```
Sources/
├── AIUsageMonitorApp/          # Executable target (AppKit shell)
│   ├── AIUsageMonitorApp.swift        # App entry point
│   ├── StatusMenuController.swift     # NSStatusItem, menu, refresh, Launch at Login
│   ├── StatusMenuImageRenderer.swift  # Menu bar image (remaining % + status badge)
│   ├── UsageMonitorSettingsStore.swift # UserDefaults settings storage
│   ├── ClaudeLogo.swift               # Official Claude brand starburst (SVG path)
│   └── AntigravityLogo.swift          # Official Antigravity brand logo (base64)
└── AIUsageMonitorCore/         # Pure logic library (unit-testable)
    ├── UsageModels.swift              # Normalized usage data models
    ├── UsageSnapshotProvider.swift    # Provider protocol
    ├── UsageMonitorSettings.swift     # Provider display/query settings model
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
UI and scheduling. Status tiers are computed from **remaining** headroom (not used amount).

## Display behavior: the expiring-unused hint

Beyond the "low remaining → yellow/red" severity tier, when a window has **lots of quota left yet
resets soon** (subscription quota refills to full at reset, so anything unused is wasted), that
progress bar switches to **indigo with a diagonal-stripe texture** and the `% remaining` text turns
indigo too — nudging you to spend the quota before it resets. The weekly (7d) window hits this most
often. The stripe is a color-blind-friendly second cue, not color alone.

Trigger (`RemainingQuotaPresenter.isExpiringUnused`, a pure, unit-tested function): the window label
must parse to a fixed period (`5h` / `7d`), remaining must be **≥ 40%**, and the reset must be **≤
15% of the period away** (5h → <45 min, 7d → <~25 h). Antigravity is a shared cooldown pool with
model-name labels, so its period is unparseable and it never triggers by design.

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
