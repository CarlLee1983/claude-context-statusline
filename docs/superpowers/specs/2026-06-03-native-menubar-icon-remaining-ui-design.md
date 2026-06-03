# Native Menu Bar Icon + Remaining UI Design

Date: 2026-06-03
Status: approved for implementation planning

## Goal

Optimize the native macOS menu bar UI for the AI usage monitor so it is compact, visually polished, and consistent with real product identity cues. The menu bar should stop showing raw provider abbreviations such as `CC`, `CX`, and `AG`, and should instead show provider icons plus a remaining-quota number.

## User-approved direction

Use the `icon + number chip` style from the visual companion mockups.

Example display semantics:

- Claude Code used 3% -> menu bar shows `97`
- Codex used 1% -> menu bar shows `99`
- Antigravity available 100% -> menu bar shows `100`

The number in the menu bar is always remaining quota, rounded to an integer and displayed without a percent sign to keep the status item compact. The tooltip and dropdown menu provide the full meaning.

## Research-backed icon rules

### Claude Code

Use a Spark-style icon. Claude Code documentation states that the Spark icon indicates Claude Code in VS Code. The implementation should render a compact Spark mark in the Claude/Anthropic orange family.

Source: `https://code.claude.com/docs/en/vs-code`

### Codex

No separate official Codex-specific small icon was confirmed from official OpenAI Codex pages. Use OpenAI mark language carefully and keep it monochrome/unaltered in spirit. Avoid inventing a new Codex brand mark or recoloring official OpenAI assets in a way that implies an official logo variation.

Source: `https://openai.com/brand/`

### Antigravity

Use the official Antigravity icon asset exposed by the official site.

Source: `https://antigravity.google/assets/image/antigravity-logo.png`

## Menu bar behavior

The native menu bar status item should render a retina-safe image instead of plain text when rendering succeeds.

Each provider is displayed as a subtle soft chip:

- provider icon on the left
- remaining quota integer on the right
- no provider abbreviation text
- no percent sign in the menu bar
- stable spacing and tabular numeric rendering

Fallback behavior:

- If image rendering fails, fall back to a text title.
- The text fallback should still use remaining quota semantics, e.g. `Claude 97 Codex 99 Antigravity 100` or a similarly readable compact fallback.
- The status item must never render empty because an image could not be created.

## Remaining quota calculation

Add a presentation-level remaining value derived from each usage window:

- For `.used`: `remaining = 100 - percent`
- For `.available`: `remaining = percent`
- Clamp result to `0...100`
- Round for menu bar display

Do not change core parser semantics. Existing parser/model `percent` values continue to represent the source data according to `QuotaKind`; the new remaining number is a UI projection.

## Dropdown behavior

The dropdown menu should preserve detailed provider context:

- provider full name
- plan, when available
- window label
- remaining percent
- original source semantic (`used` or `available`)
- reset time, when available
- unavailable / no-data states

Example row copy:

- `5h: 97% remaining · used 3% · reset 14:30`
- `Gemini 3.5 Flash: 100% remaining · available`

## Architecture

Keep UI rendering separate from provider parsing:

- Add a small AppKit presentation layer for status item rendering.
- Keep provider snapshots and parser logic in `AIUsageMonitorCore` unchanged unless a tiny presentation helper belongs there and is covered by tests.
- Prefer a renderer object/function that accepts `[ProviderSnapshot]` and returns either an `NSImage` plus accessibility summary or a fallback string.

Suggested components:

- `RemainingQuotaPresenter`: pure logic for remaining values and text summaries.
- `StatusMenuImageRenderer`: AppKit drawing for chips/icons/text.
- `StatusMenuController`: owns `NSStatusItem`, calls renderer, and preserves menu rebuild behavior.

## Testing strategy

Use test-first implementation.

Minimum tests:

1. Remaining calculation
   - `.used` 3 -> `97`
   - `.used` 100 -> `0`
   - `.available` 75 -> `75`
   - out-of-range inputs remain clamped through existing model behavior

2. Summary/fallback string
   - provider abbreviations are not used in the primary summary if full names are available
   - summary uses remaining values, not raw used values

3. Dropdown row copy
   - used windows show both remaining and used semantics
   - available windows show remaining and available semantics

4. Renderer smoke test where practical
   - non-empty image/fallback result for non-empty snapshots
   - non-empty fallback for empty/unavailable snapshots

## Non-goals

- Do not build a new official logo or claim a custom mark is official.
- Do not alter provider parsers solely for display.
- Do not add new third-party dependencies.
- Do not replace the dropdown with a custom SwiftUI popover in this iteration.
- Do not implement rate-limit fetching changes as part of this UI pass.

## Open risks

- Official icon asset usage may have trademark constraints. The local personal menu bar app can reference service identities, but the implementation should avoid presenting the app as official or endorsed.
- Antigravity remote asset should not be fetched at runtime for reliability. Prefer embedding a small local representation or rendering a simplified local shape based on the official asset after confirming repository policy.
- Pixel-perfect validation of a macOS menu bar item is limited in automated tests; manual visual verification will still be required after build.
