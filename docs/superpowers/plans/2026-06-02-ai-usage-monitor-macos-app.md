# AI Usage Monitor macOS App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local-only native macOS menu bar app MVP that displays Claude, Codex, and Antigravity usage without relying on SwiftBar.

**Architecture:** Create a Swift Package executable using SwiftUI `MenuBarExtra`. Keep provider parsing and shell execution separate from UI so provider logic is unit-testable; first MVP uses a fixture/demo data provider in the app plus tested parsers for Codex JSON-RPC and Antigravity `/usage` output.

**Tech Stack:** Swift 6.2, Swift Package Manager, SwiftUI/AppKit on macOS 14+.

---

## File Structure

- Create `macos/AIUsageMonitor/Package.swift`: Swift package manifest for app executable and tests.
- Create `macos/AIUsageMonitor/Sources/AIUsageMonitorCore/UsageModels.swift`: shared models and color/label semantics.
- Create `macos/AIUsageMonitor/Sources/AIUsageMonitorCore/AntigravityUsageParser.swift`: parse `agy /usage` TUI text into available quota windows.
- Create `macos/AIUsageMonitor/Sources/AIUsageMonitorCore/CodexRateLimitParser.swift`: parse Codex app-server `rateLimits` JSON.
- Create `macos/AIUsageMonitor/Sources/AIUsageMonitorCore/UsageSnapshotProvider.swift`: async provider protocol plus demo provider.
- Create `macos/AIUsageMonitor/Sources/AIUsageMonitorApp/AIUsageMonitorApp.swift`: SwiftUI menu bar app entrypoint.
- Create `macos/AIUsageMonitor/Sources/AIUsageMonitorApp/UsageMenuView.swift`: dropdown rows and refresh button.
- Create `macos/AIUsageMonitor/Tests/AIUsageMonitorCoreTests/AntigravityUsageParserTests.swift`: TDD parser tests.
- Create `macos/AIUsageMonitor/Tests/AIUsageMonitorCoreTests/CodexRateLimitParserTests.swift`: TDD parser tests.

## Task 1: Core Models and Antigravity Parser

- [ ] Write failing parser tests for `agy /usage` text retaining available semantics.
- [ ] Run `swift test --filter AntigravityUsageParserTests` and confirm compile/test failure.
- [ ] Add minimal `UsageWindow`, `UsageSnapshot`, `QuotaKind`, and `AntigravityUsageParser` implementation.
- [ ] Run the parser test and confirm pass.

## Task 2: Codex Parser

- [ ] Write failing JSON parser tests for Codex primary/secondary rate limits.
- [ ] Run `swift test --filter CodexRateLimitParserTests` and confirm failure.
- [ ] Add minimal `CodexRateLimitParser` implementation.
- [ ] Run parser tests and confirm pass.

## Task 3: Menu Bar App MVP

- [ ] Add SwiftUI executable target with `MenuBarExtra`.
- [ ] Add `DemoUsageSnapshotProvider` for first local UI MVP.
- [ ] Add compact label and dropdown rows with bars, percent, used/available labels, reset text.
- [ ] Build with `swift build`.
- [ ] Run full `swift test`.

## Task 4: Local Launch Documentation

- [ ] Add concise run instructions to a macOS app README.
- [ ] Verify commands work from package directory.

## Self-Review

- Spec coverage: local-only native menu bar app MVP is covered by executable target, SwiftUI menu, demo provider, and parser foundations.
- Placeholder scan: no implementation placeholders are required for MVP; production provider subprocess integration is intentionally deferred after app shell compiles.
- Type consistency: parser tasks share `UsageWindow` and `QuotaKind` from core models.
