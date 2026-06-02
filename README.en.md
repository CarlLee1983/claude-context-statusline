# claude-context-statusline

[繁體中文](README.md) · **English**

A persistent statusline for [Claude Code](https://docs.anthropic.com/en/docs/claude-code) that shows how much of the current session's context window is in use — see at a glance how much room is left.

```
Opus 4.8 · [████░░░░░░] 39% · 78k/200k
```

- **Model name** (dimmed) · **colored bar** · **used % · used/limit tokens**
- Alert colors: green `<70%`, yellow `70–85%`, red `≥85%`
- Context limit auto-detected: `model.id` containing `1m` → 1,000,000, otherwise 200,000
- Reflects the main session only (filters out subagent / sidechain messages, matching `/context`)
- Pure standard library, single file, zero dependencies; no error ever breaks the statusline

## Requirements

- macOS (uses the built-in `/usr/bin/python3`, nothing to install)
- Claude Code

## Install

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

## Uninstall

```bash
./uninstall.sh
```

## How it works

Each time Claude Code refreshes the statusline it pipes a JSON blob to the statusline command on stdin, containing `model.id` and `transcript_path`. This script:

1. Reads `transcript_path` (JSONL) and scans **from the end backwards** for the first non-sidechain record carrying `message.usage`
2. Used context = `input_tokens + cache_read_input_tokens + cache_creation_input_tokens`
3. Percentage = used ÷ model limit

For efficiency, large transcripts only read the trailing ~2MB; it falls back to a full scan only when nothing is found in the tail (e.g. recent messages are all sidechain).

## Customize

Edit the constants at the top of `~/.claude/hooks/ctx-statusline.py`:

| Constant | Default | Meaning |
|----------|---------|---------|
| `BAR_WIDTH` | `10` | Progress bar width (characters) |
| `WARN_PCT` | `70` | Turn yellow at/above this % |
| `CRIT_PCT` | `85` | Turn red at/above this % |
| `TAIL_BYTES` | `2_000_000` | Trailing bytes read for large transcripts |

Restart a session to apply.

## Development

Pure standard library, no dependencies to install. Run the tests:

```bash
python3 -m unittest discover -s tests -v
```

Manually inspect the output (includes ANSI color codes):

```bash
echo '{"model":{"id":"claude-opus-4-8","display_name":"Opus 4.8"},"transcript_path":"/path/to/transcript.jsonl"}' | ./ctx-statusline.py
```

Contributions welcome — see [CONTRIBUTING.md](CONTRIBUTING.md); changes are tracked in [CHANGELOG.md](CHANGELOG.md).

## License

[MIT](LICENSE)
