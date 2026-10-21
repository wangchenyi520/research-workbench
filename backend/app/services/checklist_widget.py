"""桌面悬浮清单（tkinter 无边框小窗口，与今日页清单双向联动）。

需求与行为（2026-10-06 用户拍板）：
- 显示今日清单：未完成在上、已完成划线沉底分组；每条只有勾选框 + 标题（简洁）。
- 打勾后划线保留不消失，再点一下取消完成（与今日页同一份勾选逻辑）。
- 窗口置顶可开关、拖动标题栏移动、拖边缘/角缩放。
- 底部输入框快速添加（回车确认，加入今日清单）。
- 开关状态 / 位置 / 大小 / 置顶全部持久化（data/checklist_widget.json），
  退出工作台时开着 → 下次启动自动恢复。
- 数据每 4 秒从数据库刷新（App 里改勾选也会同步过来）；两边操作写同一份数据。
- 最小化：收起大窗、显示独立胶囊窗口 checklist_pill（ULW 逐像素 alpha 真透明，
  可拖动、点击还原；颜色/透明度走设置页「桌面胶囊」模块）。

渲染（2026-10-12 迁移）：改用 UpdateLayeredWindow 逐像素真 alpha（与桌面胶囊同一
套光滑渲染，见「五.73」）——不再用 -transparentcolor 色键抠像 + 阈值吸附；圆角/
勾选框/文字边缘全部光滑；透明度直接烘焙进帧 alpha（ULW 不能再叠 -alpha）。实测
ULW 窗口上 tk 子控件不可见（Canvas/Entry 都被 ULW 面盖住），因此**整窗含输入框
全部 PIL 绘制**：输入框为自绘文本 + 根窗口键盘绑定（回车提交 / Backspace 退格 /
Esc 失焦 / 光标闪烁）。

架构与 pomodoro_widget 保持一致：全局唯一常驻 tkinter 线程 + 单 Tk root，
只 show/withdraw 不 destroy；线程死亡自愈（清 active + 可重建）。
"""

import json
import re
import threading
import time
from datetime import date

from ..config import DATA_DIR
from .pill_window import push_frame, reset_layered, root_hwnd, set_layered

_lock = threading.Lock()
_pref_lock = threading.Lock()
_cmds: list = []
_state = {
    "active": False,
    "topmost": True,
    "minimized": False,
}
_thread = None
_tk_ok = True
_PREF_PATH = DATA_DIR / "checklist_widget.json"
_DEFAULT_W, _DEFAULT_H = 300, 460
_MIN_W, _MIN_H = 240, 220

# ---------- 偏好持久化（开关/位置/大小/置顶/已完成折叠） ----------


def _load_pref() -> dict:
    with _pref_lock:
        return _read_pref()


def _read_pref() -> dict:
    try:
        if _PREF_PATH.exists():
            data = json.loads(_PREF_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception as e:
        print(f"[checklist-widget] load pref failed: {e}")
    return {}


def _save_pref(**kw):
    with _pref_lock:
        try:
            data = _read_pref()
            data.update(kw)
            _PREF_PATH.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            print(f"[checklist-widget] save pref failed: {e}")


# ---------- 全局状态 ----------


def _snapshot() -> dict:
    with _lock:
        return dict(_state)


def _put(cmd: dict):
    with _lock:
        _cmds.append(cmd)


def _clear_stale():
    """tkinter 线程已死但 active 残留时自愈（同 pomodoro_widget 的坑）。"""
    with _lock:
        if _state["active"] and not (_thread is not None and _thread.is_alive()):
            _state["active"] = False
            _state["minimized"] = False
            return True
    return False


def is_active() -> bool:
    _clear_stale()
    return _snapshot()["active"]


def public_state() -> dict:
    _clear_stale()
    s = _snapshot()
    return {"active": s["active"], "topmost": s["topmost"], "minimized": s["minimized"]}


def start():
    """显示悬浮清单（恢复上次位置/大小/置顶）。"""
    global _tk_ok
    if not _tk_ok:
        return False, "当前环境不支持桌面窗口"
    _clear_stale()
    _ensure_thread()
    time.sleep(0.05)
    if not _tk_ok:
        return False, "当前环境不支持桌面窗口"
    _save_pref(open=True)
    _put({"t": "show"})
    return True, "ok"


def hide():
    _clear_stale()
    if not _snapshot()["active"]:
        _save_pref(open=False)
        return False, "桌面清单未在显示"
    _save_pref(open=False)
    _put({"t": "hide"})
    return True, "ok"


def restore_from_pill():
    """胶囊被点击：命令大窗还原展开态（供 checklist_pill 调用；线程安全）。"""
    _clear_stale()
    if not _snapshot()["active"]:
        return
    _put({"t": "restore"})


_style_notify_count = 0  # 样式通知计数（测试/调试用）


def notify_style():
    """设置变更通知：命令大窗立即重读外观并应用（供设置端点调用；线程安全）。"""
    global _style_notify_count
    _style_notify_count += 1
    _clear_stale()
    if not _snapshot()["active"]:
        return
    _put({"t": "style"})


def control(action: str, value=None):
    """hide / topmost(bool) / minimize / restore"""
    if action == "hide":
        return hide()
    if action == "topmost":
        _clear_stale()
        if not _snapshot()["active"]:
            return False, "桌面清单未在显示"
        _put({"t": "topmost", "v": bool(value)})
        return True, "ok"
    if action in ("minimize", "restore"):
        _clear_stale()
        if not _snapshot()["active"]:
            return False, "桌面清单未在显示"
        _put({"t": action})
        return True, "ok"
    return False, f"未知操作 {action}"


def restore_on_startup():
    """启动时若上次退出前悬浮清单开着，则延迟 2 秒恢复。

    桌面版后端与 pywebview 同进程：在后端启动阶段创建 Tk 窗口（首次还要导入
    tkinter/PIL）会与主窗口/WebView 抢资源，导致启动变慢；延迟到主窗口加载后再弹。
    """
    if _load_pref().get("open"):
        try:
            t = threading.Timer(2.0, start)
            t.daemon = True
            t.start()
            return True, "scheduled"
        except Exception as e:
            print(f"[checklist-widget] restore failed: {e}")
    return False, "not open"


# ---------- 数据操作（供窗口线程与测试调用） ----------


def _fetch():
    """读取今日清单（未完成含顺延 + 今日已完成）。"""
    from ..database import SessionLocal
    from .daily_ops import fetch_checklist

    db = SessionLocal()
    try:
        return fetch_checklist(db)
    finally:
        db.close()


def toggle_item(item_id: int) -> bool:
    """勾选/取消勾选（与今日页同一逻辑：任务联动、目标进度、权重归一）。"""
    from ..database import SessionLocal
    from ..models import DailyItem
    from .daily_ops import set_item_status

    db = SessionLocal()
    try:
        item = db.get(DailyItem, item_id)
        if not item:
            return False
        new_status = "pending" if item.status == "done" else "done"
        return set_item_status(db, item_id, new_status)
    except Exception as e:
        print(f"[checklist-widget] toggle failed: {e}")
        return False
    finally:
        db.close()


def add_item(content: str) -> bool:
    """快速添加今日清单项（手动/重要紧急/权重 10）。"""
    from ..database import SessionLocal
    from .daily_ops import quick_add

    db = SessionLocal()
    try:
        return quick_add(db, content) is not None
    except Exception as e:
        print(f"[checklist-widget] add failed: {e}")
        return False
    finally:
        db.close()


# ---------- 常驻 tkinter 线程 ----------


def _ensure_thread():
    global _thread
    with _lock:
        if _thread is not None and _thread.is_alive():
            return
        t = threading.Thread(target=_tk_main, daemon=True, name="checklist-widget-tk")
        _thread = t
    t.start()


# 基础色（主题色对齐工作台默认紫 #6a56e8）
# 背景颜色 / 透明度 由设置项 checklist_widget_bg / checklist_widget_opacity 控制
# （在 App 设置页调整），其余颜色按背景明暗动态派生（见 _palette）。
_ACCENT = "#6a56e8"
_RED = "#d64545"
_DEFAULT_BG = "#ffffff"
_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

# 调试/测试钩子：最近一次渲染的整帧（验证透明度烘焙等；不参与业务逻辑）
_debug = {"frame": None}


def _rgb(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _lum(c):
    r, g, b = _rgb(c)
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255


def _mix(c1, c2, t):
    def _l(a, b):
        return int(round(a + (b - a) * t))
    r1, g1, b1 = _rgb(c1)
    r2, g2, b2 = _rgb(c2)
    return "#%02x%02x%02x" % (_l(r1, r2), _l(g1, g2), _l(b1, b2))


def _palette(bg):
    """按背景色明暗派生整套配色（浅色背景深文字 / 深色背景浅文字）。"""
    bg = (bg or _DEFAULT_BG).lower()
    if not _HEX_RE.match(bg):
        bg = _DEFAULT_BG
    dark = _lum(bg) < 0.52
    soft = "#ffffff" if dark else "#000000"
    txt = "#f2f0ed" if dark else "#26241f"
    accent = _ACCENT if not dark else _mix(_ACCENT, "#ffffff", 0.32)
    return {
        "card": bg,
        "border": _mix(bg, soft, 0.12),
        "header": _mix(bg, _ACCENT, 0.24 if dark else 0.10),
        "txt": txt,
        "sub": "#b8b3a8" if dark else "#8a867c",
        "muted": "#8d897f" if dark else "#b3aea3",
        "faint": "#7a766e" if dark else "#c9c4b9",
        "done": "#8f8a80" if dark else "#aaa69b",
        "hover": _mix(bg, soft, 0.06),
        "entry_bg": _mix(bg, soft, 0.05),
        "accent": accent,
        "icon": _mix(txt, bg, 0.35),
        "scroll": _mix(bg, soft, 0.16),
        "chk_outline": _mix(bg, txt, 0.40),
        "chk_bg": _mix(bg, soft, 0.07),
        "btn_hover": _mix(bg, _ACCENT, 0.14),
    }


def _fetch_style():
    """读取设置页配置的悬浮清单外观（背景色/透明度，默认白底不透明）。

    迷你胶囊的独立外观由 checklist_pill（ULW 窗口）自己读取 cap_checklist_*。
    """
    from ..database import SessionLocal
    from ..models import Setting

    rows = {}
    db = SessionLocal()
    try:
        for r in db.query(Setting).filter(
            Setting.key.in_(["checklist_widget_bg", "checklist_widget_opacity", "checklist_widget_bg_mode"])
        ).all():
            rows[r.key] = r.value
    finally:
        db.close()
    bg = rows.get("checklist_widget_bg") or _DEFAULT_BG
    if not _HEX_RE.match(bg or ""):
        bg = _DEFAULT_BG
    mode = rows.get("checklist_widget_bg_mode") or "solid"
    if mode not in ("solid", "frost", "transparent"):
        mode = "solid"
    try:
        op = int(float(rows.get("checklist_widget_opacity") or 100))
    except (TypeError, ValueError):
        op = 100
    op = max(30, min(100, op))
    return {"bg": bg.lower(), "opacity": op, "mode": mode}


def _tk_main():
    global _tk_ok
    try:
        import tkinter as tk

        from PIL import Image, ImageDraw
    except Exception as e:
        print(f"[checklist-widget] tkinter/PIL unavailable: {e}")
        _tk_ok = False
        return

    fonts = {}

    def _font(path, size):
        key = (path, size)
        if key not in fonts:
            from PIL import ImageFont

            try:
                fonts[key] = ImageFont.truetype(path, size)
            except Exception:
                fonts[key] = ImageFont.load_default()
        return fonts[key]

    try:
        SS = 2  # 形状层超采样倍率（文字 1:1 绘制）

        root = tk.Tk()
        root.title("桌面清单")
        root.overrideredirect(True)
        root.withdraw()
        root.update_idletasks()
        hwnd = root_hwnd(root)
        set_layered(hwnd)

        # 尺寸状态（UI 线程持有）
        pref = _load_pref()
        win = {
            "W": max(_MIN_W, int(pref.get("w") or _DEFAULT_W)),
            "H": max(_MIN_H, int(pref.get("h") or _DEFAULT_H)),
        }
        root.geometry(f"{win['W']}x{win['H']}+{-10000}+{-10000}")

        # 字体（Microsoft YaHei UI；图标用 Segoe MDL2 Assets）
        F_TITLE = _font("C:/Windows/Fonts/msyhbd.ttc", 16)
        F_SUB = _font("C:/Windows/Fonts/msyh.ttc", 11)
        F_ROW = _font("C:/Windows/Fonts/msyh.ttc", 13)
        F_SECTION = _font("C:/Windows/Fonts/msyh.ttc", 12)
        F_EMPTY = _font("C:/Windows/Fonts/msyh.ttc", 12)
        F_TIP = _font("C:/Windows/Fonts/msyh.ttc", 12)
        F_INPUT = _font("C:/Windows/Fonts/msyh.ttc", 13)
        F_ICON = _font("C:/Windows/Fonts/segmdl2.ttf", 15)
        F_CHEV = _font("C:/Windows/Fonts/segmdl2.ttf", 12)

        _meas = ImageDraw.Draw(Image.new("L", (1, 1)))

        def draw_sym(d, sym, font, fill, cx, cy, stroke=False):
            """画字形符号：按真实字形包围盒把视觉中心校正到 (cx, cy)。"""
            l, t, r, b = d.textbbox((0, 0), sym, font=font)
            kw = {"stroke_width": 1, "stroke_fill": "#ffffff"} if stroke else {}
            d.text((cx - (l + r) / 2, cy - (t + b) / 2), sym, font=font, fill=fill, **kw)

        # 当前配色（随设置页的背景色动态派生）
        pal = [_palette(_DEFAULT_BG)]
        opacity = [100]

        # 行/数据缓存
        data_cache = {"pending": [], "done": []}
        rows = []            # [{y0, y1, kind, id, content, truncated, hit_top, hit_bottom}]
        scroll = [0.0]
        hover_btn = [None]
        hover_hit = [None]   # "i<id>" / "sec" / None
        done_collapsed = [bool(pref.get("done_collapsed"))]
        last_load = [0.0]
        press_state = [None]  # 正被按住的小圆圈（item id）
        pop = [None]          # 松开后的回弹动画 {id, frames, i}
        pop_after = [None]
        transparent = [False]  # 背景纯透明模式（卡片底去掉，桌面完全透出，文字带描边）

        # 自绘输入框状态（ULW 窗口上原生 Entry 不可见，必须 PIL 绘制 + 键盘绑定）
        PLACEHOLDER = "添加任务"
        inp = {"text": "", "focused": False, "err": False}
        caret_phase = [0]

        # 布局常量
        HEADER_H = 52        # 标题带高度
        ROW_H = 34           # 行高
        INPUT_H = 48         # 底部添加区高度

        # ---------- 整帧渲染（形状 2× 超采样 → LANCZOS；文字 1:1） ----------
        def _ellipsis(text, max_w):
            if _meas.textlength(text, font=F_ROW) <= max_w:
                return text
            ell = "…"
            while text and _meas.textlength(text + ell, font=F_ROW) > max_w:
                text = text[:-1]
            return text + ell

        def render_frame():
            W, H = win["W"], win["H"]
            p = pal[0]
            tr = transparent[0]
            list_top = HEADER_H + 10
            list_bottom = H - INPUT_H - 8
            list_h = max(10, list_bottom - list_top)
            pend, done = data_cache["pending"], data_cache["done"]
            total = len(pend) + len(done)

            # ---- 组装行序列：未完成 → 「已完成 N」分组（可折叠）→ 已完成（划线） ----
            seq = []
            for it in pend:
                seq.append(("item", it, False))
            if done:
                seq.append(("section", f"已完成 {len(done)}", None))
                if not done_collapsed[0]:
                    for it in done:
                        seq.append(("item", it, True))
            content_h = len(seq) * ROW_H
            max_scroll = max(0, content_h - list_h)
            scroll[0] = max(0.0, min(scroll[0], max_scroll))

            vis = []
            rows.clear()
            for idx, (kind, payload, is_done) in enumerate(seq):
                y0 = list_top + idx * ROW_H - scroll[0]
                y1 = y0 + ROW_H
                if y1 < list_top or y0 > list_bottom:
                    continue
                cy = y0 + ROW_H / 2
                key = "sec" if kind == "section" else f"i{payload['id']}"
                hovered = hover_hit[0] == key and y0 >= list_top - ROW_H
                rec = {"kind": kind, "y0": y0, "y1": y1, "cy": cy, "hover": hovered,
                       "id": None, "text": "", "trunc": False, "scale": 1.0,
                       "press": False, "done": bool(is_done)}
                if kind == "item":
                    it = payload
                    txt = _ellipsis(it["content"], W - 66)
                    scale, pressed = 1.0, False
                    if press_state[0] == it["id"]:
                        scale, pressed = 0.78, True
                    elif pop[0] and pop[0]["id"] == it["id"]:
                        scale = pop[0]["frames"][pop[0]["i"]]
                    rec.update(id=it["id"], text=txt, trunc=(txt != it["content"]),
                               scale=scale, press=pressed)
                    rows.append({"y0": y0, "y1": y1, "kind": "item", "id": it["id"],
                                 "content": it["content"], "truncated": txt != it["content"],
                                 "hit_top": list_top, "hit_bottom": list_bottom})
                else:
                    rec["text"] = payload
                    rows.append({"y0": y0, "y1": y1, "kind": "section", "id": None,
                                 "hit_top": list_top, "hit_bottom": list_bottom})
                vis.append(rec)

            # ---- 形状层（SS 超采样；末尾统一 LANCZOS 降采样） ----
            im = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)

            def P(v):
                return v * SS

            if not tr:
                # 卡片底
                d.rounded_rectangle([P(3), P(3), P(W - 3), P(H - 3)], radius=P(14), fill=p["card"])
                # 标题带（只圆上两角）
                d.rounded_rectangle([P(3), P(3), P(W - 3), P(HEADER_H)], radius=P(14), fill=p["header"])
                d.rectangle([P(3), P(HEADER_H - 14), P(W - 3), P(HEADER_H)], fill=p["header"])
                # 卡片描边
                d.rounded_rectangle([P(4), P(4), P(W - 4), P(H - 4)], radius=P(13),
                                    outline=p["border"], width=SS)
            # 底部添加条（两种模式都保留：输入需要可见底）
            pill_top, pill_bot = H - 48, H - 14
            d.rounded_rectangle([P(12), P(pill_top), P(W - 12), P(pill_bot)], radius=P(17),
                                fill=p["entry_bg"])

            # 空态水印（淡淡圆勾）
            if not seq:
                wcx, wcy = W / 2, list_top + 46
                wcol = _mix(p["card"], "#ffffff" if _lum(p["card"]) < 0.52 else "#000000", 0.11)
                wcol2 = _mix(p["card"], "#ffffff" if _lum(p["card"]) < 0.52 else "#000000", 0.14)
                d.ellipse([P(wcx - 20), P(wcy - 20), P(wcx + 20), P(wcy + 20)],
                          outline=wcol, width=int(2 * SS))
                pts = [(wcx - 9, wcy + 1), (wcx - 2, wcy + 8), (wcx + 11, wcy - 6.5)]
                d.line([P(pts[0][0]), P(pts[0][1]), P(pts[1][0]), P(pts[1][1]),
                        P(pts[2][0]), P(pts[2][1])], fill=wcol2, width=int(3 * SS), joint="curve")

            # 行（悬停底 + 勾选框）
            for r in vis:
                if r["hover"] and not tr:
                    d.rectangle([P(8), P(max(r["y0"] + 1, list_top - 4)),
                                 P(W - 8), P(min(r["y1"] - 1, list_bottom + 4))], fill=p["hover"])
                if r["kind"] == "item":
                    cy = r["cy"]
                    scale, is_done = r["scale"], r["done"]
                    cx, rr_ = 22, 8 * scale
                    if is_done:
                        fill = _mix(p["accent"], "#000000", 0.10) if r["press"] else p["accent"]
                        d.ellipse([P(cx - rr_), P(cy - rr_), P(cx + rr_), P(cy + rr_)], fill=fill)
                        m = lambda x, y: (P(cx + (x - 10) * scale), P(cy + (y - 10) * scale))  # noqa: E731
                        d.line([m(6, 10.4), m(8.8, 13.2), m(14.2, 6.8)], fill="#ffffff",
                               width=max(1, int(2.1 * SS * scale)), joint="curve")
                    else:
                        fill = _mix(p["chk_bg"], p["accent"], 0.16) if r["press"] else p["chk_bg"]
                        outline = _mix(p["chk_outline"], p["accent"], 0.55) if r["press"] else p["chk_outline"]
                        if tr:  # 纯透明模式：白色描边保证任何壁纸可辨
                            d.ellipse([P(cx - rr_ - 1), P(cy - rr_ - 1), P(cx + rr_ + 1), P(cy + rr_ + 1)],
                                      outline="#ffffff", width=max(1, int(1.2 * SS)))
                        d.ellipse([P(cx - rr_), P(cy - rr_), P(cx + rr_), P(cy + rr_)],
                                  fill=fill, outline=outline, width=max(1, int(1.5 * SS * scale)))

            # 细滚动条
            if max_scroll > 0:
                bar_h = max(24, list_h * list_h / content_h)
                bar_y = list_top + (list_h - bar_h) * (scroll[0] / max_scroll)
                d.rectangle([P(W - 8), P(bar_y), P(W - 4), P(bar_y + bar_h)], fill=p["scroll"])

            # 标题带按钮悬停底
            for name, (cx, cy) in _btn_positions(win["W"]).items():
                if hover_btn[0] == name:
                    d.ellipse([P(cx - BTN_R), P(cy - BTN_R), P(cx + BTN_R), P(cy + BTN_R)],
                              fill=p["btn_hover"])

            # 悬停提示气泡底（深色圆角，Windows 风格）
            tip_rec = tip_state[0]
            if tip_rec is not None:
                x0, y0, tw, th = tip_rec["x0"], tip_rec["y0"], tip_rec["tw"], tip_rec["th"]
                d.rounded_rectangle([P(x0), P(y0), P(x0 + tw), P(y0 + th)], radius=P(7),
                                    fill="#2f2f34", outline="#4c4c55", width=SS)

            # ---- 降采样 → 文字层（1:1，清晰） ----
            im = im.resize((W, H), Image.LANCZOS)
            d = ImageDraw.Draw(im)

            def T(x, y, text, font, fill, anchor="lm"):
                if tr:
                    d.text((x, y), text, font=font, fill=fill, anchor=anchor,
                           stroke_width=1, stroke_fill="#ffffff")
                else:
                    d.text((x, y), text, font=font, fill=fill, anchor=anchor)

            # 标题 + 日期/进度
            T(18, 19, "今日清单", F_TITLE, p["accent"])
            sub = f"{date.today().isoformat()} · 已完成 {len(done)}/{total}" if total else date.today().isoformat()
            T(18, 38, sub, F_SUB, p["sub"])

            # 空态文案
            if not seq:
                T(W / 2, list_top + 88, "今天还没有安排", F_EMPTY, p["muted"], anchor="mm")
                T(W / 2, list_top + 110, "在下方添加任务", F_EMPTY, p["faint"], anchor="mm")

            # 行文字
            for r in vis:
                cy = r["cy"]
                if r["kind"] == "section":
                    chev = "\uE76C" if done_collapsed[0] else "\uE70D"
                    draw_sym(d, chev, F_CHEV, p["sub"], 24, cy, stroke=tr)
                    T(42, cy, r["text"], F_SECTION, p["sub"])
                    continue
                col = p["done"] if r["done"] else p["txt"]
                T(44, cy, r["text"], F_ROW, col)
                if r["done"]:  # 划线（PIL 无 overstrike，手绘）
                    tw_ = _meas.textlength(r["text"], font=F_ROW)
                    d.line([(44, cy), (44 + tw_, cy)], fill=col, width=1)

            # 按钮图标（Segoe MDL2）
            for name, (cx, cy) in _btn_positions(W).items():
                if name == "pin":
                    pinned = _snapshot()["topmost"]
                    sym = "\uE718" if pinned else "\uE77A"
                    color = p["accent"] if pinned else p["icon"]
                elif name == "min":
                    sym, color = "\uE921", p["icon"]
                else:
                    sym, color = "\uE711", p["icon"]
                draw_sym(d, sym, F_ICON, color, cx, cy, stroke=tr)

            # 底部添加条：加号 + 输入文本/占位/光标
            draw_sym(d, "\uE710", F_ICON, p["accent"], 28, H - 31, stroke=tr)
            txt = inp["text"]
            if not txt and not inp["focused"]:
                T(46, H - 31, PLACEHOLDER, F_INPUT, p["muted"])
            else:
                col = _RED if inp["err"] else p["txt"]
                show = _ellipsis_input(txt)
                T(46, H - 31, show, F_INPUT, col)
                if inp["focused"] and caret_phase[0] == 0:
                    cx = 46 + _meas.textlength(show, font=F_INPUT) + 2
                    d.line([(cx, H - 39), (cx, H - 22)], fill=p["txt"], width=1)

            # 提示气泡文字
            if tip_rec is not None:
                x0, y0 = tip_rec["x0"], tip_rec["y0"]
                for i, line in enumerate(tip_rec["lines"]):
                    d.text((x0 + 10, y0 + 7 + i * (F_TIP.size + 3)), line, font=F_TIP, fill="#f3f2ee")

            # 整窗透明（烘焙进帧 alpha；纯透明模式不施加，保证内容清晰）
            if not tr and opacity[0] < 100:
                a = im.getchannel("A").point(lambda v: int(v * opacity[0] / 100))
                im.putalpha(a)
            return im

        def _ellipsis_input(text):
            max_w = win["W"] - 70 - 8
            if _meas.textlength(text, font=F_INPUT) <= max_w:
                return text
            while text and _meas.textlength("…" + text, font=F_INPUT) > max_w:
                text = text[1:]
            return "…" + text

        def render():
            if _snapshot()["minimized"] or not _snapshot()["active"]:
                return
            try:
                if root.state() != "normal":
                    return
            except Exception:
                return
            try:
                img = render_frame()
            except Exception as e:
                print(f"[checklist-widget] render failed: {e}")
                return
            _debug["frame"] = img
            if not push_frame(hwnd, img):
                reset_layered(hwnd)
                if not push_frame(hwnd, img):
                    print("[checklist-widget] push frame failed")

        # ---------- 悬停提示（超长标题显示完整内容，Windows 风格深色气泡） ----------
        tip_state = [None]     # {lines, x0, y0, tw, th}
        tip_after = [None]
        tip_pending_for = [None]
        tip_shown_for = [None]

        def hide_tip():
            if tip_after[0]:
                try:
                    root.after_cancel(tip_after[0])
                except Exception:
                    pass
                tip_after[0] = None
            tip_pending_for[0] = None
            if tip_state[0] is not None or tip_shown_for[0] is not None:
                tip_state[0] = None
                tip_shown_for[0] = None
                render()

        def _wrap_text(text, max_w):
            lines, cur = [], ""
            for ch in text:
                if not cur or _meas.textlength(cur + ch, font=F_TIP) <= max_w:
                    cur += ch
                else:
                    lines.append(cur)
                    cur = ch
            if cur:
                lines.append(cur)
            return lines[:4]

        def _fire_tip(row):
            tip_after[0] = None
            tip_pending_for[0] = None
            W, H = win["W"], win["H"]
            # 校验指针仍在窗口内、仍悬停在该行上：防止「移出窗口」时队列里迟到的
            # Motion 事件把气泡又画出来（画完鼠标已在窗外、无人收起 → 残留，用户反馈 bug）
            px = root.winfo_pointerx() - root.winfo_x()
            py = root.winfo_pointery() - root.winfo_y()
            if not (0 <= px < W and 0 <= py < H):
                return
            if not (row["y0"] <= py <= row["y1"]):
                return
            max_w = W - 40
            lines = _wrap_text(row["content"], max_w)
            if not lines:
                return
            tw = int(min(max_w, max(_meas.textlength(l, font=F_TIP) for l in lines))) + 20
            th = len(lines) * (F_TIP.size + 5) + 14
            x0 = 10
            y_above = row["y0"] - th - 6
            y0 = y_above if y_above >= 6 else min(row["y1"] + 6, H - 10 - th)
            y0 = max(6, y0)
            tip_state[0] = {"lines": lines, "x0": x0, "y0": y0, "tw": tw, "th": th}
            tip_shown_for[0] = row["id"]
            render()

        def _schedule_tip(row):
            rid = row["id"]
            if tip_shown_for[0] == rid or tip_pending_for[0] == rid:
                return
            hide_tip()
            tip_pending_for[0] = rid
            tip_after[0] = root.after(350, lambda r=row: _fire_tip(r))

        # ---------- 标题带按钮（MDL2 线性图标 + 悬停浅底，To Do 式） ----------
        BTN_R = 13
        BTN_CY = 27

        def _btn_positions(W):
            return {"pin": (W - 86, BTN_CY), "min": (W - 56, BTN_CY), "close": (W - 26, BTN_CY)}

        # ---------- 交互 ----------
        # 无边框窗客户区与窗口矩形存在坐标差，感应边取 16px（实际可见约 13px），
        # 保证四角/四边都容易拖到
        M = 16  # 缩放感应边宽
        drag = {"on": False, "dx": 0, "dy": 0}
        resize = {"on": False, "zone": "", "rx": 0, "ry": 0, "x": 0, "y": 0, "w": 0, "h": 0, "last": 0.0}

        def zone_at(x, y, W, H):
            if x >= W or y >= H or x < 0 or y < 0:
                return ""
            left = x <= M
            right = x >= W - M
            top = y <= M
            bottom = y >= H - M
            if top and left:
                return "nw"
            if top and right:
                return "ne"
            if bottom and left:
                return "sw"
            if bottom and right:
                return "se"
            if left:
                return "w"
            if right:
                return "e"
            if top:
                return "n"
            if bottom:
                return "s"
            return ""

        CURSORS = {"nw": "size_nw_se", "se": "size_nw_se", "ne": "size_ne_sw", "sw": "size_ne_sw",
                   "n": "size_ns", "s": "size_ns", "w": "size_we", "e": "size_we"}

        def btn_at(x, y, W):
            for name, (cx, cy) in _btn_positions(W).items():
                if (x - cx) ** 2 + (y - cy) ** 2 <= (BTN_R + 4) ** 2:
                    return name
            return None

        def row_at(x, y):
            for r in rows:
                if r["hit_top"] <= y <= r["hit_bottom"] and r["y0"] <= y <= r["y1"]:
                    return r
            return None

        # ---------- 自绘输入框 ----------
        def input_focus():
            inp["focused"] = True
            inp["err"] = False
            try:
                root.focus_force()
            except Exception:
                pass
            render()

        def input_blur():
            if inp["focused"]:
                inp["focused"] = False
                render()

        def input_submit():
            txt = inp["text"].strip()
            if not txt:
                return
            ok = add_item(txt)
            if ok:
                inp["text"] = ""
                inp["err"] = False
                refresh(force=True)
            else:
                inp["err"] = True
            render()

        def on_key(e):
            if not inp["focused"] or _snapshot()["minimized"]:
                return
            if e.keysym == "Return":
                input_submit()
            elif e.keysym == "BackSpace":
                if inp["text"]:
                    inp["text"] = inp["text"][:-1]
                    inp["err"] = False
                    render()
            elif e.keysym == "Escape":
                input_blur()
            elif e.char and e.char.isprintable() and not (e.state & 0x4):
                inp["text"] += e.char
                inp["err"] = False
                render()

        def on_press(e):
            W, H = win["W"], win["H"]
            z = zone_at(e.x, e.y, W, H)
            if z:
                resize.update(on=True, zone=z, rx=e.x_root, ry=e.y_root,
                              x=root.winfo_x(), y=root.winfo_y(), w=W, h=H, last=0.0)
                return
            b = btn_at(e.x, e.y, W)
            if b == "pin":
                control("topmost", not _snapshot()["topmost"])
                return
            if b == "min":
                minimize_to_mini()
                return
            if b == "close":
                hide()
                return
            if e.y <= HEADER_H:  # 标题带（按钮区之外）→ 拖动
                drag.update(on=True, dx=e.x_root - root.winfo_x(), dy=e.y_root - root.winfo_y())
                return
            if e.y >= H - INPUT_H:  # 底部添加区：点空白也聚焦输入框
                if e.y >= H - 44:
                    input_focus()
                return
            input_blur()
            hit = row_at(e.x, e.y)
            if hit is not None:
                if hit["kind"] == "section":
                    done_collapsed[0] = not done_collapsed[0]
                    _save_pref(done_collapsed=done_collapsed[0])
                    render()
                elif hit["id"]:
                    # 只有点中「小圆圈」才切换完成；点文字不触发（用户 2026-10-06 拍板）
                    cy = (hit["y0"] + hit["y1"]) / 2
                    if (e.x - 22) ** 2 + (e.y - cy) ** 2 <= 16 ** 2:
                        hide_tip()
                        press_state[0] = hit["id"]   # 按下缩小（Windows 式按压反馈）
                        render()
                return
            # 列表空白区域也可拖动（方便小窗移动）
            drag.update(on=True, dx=e.x_root - root.winfo_x(), dy=e.y_root - root.winfo_y())

        def on_move(e):
            if resize["on"]:
                _do_resize(e)
                return
            if drag["on"]:
                root.geometry(f"+{e.x_root - drag['dx']}+{e.y_root - drag['dy']}")
                return
            # hover 反馈 + 光标（只有小圆圈是手型；超长标题悬停出完整内容提示）
            W, H = win["W"], win["H"]
            z = zone_at(e.x, e.y, W, H)
            cur = CURSORS.get(z, "")
            b = btn_at(e.x, e.y, W)
            hit = None
            over_check = False
            if not cur and not b and HEADER_H < e.y < H - INPUT_H:
                hit = row_at(e.x, e.y)
                if hit is not None and hit["kind"] == "item":
                    cy = (hit["y0"] + hit["y1"]) / 2
                    over_check = (e.x - 22) ** 2 + (e.y - cy) ** 2 <= 16 ** 2
            if b or over_check:
                cur = "hand2"
            if (root.cget("cursor") or "") != cur:
                try:
                    root.configure(cursor=cur)
                except Exception:
                    pass
            if b != hover_btn[0]:
                hover_btn[0] = b
                render()
            new_hover = None
            if hit is not None:
                new_hover = "sec" if hit["kind"] == "section" else f"i{hit['id']}"
            if new_hover != hover_hit[0]:
                hover_hit[0] = new_hover
                render()
            # 按住移出小圆圈 → 取消按下态（Windows 按压直觉）
            if press_state[0] is not None:
                still = False
                if hit is not None and hit["id"] == press_state[0]:
                    cy = (hit["y0"] + hit["y1"]) / 2
                    still = (e.x - 22) ** 2 + (e.y - cy) ** 2 <= 18 ** 2
                if not still:
                    press_state[0] = None
                    render()
            if hit is not None and hit["kind"] == "item" and hit.get("truncated"):
                _schedule_tip(hit)
            else:
                hide_tip()

        def start_pop(item_id):
            """松开后的回弹动画：0.84 → 0.93 → 1.0（约 110ms），有 Windows 式灵动感。"""
            if pop_after[0]:
                try:
                    root.after_cancel(pop_after[0])
                except Exception:
                    pass
                pop_after[0] = None
            pop[0] = {"id": item_id, "frames": [0.84, 0.93], "i": 0}

            def step():
                pop_after[0] = None
                if not pop[0]:
                    return
                pop[0]["i"] += 1
                if pop[0]["i"] < len(pop[0]["frames"]):
                    render()
                    pop_after[0] = root.after(55, step)
                else:
                    pop[0] = None
                    render()

            render()
            pop_after[0] = root.after(55, step)

        def on_release(e):
            if resize["on"]:
                _do_resize(e, force=True)  # 按松手时的最终坐标定稿（拖拽节流可能少算最后几帧）
                resize["on"] = False
                _persist_geometry()
                render()
            if drag["on"]:
                drag["on"] = False
                _persist_geometry()
            if press_state[0] is not None:
                item_id = press_state[0]
                press_state[0] = None
                # 松开时仍在小圆圈内才触发完成（按住移出=取消，符合 Windows 按压直觉）
                hit = row_at(e.x, e.y)
                fire = False
                if hit is not None and hit["id"] == item_id:
                    cy = (hit["y0"] + hit["y1"]) / 2
                    fire = (e.x - 22) ** 2 + (e.y - cy) ** 2 <= 18 ** 2
                if fire and toggle_item(item_id):
                    start_pop(item_id)
                    refresh(force=True)
                else:
                    render()

        def _do_resize(e, force=False):
            dx, dy = e.x_root - resize["rx"], e.y_root - resize["ry"]
            z = resize["zone"]
            x, y, w, h = resize["x"], resize["y"], resize["w"], resize["h"]
            if "e" in z:
                w = resize["w"] + dx
            if "s" in z:
                h = resize["h"] + dy
            if "w" in z:
                w = resize["w"] - dx
                x = resize["x"] + dx
            if "n" in z:
                h = resize["h"] - dy
                y = resize["y"] + dy
            w = max(_MIN_W, int(w))
            h = max(_MIN_H, int(h))
            if "w" in z:
                x = resize["x"] + resize["w"] - w
            if "n" in z:
                y = resize["y"] + resize["h"] - h
            win["W"], win["H"] = w, h
            root.geometry(f"{w}x{h}+{int(x)}+{int(y)}")
            # 拖动过程节流重建（60ms），松手时再按最终坐标定稿一次
            now = time.monotonic()
            if force or now - resize["last"] >= 0.06:
                resize["last"] = now
                render()

        def _persist_geometry():
            try:
                _save_pref(open=True, x=root.winfo_x(), y=root.winfo_y(), w=win["W"], h=win["H"])
            except Exception:
                pass

        root.bind("<Button-1>", on_press)
        root.bind("<B1-Motion>", on_move)
        root.bind("<ButtonRelease-1>", on_release)
        root.bind("<Motion>", on_move)
        root.bind("<MouseWheel>", lambda e: _wheel(e))
        root.bind("<Key>", on_key)

        def _on_leave(_e=None):
            hide_tip()

        root.bind("<Leave>", _on_leave)

        def _wheel(e):
            H = win["H"]
            list_h = max(10, (H - INPUT_H - 8) - (HEADER_H + 10))
            content_h = _seq_len() * ROW_H
            max_scroll = max(0, content_h - list_h)
            if max_scroll <= 0:
                return
            hide_tip()
            scroll[0] = max(0.0, min(max_scroll, scroll[0] - (e.delta / 120) * 40))
            render()

        def _seq_len():
            pend, done = data_cache["pending"], data_cache["done"]
            n = len(pend)
            if done:
                n += 1 + (0 if done_collapsed[0] else len(done))
            return n

        # ---------- 数据/外观刷新 ----------
        style_cache = [None]

        def apply_style(style):
            """应用设置页配置的背景色/背景效果/透明度（重建配色 + 把透明度烘焙进帧）。"""
            transparent[0] = style.get("mode") == "transparent"
            # 纯透明模式背景未知（桌面），固定用深色文字 + 白色描边，任何壁纸下都清晰
            pal[0] = _palette(_DEFAULT_BG if transparent[0] else style["bg"])
            opacity[0] = 100 if transparent[0] else int(style["opacity"])
            render()

        def refresh(force=False):
            now = time.monotonic()
            if not force and now - last_load[0] < 4.0:
                return
            last_load[0] = now
            try:
                data = _fetch()
                style = _fetch_style()
            except Exception as e:
                print(f"[checklist-widget] fetch failed: {e}")
                return
            if style != style_cache[0]:
                style_cache[0] = style
                apply_style(style)
            if force or data != data_cache:
                data_cache.update(data)
                render()

        # ---------- 最小化：收起大窗、交给独立胶囊窗口 checklist_pill ----------
        def minimize_to_mini():
            """最小化：收起大窗，显示桌面胶囊（ULW 真 alpha 渲染，可拖动/点击还原）。"""
            if _snapshot()["minimized"]:
                return
            _persist_geometry()  # 保存展开态的位置/大小
            with _lock:
                _state["minimized"] = True
            _save_pref(minimized=True)
            from . import checklist_pill

            checklist_pill.PILL.start()
            root.withdraw()

        def restore_mini():
            """还原展开态：隐藏胶囊，回到最小化前的位置/大小与置顶设置。"""
            if not _snapshot()["minimized"]:
                return
            with _lock:
                _state["minimized"] = False
            _save_pref(minimized=False)
            from . import checklist_pill

            checklist_pill.PILL.hide()
            # 注意顺序：先切置顶再定位置——Windows 上 attributes("-topmost") 会重新应用
            # Tk 记住的位置，若放在 geometry 之后会把刚设置的位置覆盖掉（坑 #94）
            apply_topmost(_snapshot()["topmost"])
            place_window()
            root.deiconify()
            reset_layered(hwnd)  # withdraw→显示后 layered surface 失效，先重设再提交
            refresh(force=True)
            render()

        # ---------- 命令处理 ----------
        def place_window():
            pref = _load_pref()
            W, H = win["W"], win["H"]
            sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
            x = pref.get("x")
            y = pref.get("y")
            if x is None or y is None:
                x, y = sw - W - 44, 100
            x = max(-W + 80, min(int(x), sw - 80))
            y = max(0, min(int(y), sh - 60))
            root.geometry(f"{W}x{H}+{int(x)}+{int(y)}")

        def apply_topmost(v):
            with _lock:
                _state["topmost"] = bool(v)
            try:
                root.attributes("-topmost", bool(v))
            except Exception:
                pass
            _save_pref(topmost=bool(v))
            render()

        def handle(c):
            t = c["t"]
            if t == "show":
                with _lock:
                    _state["active"] = True
                    _state["minimized"] = bool(_load_pref().get("minimized"))
                if _snapshot()["minimized"]:
                    # 上次退出时是最小化状态 → 显示桌面胶囊（大窗保持收起）
                    from . import checklist_pill

                    checklist_pill.PILL.start()
                    root.withdraw()
                else:
                    apply_topmost(_load_pref().get("topmost", True))  # 先切置顶再定位置（坑 #94）
                    place_window()
                    root.deiconify()
                    reset_layered(hwnd)
                    refresh(force=True)   # 拉数据并渲染（先渲染再显示由 deiconify+render 顺序保证）
                    render()
            elif t == "minimize":
                minimize_to_mini()
            elif t == "restore":
                restore_mini()
            elif t == "hide":
                with _lock:
                    _state["active"] = False
                    _state["minimized"] = False
                hide_tip()
                try:
                    root.configure(cursor="")
                except Exception:
                    pass
                root.withdraw()
                from . import checklist_pill

                checklist_pill.PILL.hide()  # 最小化状态下关闭 = 同时收起胶囊
            elif t == "topmost":
                apply_topmost(c.get("v"))
            elif t == "style":
                # 设置页改颜色/透明度后立即生效（不等 4 秒轮询兜底）
                try:
                    st = _fetch_style()
                except Exception:
                    st = None
                if st is not None and st != style_cache[0]:
                    style_cache[0] = st
                    apply_style(st)
            elif t == "quit":
                with _lock:
                    _state["active"] = False
                hide_tip()
                root.withdraw()

        def loop():
            try:
                with _lock:
                    pending = list(_cmds)
                    _cmds.clear()
                for c in pending:
                    handle(c)
                s = _snapshot()
                if s["active"] and not s["minimized"]:
                    refresh(force=False)
                    # 自绘输入框光标闪烁（500ms 相位翻转，仅在聚焦时）
                    if inp["focused"]:
                        ph = int(time.monotonic() * 2) % 2
                        if ph != caret_phase[0]:
                            caret_phase[0] = ph
                            render()
                    # 兜底：气泡还在但指针已移出窗口（跨窗口 Leave 偶发丢失）→ 收起
                    if tip_state[0] is not None:
                        px = root.winfo_pointerx() - root.winfo_x()
                        py = root.winfo_pointery() - root.winfo_y()
                        if not (0 <= px < win["W"] and 0 <= py < win["H"]):
                            hide_tip()
            except Exception as e:
                print(f"[checklist-widget] loop error: {e}")
            root.after(150, loop)

        root.withdraw()
        root.after(200, loop)
        root.mainloop()
    except Exception as e:
        print(f"[checklist-widget] tk main failed: {e}")
        _tk_ok = False
    finally:
        with _lock:
            _state["active"] = False
        try:
            root.destroy()
        except Exception:
            pass
