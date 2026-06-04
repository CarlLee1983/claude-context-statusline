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
import math
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
# 狀態分級以「剩餘」quota 計算,與原生 menu app 的 RemainingQuotaPresenter 對齊。
WARN_REMAINING = 40   # 剩餘 ≤ 此值轉黃
CRIT_REMAINING = 10   # 剩餘 ≤ 此值轉紅
# 「用不完就浪費」(expiring-unused):剩很多 + 快 reset。對齊原生 RemainingQuotaPresenter。
EXPIRING_REMAINING_THRESHOLD = 40   # 剩餘 ≥ 此值且快 reset 才標記
EXPIRING_WINDOW_FRACTION = 0.15     # 進入窗口末段此比例視為快 reset
EXPIRING_COLOR = "#5856d6"          # 靛藍,與紅黃綠嚴重度色不衝突(對齊原生 indigo)
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

CLAUDE_PATH = "m4.7144 15.9555 4.7174-2.6471.079-.2307-.079-.1275h-.2307l-.7893-.0486-2.6956-.0729-2.3375-.0971-2.2646-.1214-.5707-.1215-.5343-.7042.0546-.3522.4797-.3218.686.0608 1.5179.1032 2.2767.1578 1.6514.0972 2.4468.255h.3886l.0546-.1579-.1336-.0971-.1032-.0972L6.973 9.8356l-2.55-1.6879-1.3356-.9714-.7225-.4918-.3643-.4614-.1578-1.0078.6557-.7225.8803.0607.2246.0607.8925.686 1.9064 1.4754 2.4893 1.8336.3643.3035.1457-.1032.0182-.0728-.164-.2733-1.3539-2.4467-1.445-2.4893-.6435-1.032-.17-.6194c-.0607-.255-.1032-.4674-.1032-.7285L6.287.1335 6.6997 0l.9957.1336.419.3642.6192 1.4147 1.0018 2.2282 1.5543 3.0296.4553.8985.2429.8318.091.255h.1579v-.1457l.1275-1.706.2368-2.0947.2307-2.6957.0789-.7589.3764-.9107.7468-.4918.5828.2793.4797.686-.0668.4433-.2853 1.8517-.5586 2.9021-.3643 1.9429h.2125l.2429-.2429.9835-1.3053 1.6514-2.0643.7286-.8196.85-.9046.5464-.4311h1.0321l.759 1.1293-.34 1.1657-1.0625 1.3478-.8804 1.1414-1.2628 1.7-.7893 1.36.0729.1093.1882-.0183 2.8535-.607 1.5421-.2794 1.8396-.3157.8318.3886.091.3946-.3278.8075-1.967.4857-2.3072.4614-3.4364.8136-.0425.0304.0486.0607 1.5482.1457.6618.0364h1.621l3.0175.2247.7892.522.4736.6376-.079.4857-1.2142.6193-1.6393-.3886-3.825-.9107-1.3113-.3279h-.1822v.1093l1.0929 1.0686 2.0035 1.8092 2.5075 2.3314.1275.5768-.3218.4554-.34-.0486-2.2039-1.6575-.85-.7468-1.9246-1.621h-.1275v.17l.4432.6496 2.3436 3.5214.1214 1.0807-.17.3521-.6071.2125-.6679-.1214-1.3721-1.9246L14.38 17.959l-1.1414-1.9428-.1397.079-.674 7.2552-.3156.3703-.7286.2793-.6071-.4614-.3218-.7468.3218-1.4753.3886-1.9246.3157-1.53.2853-1.9004.17-.6314-.0121-.0425-.1397.0182-1.4328 1.9672-2.1796 2.9446-1.7243 1.8456-.4128.164-.7164-.3704.0667-.6618.4008-.5889 2.386-3.0357 1.4389-1.882.929-1.0868-.0062-.1579h-.0546l-6.3385 4.1164-1.1293.1457-.4857-.4554.0608-.7467.2307-.2429 1.9064-1.3114Z"

OPENAI_PATH = (
    "M22.2819 9.8211a5.9847 5.9847 0 0 0-.5157-4.9108 6.0462 6.0462 0 0 0-6.5098-2.9A6.0651 6.0651 0 0 0 4.9807 4.1818a5.9847 5.9847 0 0 0-3.9977 2.9 6.0462 6.0462 0 0 0 .7427 7.0966 5.98 5.98 0 0 0 .511 4.9107 6.051 6.051 0 0 0 6.5146 2.9001A5.9847 5.9847 0 0 0 13.2599 24a6.0557 6.0557 0 0 0 5.7718-4.2058 5.9894 5.9894 0 0 0 3.9977-2.9001 6.0557 6.0557 0 0 0-.7475-7.0729zm-9.022 12.6081a4.4755 4.4755 0 0 1-2.8764-1.0408l.1419-.0804 4.7783-2.7582a.7948.7948 0 0 0 .3927-.6813v-6.7369l2.02 1.1686a.071.071 0 0 1 .038.052v5.5826a4.504 4.504 0 0 1-4.4945 4.4944zm-9.6607-4.1254a4.4708 4.4708 0 0 1-.5346-3.0137l.142.0852 4.783 2.7582a.7712.7712 0 0 0 .7806 0l5.8428-3.3685v2.3324a.0804.0804 0 0 1-.0332.0615L9.74 19.9502a4.4992 4.4992 0 0 1-6.1408-1.6464zM2.3408 7.8956a4.485 4.485 0 0 1 2.3655-1.9728V11.6a.7664.7664 0 0 0 .3879.6765l5.8144 3.3543-2.0201 1.1685a.0757.0757 0 0 1-.071 0l-4.8303-2.7865A4.504 4.504 0 0 1 2.3408 7.872zm16.5963 3.8558L13.1038 8.364 15.1192 7.2a.0757.0757 0 0 1 .071 0l4.8303 2.7913a4.4944 4.4944 0 0 1-.6765 8.1042v-5.6772a.79.79 0 0 0-.407-.667zm2.0107-3.0231l-.142-.0852-4.7735-2.7818a.7759.7759 0 0 0-.7854 0L9.409 9.2297V6.8974a.0662.0662 0 0 1 .0284-.0615l4.8303-2.7866a4.4992 4.4992 0 0 1 6.6802 4.66zM8.3065 12.863l-2.02-1.1638a.0804.0804 0 0 1-.038-.0567V6.0742a4.4992 4.4992 0 0 1 7.3757-3.4537l-.142.0805L8.704 5.459a.7948.7948 0 0 0-.3927.6813zm1.0976-2.3654l2.602-1.4998 2.6069 1.4998v2.9994l-2.5974 1.4997-2.6067-1.4997Z"
)

ANTIGRAVITY_LOGO_B64 = "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"




# ---------- 共用工具 ----------

def parse_svg_path(path_str, view_w=24.0, view_h=24.0, target_size=14.0):
    tokens = re.findall(r'[a-zA-Z]|-?\d*\.\d+|-?\d+', path_str)
    subpaths = []
    current_subpath = []
    cx, cy = 0.0, 0.0
    sx, sy = 0.0, 0.0
    scale_factor = target_size / view_w
    
    i = 0
    cmd = None
    while i < len(tokens):
        token = tokens[i]
        if token.isalpha():
            cmd = token
            i += 1
            
        if cmd in ('m', 'M'):
            if current_subpath:
                subpaths.append(current_subpath)
                current_subpath = []
            dx = float(tokens[i])
            dy = float(tokens[i+1])
            if cmd == 'm':
                cx += dx
                cy += dy
            else:
                cx = dx
                cy = dy
            sx, sy = cx, cy
            current_subpath.append((cx * scale_factor, cy * scale_factor))
            i += 2
            cmd = 'l' if cmd == 'm' else 'L'
        elif cmd == 'l':
            dx = float(tokens[i])
            dy = float(tokens[i+1])
            cx += dx
            cy += dy
            current_subpath.append((cx * scale_factor, cy * scale_factor))
            i += 2
        elif cmd == 'L':
            cx = float(tokens[i])
            cy = float(tokens[i+1])
            current_subpath.append((cx * scale_factor, cy * scale_factor))
            i += 2
        elif cmd == 'h':
            dx = float(tokens[i])
            cx += dx
            current_subpath.append((cx * scale_factor, cy * scale_factor))
            i += 1
        elif cmd == 'H':
            cx = float(tokens[i])
            current_subpath.append((cx * scale_factor, cy * scale_factor))
            i += 1
        elif cmd == 'v':
            dy = float(tokens[i])
            cy += dy
            current_subpath.append((cx * scale_factor, cy * scale_factor))
            i += 1
        elif cmd == 'V':
            cy = float(tokens[i])
            current_subpath.append((cx * scale_factor, cy * scale_factor))
            i += 1
        elif cmd == 'c':
            x1 = cx + float(tokens[i])
            y1 = cy + float(tokens[i+1])
            x2 = cx + float(tokens[i+2])
            y2 = cy + float(tokens[i+3])
            x3 = cx + float(tokens[i+4])
            y3 = cy + float(tokens[i+5])
            
            steps = 6
            for step in range(1, steps + 1):
                t = step / steps
                bx = (1-t)**3 * cx + 3*(1-t)**2 * t * x1 + 3*(1-t) * t**2 * x2 + t**3 * x3
                by = (1-t)**3 * cy + 3*(1-t)**2 * t * y1 + 3*(1-t) * t**2 * y2 + t**3 * y3
                current_subpath.append((bx * scale_factor, by * scale_factor))
            cx, cy = x3, y3
            i += 6
        elif cmd == 'C':
            x1 = float(tokens[i])
            y1 = float(tokens[i+1])
            x2 = float(tokens[i+2])
            y2 = float(tokens[i+3])
            x3 = float(tokens[i+4])
            y3 = float(tokens[i+5])
            
            steps = 6
            for step in range(1, steps + 1):
                t = step / steps
                bx = (1-t)**3 * cx + 3*(1-t)**2 * t * x1 + 3*(1-t) * t**2 * x2 + t**3 * x3
                by = (1-t)**3 * cy + 3*(1-t)**2 * t * y1 + 3*(1-t) * t**2 * y2 + t**3 * y3
                current_subpath.append((bx * scale_factor, by * scale_factor))
            cx, cy = x3, y3
            i += 6
        elif cmd in ('a', 'A'):
            rx = float(tokens[i])
            ry = float(tokens[i+1])
            rot = float(tokens[i+2])
            large_arc = int(float(tokens[i+3]))
            sweep = int(float(tokens[i+4]))
            target_x = float(tokens[i+5])
            target_y = float(tokens[i+6])
            
            if cmd == 'a':
                x2 = cx + target_x
                y2 = cy + target_y
            else:
                x2 = target_x
                y2 = target_y
                
            if rx == 0 or ry == 0:
                cx, cy = x2, y2
                current_subpath.append((cx * scale_factor, cy * scale_factor))
            else:
                rx = abs(rx)
                ry = abs(ry)
                rot_rad = math.radians(rot)
                cos_r = math.cos(rot_rad)
                sin_r = math.sin(rot_rad)
                
                dx = (cx - x2) / 2.0
                dy = (cy - y2) / 2.0
                x1_prime = cos_r * dx + sin_r * dy
                y1_prime = -sin_r * dx + cos_r * dy
                
                rx_sq = rx * rx
                ry_sq = ry * ry
                x1_prime_sq = x1_prime * x1_prime
                y1_prime_sq = y1_prime * y1_prime
                
                radii_check = x1_prime_sq / rx_sq + y1_prime_sq / ry_sq
                if radii_check > 1.0:
                    rx *= math.sqrt(radii_check)
                    ry *= math.sqrt(radii_check)
                    rx_sq = rx * rx
                    ry_sq = ry * ry
                
                sq = (rx_sq * ry_sq - rx_sq * y1_prime_sq - ry_sq * x1_prime_sq) / (rx_sq * y1_prime_sq + ry_sq * x1_prime_sq)
                sq = max(0.0, sq)
                coef = math.sqrt(sq)
                if large_arc == sweep:
                    coef = -coef
                
                cx_prime = coef * (rx * y1_prime / ry)
                cy_prime = coef * (-ry * x1_prime / rx)
                
                center_x = cos_r * cx_prime - sin_r * cy_prime + (cx + x2) / 2.0
                center_y = sin_r * cx_prime + cos_r * cy_prime + (cy + y2) / 2.0
                
                def angle_between(u, v):
                    val = (u[0]*v[0] + u[1]*v[1]) / (math.sqrt(u[0]**2 + u[1]**2) * math.sqrt(v[0]**2 + v[1]**2))
                    val = max(-1.0, min(1.0, val))
                    ang = math.acos(val)
                    if (u[0]*v[1] - u[1]*v[0]) < 0:
                        ang = -ang
                    return ang
                
                v1 = ((x1_prime - cx_prime)/rx, (y1_prime - cy_prime)/ry)
                v2 = ((-x1_prime - cx_prime)/rx, (-y1_prime - cy_prime)/ry)
                theta1 = angle_between((1.0, 0.0), v1)
                d_theta = angle_between(v1, v2)
                
                if sweep == 0 and d_theta > 0:
                    d_theta -= 2 * math.pi
                elif sweep == 1 and d_theta < 0:
                    d_theta += 2 * math.pi
                
                steps = 12
                for step in range(1, steps + 1):
                    t = step / steps
                    ang = theta1 + t * d_theta
                    px_val = rx * math.cos(ang)
                    py_val = ry * math.sin(ang)
                    x_rot = cos_r * px_val - sin_r * py_val + center_x
                    y_rot = sin_r * px_val + cos_r * py_val + center_y
                    current_subpath.append((x_rot * scale_factor, y_rot * scale_factor))
                
                cx, cy = x2, y2
            i += 7
        elif cmd in ('z', 'Z'):
            if current_subpath:
                subpaths.append(current_subpath)
                current_subpath = []
            cx, cy = sx, sy
            
    if current_subpath:
        subpaths.append(current_subpath)
    return subpaths


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
    rec = {"name": "Codex", "short": "Cx", "icon": "openai", "ok": False,
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


_REFRESH_UNITS = {"d": 86400, "h": 3600, "m": 60, "s": 1}


def _parse_refresh_seconds(text):
    """從 "Refreshes in 2h 46m" 取倒數秒數（支援 d/h/m/s 任意子集）；無倒數回 None。"""
    match = re.search(r"Refreshes in\s+(.+)", text, re.IGNORECASE)
    if not match:
        return None
    total = 0.0
    matched = False
    for num, unit in re.findall(r"(\d+(?:\.\d+)?)\s*([dhms])\b", match.group(1)):
        total += float(num) * _REFRESH_UNITS[unit]
        matched = True
    return total if matched else None


def _parse_antigravity_usage(text, now=None):
    """解析 /usage 面板，回傳 SwiftBar windows。

    /usage 顯示的是 quota available 百分比。為了不讓 100% available
    被轉成 0% 而看起來像沒有 bar，Antigravity 視窗保留 available 語義。
    未滿額的視窗面板會印 "… · Refreshes in 2h 46m" 倒數，換算成絕對 reset
    時間戳塞進 window（滿額顯示 "Quota available"，故無 reset）。
    """
    now = time.time() if now is None else now
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
        reset = None
        for nxt in lines[i + 1:i + 4]:
            if pct is None:
                match = re.search(r"(\d+(?:\.\d+)?)\s*%", nxt)
                if match:
                    pct = float(match.group(1))
            if reset is None:
                secs = _parse_refresh_seconds(nxt)
                if secs is not None:
                    reset = now + secs
        if pct is None:
            continue
        window = {
            "label": line,
            "pct": max(0.0, min(100.0, pct)),
            "kind": "available",
        }
        if reset is not None:
            window["reset"] = reset
        windows.append(window)
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
        windows = _parse_antigravity_usage(usage_text, now=now_ms / 1000)
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

# tier -> 顏色,與原生 app 一致:狀態由「剩餘」量決定,而非已用量。
TIER_COLORS = {"good": GREEN, "warn": YELLOW, "critical": RED}


def _remaining_pct(w):
    """剩餘 quota %(對齊原生 RemainingQuotaPresenter.remainingPercent):
    used 視窗 = 100 - 已用;available 視窗(Antigravity)= 其可用 %。"""
    pct = w.get("pct", 0)
    remaining = pct if w.get("kind") == "available" else 100 - pct
    return int(max(0, min(100, round(remaining))))


_UNIT_SECONDS = {"h": 3600, "d": 86400, "w": 604800, "m": 2592000}


def _window_duration(label):
    """從 label(5h/7d/2w)解析固定窗口長度(秒);解不出回 None。
    對齊原生 RemainingQuotaPresenter.windowDuration:大小寫不敏感、容忍中間空白,
    free-form label(如 Antigravity 模型名)一律 None。單位 h/d/w/m(m=30 天)。"""
    if not isinstance(label, str):
        return None
    trimmed = label.strip().lower()
    if not trimmed:
        return None
    seconds = _UNIT_SECONDS.get(trimmed[-1])
    if seconds is None:
        return None
    number_part = trimmed[:-1].strip()
    if not number_part.isdigit():
        return None
    value = int(number_part)
    if value <= 0:
        return None
    return float(value) * seconds


def _is_expiring_unused(w, now=None):
    """剩很多 + 快 reset -> True(對齊原生 isExpiringUnused)。
    label 不可解、剩餘 < 門檻、無 reset 或 reset 已過,一律 False。"""
    duration = _window_duration(w.get("label"))
    if duration is None:
        return False
    if _remaining_pct(w) < EXPIRING_REMAINING_THRESHOLD:
        return False
    reset = w.get("reset")
    if not reset:
        return False
    now_ts = now if now is not None else datetime.now(timezone.utc).timestamp()
    time_until = reset - now_ts
    if time_until <= 0:
        return False
    return time_until <= duration * EXPIRING_WINDOW_FRACTION


def _tier(remaining):
    """剩餘量 -> 狀態分級,門檻與原生 app 相同。"""
    if remaining <= CRIT_REMAINING:
        return "critical"
    if remaining <= WARN_REMAINING:
        return "warn"
    return "good"


def _rgb_for_window(w):
    return TIER_COLORS[_tier(_remaining_pct(w))]


def _hex_for_window(w):
    return "#%02x%02x%02x" % _rgb_for_window(w)


# ---------- menu bar 圖片渲染(PIL,選用) ----------

def _menubar_image(records):
    """回傳 base64 PNG(膠囊:扁平圖示 + 左下角狀態角標 + 剩餘 %),失敗回 None。

    視覺概念對齊原生 menu app(StatusMenuImageRenderer):
    - 數字顯示「剩餘」quota,固定白色。
    - 狀態用圖示左下角的角標表示:warn 黃三角、crit 紅驚嘆號(皆含白環),
      good 不顯示角標 —— 形狀+顏色雙重編碼,色盲友善。
    - 圖示為扁平標記:Claude 火花、Codex OpenAI 標記、Antigravity 拱形。
    """
    try:
        import base64
        import io
        import math
        from PIL import Image, ImageDraw, ImageFont
    except Exception:
        return None

    s = 3                       # 視網膜倍率(用 DPI 還原成點數)
    ss = 4                      # 圖示/角標額外超取樣,resize 後邊緣平滑
    icon_pt = 14                # 圖示繪製基準單位(對齊原生 iconSize)
    FG = (255, 255, 255)        # 數字 / 多數圖示用白色
    LANCZOS = getattr(Image, "Resampling", Image).LANCZOS

    def font(px):
        for n in ("/System/Library/Fonts/SFNSMono.ttf",
                  "/System/Library/Fonts/SFNSRounded.ttf",
                  "/System/Library/Fonts/SFNS.ttf"):
            try:
                return ImageFont.truetype(n, px)
            except Exception:
                continue
        return ImageFont.load_default()

    def _canvas(px):            # 回傳 (image, draw, R) 供超取樣繪製
        R = px * ss
        im = Image.new("RGBA", (R, R), (0, 0, 0, 0))
        return im, ImageDraw.Draw(im), R

    # ---- 扁平圖示(回傳邊長 px 的 RGBA)----
    def icon_spark(px):         # Claude: 官方 starburst / 暖橘
        im, d, R = _canvas(px)
        subpaths = parse_svg_path(CLAUDE_PATH, target_size=R)
        for pts in subpaths:
            if len(pts) >= 3:
                d.polygon(pts, fill=(217, 115, 79, 255))
        return im.resize((px, px), LANCZOS)

    def icon_openai(px):        # Codex: OpenAI 官方標記 / 白色
        im, d, R = _canvas(px)
        subpaths = parse_svg_path(OPENAI_PATH, target_size=R)
        
        # Render onto a grayscale mask first to erase outlines to transparent
        mask = Image.new("L", (R, R), 0)
        d_mask = ImageDraw.Draw(mask)
        
        # Fill each subpath
        for pts in subpaths:
            if len(pts) >= 3:
                d_mask.polygon(pts, fill=255)
                
        # Erase the outlines to separate petals with transparency
        outline_w = max(1, int(round(8.0 * px * ss / 168.0)))
        for pts in subpaths:
            if len(pts) >= 3:
                d_mask.polygon(pts, outline=0, width=outline_w)
                
        # Paste solid white onto the super-sampled image using the mask
        im.paste((255, 255, 255, 255), (0, 0), mask=mask)
        return im.resize((px, px), LANCZOS)

    def icon_gravity(px):       # Antigravity: 官方 logo / 彩色
        import base64
        import io
        data = base64.b64decode(ANTIGRAVITY_LOGO_B64)
        img_ag = Image.open(io.BytesIO(data))
        # Resize to fit within px x px maintaining aspect ratio
        img_ag.thumbnail((px, px), LANCZOS)
        # Create a centered canvas
        canvas = Image.new("RGBA", (px, px), (0, 0, 0, 0))
        canvas.paste(img_ag, ((px - img_ag.width) // 2, (px - img_ag.height) // 2))
        return canvas

    def icon_dot(px):           # 其他:中性圓點
        im, d, R = _canvas(px)
        u = R / icon_pt
        d.ellipse((3 * u, 3 * u, R - 3 * u, R - 3 * u), fill=FG + (217,))
        return im.resize((px, px), LANCZOS)

    icons = {"spark": icon_spark, "openai": icon_openai, "gravity": icon_gravity}

    # ---- 左下角狀態角標 ----
    def badge_warn(px):         # 黃三角 + 白環 + 深色驚嘆號
        im, d, R = _canvas(px)
        inset = R * 0.06
        apex, bl, br = (R / 2, inset), (inset, R - inset), (R - inset, R - inset)
        d.polygon([apex, bl, br], fill=(255, 255, 255, 235))   # 白環
        cx, cy = (apex[0] + bl[0] + br[0]) / 3, (apex[1] + bl[1] + br[1]) / 3
        tri = [(cx + (p[0] - cx) * 0.72, cy + (p[1] - cy) * 0.72) for p in (apex, bl, br)]
        d.polygon(tri, fill=(255, 204, 0, 255))
        bw = R * 0.12
        d.rounded_rectangle((R / 2 - bw / 2, R * 0.40, R / 2 + bw / 2, R * 0.62),
                            radius=bw / 2, fill=(0, 0, 0, 184))
        dot = R * 0.13
        d.ellipse((R / 2 - dot / 2, R * 0.68, R / 2 + dot / 2, R * 0.68 + dot),
                  fill=(0, 0, 0, 184))
        return im.resize((px, px), LANCZOS)

    def badge_crit(px):         # 紅圓 + 白環 + 白驚嘆號
        im, d, R = _canvas(px)
        d.ellipse((0, 0, R, R), fill=(255, 255, 255, 235))     # 白環
        r2 = R * 0.12
        d.ellipse((r2, r2, R - r2, R - r2), fill=(255, 59, 48, 255))
        bw = R * 0.15
        d.rounded_rectangle((R / 2 - bw / 2, R * 0.27, R / 2 + bw / 2, R * 0.57),
                            radius=bw / 2, fill=FG + (255,))
        dot = bw * 1.1
        d.ellipse((R / 2 - dot / 2, R * 0.64, R / 2 + dot / 2, R * 0.64 + dot),
                  fill=FG + (255,))
        return im.resize((px, px), LANCZOS)

    badges = {"warn": badge_warn, "critical": badge_crit}

    # ---- 版面(以 s-像素計;幾何對齊原生 chip)----
    H = 18 * s                  # 膠囊高度
    pad = 7 * s
    icon_px = icon_pt * s
    icon_gap = 5 * s
    chip_gap = 5 * s
    f = font(11 * s)
    meas = ImageDraw.Draw(Image.new("RGBA", (1, 1)))

    def number_for(r):
        ws = _windows(r) if r["ok"] else []
        return str(_remaining_pct(ws[0])) if ws else "—"

    chips = []
    for r in records:
        text = number_for(r)
        num_w = int(math.ceil(meas.textlength(text, font=f)))
        chips.append((r, text, num_w, pad * 2 + icon_px + icon_gap + num_w))

    total = sum(c[3] for c in chips) + chip_gap * max(0, len(chips) - 1)
    canvas = Image.new("RGBA", (max(1, total), H), (0, 0, 0, 0))
    d = ImageDraw.Draw(canvas)

    x = 0
    for r, text, num_w, chip_w in chips:
        # 建立圓角膠囊遮罩，確保進度條邊緣不會溢出膠囊
        mask_im = Image.new("L", (chip_w, H), 0)
        mask_draw = ImageDraw.Draw(mask_im)
        mask_draw.rounded_rectangle((0, 0, chip_w - 1, H - 1), radius=H / 2, fill=255)

        # 建立臨時膠囊畫布繪製背景進度條
        chip_im = Image.new("RGBA", (chip_w, H), (0, 0, 0, 0))
        chip_draw = ImageDraw.Draw(chip_im)

        # 1. 未填充底色 (10% 不透明度)
        chip_draw.rectangle((0, 0, chip_w, H), fill=(255, 255, 255, 25))

        # 2. 剩餘進度填充 (24% 不透明度)
        rec_windows = _windows(r) if r["ok"] else []
        remaining = _remaining_pct(rec_windows[0]) if rec_windows else 0
        progress_w = int(round(chip_w * remaining / 100.0))
        if progress_w > 0:
            chip_draw.rectangle((0, 0, progress_w, H), fill=(255, 255, 255, 61))

        # 將進度背景透過遮罩裁剪成圓角，然後貼至主 canvas
        transparent = Image.new("RGBA", (chip_w, H), (0, 0, 0, 0))
        chip_masked = Image.composite(chip_im, transparent, mask_im)
        canvas.alpha_composite(chip_masked, (x, 0))

        # 3. 繪製半透明白色框線 (維持原本 outline: 23% 不透明度)
        d.rounded_rectangle((x, 0, x + chip_w - 1, H - 1), radius=H / 2,
                            fill=None, outline=(255, 255, 255, 59),
                            width=max(1, s // 2))

        icon_left = x + pad
        icon_top = (H - icon_px) // 2
        draw_icon = icons.get(r.get("icon")) or (icon_dot if r["ok"] else None)
        if draw_icon:
            canvas.alpha_composite(draw_icon(icon_px), (int(icon_left), int(icon_top)))
        else:
            d.text((icon_left + icon_px / 2, H / 2), r["short"], font=f,
                   fill=FG + (255,), anchor="mm")

        # 狀態角標:依第一個視窗的剩餘量決定 tier,good 不畫
        rec_windows = _windows(r) if r["ok"] else []
        if rec_windows:
            make_badge = badges.get(_tier(_remaining_pct(rec_windows[0])))
            if make_badge:
                bsize = int(icon_px * 0.68)
                bx = icon_left - bsize * 0.28
                by = icon_top + icon_px - bsize * 0.84
                canvas.alpha_composite(make_badge(bsize), (int(round(bx)), int(round(by))))

        d.text((icon_left + icon_px + icon_gap, H / 2), text, font=f,
               fill=FG + (255,), anchor="lm")
        x += chip_w + chip_gap

    buf = io.BytesIO()
    # DPI = 72*s 讓 NSImage 把點數還原成 pt,像素仍為 @s 倍 → 視網膜清晰
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
            # 用不完就浪費:剩很多卻快 reset。整列轉靛藍 + ⏳ 標記(對齊原生視覺)。
            expiring = _is_expiring_unused(w)
            mark = "   ⏳ 即將重置" if expiring else ""
            color = EXPIRING_COLOR if expiring else _hex_for_window(w)
            print(f"{label}  {_bar(w['pct'])}  {w['pct']:4.0f}%{kind_text}{reset_text}{mark} | "
                  f"color={color} font=Menlo size=13")
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
                parts.append(f"{r['short']} {_remaining_pct(rec_windows[0])}%")
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
