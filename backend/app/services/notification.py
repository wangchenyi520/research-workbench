"""自定义提醒通知弹窗（tkinter 无边框置顶卡片，右下角弹出）。

用户要求：到点提醒弹窗 + 提示音，若未手动关闭则 5 分钟后自动收起。
winotify 的系统 toast 时长由 Windows 控制（最长约 25 秒），无法满足
「5 分钟自动关闭」，故用 tkinter 自绘。

2026-10-12 渲染迁移：改用 UpdateLayeredWindow 逐像素真 alpha（与桌面胶囊同
一套光滑渲染，见「五.73」）——不再用 -transparentcolor 色键抠像（抗锯齿的
过渡像素无法透明，只能在锯齿/灰边二选一）。整帧 PIL 渲染（含文字）→
push_frame（内部自动预乘 alpha），圆角/文字边缘全部光滑。

- 全局唯一常驻 tkinter 线程 + 单一 Tk root（只 show/withdraw，绝不跨线程销毁）
- 每条通知一个 Toplevel；多条排队，当前关闭后依次显示下一条
- 弹窗：深色圆角卡片 + 紫色标题 + 消息 + ✕ 关闭，右下角弹出，5 分钟自动关
- 声音：winsound.MessageBeep（系统默认提示音，pythonw 无窗口下也能响）
"""

import threading

from PIL import Image, ImageDraw, ImageFont

from .pill_window import push_frame, reset_layered, root_hwnd, set_layered

_lock = threading.Lock()
_pending: list = []          # 待显示通知 [(title, msg, target), ...]
_current = {"win": None, "after_id": None, "target": ""}
_thread_started = False
_tk_ok = True
_open_handler = None         # 桌面模式（pywebview）注册的「去处理」跳转回调

_DURATION_MS = 5 * 60 * 1000  # 5 分钟自动关闭
_W, _H = 348, 128
_CARD = "#181825"
_BTN = "#262637"
_BTN_HOVER = "#33334a"
_TEXT = "#cdd6f4"
_SUB = "#9399b2"
_ACCENT = "#cba6f7"
_RED = "#f38ba8"
_GREEN_TXT = "#a6e3a1"


def set_open_handler(fn):
    """注册「去处理」跳转回调（桌面模式由 desktop.py 传入 webview 跳转，浏览器模式回退 webbrowser）。"""
    global _open_handler
    _open_handler = fn


def open_page(target: str):
    """打开工作台页面（target 形如 '#/attendance'）：桌面模式走 pywebview 跳转，否则回退浏览器。

    必须在后台线程执行：pywebview 的 evaluate_js（edgechromium 后端）内部用无超时的
    信号量等 JS 回调，渲染器被节流/回调丢失时会长时间不返回——若从胶囊的 tkinter
    线程同步调用，整个胶囊会被卡死（所有点击失效，见 2026-10-07 排查记录）。
    """

    def _run():
        handler = _open_handler
        if handler:
            try:
                handler(target)
                return
            except Exception:
                pass
        try:
            import webbrowser

            webbrowser.open(f"http://127.0.0.1:8000/{target}")
        except Exception:
            pass

    threading.Thread(target=_run, daemon=True, name="workbench-open-page").start()


def notify(title: str, msg: str, target: str = "") -> bool:
    """弹自定义通知（右下角置顶卡片，5 分钟自动关闭，带提示音）。
    target: 「去处理」按钮跳转的页面 hash（如 "#/daily-paper"），空则默认提醒事项页。
    """
    global _thread_started, _tk_ok
    if not _tk_ok:
        return False
    with _lock:
        if not _thread_started:
            _thread_started = True
            threading.Thread(target=_tk_main, daemon=True, name="notification-tk").start()
        _pending.append((title, msg, target))
    try:
        import winsound

        winsound.MessageBeep()
    except Exception:
        pass
    return True


# ---------- 渲染 ----------
_FONTS = {}


def _font(path, size):
    key = (path, size)
    if key not in _FONTS:
        try:
            _FONTS[key] = ImageFont.truetype(path, size)
        except Exception:
            _FONTS[key] = ImageFont.load_default()
    return _FONTS[key]


def _font_ui(size, bold=False):
    return _font("C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc", size)


def _build_frame(title: str, msg: str, hover) -> Image.Image:
    """构建整帧 RGBA（形状 3× 超采样 + LANCZOS；文字 1:1 绘制保证清晰）。"""
    SS = 3
    W, H = _W, _H
    img = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # 卡片底 + 描边
    d.rounded_rectangle([3 * SS, 3 * SS, (W - 3) * SS - 1, (H - 3) * SS - 1],
                        radius=18 * SS, fill=_CARD)
    d.rounded_rectangle([3 * SS, 3 * SS, (W - 3) * SS - 1, (H - 3) * SS - 1],
                        radius=18 * SS, outline="#2b2c3f", width=SS)
    # 顶部紫色小条
    d.line([20 * SS, 22 * SS, 30 * SS, 22 * SS], fill=_ACCENT, width=4 * SS)
    # ✕ 关闭按钮圆底
    close_hover = hover == "close"
    d.ellipse([(W - 34) * SS, 12 * SS, (W - 12) * SS, 34 * SS],
              fill=_BTN_HOVER if close_hover else _BTN)
    # 「去处理」按钮底
    open_hover = hover == "open"
    d.ellipse([20 * SS, (H - 40) * SS, 110 * SS, (H - 12) * SS],
              fill=_BTN_HOVER if open_hover else _BTN)

    img = img.resize((W, H), Image.LANCZOS)

    # ---- 文字层（1:1） ----
    d = ImageDraw.Draw(img)
    d.text((40, 22), str(title)[:14], font=_font_ui(15, bold=True), fill=_ACCENT, anchor="lm")
    lines = _wrap(msg, 42)[:4]
    for i, line in enumerate(lines):
        d.text((20, 50 + i * 20), line, font=_font_ui(13), fill=_TEXT, anchor="lm")

    # ✕（两条斜线，避免字体字形差异）
    cx, cy = W - 23, 23
    for a, b in (((-5, -5), (5, 5)), ((-5, 5), (5, -5))):
        d.line([cx + a[0], cy + a[1], cx + b[0], cy + b[1]], fill=_RED, width=2)

    # 「去处理」文字 + 手绘勾（不依赖字体里的 ✓ 字形）
    label = "去处理"
    f_open = _font_ui(13, bold=True)
    tw = d.textlength(label, font=f_open)
    ox = 65 - (tw + 16) / 2  # 文字+勾整体居中
    d.text((ox, H - 26), label, font=f_open, fill=_GREEN_TXT, anchor="lm")
    gx, gy = ox + tw + 5, H - 26
    d.line([gx, gy, gx + 4, gy + 4, gx + 11, gy - 5], fill=_GREEN_TXT, width=2, joint="curve")

    # 轻微整窗透明（原 -alpha 0.97）
    a = img.getchannel("A").point(lambda v: int(v * 0.97))
    img.putalpha(a)
    return img


def _zone(x, y):
    if (x - (_W - 23)) ** 2 + (y - 23) ** 2 <= 15 ** 2:
        return "close"
    if 14 <= x <= 116 and _H - 46 <= y <= _H - 6:
        return "open"
    return None


def _tk_main():
    global _tk_ok
    try:
        import tkinter as tk
    except Exception as e:
        print(f"[notification] tkinter unavailable: {e}")
        _tk_ok = False
        return

    try:
        root = tk.Tk()
        root.title("提醒")
        root.withdraw()
    except Exception as e:
        print(f"[notification] tk init failed: {e}")
        _tk_ok = False
        return

    def _close_current():
        win = _current["win"]
        _current["win"] = None
        if _current["after_id"]:
            try:
                root.after_cancel(_current["after_id"])
            except Exception:
                pass
            _current["after_id"] = None
        _current["target"] = ""
        if win is not None:
            try:
                win.destroy()
            except Exception:
                pass

    def _show(title: str, msg: str, target: str = ""):
        _close_current()
        _current["target"] = target
        win = tk.Toplevel(root)
        _current["win"] = win
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.withdraw()

        # 定位右下角
        try:
            sw = win.winfo_screenwidth()
            sh = win.winfo_screenheight()
        except Exception:
            sw, sh = 1920, 1080
        win.geometry(f"{_W}x{_H}+{max(0, sw - _W - 24)}+{max(0, sh - _H - 80)}")
        win.update_idletasks()

        hwnd = root_hwnd(win)
        set_layered(hwnd)
        hover = [None]

        def draw():
            try:
                img = _build_frame(title, msg, hover[0])
                if not push_frame(hwnd, img):
                    reset_layered(hwnd)
                    push_frame(hwnd, img)
            except Exception as e:
                print(f"[notification] render failed: {e}")

        def on_motion(e):
            z = _zone(e.x, e.y)
            if z != hover[0]:
                hover[0] = z
                draw()

        def on_leave(_e=None):
            if hover[0] is not None:
                hover[0] = None
                draw()

        def on_close(_e=None):
            _close_current()
            _show_next()

        def on_open(_e=None):
            open_page(_current["target"] or "#/reminders")
            _close_current()
            _show_next()

        def on_click(e):
            z = _zone(e.x, e.y)
            if z == "close":
                on_close()
            elif z == "open":
                on_open()

        win.bind("<Motion>", on_motion)
        win.bind("<Leave>", on_leave)
        win.bind("<Button-1>", on_click)

        win.deiconify()
        reset_layered(hwnd)  # withdraw→显示后 layered surface 失效，先重设再提交
        draw()
        _current["after_id"] = root.after(_DURATION_MS, on_close)

    def _show_next():
        with _lock:
            if _pending:
                title, msg, target = _pending.pop(0)
                try:
                    _show(title, msg, target)
                except Exception as e:
                    print(f"[notification] show failed: {e}")
                    _current["win"] = None

    def _loop():
        try:
            with _lock:
                has_pending = bool(_pending) and _current["win"] is None
            if has_pending:
                _show_next()
        except Exception as e:
            print(f"[notification] loop error: {e}")
        root.after(200, _loop)

    root.after(200, _loop)
    root.mainloop()


def _wrap(text: str, width: int) -> list:
    """按中文字符宽度简单换行（中文算 2 个字符）。"""
    lines, cur, cur_w = [], "", 0
    for ch in str(text):
        w = 2 if ord(ch) > 0x2E80 else 1
        if cur_w + w > width:
            lines.append(cur)
            cur, cur_w = "", 0
        cur += ch
        cur_w += w
    if cur:
        lines.append(cur)
    return lines or [""]
