# claude-context-statusline

[繁體中文](README.md) · **English**

A small toolkit for keeping **AI CLI usage visible, turn completion noticed, and
multi-session status at a glance** on macOS.
It started as a Claude Code context statusline and grew into a native menu bar app that keeps
subscription **rate-limit headroom** visible in the macOS menu bar,
a completion bell that rings the terminal BEL at turn-end to trigger a Ghostty tab marker,
and a cross-session dashboard that shows the live status of every AI CLI session at once.

## Four tools

| Tool | Where it shows | What it watches | Dependencies | Install |
|------|----------------|-----------------|--------------|---------|
| [**ctx-statusline**](#1-context-statusline-ctx-statuslinepy) | Claude Code statusline | Current session's **context window** usage | System `python3`, zero deps | `brew install CarlLee1983/tap/ctx-statusline` (or `./install.sh`) |
| [**AI Usage Monitor (native app)**](macos/AIUsageMonitor/README.en.md) | macOS menu bar | Claude Code + Codex + Antigravity **rate limits** (5h / 7d headroom) | Swift 6 / macOS 14+ | `brew install CarlLee1983/tap/ai-usage-monitor` (or `./Scripts/install-app.sh`) |
| [**Completion bell (`bell/`)**](bell/README.en.md) | Ghostty tab / Dock | **Completion event → terminal tab marker** (BEL) | System `python3`, Ghostty | `./bell/install.sh` |
| [**Session dashboard (`sessions/`)**](sessions/README.en.md) | Terminal curses TUI | **Cross-session live status** (running / waiting / idle) | System `python3` | `./sessions/install.sh` |

> Each component watches different data: **ctx-statusline** shows "how much of a single
> session's context window is used"; the **native app** shows "how
> much of the subscription's 5-hour / 7-day rate limit is left"; **bell** watches
> "when an AI CLI finishes a turn → terminal tab marker" and reads no usage numbers;
> **sessions** watches "the current execution status of all AI CLI sessions" and reads
> neither usage numbers nor rate limits.

---

## Install with Homebrew (recommended)

```bash
brew tap CarlLee1983/tap
brew install ctx-statusline ai-usage-monitor
```

Run each tool's one-time setup afterwards (install never touches your config files):

```bash
ctx-statusline-setup     # merge into ~/.claude/settings.json, then restart Claude Code
ai-usage-monitor         # first run installs the app to ~/Applications and launches it
```

Each formula can be installed independently.

---

## 1. Context statusline (`ctx-statusline.py`)

A persistent statusline for [Claude Code](https://docs.anthropic.com/en/docs/claude-code) that shows how much of the current session's context window is in use — see at a glance how much room is left.

```
Opus 4.8 · [████░░░░░░] 39% · 78k/200k
```

- **Model name** (dimmed) · **colored bar** · **used % · used/limit tokens**
- Alert colors: green `<70%`, yellow `70–85%`, red `≥85%`
- Context limit auto-detected: `model.id` containing `1m` → 1,000,000, otherwise 200,000
- Reflects the main session only (filters out subagent / sidechain messages, matching `/context`)
- Pure standard library, single file, zero dependencies; no error ever breaks the statusline

### Requirements

- macOS (uses the built-in `/usr/bin/python3`, nothing to install)
- Claude Code

### Install

```bash
git clone https://github.com/CarlLee1983/claude-context-statusline.git
cd claude-context-statusline
./install.sh
```

The installer:

1. Copies `ctx-statusline.py` into `~/.claude/hooks/`
2. Merges a `statusLine` block into `~/.claude/settings.json` (backs up to `settings.json.bak.*` first, preserving your other settings)

Then **open a new Claude Code session** to see the statusline.

> If your Claude Code config is not in `~/.claude`, point at it with `CLAUDE_CONFIG_DIR`:
> `CLAUDE_CONFIG_DIR=/path/to/config ./install.sh`

### Uninstall

```bash
./uninstall.sh
```

### How it works

Each time Claude Code refreshes the statusline it pipes a JSON blob to the statusline command on stdin, containing `model.id` and `transcript_path`. This script:

1. Reads `transcript_path` (JSONL) and scans **from the end backwards** for the first non-sidechain record carrying `message.usage`
2. Used context = `input_tokens + cache_read_input_tokens + cache_creation_input_tokens`
3. Percentage = used ÷ model limit (`1m` / Fable 5 use 1,000,000; others default to 200,000)

For efficiency, large transcripts only read the trailing ~2MB; it falls back to a full scan only when nothing is found in the tail (e.g. recent messages are all sidechain).

### Customize

Edit the constants at the top of `~/.claude/hooks/ctx-statusline.py`:

| Constant | Default | Meaning |
|----------|---------|---------|
| `BAR_WIDTH` | `10` | Progress bar width (characters) |
| `WARN_PCT` | `70` | Turn yellow at/above this % |
| `CRIT_PCT` | `85` | Turn red at/above this % |
| `TAIL_BYTES` | `2_000_000` | Trailing bytes read for large transcripts |

Restart a session to apply.

---

## 2. Native menu bar app (`macos/AIUsageMonitor`)

A pure-Swift macOS menu bar app that natively fetches live Claude Code, Codex and Antigravity rate
limits (5h / 7d), shows remaining headroom in the menu bar, and auto-refreshes every 5 minutes. No
Python runtime dependency, and no signing or notarization needed for local development.

For full build, architecture, and troubleshooting notes see **[macos/AIUsageMonitor/README.en.md](macos/AIUsageMonitor/README.en.md)**.

```bash
cd macos/AIUsageMonitor
./Scripts/install-app.sh          # build + install into /Applications, then launch
```

Then click the menu bar icon → check **Launch at Login** to start at login (native `SMAppService`).

---

## 3. Completion bell (`bell/`)

When an AI CLI finishes a turn, a terminal BEL causes Ghostty to mark the tab or window as
needing attention — the Dock icon bounces while you wait in another app, and the tab title
shows 🔔 when you return. Supports Claude Code (Stop hook) and Codex (notify). Silent,
purely visual, zero extra dependencies.

For full install and architecture see **[bell/README.en.md](bell/README.en.md)**.

```bash
./bell/install.sh
```

---

## 4. Session dashboard (`sessions/`)

When you have many Ghostty tabs running AI CLIs at once, a curses TUI shows the live
status of every session (running / waiting / idle) along with each session's working
directory. Tracks session state across three AI CLIs: Claude Code, Codex, and Antigravity.
Pure standard library — reads neither usage numbers nor rate limits.

For full install and architecture see **[sessions/README.en.md](sessions/README.en.md)**.

> On Ghostty, press `Enter` in the dashboard to jump straight to a session's tab
> (Phase 2, native AppleScript).

```bash
./sessions/install.sh
./sessions/dashboard.py   # open the TUI
```

---

## Development

ctx-statusline is pure standard-library Python with nothing to install. Run the tests:

```bash
python3 -m unittest discover -s tests -v
```

Manually inspect ctx-statusline output (includes ANSI color codes):

```bash
echo '{"model":{"id":"claude-opus-4-8","display_name":"Opus 4.8"},"transcript_path":"/path/to/transcript.jsonl"}' | ./ctx-statusline.py
```

Test the native app:

```bash
cd macos/AIUsageMonitor && swift test
```

Contributions welcome — see [CONTRIBUTING.md](CONTRIBUTING.md); changes are tracked in [CHANGELOG.md](CHANGELOG.md).

## License

[MIT](LICENSE)
