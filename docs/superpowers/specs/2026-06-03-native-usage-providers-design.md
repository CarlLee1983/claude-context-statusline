# Native Usage Providers Design (Claude + Codex)

**Date:** 2026-06-03
**Status:** Approved
**Topic:** Replace the menu bar app's demo data with real Claude + Codex usage via native Swift.

## Problem

The native macOS menu bar app (`macos/AIUsageMonitor`) currently renders hardcoded
values from `DemoUsageSnapshotProvider` (e.g. Claude 93 / Codex 99). The numbers in the
menu bar are therefore wrong. The production data layer was intentionally deferred when the
app shell was built; this design adds it.

The working reference implementation already exists in Python:
`swiftbar/ai-usage.60s.py` and `experiments/usage-probe.py` fetch real usage for Claude and
Codex. This design ports that fetching logic to native Swift so the app has no runtime
Python dependency.

## Decisions

- **Approach:** Full native Swift (no shelling out to Python at runtime).
- **Scope this round:** Claude + Codex only. Antigravity is removed from the menu bar for
  now and will be added in a later round.
- **Refresh cadence:** Automatic refresh every 5 minutes, plus the existing manual
  "立即刷新 / Refresh" menu action. No on-disk cache/backoff is ported — the 5-minute timer
  is sufficient throttling.

## Architecture Principle

Follow the repository's existing pattern: **pure parsing core + thin I/O boundary.**

- Network, subprocess, and Keychain access live in thin boundary code that is NOT unit
  tested.
- All data parsing is extracted into pure functions that ARE unit tested (TDD).
- Claude and Codex are fetched concurrently. Either provider failing only marks that one
  provider unavailable; it never crashes the app or pollutes the status line.

## New Files (`Sources/AIUsageMonitorCore`)

### 1. `ClaudeUsageProvider.swift`

Boundary:
- `Process` runs `/usr/bin/security find-generic-password -s "Claude Code-credentials" -w`
  to read the OAuth credentials JSON, extracting `claudeAiOauth.accessToken`.
  **The token is never logged and never rendered.**
- `URLSession` performs `GET https://api.anthropic.com/api/oauth/usage` with headers
  `Authorization: Bearer <token>` and `anthropic-beta: oauth-2025-04-20`.

Pure function (tested):
- `parseClaudeUsage(_ data: Data) -> [UsageWindow]` — decodes `five_hour` and `seven_day`
  nodes, reading `utilization` (percent) and `resets_at` (ISO 8601). Produces `.used`
  semantics windows labelled `5h` and `7d`. Missing/invalid nodes are skipped safely;
  malformed input returns an empty array.

Provider output: a `ProviderSnapshot` named "Claude Code" (shortName "CC"). When parsing
yields no windows or the boundary fails, the snapshot is `isAvailable: false`.

### 2. `CodexUsageProvider.swift`

Boundary:
- `Process` runs `codex app-server`. Writes JSON-RPC `initialize` then
  `account/rateLimits/read` to stdin, reads stdout lines until the message with `id == 2`
  carrying a `result`, then terminates the subprocess. A timeout bounds the wait.
- **Node path resolution** (ported from the Python `_resolve`): `codex` is a
  `#!/usr/bin/env node` script, so the directory containing the resolved `codex` binary is
  prepended to the subprocess `PATH`. Resolution order: `PATH` → fixed dirs
  (`/opt/homebrew/bin`, `/usr/local/bin`, `/usr/bin`, `/bin`) → nvm / Herd / volta /
  `.local/bin` globs (newest version) → login shell `command -v`.

Parsing:
- Reuses the existing, already-tested `CodexRateLimitParser`. The JSON-RPC `result` is fed
  to the parser, producing `.used` windows (`5h` from `primary`, `7d` from `secondary`) and
  the `planType`.

Provider output: a `ProviderSnapshot` named "Codex" (shortName "Cx"), `plan` = planType.
Failure → `isAvailable: false`.

The node-path resolution logic is extracted into a small testable unit (e.g.
`CodexExecutableResolver` with a pure selection function over candidate paths) so the
"newest version wins" ordering can be unit tested without touching the filesystem.

### 3. `LiveUsageSnapshotProvider.swift`

- Conforms to `UsageSnapshotProviding`.
- `async let` runs Claude and Codex concurrently, returns `[ProviderSnapshot]` in a stable
  order (Claude, then Codex).
- A failed provider returns an `isAvailable: false` snapshot (the menu shows "無法取得"),
  rather than being dropped, so the user can tell the provider exists but the fetch failed.
- `DemoUsageSnapshotProvider` is retained for tests and previews.

## Modified Files (`Sources/AIUsageMonitorApp`)

### `AIUsageMonitorApp.swift`
- Swap `DemoUsageSnapshotProvider()` for `LiveUsageSnapshotProvider()`.

### `StatusMenuController.swift`
- Add a repeating 5-minute refresh: a `Timer.scheduledTimer` (interval 300s) on the main
  run loop that fires `Task { await refresh() }`. The existing manual Refresh action is
  kept. The timer is invalidated on quit.
- Antigravity no longer appears because the live provider list contains only Claude and
  Codex. The demo Antigravity entry is left in `DemoUsageSnapshotProvider` untouched but
  unused at runtime.

## Error Handling / Never-Crash Invariant

- Every provider wraps all boundary work in `do/catch` (or `try?`) and returns an
  unavailable snapshot on any failure (missing binary, Keychain miss, network error,
  timeout, malformed JSON).
- `StatusMenuImageRenderer` and the menu already handle empty/unavailable snapshots and
  fall back to the "AI" text title.
- The OAuth token is only ever held in memory and passed to `URLSession`; it is never
  written to logs, the menu, or the status line.

## Testing (TDD)

- `ClaudeUsageProviderTests`: feed a realistic usage JSON fixture → assert 5h/7d percents,
  reset dates, and `.used` semantics; assert empty/malformed JSON yields an empty window
  list (safe fallback).
- Codex JSON parsing is already covered by `CodexRateLimitParserTests`.
- `CodexExecutableResolverTests`: assert the candidate-selection function picks the newest
  versioned path and respects ordering, using injected candidate lists (no filesystem).
- Boundary code (`Process`, `URLSession`, Keychain) stays thin and is not unit tested.

## Out of Scope (YAGNI)

- No port of the Python on-disk cache / backoff (the 5-minute timer is enough throttling).
- No Antigravity PTY integration this round.
- No signing/notarization changes; local development bundle only.

## Self-Review

- Placeholder scan: no TBD/TODO; every new file has a defined responsibility and interface.
- Internal consistency: parsing is pure + tested, I/O is thin + untested, matching the
  stated architecture principle and the existing repo pattern.
- Scope: focused on one implementation plan (two providers + composition + timer wiring).
- Ambiguity: failed providers are explicitly shown as unavailable (not hidden); refresh is
  explicitly 300s; Antigravity is explicitly removed (not shown unavailable).
