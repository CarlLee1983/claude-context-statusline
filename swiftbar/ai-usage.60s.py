#!/usr/bin/env python3
# <xbar.title>AI Usage</xbar.title>
# <xbar.version>v0.1</xbar.version>
# <xbar.author>carl</xbar.author>
# <xbar.desc>選單列常駐顯示 Claude Code 與 Codex 的 5h / 週用量。</xbar.desc>
# <xbar.dependencies>python3</xbar.dependencies>
# <swiftbar.runInBash>false</swiftbar.runInBash>
"""SwiftBar plugin:選單列顯示各 AI CLI 的速率限制用量。

設計成可擴充:每個工具是一個 provider 函式,回傳「正規化」紀錄;
要新增工具(Gemini、其他)只要再寫一個函式並加進 PROVIDERS。

永不崩潰:任何 provider 失敗只標記 ok=False,不影響其他工具與整體輸出。
絕不印出 token。
"""

import glob
import json
import os
import pty
import re
import select
import shutil
import signal
import subprocess
import termios
import time
import fcntl
import struct
from datetime import datetime, timezone, timedelta

# ---- 可調參數 ----
WARN_PCT = 70.0   # 轉黃
CRIT_PCT = 90.0   # 轉紅
BAR_WIDTH = 10    # 下拉選單進度條格數
FETCH_TTL = 300   # 每個來源最短重抓間隔(秒);中間用快取,避開端點自身限流(429)
CACHE_DIR = os.path.expanduser("~/.cache/ai-usage")
TZ_OFFSET_HOURS = 8  # 顯示 reset 絕對時間用的時區(Asia/Taipei = UTC+8)

KEYCHAIN_SERVICE = "Claude Code-credentials"
CLAUDE_USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
OAUTH_BETA = "oauth-2025-04-20"
ANTIGRAVITY_ACCOUNTS_PATH = os.path.expanduser(
    "~/.config/opencode/antigravity-accounts.json"
)

_LOCAL_TZ = timezone(timedelta(hours=TZ_OFFSET_HOURS))


# ---------- 共用工具 ----------

def _resolve(cmd):
    """在 SwiftBar 受限 PATH 下找出可執行檔絕對路徑。

    依序:PATH -> 固定目錄 -> nvm/Herd/volta 等 node 版本目錄(取最新版)
    -> 登入 shell。node 版本管理器的路徑是版本化的,所以用 glob 撈。
    """
    found = shutil.which(cmd)
    if found:
        return found
    for d in ("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin"):
        p = os.path.join(d, cmd)
        if os.path.exists(p):
            return p
    home = os.path.expanduser("~")
    patterns = [
        f"{home}/.nvm/versions/node/*/bin/{cmd}",
        f"{home}/Library/Application Support/Herd/config/nvm/versions/node/*/bin/{cmd}",
        f"{home}/.volta/bin/{cmd}",
        f"{home}/.local/bin/{cmd}",
    ]
    hits = [m for pat in patterns for m in glob.glob(pat) if os.path.exists(m)]
    if hits:
        return sorted(hits)[-1]  # 版本字串排序,取最新
    # 最後手段:問使用者的登入 shell
    try:
        out = subprocess.run(["/bin/zsh", "-lc", f"command -v {cmd}"],
                             capture_output=True, text=True, timeout=6).stdout.strip()
        return out or None
    except Exception:
        return None


def _rel(epoch):
    """剩餘時間 -> 3h12m(顯示時即時換算,故存絕對時間戳)。"""
    secs = int(epoch - datetime.now(timezone.utc).timestamp())
    if secs <= 0:
        return "now"
    h, m = secs // 3600, (secs % 3600) // 60
    return f"{h}h{m:02d}m" if h else f"{m}m"


def _clock(epoch, now=None):
    """reset 絕對時間 -> 本地時間;非當日才補上日期(對齊原生 menu app:
    當天只顯示 19:30,跨日才顯示 06/02 19:30,避免單一時間造成誤解)。"""
    dt = datetime.fromtimestamp(epoch, tz=_LOCAL_TZ)
    today = (now or datetime.now(_LOCAL_TZ)).astimezone(_LOCAL_TZ).date()
    if dt.date() == today:
        return dt.strftime("%H:%M")
    return dt.strftime("%m/%d %H:%M")


def _window(pct, reset_dt):
    """window 只存 pct 與絕對 reset 時間戳;rel/at 留待顯示時算,避免快取造成 countdown 卡住。"""
    return {"pct": float(pct), "reset": reset_dt.timestamp()}


def _windows(rec):
    """回傳 provider 要顯示的視窗清單。

    Claude/Codex 使用固定 5h/7d；Antigravity 只有本機記錄到 rate-limit
    cooldown 時才有 provider-specific 視窗（Claude/Gemini）。
    """
    if rec.get("windows") is not None:
        return rec.get("windows") or []
    out = []
    for label, key in (("5h", "five_hour"), ("7d", "seven_day")):
        w = rec.get(key)
        if w:
            item = dict(w)
            item["label"] = label
            out.append(item)
    return out


# ---------- Provider:Claude ----------

def provider_claude():
    rec = {"name": "Claude Code", "short": "CC", "icon": "spark", "ok": False,
           "plan": None, "five_hour": None, "seven_day": None}
    try:
        raw = subprocess.run(
            ["/usr/bin/security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
            capture_output=True, text=True, timeout=5).stdout.strip()
        token = json.loads(raw)["claudeAiOauth"]["accessToken"]
    except Exception:
        return rec

    import urllib.request
    req = urllib.request.Request(CLAUDE_USAGE_URL, headers={
        "Authorization": f"Bearer {token}", "anthropic-beta": OAUTH_BETA})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.load(resp)
    except Exception:
        return rec

    def win(node):
        if not node:
            return None
        try:
            return _window(node["utilization"], datetime.fromisoformat(node["resets_at"]))
        except Exception:
            return None

    rec["five_hour"] = win(data.get("five_hour"))
    rec["seven_day"] = win(data.get("seven_day"))
    rec["ok"] = rec["five_hour"] is not None or rec["seven_day"] is not None
    return rec


# ---------- Provider:Codex ----------

def provider_codex():
    rec = {"name": "Codex", "short": "Cx", "icon": "chevron", "ok": False,
           "plan": None, "five_hour": None, "seven_day": None}
    codex = _resolve("codex")
    if not codex:
        return rec
    # codex 是 `#!/usr/bin/env node` script,需確保同目錄的 node 在 PATH 裡
    env = dict(os.environ)
    env["PATH"] = os.path.dirname(codex) + os.pathsep + env.get("PATH", "")
    try:
        proc = subprocess.Popen([codex, "app-server"], env=env,
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, text=True, bufsize=1)
    except Exception:
        return rec

    def send(obj):
        proc.stdin.write(json.dumps(obj) + "\n")
        proc.stdin.flush()

    result = None
    try:
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"clientInfo": {"name": "ai-usage", "title": "ai-usage", "version": "0.1"}}})
        send({"jsonrpc": "2.0", "id": 2, "method": "account/rateLimits/read", "params": {}})
        deadline = time.time() + 8
        while time.time() < deadline:
            line = proc.stdout.readline()
            if not line:
                break
            try:
                msg = json.loads(line)
            except Exception:
                continue
            if msg.get("id") == 2 and "result" in msg:
                result = msg["result"]
                break
    except Exception:
        result = None
    finally:
        proc.terminate()

    if not result:
        return rec
    rl = result.get("rateLimits", {})
    rec["plan"] = rl.get("planType")

    def win(node):
        if not node:
            return None
        try:
            return _window(node["usedPercent"],
                           datetime.fromtimestamp(node["resetsAt"], tz=timezone.utc))
        except Exception:
            return None

    rec["five_hour"] = win(rl.get("primary"))
    rec["seven_day"] = win(rl.get("secondary"))
    rec["ok"] = rec["five_hour"] is not None or rec["seven_day"] is not None
    return rec


# ---------- Provider:Antigravity ----------

ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b[>=][^A-Za-z]*[A-Za-z]?|\x1b\\?.")


def _strip_ansi(text):
    return ANSI_RE.sub("", text).replace("\r", "\n")


def _parse_antigravity_usage(text):
    """解析 /usage 面板，回傳 SwiftBar windows。

    /usage 顯示的是 quota available 百分比。為了不讓 100% available
    被轉成 0% 而看起來像沒有 bar，Antigravity 視窗保留 available 語義。
    """
    clean = _strip_ansi(text)
    if "Model Quota" in clean:
        clean = clean[clean.rfind("Model Quota"):]
    lines = [line.strip() for line in clean.splitlines() if line.strip()]
    windows = []
    for i, line in enumerate(lines):
        if line in {"Model Quota", "Quota available"} or line.endswith("Model Quota"):
            continue
        if "shortcuts" in line or "Scroll" in line or "esc" in line:
            continue
        if "█" in line or "░" in line:
            continue
        if "%" in line:
            continue
        pct = None
        for nxt in lines[i + 1:i + 4]:
            match = re.search(r"(\d+(?:\.\d+)?)\s*%", nxt)
            if match:
                pct = float(match.group(1))
                break
        if pct is None:
            continue
        windows.append({
            "label": line,
            "pct": max(0.0, min(100.0, pct)),
            "kind": "available",
        })
    return windows


def _capture_antigravity_usage_text(timeout=12):
    """用 pseudo-TTY 驅動 agy /usage；失敗回空字串。

    Antigravity CLI 的 slash command 需要 TTY，不能直接 pipe/stdout。
    """
    agy = _resolve("agy") or os.path.expanduser("~/.local/bin/agy")
    if not os.path.exists(agy):
        return ""

    master, slave = pty.openpty()
    try:
        # 放大 TTY 高度，讓 /usage 一次渲染完整清單，避免只拿到 viewport。
        winsize = struct.pack("HHHH", 80, 120, 0, 0)
        fcntl.ioctl(slave, termios.TIOCSWINSZ, winsize)
        proc = subprocess.Popen([agy], stdin=slave, stdout=slave, stderr=slave,
                                close_fds=True, start_new_session=True)
    except Exception:
        try:
            os.close(master)
            os.close(slave)
        except Exception:
            pass
        return ""
    finally:
        try:
            os.close(slave)
        except Exception:
            pass

    chunks = []
    sent = False
    saw_usage = False
    deadline = time.time() + timeout
    try:
        while time.time() < deadline:
            ready, _, _ = select.select([master], [], [], 0.2)
            if not ready:
                continue
            try:
                data = os.read(master, 8192)
            except OSError:
                break
            if not data:
                break
            text = data.decode("utf-8", errors="replace")
            chunks.append(text)
            joined = "".join(chunks)
            if not sent and ("? for shortcuts" in joined or "Google AI Pro" in joined):
                os.write(master, b"/usage\r")
                sent = True
            if "Model Quota" in joined:
                saw_usage = True
                # 多讀一小段，等 TUI 把後續模型列渲染完。
                if time.time() + 0.8 < deadline:
                    deadline = time.time() + 0.8
        return "".join(chunks) if saw_usage else ""
    finally:
        try:
            os.write(master, b"\x1b/quit\r")
        except Exception:
            pass
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except Exception:
            proc.terminate()
        try:
            proc.wait(timeout=1)
        except Exception:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except Exception:
                proc.kill()
        try:
            os.close(master)
        except Exception:
            pass


def provider_antigravity(accounts_path=ANTIGRAVITY_ACCOUNTS_PATH, now_ms=None, usage_text=None):
    """讀取 opencode Antigravity OAuth plugin 的本機帳號狀態。

    Antigravity 目前沒有像 Claude/Codex 一樣的公開百分比用量端點可重用；
    本 provider 採保守顯示：帳號存在即標示 ready，若本機帳號檔記錄了
    尚未過期的 rate-limit reset，則以 100% 顯示該 quota pool 直到 reset。
    """
    rec = {"name": "Antigravity", "short": "AG", "icon": "gravity", "ok": False,
           "plan": None, "five_hour": None, "seven_day": None, "windows": [],
           "status": None}
    now_ms = int(time.time() * 1000) if now_ms is None else int(now_ms)

    if usage_text is None and accounts_path == ANTIGRAVITY_ACCOUNTS_PATH:
        usage_text = _capture_antigravity_usage_text()
    if usage_text:
        windows = _parse_antigravity_usage(usage_text)
        if windows:
            rec["ok"] = True
            rec["plan"] = "agy /usage"
            rec["windows"] = windows
            rec["status"] = "usage"
            return rec

    try:
        with open(accounts_path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return rec

    accounts = data.get("accounts") if isinstance(data, dict) else None
    if not isinstance(accounts, list) or not accounts:
        return rec

    rec["ok"] = True
    rec["plan"] = "{} acct{}".format(len(accounts), "" if len(accounts) == 1 else "s")

    # 同一 quota pool 多帳號時取最晚 reset；只顯示 Antigravity quota，
    # 不混入 Gemini CLI quota（gemini-cli）避免名稱誤導。
    pools = {"Claude": 0, "Gemini": 0}
    for account in accounts:
        if not isinstance(account, dict):
            continue
        resets = account.get("rateLimitResetTimes")
        if not isinstance(resets, dict):
            continue
        for key, value in resets.items():
            if not isinstance(value, (int, float)) or value <= now_ms:
                continue
            if key == "claude" or key.startswith("claude:"):
                pools["Claude"] = max(pools["Claude"], int(value))
            elif key == "gemini-antigravity" or key.startswith("gemini-antigravity:"):
                pools["Gemini"] = max(pools["Gemini"], int(value))

    rec["windows"] = [
        {"label": label, "pct": 100.0, "reset": reset / 1000}
        for label, reset in pools.items()
        if reset > now_ms
    ]
    rec["status"] = "limited" if rec["windows"] else "ready"
    return rec


# 要新增工具:在這裡加一個 provider 函式即可。
PROVIDERS = [provider_claude, provider_codex, provider_antigravity]


# ---------- 快取(降低呼叫頻率、避開端點限流)----------

def _good(cache, now):
    """從快取取出『上次成功值』,並依年齡標記 stale_min。"""
    if cache and cache.get("good"):
        rec = dict(cache["good"])
        age = int((now - cache.get("good_ts", now)) / 60)
        if age > 0:
            rec["stale_min"] = age
        return rec
    return None


def _cached(fn):
    """節流 + 退避:

    - 每個 provider 最短 FETCH_TTL 才真的抓一次(成功或失敗都算一次嘗試),
      避免失敗時每 60s 猛打、把端點限流(429)續命。
    - 兩段式快取:`last attempt` 用來退避;`good` 保留上次成功值,
      失敗期間照樣顯示(標記幾分鐘前),而不是顯示 —。
    """
    key = getattr(fn, "__name__", "p")
    path = os.path.join(CACHE_DIR, key + ".json")
    now = time.time()
    cache = None
    try:
        with open(path, encoding="utf-8") as f:
            cache = json.load(f)
    except Exception:
        cache = None

    # 距上次嘗試還沒到 TTL -> 不碰網路/子程序,直接給上次成功值(或失敗紀錄)
    if cache and now - cache.get("ts", 0) < FETCH_TTL:
        return _good(cache, now) or cache.get("rec")

    rec = fn()
    out = {"ts": now, "rec": rec}
    if rec.get("ok"):
        out["good"], out["good_ts"] = rec, now
    elif cache and cache.get("good"):
        out["good"], out["good_ts"] = cache["good"], cache.get("good_ts", now)
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f)
    except Exception:
        pass

    return rec if rec.get("ok") else (_good(out, now) or rec)


# ---------- 顏色 / 狀態 ----------

GREEN = (52, 199, 89)
YELLOW = (255, 204, 0)
RED = (255, 59, 48)

# Brand accents used for the tool icon itself; progress indicators still use
# green/yellow/red so status remains immediately readable.
BRAND_COLORS = {
    "spark": (217, 119, 87),      # Claude / Anthropic warm orange
    "chevron": (16, 163, 127),   # Codex / OpenAI green
}


def _rgb(pct):
    if pct >= CRIT_PCT:
        return RED
    if pct >= WARN_PCT:
        return YELLOW
    return GREEN


def _rgb_for_window(w):
    pct = w.get("pct", 0)
    if w.get("kind") == "available":
        if pct <= 100 - CRIT_PCT:
            return RED
        if pct <= 100 - WARN_PCT:
            return YELLOW
        return GREEN
    return _rgb(pct)


def _hex(pct):
    return "#%02x%02x%02x" % _rgb(pct)


def _hex_for_window(w):
    return "#%02x%02x%02x" % _rgb_for_window(w)


def _dot(pct):
    return "🔴" if pct >= CRIT_PCT else "🟡" if pct >= WARN_PCT else "🟢"


def _worst(records):
    pcts = [w["pct"] for r in records if r["ok"] for w in _windows(r) if w]
    return max(pcts) if pcts else 0.0


# ---------- menu bar 圖片渲染(PIL,選用) ----------

def _is_dark():
    try:
        out = subprocess.run(["/usr/bin/defaults", "read", "-g", "AppleInterfaceStyle"],
                             capture_output=True, text=True, timeout=2).stdout.strip()
        return out == "Dark"
    except Exception:
        return True


def _menubar_image(records):
    """回傳 base64 PNG(膠囊:圖示 + 環形進度 + %),失敗回 None。"""
    try:
        import base64
        import io
        import math
        from PIL import Image, ImageDraw, ImageFont
    except Exception:
        return None

    s = 3                       # 視網膜倍率(用 DPI 還原成點數)
    H = 19                      # 邏輯高度(pt)
    dark = _is_dark()
    fg = (236, 236, 240) if dark else (38, 38, 42)
    pill_bg = (255, 255, 255, 24) if dark else (0, 0, 0, 13)
    pill_border = (255, 255, 255, 36) if dark else (255, 255, 255, 96)
    pill_shadow = (0, 0, 0, 68) if dark else (0, 0, 0, 28)
    track = (255, 255, 255, 48) if dark else (0, 0, 0, 38)

    def mix(a, b, t):
        return tuple(int(a[i] * (1 - t) + b[i] * t) for i in range(3))

    def glow(col, alpha):
        return col + (alpha,)

    def font(px):
        for n in ("/System/Library/Fonts/SFNSRounded.ttf", "/System/Library/Fonts/SFNS.ttf"):
            try:
                return ImageFont.truetype(n, px)
            except Exception:
                continue
        return ImageFont.load_default()

    def mini_bar(width, height, pct, col):
        im = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        radius = height / 2
        d.rounded_rectangle((0, 0, width, height), radius=radius, fill=track)
        if pct > 0:
            fill_w = max(height, width * min(100, pct) / 100)
            d.rounded_rectangle((0, 0, fill_w, height), radius=radius, fill=glow(col, 255))
            d.line((1, 1, max(1, fill_w - 2), 1), fill=glow(mix(col, (255, 255, 255), 0.35), 160), width=1)
        return im

    def _badge(d, R, accent):
        light = mix(accent, (255, 255, 255), 0.34 if dark else 0.18)
        shade = mix(accent, (0, 0, 0), 0.40 if dark else 0.24)
        d.rounded_rectangle((R * 0.07, R * 0.09, R * 0.93, R * 0.91),
                            radius=R * 0.26, fill=glow(shade, 86))
        d.rounded_rectangle((R * 0.12, R * 0.05, R * 0.88, R * 0.82),
                            radius=R * 0.24, fill=glow(accent, 46))
        d.arc((R * 0.18, R * 0.10, R * 0.84, R * 0.76),
              210, 330, fill=glow(light, 135), width=max(1, int(R * 0.04)))

    def spark(diam, accent, brand):     # Claude:faceted sparkle badge with orbit dots
        ss = 4
        R = diam * ss
        im = Image.new("RGBA", (R, R), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        _badge(d, R, brand)
        c = R / 2
        bright = mix(fg, brand, 0.28)
        inner, outer, bw = R * 0.08, R * 0.34, R * 0.08
        for k in range(8):
            a = math.pi * k / 4
            pa = a + math.pi / 2
            tip = (c + outer * math.cos(a), c + outer * math.sin(a))
            b1 = (c + inner * math.cos(a) + bw * math.cos(pa),
                  c + inner * math.sin(a) + bw * math.sin(pa))
            b2 = (c + inner * math.cos(a) - bw * math.cos(pa),
                  c + inner * math.sin(a) - bw * math.sin(pa))
            fill = bright if k % 2 == 0 else mix(fg, brand, 0.58)
            d.polygon([tip, b1, b2], fill=glow(fill, 245))
        d.ellipse((c - R * 0.09, c - R * 0.09, c + R * 0.09, c + R * 0.09),
                  fill=glow(fg, 255))
        for px, py, rr in ((R * 0.76, R * 0.25, R * 0.045), (R * 0.25, R * 0.74, R * 0.035)):
            d.ellipse((px - rr, py - rr, px + rr, py + rr), fill=glow(fg, 205))
        return im.resize((diam, diam), Image.LANCZOS)

    def chevron(diam, accent, brand):   # Codex:layered command chevrons inside a badge
        ss = 4
        R = diam * ss
        im = Image.new("RGBA", (R, R), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        _badge(d, R, brand)
        w = int(R * 0.11)
        shadow = glow(mix(brand, (0, 0, 0), 0.50), 150)
        colors = [glow(mix(fg, brand, 0.34), 250), glow(fg, 245)]
        for idx, off in enumerate((-R * 0.12, R * 0.14)):
            pts = [(R * 0.31 + off, R * 0.30), (R * 0.56 + off, R * 0.5),
                   (R * 0.31 + off, R * 0.70)]
            d.line([(x + R * 0.025, y + R * 0.025) for x, y in pts],
                   fill=shadow, width=w, joint="curve")
            d.line(pts, fill=colors[idx], width=w, joint="curve")
            for p in pts:        # 圓角端點
                d.ellipse((p[0] - w / 2, p[1] - w / 2, p[0] + w / 2, p[1] + w / 2),
                          fill=colors[idx])
        return im.resize((diam, diam), Image.LANCZOS)

    icons = {"spark": spark, "chevron": chevron}
    f = font(10 * s)
    ph = 16 * s                 # 膠囊高度
    pw = 58 * s                 # compact chip width
    gap = 4 * s
    canvas = Image.new("RGBA", (pw * len(records) + gap * (len(records) - 1), H * s),
                       (0, 0, 0, 0))
    d = ImageDraw.Draw(canvas)
    y = (H * s - ph) // 2
    x = 0
    for r in records:
        # Subtle shadow/border gives the menu-bar chips depth without getting noisy.
        d.rounded_rectangle((x, y + 0.6 * s, x + pw, y + ph + 0.6 * s),
                            radius=ph / 2, fill=pill_shadow)
        d.rounded_rectangle((x, y, x + pw, y + ph), radius=ph / 2,
                            fill=pill_bg, outline=pill_border, width=max(1, s // 2))
        # 用第一個視窗當主要顯示；Claude/Codex 是 5h，Antigravity 是限流中的 pool。
        rec_windows = _windows(r) if r["ok"] else []
        w5 = rec_windows[0] if rec_windows else None
        pct = w5["pct"] if w5 else 0
        accent = _rgb_for_window(w5) if w5 else ((142, 142, 147) if dark else (116, 116, 122))
        draw_icon = icons.get(r.get("icon"))
        brand = BRAND_COLORS.get(r.get("icon"), accent) if w5 else accent
        if draw_icon:
            ic = draw_icon(12 * s, accent, brand)
            canvas.alpha_composite(ic, (x + 6 * s, y + (ph - 12 * s) // 2))
        else:
            d.text((x + 10 * s, y + ph / 2), r["short"], font=f, fill=fg, anchor="lm")
        if w5:
            mb = mini_bar(17 * s, 4 * s, pct, accent)
            canvas.alpha_composite(mb, (x + 22 * s, y + (ph - 4 * s) // 2))
            d.text((x + pw - 6 * s, y + ph / 2), f"{pct:.0f}", font=f, fill=fg, anchor="rm")
        else:
            d.text((x + pw - 7 * s, y + ph / 2), "—", font=f, fill=fg, anchor="rm")
        x += pw + gap

    buf = io.BytesIO()
    # DPI = 72*s 讓 NSImage 把點數還原成 H pt,像素仍為 @s 倍 → 視網膜清晰
    canvas.save(buf, format="PNG", dpi=(72 * s, 72 * s))
    return base64.b64encode(buf.getvalue()).decode("ascii")


# ---------- 下拉選單(文字 + 進度條) ----------

def _bar(pct):
    filled = max(0, min(BAR_WIDTH, round(pct * BAR_WIDTH / 100)))
    return "█" * filled + "░" * (BAR_WIDTH - filled)


def _print_dropdown(records):
    for r in records:
        plan = f"  ·  {r['plan']}" if r.get("plan") else ""
        if not r["ok"]:
            print(f"{r['name']}{plan}　✗ 無法取得 | color=#888888 size=13")
            print("---")
            continue
        tag = f"   ↺ {r['stale_min']}分前" if r.get("stale_min") else ""
        print(f"{r['name']}{plan}{tag} | size=13")
        windows = _windows(r)
        if not windows and r.get("status") == "ready":
            print("ready  無本機限流紀錄 | color=#34c759 size=13")
        for w in windows:
            label = w.get("label", "?")
            reset = w.get("reset")
            reset_text = f"   ⟳ {_rel(reset)}  ({_clock(reset)})" if reset else ""
            kind_text = " available" if w.get("kind") == "available" else ""
            print(f"{label}  {_bar(w['pct'])}  {w['pct']:4.0f}%{kind_text}{reset_text} | "
                  f"color={_hex_for_window(w)} font=Menlo size=13")
        print("---")
    print("立即刷新 | refresh=true sfimage=arrow.clockwise")


def main():
    records = []
    for fn in PROVIDERS:
        try:
            records.append(_cached(fn))
        except Exception:
            records.append({"name": getattr(fn, "__name__", "?"), "short": "?",
                            "icon": None, "ok": False,
                            "five_hour": None, "seven_day": None, "plan": None})

    # 選單列:優先用 PIL 渲染的膠囊圖;失敗則退回文字
    img = _menubar_image(records)
    if img:
        print(f"| image={img}")
    else:
        parts = []
        for r in records:
            rec_windows = _windows(r) if r["ok"] else []
            if r["ok"] and rec_windows:
                parts.append(f"{r['short']} {rec_windows[0]['pct']:.0f}%")
            elif r["ok"] and r.get("status") == "ready":
                parts.append(f"{r['short']} ✓")
            else:
                parts.append(f"{r['short']} —")
        # Text fallback for machines without Pillow: keep it neutral instead of
        # showing a generic traffic-light dot that looks like an unfinished icon.
        print("AI  " + "  ".join(parts))

    print("---")
    _print_dropdown(records)


if __name__ == "__main__":
    # 永不崩潰:任何未預期例外都不該污染選單列
    try:
        main()
    except Exception:
        print("AI —")
        print("---")
        print("plugin 發生錯誤 | color=#888888")
