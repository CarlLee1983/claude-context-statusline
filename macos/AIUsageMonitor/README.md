# AI Usage Monitor

Local-only native macOS menu bar app MVP for AI CLI usage status.

## Run

```bash
cd macos/AIUsageMonitor
swift run AIUsageMonitorApp
```

This first MVP uses demo provider data while the parser/provider foundation is built and tested. It runs as an accessory menu bar app through AppKit `NSStatusItem` and does not require signing or notarization for local development.

## Current coverage

- Antigravity `agy /usage` text parser for available model quota.
- Codex rate-limit JSON parser for 5-hour and 7-day usage windows.
- Native AppKit menu bar UI scaffold with refresh and quit actions.
