# AI Usage — SwiftBar plugin

[繁體中文](README.md) · **English**

A single-file Python plugin for [SwiftBar](https://github.com/swiftbar/SwiftBar) that keeps each
AI CLI's rate-limit headroom (5h / 7d) in the macOS menu bar. It shows the same kind of data as
the [native menu bar app](../macos/AIUsageMonitor/README.en.md) — the difference is only that this
version runs under SwiftBar and ships as one `.py` file.

Three providers are built in:

- **Claude Code** — reads the OAuth token from the Keychain and calls the Anthropic usage
  endpoint for 5h / 7d utilization.
- **Codex** — uses `codex app-server` JSON-RPC (`account/rateLimits/read`) for 5h / 7d.
- **Antigravity** — has no public usage endpoint; reads the local opencode accounts file and, when
  an unexpired rate-limit cooldown is recorded, shows that quota pool at 100% until reset;
  otherwise it reports `ready`.

> **Never crashes, never leaks**: a failing provider is just marked "unavailable" and never breaks
> the others or the overall output; no code path ever prints a token to the menu bar.

## Display

- **Menu bar**: with Pillow available it renders a capsule image (flat tool icon + status corner
  badge + remaining %); otherwise it falls back to plain text (e.g. `AI  CC 61%  Cx 88%`).
- **Dropdown**: one section per tool, listing each window's progress bar, remaining %, countdown to
  reset, and absolute reset time, with a "Refresh now" item at the bottom.
- **Status color (driven by *remaining* headroom, matching the native app's
  `RemainingQuotaPresenter`)**: green (healthy), yellow (remaining ≤ `WARN_REMAINING`), red
  (remaining ≤ `CRIT_REMAINING`). Status is also shape-encoded (yellow triangle / red exclamation)
  for colorblind friendliness.
- **Expiring-unused hint**: when a window has **lots of quota left yet resets soon** (remaining ≥
  `EXPIRING_REMAINING_THRESHOLD` and the reset is ≤ `EXPIRING_WINDOW_FRACTION` of the period away),
  that row turns **indigo** with a `⏳ resets soon` marker, nudging you to spend the quota before it
  resets (most common on the weekly window). The period is parsed from the window label (`5h`/`7d`);
  Antigravity's model-name labels don't parse, so it never triggers. Same logic as the
  [native app](../macos/AIUsageMonitor/README.md).

## Requirements

- [SwiftBar](https://github.com/swiftbar/SwiftBar): `brew install --cask swiftbar`
- `python3` (the system `/usr/bin/python3` is fine)
- **Optional**: [Pillow](https://pypi.org/project/Pillow/) — used to draw the capsule menu-bar
  image; without it the plugin still works in text mode. Install it into *the same `python3` that
  actually runs the plugin*.
- Each provider depends on what you actually use: a logged-in Claude Code, a runnable `codex`, an
  opencode Antigravity accounts file.

## Install

First install and launch SwiftBar (`brew install --cask swiftbar`), choosing a **plugins folder** on first run.

### One-shot install (recommended)

```bash
./swiftbar/install.sh
```

The script reads SwiftBar's configured plugin folder from its preferences → **symlinks** the plugin
in (so a later `git pull` updates it) → `chmod +x` → asks SwiftBar to refresh. If the folder can't be
read, it falls back to `~/.config/swiftbar` and tells you to point SwiftBar's Plugin Folder there.

Override the folder, or copy instead of symlink:

```bash
./swiftbar/install.sh /path/to/plugins          # positional arg
SWIFTBAR_PLUGIN_DIR=/path ./swiftbar/install.sh # same, via env var
SWIFTBAR_INSTALL_COPY=1 ./swiftbar/install.sh   # copy instead of symlink (sharing to a machine without this repo)
```

### Manual install

```bash
ln -s "$PWD/swiftbar/ai-usage.60s.py" ~/.config/swiftbar/ai-usage.60s.py
chmod +x swiftbar/ai-usage.60s.py
```

Then click **Refresh All** in the SwiftBar menu (or restart SwiftBar).

> The `60s` in the filename is SwiftBar's refresh-interval convention (re-run every 60 seconds).
> Rename to change it, e.g. `ai-usage.5m.py`. Actual endpoint calls are throttled separately (see
> caching below), so a fast refresh interval won't hammer them.

## Caching & throttling

To avoid hitting endpoints on every refresh (and getting 429'd), each provider uses a two-stage
cache under `~/.cache/ai-usage/`:

- **Throttle**: if the last attempt was under `FETCH_TTL` (300s default) ago, it serves the cache
  and touches neither the network nor any subprocess.
- **Backoff with last-good**: on a failed fetch it reuses the *last successful value* tagged
  "N min ago" instead of showing "—".

## Customize

Edit the constants at the top of the plugin:

| Constant | Default | Meaning |
|----------|---------|---------|
| `WARN_REMAINING` | `40` | Turn yellow when remaining headroom ≤ this |
| `CRIT_REMAINING` | `10` | Turn red when remaining headroom ≤ this |
| `BAR_WIDTH` | `10` | Dropdown progress-bar cells |
| `FETCH_TTL` | `300` | Minimum re-fetch interval per source (seconds) |
| `CACHE_DIR` | `~/.cache/ai-usage` | Cache directory |
| `TZ_OFFSET_HOURS` | `8` | Timezone for absolute reset times (default Asia/Taipei, UTC+8) |

## Adding a provider

The plugin is intentionally extensible: each tool is a provider function returning a "normalized"
record (`name` / `short` / `icon` / `ok` / `five_hour` / `seven_day`, etc.). To add a tool, write a
function of the same shape and append it to the `PROVIDERS` list at the bottom of the file.

## Troubleshooting

- **Menu bar shows text only, no capsule image**: Pillow isn't found. Install Pillow into the
  `python3` that actually runs the plugin (check the shebang with `head -1`, or confirm in SwiftBar
  settings), or just accept text mode.
- **Codex shows "unavailable"**: SwiftBar's PATH is minimal; the plugin already tries Homebrew,
  nvm/Volta/Herd node paths, and the login shell to locate `codex`. If it still can't be found,
  confirm `codex` runs from your terminal.
- **Claude shows "unavailable"**: confirm you're logged into Claude Code (the Keychain holds
  `Claude Code-credentials`) and can reach `api.anthropic.com`.
- **Shows "N min ago"**: the plugin is reusing the last successful value (current fetch failed or is
  still within the `FETCH_TTL` throttle window) — this is normal backoff behavior.
