# Completion bell — bell/

[繁體中文](README.md) · **English**

When an AI CLI finishes a turn, this component sends a terminal BEL (`\a`) that causes
[Ghostty](https://ghostty.org/) to mark the tab or window as needing attention.
Switch to another app while you wait for the AI; the Ghostty Dock icon bounces when
it's done, and the tab title shows 🔔 when you return.

> **How this differs from the other components**: `ctx-statusline` shows "how much of
> the current session's context window is used"; the native app and SwiftBar plugin show
> "how much of the subscription's 5h / 7d rate limit is left"; this component (`bell`)
> watches **completion events → terminal tab marker** and reads no usage numbers at all.

## Architecture

```
[AI CLI finishes a turn]
         │  Stop hook / notify
         ▼
  bell/notify.sh  ──── printf '\a' ──→  /dev/tty  ──→  [Ghostty receives BEL]
  (trigger layer)                                         (display layer)
                                                    marks tab 🔔 / bounces Dock
```

The two layers are decoupled: the trigger layer (each CLI's hook or notify) and the
display layer (Ghostty config) are independent. When a future Ghostty release fixes
the tab-marker regression, the trigger layer needs **no changes at all**.

## Requirements

- macOS, with the system `/usr/bin/python3` (nothing extra to install)
- [Ghostty](https://ghostty.org/)
- Whichever AI CLIs you actually use: Claude Code, Codex

## Install

```bash
./bell/install.sh
```

The installer does three things (each with a backup, additive-only, idempotent):

1. **Claude Code** `~/.claude/settings.json` — adds `bell/notify.sh claude` to `hooks.Stop`
2. **Codex** `~/.codex/config.toml` — prepends `notify = ["/path/to/claude-context-statusline/bell/notify.sh", "codex"]`
   (the installer resolves and writes the **absolute path** to `notify.sh`, so it keeps
   working regardless of CWD; if a `notify` key already exists at the top level, it skips
   and prompts you to point it at this script manually)
3. **Ghostty** `~/.config/ghostty/config` (XDG location) — appends `bell-features = title,attention`
   (if `bell-features` is already defined, it **skips and does not overwrite** your hand-set
   value; if `~/Library/Application Support/com.mitchellh.ghostty/config` also sets
   `bell-features`, it **warns but does not touch** that file)

After installing:
- **Reopen a Claude Code session** so the Stop hook loads
- **Reload Ghostty config**: `Cmd+Shift+,` or restart Ghostty

Override config directories (testing / non-standard paths):

```bash
CLAUDE_CONFIG_DIR=/path/to/claude ./bell/install.sh
CODEX_HOME=/path/to/codex ./bell/install.sh
XDG_CONFIG_HOME=/path/to/xdg ./bell/install.sh
```

## Uninstall

```bash
./bell/uninstall.sh
```

Removes what the installer added (identified by a marker comment), backs up each file
first, and skips any side that was not previously modified.

## Ghostty configuration

After install, the Ghostty config gains:

```
bell-features = title,attention
```

- `title` — shows 🔔 in the tab title
- `attention` — bounces the Dock icon when Ghostty is not focused (**reliable fallback**)
- Listing only these two items → **silent, purely visual** (does not inherit any
  `audio` or `system` behavior that might be in the defaults)

**Known limitation (Ghostty 1.3.1, 2026-06)**: on macOS, `title` has a regression —
the 🔔 on a background tab only appears once you click back to it, which is exactly the
"switched away while waiting" use case. For now, `attention` (Dock bounce) is the most
reliable signal. Ghostty 1.4 (expected 2026-09) fixes this regression, after which the
tab 🔔 will update immediately — **no change to this config is needed**.

## CLI trigger points

| CLI | Mechanism | Notes |
|-----|-----------|-------|
| **Claude Code** | `hooks.Stop` — fires after every turn | sends BEL unconditionally |
| **Codex** | `config.toml` `notify` — filters for `agent-turn-complete` | if a `notify` key already exists, manual integration is needed |
| **Antigravity** | **Not yet supported** | pending investigation of whether it exposes a completion event or hook |

## Never-crash guarantee

`notify.sh` follows the repo-wide "never break the host CLI" invariant:

- A failure to write to `/dev/tty` (no controlling terminal, redirected output) is
  silently swallowed and the script exits 0
- Pure `/bin/sh`, zero dependencies — no environmental surprise can cause it to error
- `BELL_TTY` overrides the output target (for testing):
  `BELL_TTY=/tmp/fake-tty ./bell/notify.sh claude`

## Tests

```bash
python3 -m unittest tests.test_bell -v
```

Or run the full test suite:

```bash
python3 -m unittest discover -s tests -v
```

Tests cover: `notify.sh` source filtering, Claude settings merge (empty / existing /
idempotent / bad JSON), Codex line-scan (existing notify / no notify / prepend position /
permissions), and Ghostty config merge.
