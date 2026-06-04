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
[Claude Code hooks]        [Codex notify]
  SessionStart               agent-turn-complete
  UserPromptSubmit                │
  Notification                    │
  Stop / SessionEnd               │
         │                        ▼
         └──────→  sessions/track.sh  (thin shell, never crashes)
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

The TUI sorts: `waiting` (top) → `running` → `idle` (bottom); within each group,
most recently updated first. Sessions not updated for more than 30 minutes are marked
`(stale)`.

## Codex limitation

Codex emits only one notify event (`agent-turn-complete`), so Codex sessions will
always show `idle` + last-done time — they never appear as `running` or `waiting`.

## Requirements

- macOS, with the system `/usr/bin/python3` (nothing extra to install)
- Claude Code and/or Codex

> tmux is not required (it is part of the phase-2 plan, see below).

## Install

```bash
./sessions/install.sh
```

The installer does two things (each with a backup, additive-only, idempotent):

1. **Claude Code** `~/.claude/settings.json` — adds `sessions/track.sh claude` to
   `hooks.SessionStart`, `hooks.UserPromptSubmit`, `hooks.Stop`, and `hooks.Notification`
   (command-matching, so re-running is safe)
2. **Codex** `~/.codex/config.toml` — sets the top-level `notify` to
   `["/path/to/sessions/notify.sh", "codex"]` (see "Codex notify dispatcher" below)

After installing:
- **Reopen a Claude Code session** so the hooks load
- Open the dashboard: `./sessions/dashboard.py`

Override config directories (testing / non-standard paths):

```bash
CLAUDE_CONFIG_DIR=/path/to/claude ./sessions/install.sh
CODEX_HOME=/path/to/codex ./sessions/install.sh
AI_SESSIONS_DIR=/path/to/state ./sessions/install.sh
```

## Uninstall

```bash
./sessions/uninstall.sh
```

Removes the four Claude hook entries and the Codex notify setting (both with backups).

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
| `Enter` | copy the selected session's working directory path (`pbcopy`) |
| `q` | quit |

The TUI auto-polls the state directory every second; `r` forces an immediate re-read.
Status is encoded with **color + emoji + shape glyph** (colorblind-friendly).

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

## Phase 2 (future, not yet implemented)

The current release is **phase 1** (read-only status tracking). The planned **phase 2**
(triggered by `$TMUX` detection) will add, in a tmux environment:

- `select-window` to jump directly to a session's tab
- `capture-pane` to show a preview of recent output
- tmux ↔ Ghostty BEL passthrough

The status semantics (hook → state) are identical across both phases; phase 2 only
adds functionality at the display and navigation layers.
