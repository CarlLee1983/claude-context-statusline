#!/usr/bin/env python3
"""Claude Code 狀態列：顯示目前 session 的 context window 佔用程度。

Claude Code statusline: show how much of the current session's context
window is in use.

從 stdin 讀取 Claude Code 傳入的 statusline JSON：context 上限與已用量優先採
`context_window`（`context_window_size`、`current_usage`、`used_percentage`），
缺少時才退回 model id 啟發式與 transcript（JSONL）最後一筆 usage；算出已用
context 佔上限的百分比，輸出「模型膠囊 + 平滑進度條」。若有 `rate_limits`，再附加
`5h 11% 2h41m │ 7d 14% 3d4h`（百分比與距離重置的倒數）。

Reads the statusline JSON Claude Code pipes in on stdin. The context limit and
used tokens prefer `context_window` (`context_window_size`, `current_usage`,
`used_percentage`), falling back to the model-id heuristic and the last usage
record in the transcript (JSONL). It computes how much of the limit is used and
prints a model pill plus a smooth progress bar, followed by the `rate_limits`
segment (`5h 11% 2h41m │ 7d 14% 3d4h`: percent and countdown to reset) when present.

設計上絕不拋例外中斷 statusline：任何錯誤都退回 0% 顯示。
By design this never raises out to the statusline: any error falls back to
a 0% display.
"""
import json
import os
import sys
import time
from typing import Optional

DIM = "\033[2m"
BOLD = "\033[1m"
UNBOLD = "\033[22m"  # 只關粗體、不 reset，底色得以延續 / bold off only, keeps background
RESET = "\033[0m"

# 調色盤（RGB）。COLORTERM 非 truecolor/24bit 時自動換成最接近的 xterm-256 索引。
# Palette (RGB). Mapped to the nearest xterm-256 index unless COLORTERM is
# truecolor/24bit.
OK_RGB = (120, 200, 120)
WARN_RGB = (230, 190, 80)
CRIT_RGB = (235, 95, 95)
TRACK_RGB = (70, 70, 80)    # 進度條空白軌道 / empty bar track
INK_RGB = (20, 20, 24)      # 模型膠囊上的字色 / text on the model pill
FABLE_RGB = (178, 132, 255)
OPUS_RGB = (232, 141, 103)
SONNET_RGB = (98, 160, 234)
HAIKU_RGB = (94, 196, 160)
CYAN_BRIGHT_RGB = (80, 220, 230)  # 額度即將釋放（倒數強調）/ quota about to free up
CYAN_SOFT_RGB = (120, 170, 180)   # 額度接近釋放 / quota nearly freed
TARGET_RGB = (150, 170, 255)      # 今日目標上限（未達）/ today's target, not yet reached
NEUTRAL_RGB = (150, 150, 160)  # 未知模型家族 / unknown model family
MODEL_FAMILIES = (
    ("fable", FABLE_RGB),
    ("opus", OPUS_RGB),
    ("sonnet", SONNET_RGB),
    ("haiku", HAIKU_RGB),
)

BAR_WIDTH = 12
PARTIAL_BLOCKS = "▏▎▍▌▋▊▉"  # 1/8 .. 7/8
TRACK_CHAR = "─"
SEPARATOR = " │ "
# 以 code point 計的上限；上游 effort 是 ASCII 列舉（low/medium/high/xhigh/max），不處理顯示寬度。
# Cap in code points; upstream effort values are an ASCII enum
# (low/medium/high/xhigh/max), so display width is not handled.
MAX_EFFORT_CHARS = 12
# 倒數強調門檻（秒）：視窗用量 >= WARN_PCT 且剩餘時間 < SOON 用亮青粗體，< NEAR 用柔青。
# Countdown highlight thresholds (seconds): when a window's usage >= WARN_PCT,
# time left < SOON is bright cyan bold, < NEAR is soft cyan, else dim. Strict `<`
# (all thresholds are multiples of 60) so each displayed minute maps to one color.
RELEASE_SOON_5H = 30 * 60
RELEASE_NEAR_5H = 60 * 60
RELEASE_SOON_7D = 6 * 3600
RELEASE_NEAR_7D = 24 * 3600
MAX_MODEL_CHARS = 40
MAX_COUNTDOWN_SECONDS = 366 * 86400  # 超過視為無效 / beyond this is treated as invalid
WARN_PCT = 70   # >= 此值轉黃 / turn yellow at/above this
CRIT_PCT = 85   # >= 此值轉紅 / turn red at/above this

# transcript 可能很大；只讀尾端這麼多 bytes 找最後一筆 usage。
# Transcripts can be large; only read this many trailing bytes to find the
# most recent usage record. Falls back to a full scan if nothing is found.
TAIL_BYTES = 2_000_000

DEFAULT_LIMIT = 200_000
MILLION_LIMIT = 1_000_000


def context_limit(model_id: Optional[str]) -> int:
    """依 model id 判斷 context 上限；含 1m 或 Fable 5 視為百萬窗。

    Pick the context limit from the model id; ids containing ``1m`` or Fable 5
    map to the 1,000,000-token window, otherwise the default 200,000.
    """
    normalized = (model_id or "").lower().replace("_", "-")
    if "1m" in normalized or "fable-5" in normalized or "fable 5" in normalized:
        return MILLION_LIMIT
    return DEFAULT_LIMIT


def _usage_tokens(obj: dict) -> int:
    """從單筆記錄取出已用 context tokens；非主 session 或無 usage 回傳 0。

    Extract used context tokens from one record; returns 0 for non-main-session
    records (sidechain/subagent) or records without usage.
    """
    # 跳過 subagent（sidechain）訊息，只反映主 session 的 context（與 /context 一致）
    # Skip subagent (sidechain) messages so we mirror the main session only.
    if obj.get("isSidechain"):
        return 0
    message = obj.get("message")
    if not isinstance(message, dict):
        return 0
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return 0
    return (
        _int_or_zero(usage.get("input_tokens"))
        + _int_or_zero(usage.get("cache_read_input_tokens"))
        + _int_or_zero(usage.get("cache_creation_input_tokens"))
    )


def _scan_lines(lines) -> int:
    """從尾端往前找第一筆含 usage 的主 session 記錄。

    Scan from the end for the first main-session record carrying usage.
    """
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        total = _usage_tokens(obj)
        if total > 0:
            return total
    return 0


def _read_lines(path: str) -> list:
    """讀 transcript 行；先試尾端 TAIL_BYTES，必要時退回整檔。

    Read transcript lines: try the trailing TAIL_BYTES first, falling back to
    the whole file when the file is larger than the tail window.
    """
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        if size > TAIL_BYTES:
            f.seek(size - TAIL_BYTES)
            f.readline()  # 丟掉可能被切半的第一行 / drop the partial first line
        data = f.read()
    return data.decode("utf-8", errors="replace").splitlines()


def used_tokens(transcript_path: Optional[str]) -> int:
    """回傳目前主 session 已用的 context tokens。

    Return the context tokens currently used by the main session.
    """
    if not transcript_path or not os.path.isfile(transcript_path):
        return 0
    try:
        size = os.path.getsize(transcript_path)
        lines = _read_lines(transcript_path)
    except OSError:
        return 0

    total = _scan_lines(lines)
    # 尾端找不到，且檔案曾被截斷，整檔再掃一次（涵蓋「近期全是 sidechain」的情況）
    # Nothing in the tail and the file was truncated: rescan the whole file
    # (covers the "recent records are all sidechain" case).
    if total == 0 and size > TAIL_BYTES:
        try:
            with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
                total = _scan_lines(f.readlines())
        except OSError:
            return 0
    return total


def humanize(n: int) -> str:
    """把 token 數縮寫成人類可讀（72000 -> 72k、1000000 -> 1m）。

    Abbreviate a token count for humans (72000 -> 72k, 1000000 -> 1m).
    """
    if n >= 1_000_000:
        v = n / 1_000_000
        return "{}m".format(int(v) if v == int(v) else round(v, 1))
    if n >= 1_000:
        return "{}k".format(round(n / 1_000))
    return str(n)


def _is_number(v) -> bool:
    """是否為真正的數字（排除 bool、NaN、inf）。

    True for real numbers (bool, NaN and inf excluded).
    """
    return (
        isinstance(v, (int, float))
        and not isinstance(v, bool)
        and v == v
        and v not in (float("inf"), float("-inf"))
    )


def resolve_limit(context_window, model_id: Optional[str]) -> int:
    """優先用 payload 的 context_window_size（正整數），否則退回 model id 啟發式。

    Prefer the payload's context_window_size (positive int); otherwise fall
    back to the model-id heuristic.
    """
    if isinstance(context_window, dict):
        size = context_window.get("context_window_size")
        if isinstance(size, int) and not isinstance(size, bool) and size > 0:
            return size
    return context_limit(model_id)


def _int_or_zero(v) -> int:
    """非 bool 的 int 取 max(0, v)，其餘（含負數）算 0。

    Non-bool ints as max(0, v); anything else counts as 0.
    """
    return max(0, v) if isinstance(v, int) and not isinstance(v, bool) else 0


def _clamp_used(value, limit: int) -> int:
    """把已用量夾在 0..limit；溢位時正值視為 limit，負值與 NaN 視為 0。

    Clamp used tokens into 0..limit; on overflow positives count as limit,
    negatives and NaN as 0.
    """
    try:
        return max(0, min(limit, round(value)))
    except (OverflowError, ValueError):
        return limit if value > 0 else 0


def resolve_used(context_window, transcript_path: Optional[str], limit: int) -> int:
    """已用 tokens：current_usage > used_percentage > transcript 掃描。

    Used tokens: payload current_usage, else used_percentage * limit, else a
    transcript scan.
    """
    cw = context_window if isinstance(context_window, dict) else {}
    usage = cw.get("current_usage")
    if isinstance(usage, dict):
        return _clamp_used(
            _int_or_zero(usage.get("input_tokens"))
            + _int_or_zero(usage.get("cache_read_input_tokens"))
            + _int_or_zero(usage.get("cache_creation_input_tokens")),
            limit,
        )
    pct = cw.get("used_percentage")
    if _is_number(pct):
        try:
            return _clamp_used(pct * limit / 100, limit)
        except (OverflowError, ValueError):
            return limit if pct > 0 else 0
    return _clamp_used(used_tokens(transcript_path), limit)


def _truecolor() -> bool:
    return os.environ.get("COLORTERM", "").lower() in ("truecolor", "24bit")


_CUBE_LEVELS = (0, 95, 135, 175, 215, 255)


def nearest_256(rgb) -> int:
    """回傳最接近 rgb 的 xterm-256 索引（6x6x6 色立方或灰階斜坡）。

    Return the xterm-256 index nearest to rgb (6x6x6 cube or grayscale ramp).
    """
    idx = [min(range(6), key=lambda i: abs(_CUBE_LEVELS[i] - c)) for c in rgb]
    cube = tuple(_CUBE_LEVELS[i] for i in idx)
    cube_index = 16 + 36 * idx[0] + 6 * idx[1] + idx[2]
    gray_step = max(0, min(23, round((sum(rgb) / 3 - 8) / 10)))
    gray = (8 + 10 * gray_step,) * 3

    def dist(c):
        return sum((a - b) ** 2 for a, b in zip(rgb, c))

    return 232 + gray_step if dist(gray) < dist(cube) else cube_index


def _sgr(base: int, rgb) -> str:
    if _truecolor():
        return "\033[{};2;{};{};{}m".format(base, *rgb)
    return "\033[{};5;{}m".format(base, nearest_256(rgb))


def fg(rgb) -> str:
    """前景色 SGR / foreground SGR."""
    return _sgr(38, rgb)


def bg(rgb) -> str:
    """背景色 SGR / background SGR."""
    return _sgr(48, rgb)


def _level_rgb(pct):
    if pct >= CRIT_PCT:
        return CRIT_RGB
    if pct >= WARN_PCT:
        return WARN_RGB
    return OK_RGB


def _sanitize(text: str, max_chars: int) -> str:
    """去掉不可列印字元（ESC、C1、bidi 控制、孤立 surrogate），截斷並去除前後空白。

    Drop non-printable characters (ESC, C1, bidi controls, lone surrogates),
    then strip and cap the text so it can neither inject terminal escapes nor
    crash the final write.
    """
    cleaned = "".join(ch for ch in text.strip() if ch.isprintable()).strip()
    return cleaned[:max_chars].rstrip()


def effort_level(effort) -> str:
    """取出 effort.level 字串（原樣顯示）；型別不符或為空回傳空字串。

    Extract ``effort.level`` as given; "" for wrong types or empty values.
    """
    if not isinstance(effort, dict):
        return ""
    level = effort.get("level")
    return _sanitize(level, MAX_EFFORT_CHARS) if isinstance(level, str) else ""


def model_pill(model_id: str, model_name: str, effort: str = "") -> str:
    """模型膠囊：家族色底、近黑字，名稱粗體，其後可接 ` · effort`；沒有名稱就不畫。

    Model pill: family-colored background, near-black text with a bold name,
    optionally followed by ` · effort` in normal weight (bold turned off with
    SGR 22 so the background persists); empty when there is no model name.
    Family comes from the id or the display name.
    """
    if not model_name:
        return ""
    haystack = "{} {}".format(model_id, model_name).lower()
    rgb = next((c for key, c in MODEL_FAMILIES if key in haystack), NEUTRAL_RGB)
    tail = "{} \u00b7 {}".format(UNBOLD, effort) if effort else ""
    return "{}{}{} {}{} {}".format(bg(rgb), fg(INK_RGB), BOLD, model_name, tail, RESET)


def context_bar(pct: int) -> str:
    """BAR_WIDTH 格、八分之一格平滑的進度條；已填色依門檻，其餘為暗軌道。

    BAR_WIDTH cells with eighth-block smoothing; filled part uses the level
    color, the remainder is a dim track.
    """
    eighths = max(0, min(BAR_WIDTH * 8, round(pct * BAR_WIDTH * 8 / 100)))
    full, part = divmod(eighths, 8)
    filled = "█" * full + (PARTIAL_BLOCKS[part - 1] if part else "")
    track = TRACK_CHAR * (BAR_WIDTH - len(filled))
    return "{}{}{}{}{}".format(fg(_level_rgb(pct)), filled, fg(TRACK_RGB), track, RESET)


def _remaining_seconds(resets_at, now: float) -> Optional[float]:
    """距離重置的秒數；過去、無效或超過上限回傳 None。

    Seconds until reset; None when in the past, invalid or beyond the cap.
    """
    if not _is_number(resets_at):
        return None
    try:
        remaining = resets_at - now
    except OverflowError:  # 極大的 int 減 float / huge int minus float
        return None
    if not remaining > 0 or remaining > MAX_COUNTDOWN_SECONDS:
        return None
    return remaining


def _format_remaining(remaining: float) -> str:
    """把剩餘秒數（> 0）格式化成 `12m` / `2h41m` / `3d4h` / `5d`。

    Format remaining seconds (> 0) as `12m` / `2h41m` / `3d4h` / `5d`.
    """
    minutes = max(1, int(remaining // 60))
    if minutes < 60:
        return "{}m".format(minutes)
    hours, mins = divmod(minutes, 60)
    if hours < 24:
        return "{}h{:02d}m".format(hours, mins)
    days, hours = divmod(hours, 24)
    return "{}d{}h".format(days, hours) if hours else "{}d".format(days)


def format_countdown(resets_at, now: float) -> str:
    """距離重置的倒數：`12m` / `2h41m` / `3d4h` / `5d`；過去或無效回傳空字串。

    Countdown to reset: `12m` / `2h41m` / `3d4h` / `5d`; "" when the time is
    in the past or invalid.
    """
    remaining = _remaining_seconds(resets_at, now)
    return "" if remaining is None else _format_remaining(remaining)


def _countdown_style(pct: int, remaining: float, soon: int, near: int) -> str:
    """倒數文字的樣式：用量達 WARN_PCT 才依剩餘時間上青色，否則維持暗色。

    Countdown style: only when usage >= WARN_PCT is it tinted by time left;
    otherwise it stays dim.
    """
    if pct >= WARN_PCT:
        if remaining < soon:
            return fg(CYAN_BRIGHT_RGB) + BOLD
        if remaining < near:
            return fg(CYAN_SOFT_RGB)
    return DIM


def weekly_target(remaining: float) -> int:
    """今天結束前的 7d 用量目標（%）：每多一整天，目標少 100/7。

    The 7d usage target (%) for today: 100/7 lower for every full day left
    after today. Rounded half up and clamped to 0..100; under a day left → 100.
    """
    full_days = int(remaining // 86400)
    return max(0, min(100, int(100 - 100 / 7 * full_days + 0.5)))


def _target_text(pct: int, remaining: float) -> str:
    """` →73%`：用量未達目標為淡藍紫，已達（今日額度用完）改粗體警示黃。

    ` →73%`: periwinkle while under target, bold warn color once today's
    budget is spent.
    """
    target = weekly_target(remaining)
    style = fg(WARN_RGB) + BOLD if pct >= target else fg(TARGET_RGB)
    return " {}\u2192{}%{}".format(style, target, RESET)


def _rate_window(window, label: str, now: float, soon: int, near: int,
                 daily: bool = False) -> str:
    """單一速率限制視窗的片段；used_percentage 非數字則回傳空字串。

    One rate-limit window segment; "" unless used_percentage is a number.
    ``daily`` appends the "today's target" (7d window only).
    """
    if not isinstance(window, dict) or not _is_number(window.get("used_percentage")):
        return ""
    try:
        pct = max(0, min(100, round(window["used_percentage"])))
    except (OverflowError, ValueError):
        pct = 100 if window["used_percentage"] > 0 else 0
    text = "{}{}{} {}{}%{}".format(DIM, label, RESET, fg(_level_rgb(pct)), pct, RESET)
    remaining = _remaining_seconds(window.get("resets_at"), now)
    if remaining is not None:
        style = _countdown_style(pct, remaining, soon, near)
        text += " {}{}{}".format(style, _format_remaining(remaining), RESET)
        if daily:
            text += _target_text(pct, remaining)
    return text


def render_rate_limits(rate_limits, now: Optional[float] = None) -> str:
    """組出 `5h 11% 2h41m │ 7d 14% 3d4h →17%`；沒有任何視窗時回傳空字串。

    Build `5h 11% 2h41m │ 7d 14% 3d4h →17%`; "" when no window is usable.
    ``now`` (unix seconds) is injectable for tests.
    """
    if not isinstance(rate_limits, dict):
        return ""
    if now is None:
        now = time.time()
    parts = [
        _rate_window(rate_limits.get("five_hour"), "5h", now,
                     RELEASE_SOON_5H, RELEASE_NEAR_5H),
        _rate_window(rate_limits.get("seven_day"), "7d", now,
                     RELEASE_SOON_7D, RELEASE_NEAR_7D, daily=True),
    ]
    return (DIM + SEPARATOR + RESET).join(p for p in parts if p)


def render(pct: int, used: int, limit: int, model_name: str, extra: str = "",
           model_id: str = "", effort: str = "") -> str:
    """組出狀態列：模型膠囊 + 平滑進度條 + 百分比 + token 數 + 額度片段。

    Build the statusline: model pill + smooth bar + percent + tokens + the
    optional rate-limit segment.
    """
    pill = model_pill(model_id, model_name, effort)
    line = "{}{} {}{}%{} {}{}/{}{}".format(
        pill + " " if pill else "", context_bar(pct),
        fg(_level_rgb(pct)), pct, RESET, DIM, humanize(used), humanize(limit), RESET,
    )
    if extra:
        line += DIM + SEPARATOR + RESET + extra
    return line


def guard_line() -> str:
    """最外層防線的簡單純文字輸出 / simple plain output for the outer guard."""
    return TRACK_CHAR * BAR_WIDTH + " 0%"


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}

    model = data.get("model")
    model = model if isinstance(model, dict) else {}
    model_id = model.get("id", "")
    model_id = _sanitize(model_id, MAX_MODEL_CHARS) if isinstance(model_id, str) else ""
    model_name = model.get("display_name")
    model_name = _sanitize(model_name, MAX_MODEL_CHARS) if isinstance(model_name, str) else ""
    model_name = model_name or model_id
    transcript = data.get("transcript_path", "")
    transcript = transcript if isinstance(transcript, str) else ""

    context_window = data.get("context_window")
    limit = resolve_limit(context_window, model_id)
    used = resolve_used(context_window, transcript, limit)
    pct = min(100, round(used * 100 / limit)) if limit else 0
    extra = render_rate_limits(data.get("rate_limits"))

    sys.stdout.write(render(pct, used, limit, model_name, extra, model_id,
                       effort_level(data.get("effort"))))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # 最後防線：任何未預期錯誤都不該讓 statusline 變紅噴錯
        # Last resort: no unexpected error should make the statusline error out.
        sys.stdout.write(guard_line())
