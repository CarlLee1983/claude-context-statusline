# Multi-session overview — sessions/

[繁體中文](README.md) · **English**

When you have many Ghostty tabs running AI CLIs at once, this dashboard shows which
sessions are running, waiting for your input, or idle — along with each session's
working directory — in a wide curses TUI.

> **How this differs from the other components**: `ctx-statusline` shows "how much of
> the current session's context window is used"; the native app and SwiftBar plugin show
> "how much of the subscription's 5h / 7d rate limit is left"; `bell` watches
> "completion event → terminal tab marker"; this component (`sessions`) provides a
> **cross-session live status overview** and reads neither usage numbers nor rate limits.

## Architecture

```
[Claude Code hooks]      [Codex notify]        [Antigravity plugin]
  SessionStart             agent-turn-complete    PostToolUse
  UserPromptSubmit               │                Stop
  Notification                   │                  │
  Stop / SessionEnd              │                  │
         │                       ▼                  ▼
         └────────────→  sessions/track.sh  (thin shell, never crashes)
                         │
                         ▼
              ~/.cache/ai-sessions/<id>.json   (override with AI_SESSIONS_DIR)
                         │
                         ▼
              sessions/dashboard.py  (stdlib curses, polls every second)
```

The trigger layer (hook/notify configuration for each CLI) and the display layer
(curses TUI) are fully decoupled.

## Status model

| Event | Status transition |
|-------|-------------------|
| `SessionStart` | creates record → `idle` |
| `UserPromptSubmit` | → `running` (you are waiting for the AI) |
| `Notification` | → `waiting` (AI is waiting for your input) |
| `Stop` | → `idle` |
| `SessionEnd` | deletes record |
| Codex `agent-turn-complete` | → `idle` |
| Antigravity `PostToolUse` | → `running` |
| Antigravity `Stop` | → `idle` |

The TUI sorts: `waiting` (top) → `running` → `idle` (bottom); within each group,
most recently updated first. Sessions not updated for more than 30 minutes are marked
`(stale)`.

## Codex limitation

Codex emits only one notify event (`agent-turn-complete`), so Codex sessions will
always show `idle` + last-done time — they never appear as `running` or `waiting`.

## Antigravity support and limits

Antigravity (`agy`, gemini-cli family) is tracked via a dedicated agy plugin: install
creates `~/.gemini/config/plugins/ai-sessions/` (`plugin.json` + `hooks.json`) routing
`PostToolUse` (working → `running`) and `Stop` (done → `idle`) to `track.sh`.

- **Status granularity**: only `running` / `idle`, **no** `waiting` (agy emits no such event).
- **No create/delete events**: a record is created lazily on the first event and cleaned up
  by the `(stale)` timeout (like Codex).
- **Requirement**: agy plugin hooks support (`~/.gemini/config/plugins/*/hooks.json`).
- **Synchronous hook**: `PostToolUse` is synchronous (`async: false`); each tool call waits for `track.sh` to finish (~30ms).

## Requirements

- macOS, with the system `/usr/bin/python3` (nothing extra to install)
- Claude Code, Codex, and/or Antigravity (at least one)

> tmux is not required (it is part of the phase-2 plan, see below).

## Install

```bash
./sessions/install.sh
```

The installer does three things (each with a backup, additive-only, idempotent):

1. **Claude Code** `~/.claude/settings.json` — adds `sessions/track.sh claude` to
   `hooks.SessionStart`, `hooks.UserPromptSubmit`, `hooks.Stop`, `hooks.Notification`,
   and `hooks.SessionEnd` (command-matching, so re-running is safe; `SessionEnd` cleans
   up the state file when the session ends)
2. **Codex** `~/.codex/config.toml` — sets the top-level `notify` to
   `["/path/to/sessions/notify.sh", "codex"]` (see "Codex notify dispatcher" below)
3. **Antigravity** `~/.gemini/config/plugins/ai-sessions/` — creates a dedicated agy
   plugin (`plugin.json` + `hooks.json`) routing `PostToolUse`→`running` and
   `Stop`→`idle` to `track.sh` (see "Antigravity support and limits" above)

After installing:
- **Reopen a Claude Code session** so the hooks load
- Open the dashboard: `./sessions/dashboard.py`

Override config directories (testing / non-standard paths):

```bash
CLAUDE_CONFIG_DIR=/path/to/claude ./sessions/install.sh
CODEX_HOME=/path/to/codex ./sessions/install.sh
GEMINI_CONFIG_DIR=/path/to/gemini ./sessions/install.sh
AI_SESSIONS_DIR=/path/to/state ./sessions/install.sh
```

## Uninstall

```bash
./sessions/uninstall.sh
```

Removes the five Claude hook entries and the Codex notify setting (both with backups),
and deletes the Antigravity agy plugin directory `~/.gemini/config/plugins/ai-sessions/`.

> **Note**: uninstalling removes the Codex `notify` key entirely — the bell's BEL
> signal will also stop firing. To restore bell-only Codex notifications, run
> `./bell/install.sh` afterwards.

## Codex notify combined dispatcher (option A)

Codex's `config.toml` only has one top-level `notify` slot. If you already have `bell`
installed, that slot is taken by `bell/notify.sh`. The sessions installer replaces it
with `sessions/notify.sh`, which fans out to **both** bell (rings the BEL) and sessions
(writes state).

| Existing situation at install time | Outcome |
|-------------------------------------|---------|
| No `notify` | adds `sessions/notify.sh` |
| `bell/notify.sh` (managed by the bell component) | upgraded to `sessions/notify.sh` (bell behavior preserved) |
| Any other custom `notify` | **skipped** — prompts you to point it at `sessions/notify.sh` manually |

When uninstalling, the Codex `notify` key is **removed entirely** rather than rolled
back to `bell/notify.sh`. To keep Codex bell notifications, run afterwards:

```bash
./bell/install.sh
```

## TUI key bindings

| Key | Action |
|-----|--------|
| `j` / `↓` | move down |
| `k` / `↑` | move up |
| `r` | force immediate refresh |
| `Enter` | jump to the selected session's Ghostty tab (Phase 2, see below) |
| `c` | copy the selected session's working directory path (`pbcopy`) |
| `q` | quit |

The TUI auto-polls the state directory every second; `r` forces an immediate re-read.
Status is **dual-encoded** with an emoji glyph + a shape badge (colorblind-friendly).

## Never-crash guarantee

- **`track.sh`**: any failure (including missing `python3`, bad JSON, or a disk error)
  is silently swallowed and the script exits 0 — state tracking never breaks the host CLI.
- **`dashboard.py`**: wrapped with `curses.wrapper` so any exception restores the terminal
  on exit; `KeyboardInterrupt` is silently absorbed.

## Tests

```bash
python3 -m unittest tests.test_sessions -v
```

Or run the full test suite:

```bash
python3 -m unittest discover -s tests -v
```

Tests cover: event-to-status mapping, `sanitize_id`, `merge_record`,
`write_record` / `delete_record`, Claude hook merge (empty / existing / idempotent),
Codex dispatch merge (no notify / bell-notify upgrade / foreign notify skipped), and
dashboard pure logic (`load_records`, `sort_key`, `format_row`, `is_stale`, `humanize`).

## Phase 2: One-key switch (native Ghostty)

Select a row in the dashboard and press `Enter` to focus the Ghostty tab/window
where that AI session runs. Press `c` to copy the path.

- **Requires** Ghostty 1.3+ (uses its built-in AppleScript dictionary). The first
  switch triggers a macOS Automation permission prompt ("Ghostty wants to control
  Ghostty"); approve it once.
- **Matching**: maps a session to a Ghostty tab by working directory (cwd); when a
  directory has several tabs, a title heuristic prefers the CLI session tab
  (best-effort).
- **Limitation**: no live preview of tab contents (no equivalent command in the
  Ghostty dictionary — a deliberate trade-off).
- **Never crashes**: missing tab, denied permission, or Ghostty not running only
  shows a footer hint; the TUI keeps running.
