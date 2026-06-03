# AI Usage Monitor

Local-only native macOS menu bar app MVP for AI CLI usage status.

## Run

For reliable menu bar visibility, build and open the local `.app` bundle:

```bash
cd macos/AIUsageMonitor
./Scripts/build-app.sh
open .build/AIUsageMonitor.app
```

For debugging the executable directly:

```bash
swift run AIUsageMonitorApp
```

This MVP fetches live Claude and Codex usage natively (no Python runtime dependency). It runs as an accessory menu bar app through AppKit `NSStatusItem` and does not require signing or notarization for local development.

## Current coverage

- Live Claude Code usage (Keychain OAuth token → Anthropic usage endpoint), 5h / 7d windows.
- Live Codex usage (`codex app-server` JSON-RPC rate limits), 5h / 7d windows.
- Native AppKit menu bar UI with 5-minute auto-refresh plus a manual Refresh action.
- Antigravity is temporarily removed and will return in a later round.
