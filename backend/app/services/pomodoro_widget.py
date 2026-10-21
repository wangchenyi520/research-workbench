"""桌面悬浮番茄钟（tkinter 无边框小窗口，Win11 Fluent 风格）。

架构要点：
- 全局唯一常驻 tkinter 线程 + 单一 Tk root（进程内只创建一次）。
  反复跨线程创建/销毁 Tk 会触发 Tcl_AsyncDelete 崩溃并杀掉整个后端，
  因此这里只做 show/withdraw，绝不 destroy。
- 外观：深色玻璃质感圆角卡片 + 渐变发光进度环 + 运行呼吸脉冲 +
  大号等宽数字 + 圆形图标按钮（hover 反馈）+ 轻微整窗透明。
- 渲染（2026-10-12 迁移）：改用 UpdateLayeredWindow 逐像素真 alpha（与桌面胶囊
  同一套光滑渲染，见「五.73」）——不再用 -transparentcolor 色键抠像 + 阈值
  吸附（过渡像素要么被切锯齿要么留灰边）。整帧 PIL 渲染：形状层 2× 超采样 →
  LANCZOS 降采样（含文字），提交前由 push_frame 自动预乘 alpha。
- 拖动：标准公式 new_pos = 鼠标屏幕坐标 - 按下时指针在窗内偏移，
  不依赖滞后的 winfo 值（否则 Windows 上快速拖动会发散“飞走”）。
- 倒计时 monotonic 整秒累计；结束/完成时把「实际计秒数」写回 TimeLog，
  暂停期间不计入时长。
"""

import math
import threading
import time
from datetime import datetime

from .pill_window import push_frame, reset_layered, root_hwnd, set_layered

_lock = threading.Lock()
_cmds: list = []
_gen = 0
_state = {
    "active": False,
    "phase": "work",        # work / break
    "paused": False,
    "mode": "tomato",       # tomato（倒计时轮次）/ free（秒表累计）
    "remaining": 0,
    "work_total": 0,
    "break_total": 0,
    "elapsed": 0,           # free 模式已计秒（暂停不计）
    "task_id": None,
    "log_id": None,
    "session_id": None,     # 自由番茄钟 session（不绑定任务）
    "title": "",
    "topmost": True,
    "mini": False,          # 迷你胶囊模式（缩成小条，大钟的替代形态）
}
_thread_started = False
_thread = None              # 常驻 tkinter 线程对象（用于存活检测/自愈）
_tk_ok = True
_free_handler = None        # 自由番茄钟事件回调（free_pomodoro 模块注册）


def _snapshot() -> dict:
    with _lock:
        return dict(_state)


def _put(cmd: dict):
    with _lock:
        _cmds.append(cmd)


def set_free_handler(fn):
    """注册自由番茄钟事件回调（round_done / skip_break / rest_done / finish / abandon）。"""
    global _free_handler
    _free_handler = fn


def _free_handle(evt: str):
    """向自由番茄钟模块转发事件（模块级注册，避免循环 import）。"""
    fn = _free_handler
    session_id = _snapshot().get("session_id")
    if not fn or not session_id:
        return
    try:
        fn(evt, session_id)
    except Exception as e:
        print(f"[pomodoro-widget] free handler failed: {e}")


def _clear_stale():
    """tkinter 线程已死但 active 残留时自愈。

    线程异常退出（如 Tcl 错误导致 mainloop 返回）后 _state["active"] 会永久卡 True，
    命令全部积压不处理——表现为桌面钟不显示、且互斥检查永远拦截自由番茄钟。
    """
    with _lock:
        if _state["active"] and not (_thread is not None and _thread.is_alive()):
            _state["active"] = False
            _state["paused"] = False
            return True
    return False


def is_active() -> bool:
    _clear_stale()
    return _snapshot()["active"]


def public_state() -> dict:
    """对外状态快照（先做陈旧状态自愈，供路由 /state 使用）。"""
    _clear_stale()
    return _snapshot()


def start(task_id, log_id, title: str, work_min: int, break_min: int, session_id=None, mode="tomato", elapsed_init=0,
          remaining=None, phase="work", paused=False):
    """显示桌面时钟并开始计时。

    task_id/log_id 可空：自由番茄钟模式（session_id 关联 free_pomodoro session）。
    mode="free"：秒表式累计（work_min 无意义，显示已计时长），✓=结束专注；
    elapsed_init：自由秒表接管前的已有秒数（页面/后台已计的时间不倒退）。
    mode="tomato"：固定时长倒计时，轮次/休息流转。
    remaining/phase/paused：仅「退出暂停保存」的启动恢复使用——按快照恢复
    剩余时长与阶段（work/break）并以暂停状态显示，点继续接着计。
    """
    global _gen
    if not _tk_ok:
        return False, "当前环境不支持桌面窗口"
    _clear_stale()
    snap = _snapshot()
    if snap["active"] and (snap["log_id"] != log_id or snap["session_id"] != session_id):
        return False, f"桌面时钟正在运行「{snap['title'][:12]}」，请先完成或放弃"
    _ensure_thread()
    time.sleep(0.05)
    if not _tk_ok:
        return False, "当前环境不支持桌面窗口"
    is_free = mode == "free"
    _gen += 1
    work_total = 0 if is_free else max(60, int(work_min) * 60)
    break_total = max(0, int(break_min) * 60)
    ph = phase if phase in ("work", "break") else "work"
    if is_free:
        rem = 0
    elif remaining is None:
        rem = work_total if ph == "work" else break_total
    else:
        cap = work_total if ph == "work" else break_total
        rem = max(0, min(cap, int(remaining)))
    with _lock:
        _state.update(
            active=True, phase=ph, paused=bool(paused),
            mode="free" if is_free else "tomato",
            remaining=rem,
            work_total=work_total,
            break_total=break_total,
            elapsed=max(0, int(elapsed_init)),
            task_id=task_id, log_id=log_id, session_id=session_id,
            title=(title or "番茄钟")[:20], topmost=True,
            mini=False,
            gen=_gen,
        )
        _cmds.clear()
        _cmds.append({"t": "show"})
    return True, "ok"


def control(action: str, value=None):
    """pause / resume / complete / abandon / topmost(bool)"""
    _clear_stale()
    snap = _snapshot()
    if not snap["active"]:
        return False, "桌面时钟未在运行"
    if action == "pause":
        if snap["session_id"]:
            _free_handle("pause")
        _put({"t": "pause"})
    elif action == "resume":
        if snap["session_id"]:
            _free_handle("resume")
        _put({"t": "resume"})
    elif action == "complete":
        if snap["phase"] == "work":
            if snap["mode"] == "free":
                # 自由秒表：✓ = 结束本次专注（结算入账）
                if snap["session_id"]:
                    _free_handle("finish")
                _put({"t": "quit"})
                return True
            if snap["log_id"]:
                counted = max(1, snap["work_total"] - snap["remaining"])
                _close_log(snap["log_id"], counted)
            if snap["session_id"]:
                _free_handle("round_done")
            _put({"t": "to_break"})
        else:
            # 休息阶段点 ✓：任务模式=跳过休息收起；自由番茄模式=跳过休息直接下一轮
            if snap["session_id"]:
                _free_handle("skip_break")
                _put({"t": "next_round"})
            else:
                _put({"t": "finish_rest"})
    elif action == "abandon":
        if snap["session_id"]:
            _free_handle("abandon")
        if snap["log_id"]:
            _delete_log(snap["log_id"])
        _put({"t": "quit"})
    elif action == "topmost":
        _put({"t": "topmost", "v": bool(value)})
    elif action == "minimize":
        # 缩成迷你胶囊（小条）
        _put({"t": "minimize"})
    elif action == "restore":
        # 从迷你胶囊展开为大钟
        _put({"t": "restore"})
    elif action == "quit":
        _put({"t": "quit"})
    else:
        return False, f"未知操作 {action}"
    return True, "ok"


def toggle_pause():
    """悬浮钟自带 ⏸/▶ 按钮的暂停/继续。

    必须与页面卡片走同一条 control() 路径：自由番茄钟要经 _free_handle 同步
    后端 session（旧实现按钮只 _put 本地状态，后端把暂停时间也算成学习）。
    """
    snap = _snapshot()
    if not snap["active"]:
        return False, "桌面时钟未在运行"
    return control("resume" if snap["paused"] else "pause")


def restore_from_pill():
    """番茄胶囊被点击：展开大钟（供 pomodoro_pill 调用；线程安全）。"""
    _clear_stale()
    if not _snapshot()["active"]:
        return
    _put({"t": "restore"})


# ---------- 数据库操作 ----------
def _close_log(log_id: int, counted_seconds: int | None):
    """关账：优先使用实际计秒数（暂停不计时）。"""
    try:
        from ..database import SessionLocal
        from ..models import DailyItem, TimeLog

        db = SessionLocal()
        try:
            log = db.get(TimeLog, log_id)
            if log and not log.end_time:
                log.end_time = datetime.now()
                log.duration_seconds = int(counted_seconds or 0)
                # B10：不足 60 秒的番茄视为无效（开始即完成），删除不计入统计/🍅
                if log.kind == "pomodoro" and log.duration_seconds < 60:
                    db.delete(log)
                    db.commit()
                    return
                if log.kind == "pomodoro":
                    item = (
                        db.query(DailyItem)
                        .filter(DailyItem.kind == "task", DailyItem.source_id == log.task_id, DailyItem.status == "pending")
                        .first()
                    )
                    if item:
                        item.pomodoros += 1
                db.commit()
        finally:
            db.close()
    except Exception as e:
        print(f"[pomodoro-widget] close log failed: {e}")


def _delete_log(log_id: int):
    try:
        from ..database import SessionLocal
        from ..models import TimeLog

        db = SessionLocal()
        try:
            log = db.get(TimeLog, log_id)
            if log:
                db.delete(log)
                db.commit()
        finally:
            db.close()
    except Exception as e:
        print(f"[pomodoro-widget] delete log failed: {e}")


def _notify(title: str, msg: str):
    try:
        from winotify import Notification

        Notification(app_id="研究生工作台", title=title, msg=msg).show()
    except Exception:
        pass


# ---------- 调色板与颜色工具（Catppuccin Mocha 系） ----------
_CARD = "#1f1f33"       # 卡片底（略亮，给边缘吸附留阈值空间）
_RING_BG = "#2a2b40"    # 进度环底
_RING_BG2 = "#23243a"   # 环外细衬圈
_BTN = "#262637"        # 按钮底
_BTN_HOVER = "#3b3b56"
_TXT = "#cdd6f4"
_SUB = "#8f97b5"
_ACCENT = "#cba6f7"     # 工作（紫）
_BLUE = "#89b4fa"       # 渐变止（蓝）
_GREEN = "#a6e3a1"      # 休息（绿）
_TEAL = "#94e2d5"       # 休息渐变止（青）
_YELLOW = "#f9e2af"     # 暂停（黄）
_ORANGE = "#fab387"     # 暂停渐变止（橙）
_RED = "#f38ba8"


def _hex_to_rgb(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _mix(c1, c2, t):
    """按比例混合两个颜色 c1→c2（t∈0..1）。"""
    r1, g1, b1 = _hex_to_rgb(c1)
    r2, g2, b2 = _hex_to_rgb(c2)
    def _l(a, b):
        return int(round(a + (b - a) * t))
    return "#%02x%02x%02x" % (_l(r1, r2), _l(g1, g2), _l(b1, b2))


def _rgb_close(c1, c2, tol=1):
    """两色是否已几乎相同（缓动收敛判定用）。"""
    return all(abs(a - b) <= tol for a, b in zip(_hex_to_rgb(c1), _hex_to_rgb(c2)))


# ---------- 常驻 tkinter 线程 ----------
def _ensure_thread():
    global _thread_started, _thread
    with _lock:
        # 线程仍存活则复用；已死则重建（旧线程在 _tk_main 的 finally 里已销毁 root 并让出 _lock，
        # 新线程建全新 Tcl 解释器，避免 Tcl_AsyncDelete 跨线程 GC 崩溃）
        if _thread is not None and _thread.is_alive():
            return
        _thread_started = True
        t = threading.Thread(target=_tk_main, daemon=True, name="pomo-widget-tk")
        _thread = t
    t.start()


_FONTS = {}


def _font(path, size):
    key = (path, size)
    if key not in _FONTS:
        from PIL import ImageFont

        try:
            _FONTS[key] = ImageFont.truetype(path, size)
        except Exception:
            _FONTS[key] = ImageFont.load_default()
    return _FONTS[key]


def _tk_main():
    global _tk_ok
    try:
        import tkinter as tk

        import numpy as np
        from PIL import Image, ImageDraw
    except Exception as e:
        print(f"[pomodoro-widget] tkinter/PIL unavailable: {e}")
        _tk_ok = False
        return

    try:
        W, H = 238, 256
        SS = 2                     # 超采样倍率：2× 渲染 → LANCZOS 降采样 = 抗锯齿
        WW, HH = W * SS, H * SS
        CX = W / 2
        CY = 104                    # 进度环圆心
        RR = 58                     # 进度环半径
        LW = 11                     # 环宽

        root = tk.Tk()
        root.title("番茄钟")
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.withdraw()
        root.update_idletasks()
        hwnd = root_hwnd(root)
        set_layered(hwnd)

        S = SS

        # 文字字体（1:1 绘制，小字号更清晰；大小按 tk 的 pt 近似换算成 px）
        F_PHASE = _font("C:/Windows/Fonts/msyhbd.ttc", 14)
        F_TIME = _font("C:/Windows/Fonts/consolab.ttf", 37)
        F_PCT = _font("C:/Windows/Fonts/msyh.ttc", 12)
        F_TITLE = _font("C:/Windows/Fonts/msyh.ttc", 12)
        F_TIP = _font("C:/Windows/Fonts/msyhbd.ttc", 12)
        F_SYM_BIG = _font("C:/Windows/Fonts/seguisym.ttf", 17)
        F_SYM_SMALL = _font("C:/Windows/Fonts/seguisym.ttf", 13)

        def draw_sym(d, sym, font, fill, cx, cy):
            """画符号字形：按真实字形包围盒把视觉中心校正到 (cx, cy)（字形偏移不一）。"""
            l, t, r, b = d.textbbox((0, 0), sym, font=font)
            d.text((cx - (l + r) / 2, cy - (t + b) / 2), sym, font=font, fill=fill)

        # ---- 圆形图标按钮（形状在 PIL 层，符号在 PIL 文字层） ----
        BR = 20
        BY = H - 38
        pins = {
            "pause": {"cx": CX - 54, "cy": BY, "r": BR, "base": _BTN, "hover": _BTN_HOVER},
            "ok":    {"cx": CX,     "cy": BY, "r": BR,
                      "base": _mix(_BTN, _GREEN, 0.18), "hover": _mix(_BTN, _GREEN, 0.38)},
            "quit":  {"cx": CX + 54, "cy": BY, "r": BR,
                      "base": _mix(_BTN, _RED, 0.16), "hover": _mix(_BTN, _RED, 0.36)},
            "pin":   {"cx": W - 26, "cy": 26, "r": 12, "base": _BTN, "hover": _BTN_HOVER},
            "min":   {"cx": 26,     "cy": 26, "r": 12, "base": _BTN, "hover": _BTN_HOVER},
        }

        # ---- 置顶状态 tooltip（hover pin 按钮时显示；文字进帧渲染） ----
        tip_state = {"text": None}

        def show_tip(text):
            if tip_state["text"] == text:
                return
            tip_state["text"] = text
            redraw()

        def hide_tip():
            if tip_state["text"] is not None:
                tip_state["text"] = None
                redraw()

        # ---- 最小化：隐藏大钟、交给独立胶囊窗口 pomodoro_pill（ULW 渲染） ----
        hidden_by_pill = [False]  # 大钟被胶囊替代期间：暂停重绘，计时照常

        def minimize_to_pill():
            """最小化：隐藏大钟，显示番茄胶囊（胶囊读本模块状态渲染，点击可展开）。"""
            if hidden_by_pill[0] or not _snapshot()["active"]:
                return
            hidden_by_pill[0] = True
            with _lock:
                _state["mini"] = True
            hide_tip()
            hover_btn[0] = None
            from . import pomodoro_pill

            pomodoro_pill.PILL.start()
            root.withdraw()

        def restore_from_pill_inner():
            """胶囊点击：重新显示大钟。"""
            if not hidden_by_pill[0] or not _snapshot()["active"]:
                return
            hidden_by_pill[0] = False
            with _lock:
                _state["mini"] = False
            try:
                root.attributes("-topmost", True)
            except Exception:
                pass
            from . import pomodoro_pill

            pomodoro_pill.PILL.hide()
            place_corner()
            root.deiconify()
            reset_layered(hwnd)  # withdraw→显示后 layered surface 失效，先重设再提交
            still_sig[0] = None   # 作废静止签名：重新显示后必须重新提交一帧（防空白帧）
            redraw()

        # ---- 交互：命中按钮分发动作，其余区域拖动 ----
        drag = {"on": False, "dx": 0, "dy": 0}

        def btn_at(x, y):
            for name, p in pins.items():
                if (x - p["cx"]) ** 2 + (y - p["cy"]) ** 2 <= (p["r"] + 6) ** 2:
                    return name
            return None

        def handle_btn(name):
            if name == "pause":
                toggle_pause()
            elif name == "ok":
                control("complete")
            elif name == "quit":
                control("abandon")
            elif name == "min":
                minimize_to_pill()
            elif name == "pin":
                control("topmost", not _snapshot()["topmost"])
                if hover_btn[0] == "pin":
                    show_tip("已置顶" if _snapshot()["topmost"] else "未置顶")

        def on_press(e):
            b = btn_at(e.x, e.y)
            if b:
                drag["on"] = False
                handle_btn(b)
                return
            drag["on"] = True
            drag["dx"] = e.x_root - root.winfo_x()
            drag["dy"] = e.y_root - root.winfo_y()

        def on_move(e):
            if not drag["on"]:
                return
            root.geometry(f"+{e.x_root - drag['dx']}+{e.y_root - drag['dy']}")

        def on_release(e):
            drag["on"] = False

        root.bind("<Button-1>", on_press)
        root.bind("<B1-Motion>", on_move)
        root.bind("<ButtonRelease-1>", on_release)

        # ---- 渲染（PIL 2× 超采样 → 降采样；整帧 RGBA 交给 ULW 真 alpha） ----
        # 进度环（含底环/渐变/光晕）用 numpy 逐像素生成：按每个像素的角度直接插值颜色，
        # 完全无分段拼接——原先用 N 段纯色线段近似圆弧带，段与段之间颜色阶跃 + 方头线段
        # 在弧外侧留三角形间隙，降采样后会在环上形成一圈点状亮斑（用户反馈的"白色小点点"，
        # 只在进度环出现、计时刚开始时看不到）。numpy 方案物理上无接缝（满圈相邻像素色差 <6）。
        # 2026-10-14 性能审计：几何量（mgrid/sqrt/atan2/掩码，约 12ms/帧）与尺寸绑定恒定，
        # 缓存复用；否则悬浮钟 5fps 连续重绘时每帧重算纯属浪费（最大单项开销）。

        RIN = (RR - LW / 2) * S
        ROUT = (RR + LW / 2) * S
        HOUT = ROUT + 20 * S
        _ring_geo_cache = {}

        def _ring_geo():
            key = (HH, WW)
            g = _ring_geo_cache.get(key)
            if g is None:
                yy, xx = np.mgrid[0:HH, 0:WW].astype(np.float32)
                dx = xx - CX * S
                dy = yy - CY * S
                dist = np.sqrt(dx * dx + dy * dy)
                # 角度：顶部(12点)=0，顺时针增加（与倒计时方向一致）
                frac = (np.arctan2(dx, -dy) % (2 * math.pi)) / (2 * math.pi)
                ring_mask = (dist >= RIN) & (dist <= ROUT)
                g = {
                    "dist": dist,
                    "frac": frac,
                    "ring": ring_mask,
                    "halo": (dist > ROUT) & (dist <= HOUT),
                    "ring2": ((dist >= (RR + 3 - 0.6) * S) & (dist <= (RR + 3 + 0.6) * S)
                              & ring_mask),
                }
                _ring_geo_cache[key] = g
            return g

        def gradient_ring(ca, cb, p, pulse):
            """numpy 逐像素渐变环（底环 + 主渐变环 + 外衬圈 + 渐隐光晕）。
            返回 (HH, WW, 4) uint8 数组（RGBA），非环区域全 0。"""
            ca_rgb = _hex_to_rgb(ca)
            cb_rgb = _hex_to_rgb(cb)
            card_rgb = _hex_to_rgb(_CARD)
            ring_rgb = _hex_to_rgb(_RING_BG)
            ring2_rgb = _hex_to_rgb(_RING_BG2)
            mid_rgb = tuple(int(round((a + b) / 2)) for a, b in zip(ca_rgb, cb_rgb))
            g = _ring_geo()
            dist, frac = g["dist"], g["frac"]
            pp = max(0.0, min(1.0, p))
            prog = frac <= pp
            arr = np.zeros((HH, WW, 4), dtype=np.uint8)
            # 底环（未覆盖进度部分）
            m = g["ring"] & ~prog
            arr[m] = ring_rgb + (255,)
            # 外衬圈（底环外缘深色细线，渐变覆盖部分不画以贴合原视觉）
            m = g["ring2"] & ~prog
            arr[m] = ring2_rgb + (255,)
            # 主渐变环（起点紫 → 尖端蓝，角度插值）
            m = g["ring"] & prog
            t = (frac[m] / max(pp, 1e-6)).clip(0, 1)
            for ch in range(3):
                arr[m, ch] = (ca_rgb[ch] + (cb_rgb[ch] - ca_rgb[ch]) * t).astype(np.uint8)
            # 渐隐光晕（进度部分，向外随距离混入卡底；pulse 呼吸时变亮）
            hm = g["halo"] & prog
            if hm.any():
                fade = ((dist[hm] - ROUT) / max(HOUT - ROUT, 1e-6)).clip(0, 1)
                mix_amt = np.clip((0.25 + 0.30 * fade) - 0.10 * pulse, 0.05, 0.8)
                for ch in range(3):
                    arr[hm, ch] = (mid_rgb[ch] + (card_rgb[ch] - mid_rgb[ch]) * mix_amt).astype(np.uint8)
            # alpha：环（底环/渐变）+ 光晕进度部分（与原 any(axis=2) 等价）
            arr[g["ring"] | hm, 3] = 255
            return arr

        def radial_glow(d, ca):
            cx, cy, r = CX * S, CY * S, (RR + 12) * S
            steps = 28
            for i in range(steps):
                t = i / (steps - 1)
                rr = r * (1 - t)
                col = _mix(_CARD, ca, t * 0.18)
                d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=col)

        def draw_btn(d, b, hovered, pinned=False):
            cx, cy, r = b["cx"] * S, b["cy"] * S, b["r"] * S
            base = b["hover"] if hovered else b["base"]
            if pinned:
                base = _mix(base, _ACCENT, 0.38)
            d.ellipse([cx - r - 1.5 * S, cy - r - 1.5 * S, cx + r + 1.5 * S, cy + r + 1.5 * S],
                      fill=_mix(base, "#000000", 0.35))
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=base,
                      outline=_mix(base, "#000000", 0.30), width=S)
            if pinned:
                d.ellipse([cx - r - 4 * S, cy - r - 4 * S, cx + r + 4 * S, cy + r + 4 * S],
                          outline=_mix(_ACCENT, _CARD, 0.30), width=int(round(1.5 * S)))

        def _fit(d, text, font, max_w):
            """按测量宽度截断文字（加省略号）。"""
            if d.textlength(text, font=font) <= max_w:
                return text
            while text and d.textlength(text + "…", font=font) > max_w:
                text = text[:-1]
            return text + "…"

        def build_frame(ca, cb, p, pulse, hover, topmost, view, tip):
            """整帧 RGBA：形状 2× 超采样 → LANCZOS 降采样；文字 1:1 绘制（清晰）。"""
            im = Image.new("RGBA", (WW, HH), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            # 卡底
            d.rounded_rectangle([3 * S, 3 * S, (W - 3) * S, (H - 3) * S], radius=24 * S, fill=_CARD)
            d.rounded_rectangle([4 * S, 4 * S, (W - 4) * S, (H - 4) * S], radius=22 * S,
                                outline=_mix(_CARD, "#000000", 0.20), width=S)
            d.rounded_rectangle([7 * S, 7 * S, (W - 7) * S, (H - 7) * S], radius=19 * S,
                                outline=_mix(_CARD, "#000000", 0.20), width=S)
            d.line([28 * S, 13 * S, (W - 28) * S, 13 * S], fill=_mix(_CARD, "#000000", 0.18), width=S)
            # 环境光晕圆盘
            radial_glow(d, ca)
            # 进度环（numpy 逐像素渐变，无分段接缝）
            ring_arr = gradient_ring(ca, cb, p, pulse)
            if ring_arr.any():
                im.alpha_composite(Image.fromarray(ring_arr, "RGBA"))
            d = ImageDraw.Draw(im)
            if p > 0.0005:
                sweep = min(359.5, max(0.5, p * 359.5))
                # 进度尖端光点
                ang = math.radians(90 - sweep)
                tx = (CX + RR * math.cos(ang)) * S
                ty = (CY - RR * math.sin(ang)) * S
                d.ellipse([tx - 6 * S, ty - 6 * S, tx + 6 * S, ty + 6 * S], fill=_mix(cb, _CARD, 0.35))
                d.ellipse([tx - 3.5 * S, ty - 3.5 * S, tx + 3.5 * S, ty + 3.5 * S], fill=cb)
            # 按钮（pin 置顶态：紫色底 + 外圈光环）
            for name, b in pins.items():
                draw_btn(d, b, hover == name, pinned=(name == "pin" and topmost))
            # 置顶 tooltip 底（进超采样层，圆角光滑）
            tip_box = None
            if tip:
                tw_ = int(d.textlength(tip, font=F_TIP)) + 22
                th_ = 24
                tcx = pins["pin"]["cx"] - pins["pin"]["r"] - 10 - tw_ / 2
                tcy = pins["pin"]["cy"]
                tip_box = (tcx, tcy)
                d.rounded_rectangle([(tcx - tw_ / 2) * S, (tcy - th_ / 2) * S,
                                     (tcx + tw_ / 2) * S, (tcy + th_ / 2) * S],
                                    radius=7 * S, fill=_mix(_CARD, "#ffffff", 0.10),
                                    outline=_mix(_CARD, "#ffffff", 0.12), width=S)
            # 降采样 → 文字层（1:1，清晰）
            im = im.resize((W, H), Image.LANCZOS)
            d = ImageDraw.Draw(im)
            d.text((CX, CY - 30), view["phase"], font=F_PHASE, fill=view["phase_c"], anchor="mm")
            d.text((CX, CY + 8), view["time"], font=F_TIME, fill=view["time_c"], anchor="mm")
            d.text((CX, CY + 38), view["pct"], font=F_PCT, fill=_SUB, anchor="mm")
            d.text((CX, H - 72), _fit(d, view["title"], F_TITLE, W - 44), font=F_TITLE,
                   fill=_SUB, anchor="mm")
            draw_sym(d, view["sym_pause"], F_SYM_BIG, _TXT, pins["pause"]["cx"], pins["pause"]["cy"])
            draw_sym(d, "✓", F_SYM_BIG, _GREEN, pins["ok"]["cx"], pins["ok"]["cy"])
            draw_sym(d, "✕", F_SYM_BIG, _RED, pins["quit"]["cx"], pins["quit"]["cy"])
            draw_sym(d, "📌", F_SYM_SMALL, view["pin_c"], pins["pin"]["cx"], pins["pin"]["cy"])
            draw_sym(d, "—", F_SYM_SMALL, _SUB, pins["min"]["cx"], pins["min"]["cy"])
            if tip and tip_box:
                d.text(tip_box, tip, font=F_TIP, fill=_TXT, anchor="mm")
            # 轻微整窗透明（原 -alpha 0.97）
            a = im.getchannel("A").point(lambda v: int(v * 0.97))
            im.putalpha(a)
            return im

        # 缓动动画状态（环进度与配色平滑过渡）
        disp_p = [0.0]
        cur_ca = [_ACCENT]
        cur_cb = [_BLUE]
        still_sig = [None]   # 暂停静止帧跳过签名（见 redraw）
        hover_btn = [None]

        def fmt(sec):
            sec = max(0, int(sec))
            return f"{sec // 60:02d}:{sec % 60:02d}"

        def fmt_clock(sec):
            sec = max(0, int(sec))
            h, rem = divmod(sec, 3600)
            m, s = divmod(rem, 60)
            return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

        def on_hover(e):
            nb = None
            for name, p in pins.items():
                if (e.x - p["cx"]) ** 2 + (e.y - p["cy"]) ** 2 <= (p["r"] + 3) ** 2:
                    nb = name
                    break
            changed = nb != hover_btn[0]
            hover_btn[0] = nb
            want_tip = ("已置顶" if _snapshot()["topmost"] else "未置顶") if nb == "pin" else None
            tip_changed = tip_state["text"] != want_tip
            tip_state["text"] = want_tip
            if changed or tip_changed:
                redraw()

        root.bind("<Motion>", on_hover)

        def redraw():
            s = _snapshot()
            if not s["active"] or hidden_by_pill[0]:
                still_sig[0] = None   # 隐藏期间作废：重新显示后必须重新提交一帧
                return
            try:
                if root.state() != "normal":
                    still_sig[0] = None
                    return
            except Exception:
                still_sig[0] = None
                return
            running = s["active"] and not s["paused"]
            pulse = (0.5 + 0.5 * math.sin(time.monotonic() * 3.2)) if running else 0.35
            # 目标配色与进度
            if s["mode"] == "free":
                t_p, t_a, t_b = 1.0, _ACCENT, _BLUE
            elif s["phase"] == "break":
                t_p = 1 - (s["remaining"] / max(1, s["break_total"]))
                t_a, t_b = _GREEN, _TEAL
            else:
                t_p = 1 - (s["remaining"] / max(1, s["work_total"]))
                t_a, t_b = _ACCENT, _BLUE
            if s["paused"]:
                t_a, t_b = _YELLOW, _ORANGE
            # 缓动
            disp_p[0] += (max(0.0, min(1.0, t_p)) - disp_p[0]) * 0.28
            cur_ca[0] = _mix(cur_ca[0], t_a, 0.28)
            cur_cb[0] = _mix(cur_cb[0], t_b, 0.28)
            # 文本视图
            if s["mode"] == "free":
                phase = "已暂停" if s["paused"] else "专注中"
                phase_c = _YELLOW if s["paused"] else _ACCENT
                time_s = fmt_clock(s["elapsed"])
                time_c = _RED if s["paused"] else _TXT
                pct = ""
            else:
                is_break = s["phase"] == "break"
                phase = (("已暂停" if s["paused"] else "休息中") if is_break
                         else ("已暂停" if s["paused"] else "工作中"))
                phase_c = _YELLOW if s["paused"] else (_GREEN if is_break else _ACCENT)
                time_s = fmt(s["remaining"])
                time_c = _RED if s["paused"] else (_GREEN if is_break else _TXT)
                pct = f"{int(round(disp_p[0] * 100))}%"
            view = {"phase": phase, "phase_c": phase_c, "time": time_s, "time_c": time_c,
                    "pct": pct, "title": s["title"],
                    "sym_pause": "▶" if s["paused"] else "⏸",
                    "pin_c": _ACCENT if s["topmost"] else _SUB}
            # 暂停且画面静止（缓动收敛、输入无变化）→ 跳过重绘：每帧 ~16ms × 5fps 纯浪费
            # （2026-10-14 性能审计；运行中呼吸动画/进度环需要连续帧，不跳过）
            if not running:
                conv = (abs(disp_p[0] - max(0.0, min(1.0, t_p))) < 0.004
                        and _rgb_close(cur_ca[0], t_a) and _rgb_close(cur_cb[0], t_b))
                sig = (s["phase"], int(s["remaining"] or 0), int(s["elapsed"] or 0),
                       s["title"], hover_btn[0], bool(s["topmost"]), tip_state["text"],
                       view["time"], view["pct"])
                if conv and sig == still_sig[0]:
                    return
                still_sig[0] = sig
            else:
                still_sig[0] = None
            img = build_frame(cur_ca[0], cur_cb[0], disp_p[0], pulse, hover_btn[0],
                              s["topmost"], view, tip_state["text"])
            if not push_frame(hwnd, img):
                reset_layered(hwnd)
                if not push_frame(hwnd, img):
                    print("[pomodoro-widget] push frame failed")

        def place_corner():
            sw = root.winfo_screenwidth()
            sh = root.winfo_screenheight()
            root.geometry(f"{W}x{H}+{sw - W - 44}+{sh - H - 96}")

        def handle(c):
            nonlocal last_tick
            s = _snapshot()
            if c["t"] == "show":
                # 新会话从零计时：上次会话结束后 last_tick 冻结，若不重置，
                # 空闲几分钟后重开会把整段空闲时间当已流逝秒数一次性扣掉（甚至直接自动关账）
                last_tick = time.monotonic()
                hidden_by_pill[0] = False
                with _lock:
                    _state["mini"] = False
                place_corner()
                # start 声明 topmost=True，但窗口属性此前只在「切换」命令里设置——
                # 不在这里置顶的话，窗口实际不置顶会被其他窗口遮挡（点不到/看不见）
                try:
                    root.attributes("-topmost", True)
                except Exception:
                    pass
                root.deiconify()
                reset_layered(hwnd)  # withdraw→显示后 layered surface 失效，先重设再提交
                still_sig[0] = None   # 作废静止签名：重新显示后必须重新提交一帧（防空白帧）
                redraw()
            elif c["t"] == "pause":
                with _lock:
                    if _state["active"]:
                        _state["paused"] = True
            elif c["t"] == "resume":
                with _lock:
                    if _state["active"]:
                        _state["paused"] = False
            elif c["t"] == "topmost":
                v = bool(c.get("v"))
                with _lock:
                    _state["topmost"] = v
                try:
                    root.attributes("-topmost", v)
                except Exception:
                    pass
            elif c["t"] == "to_break":
                bs = _snapshot()
                if bs["phase"] != "work":
                    pass  # 幂等保护：已在休息/重复命令时不重置休息
                elif bs["break_total"] > 0:
                    with _lock:
                        _state.update(phase="break", remaining=bs["break_total"], paused=False, log_id=None)
                    if not bs["session_id"]:
                        _notify("🍅 番茄完成", f"「{bs['title']}」完成一个番茄，休息一下")
                    # 自由番茄模式的完成通知由 free_pomodoro.settle_round 发送，避免重复
                elif bs["session_id"]:
                    # 自由番茄休息时长为 0：直接开始下一轮（不收起）
                    with _lock:
                        _state.update(phase="work", remaining=bs["work_total"], paused=False)
                else:
                    _hide("🍅 番茄完成", f"「{bs['title']}」完成一个番茄")
            elif c["t"] == "finish_rest":
                _hide("☕ 休息结束", "开始下一个番茄吧！")
            elif c["t"] == "next_round":
                bs = _snapshot()
                with _lock:
                    _state.update(phase="work", remaining=bs["work_total"], paused=False)
            elif c["t"] == "minimize":
                minimize_to_pill()
            elif c["t"] == "restore":
                restore_from_pill_inner()
            elif c["t"] == "quit":
                _hide(None, None)

        def _hide(title, msg):
            with _lock:
                _state["active"] = False
                _state["mini"] = False
            hover_btn[0] = None
            hidden_by_pill[0] = False
            root.withdraw()
            try:
                from . import pomodoro_pill

                pomodoro_pill.PILL.hide()  # 计时结束顺手收起胶囊（幂等）
            except Exception:
                pass
            if title:
                _notify(title, msg)

        last_tick = time.monotonic()

        def loop():
            nonlocal last_tick
            try:
                with _lock:
                    pending = list(_cmds)
                    _cmds.clear()
                for c in pending:
                    handle(c)

                s = _snapshot()
                now = time.monotonic()
                if s["active"] and not s["paused"] and now - last_tick >= 1.0:
                    steps = int(now - last_tick)
                    last_tick += steps
                    if s["mode"] == "free":
                        # 自由秒表：累计计时（暂停不计）
                        with _lock:
                            _state["elapsed"] += steps
                    else:
                        rem = s["remaining"] - steps
                        with _lock:
                            _state["remaining"] = max(0, rem)
                        if rem <= 0:
                            if s["phase"] == "work":
                                if s["log_id"]:
                                    _close_log(s["log_id"], s["work_total"])
                                if s["session_id"]:
                                    _free_handle("round_done")
                                handle({"t": "to_break"})
                            elif s["session_id"]:
                                # 自由番茄模式：休息倒计时走完自动开始下一轮（不收起）
                                _free_handle("rest_done")
                                handle({"t": "next_round"})
                            else:
                                handle({"t": "finish_rest"})
                elif s["active"] and s["paused"]:
                    # 暂停期间让时间游标跟随 now：恢复后只计恢复后的真实运行时间，
                    # 不把整段暂停时长一次性补计进 elapsed（自由秒表）/ remaining（倒计时）。
                    # 旧实现游标冻结在暂停时刻，恢复瞬间把暂停时长全部吞掉（用户反馈 bug）。
                    last_tick = now
                if not hidden_by_pill[0]:   # 胶囊替代大钟期间不必重绘（计时逻辑照常）
                    redraw()
            except Exception as e:
                print(f"[pomodoro-widget] loop error: {e}")
            root.after(200, loop)

        root.withdraw()
        root.after(300, loop)
        root.mainloop()
    except Exception as e:
        print(f"[pomodoro-widget] tk main failed: {e}")
        _tk_ok = False
    finally:
        # 线程退出（mainloop 正常返回或异常）：清理全局状态 + 在本线程内销毁 Tk。
        # 不清 active 会让互斥检查永久拦截（本文件踩过的坑）；不在本线程 destroy
        # 则解释器可能被其它线程 GC，触发 Tcl_AsyncDelete 崩溃杀掉后端。
        with _lock:
            _state["active"] = False
            _state["paused"] = False
        try:
            root.destroy()
        except Exception:
            pass