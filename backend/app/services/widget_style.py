"""桌面胶囊共享样式：设置读取（背景色/透明度）+ 按背景明暗派生配色。

四个桌面胶囊（今日清单 / 考勤 / 提醒 / 番茄钟）共用：
- 设置项：cap_{key}_bg（十六进制，空=用 fallback 默认）/ cap_{key}_opacity（30~100，空=fallback）
- palette(bg)：浅色背景深文字、深色背景浅文字，其余颜色（图标/悬停/描边/状态色）随明暗派生
- 在 App 设置页「桌面胶囊」模块调整（先选胶囊再改颜色/透明度），各胶囊每几秒轮询设置变化
"""

import re

HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

DEFAULT_ACCENT = "#6a56e8"


def rgb(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def lum(c):
    r, g, b = rgb(c)
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255


def mix(c1, c2, t):
    def _l(a, b):
        return int(round(a + (b - a) * t))

    r1, g1, b1 = rgb(c1)
    r2, g2, b2 = rgb(c2)
    return "#%02x%02x%02x" % (_l(r1, r2), _l(g1, g2), _l(b1, b2))


def normalize_bg(bg, fallback="#ffffff"):
    bg = (bg or "").lower()
    return bg if HEX_RE.match(bg) else fallback


def palette(bg):
    """按背景明暗派生胶囊配色（文字/次要文字/图标/悬停底/描边/状态色/按钮）。"""
    bg = normalize_bg(bg)
    dark = lum(bg) < 0.52
    soft = "#ffffff" if dark else "#000000"
    txt = "#f2f0ed" if dark else "#26241f"
    accent = DEFAULT_ACCENT if not dark else mix(DEFAULT_ACCENT, "#ffffff", 0.32)
    return {
        "bg": bg,
        "txt": txt,
        "sub": "#b8b3a8" if dark else "#8a867c",
        "muted": "#8d897f" if dark else "#b3aea3",
        "icon": mix(txt, bg, 0.38),
        "hover": mix(bg, soft, 0.07),
        "border": mix(bg, soft, 0.14),
        "accent": accent,
        # 状态色（胶囊圆点/计时数字）：深底用亮色、浅底用深色，保证对比
        "green": "#5fd39a" if dark else "#16a34a",
        "orange": "#f0a860" if dark else "#d97706",
        "red": "#e06c75" if dark else "#d64545",
        "yellow": "#e8c664" if dark else "#b8860b",
        "disabled": "#6f6a62" if dark else "#b3aea3",
        "btn_bg": mix(bg, soft, 0.08),
        "btn_hover": mix(bg, soft, 0.15),
    }


def fetch_cap_raw(key):
    """读取某个胶囊的原始外观设置：返回 (bg 字符串, opacity 字符串)，都可能为空（未设置/跟随）。"""
    from ..database import SessionLocal
    from ..models import Setting

    rows = {}
    db = SessionLocal()
    try:
        for r in db.query(Setting).filter(
            Setting.key.in_([f"cap_{key}_bg", f"cap_{key}_opacity"])
        ).all():
            rows[r.key] = (r.value or "").strip()
    finally:
        db.close()
    return rows.get(f"cap_{key}_bg", ""), rows.get(f"cap_{key}_opacity", "")


def clamp_opacity(raw, fallback=100):
    try:
        op = int(float(raw)) if raw else int(fallback)
    except (TypeError, ValueError):
        op = int(fallback)
    return max(30, min(100, op))


def fetch_cap_style(key, fallback_bg="#ffffff", fallback_opacity=100):
    """读取某个胶囊的外观（空值回落 fallback）；bg_set/op_set 表示用户是否显式设置过。"""
    raw_bg, raw_op = fetch_cap_raw(key)
    bg = normalize_bg(raw_bg, fallback=normalize_bg(fallback_bg))
    return {
        "bg": bg,
        "opacity": clamp_opacity(raw_op, fallback=fallback_opacity),
        "bg_set": bool(HEX_RE.match(raw_bg or "")),
        "op_set": bool((raw_op or "").strip()),
    }


def fmt_clock(sec):
    """秒 → mm:ss / h:mm:ss（番茄钟等倒计时/正计时通用）。"""
    sec = max(0, int(sec or 0))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def fmt_hm(sec):
    """秒 → Xh Ym（考勤在岗时长等）。"""
    sec = max(0, int(sec or 0))
    h = sec // 3600
    m = (sec % 3600) // 60
    return f"{h}h {m:02d}m"


def countdown_text(delta_sec):
    """距目标时刻的简洁倒计时文案（胶囊用）。"""
    sec = int(delta_sec)
    if sec <= 0:
        return "现在"
    if sec < 3600:
        return f"{max(1, sec // 60)} 分钟后"
    if sec < 86400:
        h, m = divmod(sec // 60, 60)
        return f"{h}h{m:02d}m 后"
    days = sec // 86400
    if days == 1:
        return "明天"
    return f"{days} 天后"
