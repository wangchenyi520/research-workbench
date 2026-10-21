"""桌面胶囊通用窗口：UpdateLayeredWindow 逐像素 alpha 悬浮窗。

为什么不用原来的「色键抠像」：无边框窗用 -transparentcolor 时系统只抠「完全等于
指定颜色」的像素，抗锯齿产生的过渡像素无法透明，只能在「一刀切（锯齿）」和
「保留成灰边（毛刺）」间二选一（用户反馈的"像抠出来的"）。本模块改用 Win32
UpdateLayeredWindow：整帧 RGBA 直接提交，逐像素真 alpha，圆角/文字/阴影全部
光滑（与 Office 图形同一种透明机制）。

⚠️ 提交的位图必须是**预乘 alpha**（RGB 已乘 alpha）：ULW 的 AC_SRC_ALPHA 按预乘
语义合成，若直通 RGB，部分透明像素（抗锯齿边缘/半透明底）会被饱和成实色 → 圆角
变硬阶梯（用户反馈的"毛刺"）。2026-10-12 修复，见「八」坑 #109。

架构（与 pomodoro/checklist 服务一致）：
- 每个胶囊 = 独立常驻 tkinter 线程 + 单 Tk root（只 show/withdraw，绝不 destroy；
  线程死亡自愈）；tk 只作为事件壳（鼠标事件 + 窗口管理），画面完全由 PIL 渲染。
- 鼠标命中按窗口矩形（含圆角外透明角落，差异可忽略）；拖动移动（位置持久化）。
- 样式：背景色/透明度从设置 cap_{key}_bg / cap_{key}_opacity 读取（设置页
  「桌面胶囊」模块），轮询热更新；透明度乘进整帧 alpha。
- 子类接口：
    KEY / TITLE / W / H / DEFAULT_BG / DEFAULT_OPACITY
    default_pos(sw, sh) -> (x, y)     默认位置（右下角错开）
    poll() -> bool                    刷新数据缓存；返回 True 表示需要重绘
    render(pal, style) -> RGBA Image  构建整帧（pal = widget_style.palette(bg)）
    on_zone(name, event)              点击按钮分区
    on_body_click(event)              点击非按钮区（未拖动）
    分区：render 时写 self.zones = [(name, x1, y1, x2, y2), ...]（左上原点）
"""

import ctypes
import json
import threading
import time
import tkinter as tk
from ctypes import wintypes

from PIL import Image, ImageChops

from ..config import DATA_DIR

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

# ---- 64 位句柄必须显式声明 restype/argtypes，否则被截断（静默失败） ----
user32.GetAncestor.restype = ctypes.c_void_p
user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
user32.GetWindowLongW.restype = ctypes.c_long
user32.GetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int]
user32.SetWindowLongW.restype = ctypes.c_long
user32.SetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_long]
user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.RECT)]
user32.WindowFromPoint.restype = ctypes.c_void_p
user32.WindowFromPoint.argtypes = [wintypes.POINT]
user32.GetClassNameW.restype = ctypes.c_int
user32.GetClassNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
user32.GetDC.restype = ctypes.c_void_p
user32.GetDC.argtypes = [ctypes.c_void_p]
user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
try:
    user32.SetThreadDpiAwarenessContext.restype = ctypes.c_bool
    user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    user32.GetDpiForWindow.restype = ctypes.c_uint
    user32.GetDpiForWindow.argtypes = [ctypes.c_void_p]
except Exception:
    pass
user32.UpdateLayeredWindow.restype = ctypes.c_int
user32.UpdateLayeredWindow.argtypes = [
    ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
    ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint,
]
user32.MonitorFromWindow.restype = ctypes.c_void_p
user32.MonitorFromWindow.argtypes = [ctypes.c_void_p, ctypes.c_uint]
user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
user32.SetWindowPos.restype = ctypes.c_int
user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, ctypes.c_uint]
gdi32.CreateCompatibleDC.restype = ctypes.c_void_p
gdi32.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
gdi32.CreateBitmap.restype = ctypes.c_void_p
gdi32.CreateBitmap.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p]
gdi32.SelectObject.restype = ctypes.c_void_p
gdi32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
gdi32.DeleteDC.argtypes = [ctypes.c_void_p]
gdi32.SetDIBits.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint,
                            ctypes.c_char_p, ctypes.c_void_p, ctypes.c_uint]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD),
    ]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_byte), ("BlendFlags", ctypes.c_byte),
                ("SourceConstantAlpha", ctypes.c_byte), ("AlphaFormat", ctypes.c_byte)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


# SetWindowPos 常量（HWND_TOPMOST 必须用 c_void_p(-1)，坑 #93）
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
HWND_TOPMOST = ctypes.c_void_p(-1)
MONITOR_DEFAULTTONEAREST = 2


def root_hwnd(win) -> int:
    """tk 顶层窗的真实 HWND（winfo_id 返回内容子窗，需取 GA_ROOT）。"""
    h = user32.GetAncestor(win.winfo_id(), 2)
    return h or win.winfo_id()


TASKBAR_CLASSES = ("Shell_TrayWnd", "Shell_SecondaryTrayWnd")


def is_taskbar_window(hwnd) -> bool:
    """窗口（根句柄）是否系统任务栏（主屏 Shell_TrayWnd / 副屏 Shell_SecondaryTrayWnd）。"""
    try:
        buf = ctypes.create_unicode_buffer(64)
        if user32.GetClassNameW(hwnd, buf, 64):
            return buf.value in TASKBAR_CLASSES
    except Exception:
        pass
    return False


def set_layered(hwnd: int):
    """给窗口加 WS_EX_LAYERED（ULW 必需）。"""
    ex = user32.GetWindowLongW(hwnd, -20)
    user32.SetWindowLongW(hwnd, -20, ex | 0x80000)


def reset_layered(hwnd: int):
    """重设 WS_EX_LAYERED（先去掉再加回）：治愈 withdraw 后失效的 layered surface。

    任何「隐藏（withdraw）→ 重新显示」过的窗口，再次 ULW 提交前都要调用（或提交
    失败后自愈重试）。见坑 #97。
    """
    try:
        ex = user32.GetWindowLongW(hwnd, -20)
        user32.SetWindowLongW(hwnd, -20, ex & ~0x80000)
        user32.SetWindowLongW(hwnd, -20, (ex & ~0x80000) | 0x80000)
    except Exception:
        pass


def premultiply(img: Image.Image) -> Image.Image:
    """RGB 乘以 alpha（ULW 的 AC_SRC_ALPHA 要求预乘，否则边缘饱和成实色）。"""
    r, g, b, a = img.split()
    return Image.merge("RGBA", (ImageChops.multiply(r, a),
                                ImageChops.multiply(g, a),
                                ImageChops.multiply(b, a), a))


def push_frame(hwnd: int, img: Image.Image) -> bool:
    """以 UpdateLayeredWindow 提交一帧（RGBA，逐像素 alpha，提交前自动预乘）。

    注意：窗口处于隐藏（withdrawn）状态时调用会失败（错误 87）且 layered surface
    失效；从隐藏恢复显示后需先 _reset_layered()（去掉再加回 WS_EX_LAYERED）才能
    再次提交。见 2026-10-07 排查记录。
    """
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    img = premultiply(img)
    w, h = img.size
    data = img.tobytes("raw", "BGRA")
    buf = ctypes.create_string_buffer(data, len(data))
    hdc_screen = user32.GetDC(None)
    hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
    bmp = gdi32.CreateBitmap(w, h, 1, 32, None)
    old = gdi32.SelectObject(hdc_mem, bmp)
    bi = BITMAPINFOHEADER()
    bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bi.biWidth = w
    bi.biHeight = -h  # top-down
    bi.biPlanes = 1
    bi.biBitCount = 32
    bi.biCompression = 0  # BI_RGB
    bi.biSizeImage = w * h * 4
    gdi32.SetDIBits(hdc_mem, bmp, 0, h, buf, ctypes.byref(bi), 0)
    size = wintypes.SIZE(w, h)
    src = wintypes.POINT(0, 0)
    blend = BLENDFUNCTION(0, 0, 255, 1)  # AC_SRC_OVER / AC_SRC_ALPHA
    ok = user32.UpdateLayeredWindow(hwnd, hdc_screen, None, ctypes.byref(size),
                                    hdc_mem, ctypes.byref(src), 0, ctypes.byref(blend), 0x02)
    gdi32.SelectObject(hdc_mem, old)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(hdc_mem)
    user32.ReleaseDC(None, hdc_screen)
    return bool(ok)


class PillWindow:
    KEY = "pill"
    TITLE = "胶囊"
    W, H = 240, 48
    DEFAULT_BG = "#ffffff"
    DEFAULT_OPACITY = 100
    TICK_MS = 250        # 主循环 tick（数据轮询节流由子类 poll 自己控制）
    STYLE_MS = 4000      # 样式轮询间隔

    def __init__(self):
        self._lock = threading.Lock()
        self._cmds = []
        self._state = {"active": False}
        self._thread = None
        self._tk_ok = True
        self._notify_count = 0   # 样式通知计数（测试/调试用）
        self._pref_lock = threading.Lock()
        self._pref_path = DATA_DIR / f"pill_{self.KEY}.json"
        # ---- tk 线程内状态 ----
        self._root = None
        self._hwnd = None
        self._scale = 1.0   # DPI 缩放（本线程 per-monitor aware，按物理像素渲染）
        self._zones = []
        self._hover = None
        self._inside = False   # 指针是否在窗口内（悬停整体反馈用；Leave 时重置）
        self._style = None
        self._fonts = {}
        self._dirty = True
        self._last_style = 0.0
        self._last_raise = 0.0
        self._last_tb_raise = 0.0   # 任务栏快速通道（0.5s）
        self._drag = {"on": False, "dx": 0, "dy": 0, "px": 0, "py": 0, "moved": False, "zone": None}

    # ---------- 偏好 ----------
    def _read_pref(self) -> dict:
        try:
            if self._pref_path.exists():
                data = json.loads(self._pref_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
        except Exception as e:
            print(f"[pill-{self.KEY}] load pref failed: {e}")
        return {}

    def _save_pref(self, **kw):
        with self._pref_lock:
            try:
                data = self._read_pref()
                data.update(kw)
                self._pref_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            except Exception as e:
                print(f"[pill-{self.KEY}] save pref failed: {e}")

    # ---------- 生命周期（主线程侧） ----------
    def _clear_stale(self):
        with self._lock:
            if self._state["active"] and not (self._thread is not None and self._thread.is_alive()):
                self._state["active"] = False
                return True
        return False

    def is_active(self) -> bool:
        self._clear_stale()
        with self._lock:
            return self._state["active"]

    def public_state(self) -> dict:
        self._clear_stale()
        with self._lock:
            return dict(self._state)

    def start(self):
        if not self._tk_ok:
            return False, "当前环境不支持桌面窗口"
        self._clear_stale()
        self._ensure_thread()
        time.sleep(0.05)
        if not self._tk_ok:
            return False, "当前环境不支持桌面窗口"
        self._save_pref(open=True)
        self._put({"t": "show"})
        return True, "ok"

    def hide(self):
        if not self.is_active():
            self._save_pref(open=False)
            return False, "胶囊未在显示"
        self._save_pref(open=False)
        self._put({"t": "hide"})
        return True, "ok"

    def toggle(self):
        return self.hide() if self.is_active() else self.start()

    def control(self, action: str, value=None):
        """通用动作：hide / show / topmost(bool)；子类可扩展。"""
        if action == "hide":
            return self.hide()
        if action == "show":
            return self.start()
        if action == "topmost":
            if not self.is_active():
                return False, "胶囊未在显示"
            self._put({"t": "topmost", "v": bool(value)})
            return True, "ok"
        return False, f"未知操作 {action}"

    def notify_style(self):
        """设置变更通知（线程安全）：命令窗口线程立即重读外观并重绘，不等 4 秒轮询。"""
        with self._lock:
            self._notify_count += 1
        self._clear_stale()
        if not self.is_active():
            return
        self._put({"t": "style"})

    def restore_on_startup(self):
        """启动时若上次退出前开着则延迟 2 秒恢复（等主窗口加载，避免抢启动资源）。"""
        if self._read_pref().get("open"):
            try:
                t = threading.Timer(2.0, self.start)
                t.daemon = True
                t.start()
                return True, "scheduled"
            except Exception as e:
                print(f"[pill-{self.KEY}] restore failed: {e}")
        return False, "not open"

    def _ensure_thread(self):
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            t = threading.Thread(target=self._tk_main, daemon=True, name=f"pill-{self.KEY}-tk")
            self._thread = t
        t.start()

    def _put(self, cmd: dict):
        with self._lock:
            self._cmds.append(cmd)

    # ---------- 子类接口 ----------
    def default_pos(self, sw, sh):
        Wp, Hp = self.phys_size()
        return sw - Wp - 24, sh - Hp - 48

    def phys_size(self):
        """物理像素尺寸（DPI 缩放下按比例放大，保证 1:1 清晰渲染）。"""
        s = self._scale or 1.0
        return max(1, round(self.W * s)), max(1, round(self.H * s))

    def poll(self) -> bool:
        """刷新数据缓存；返回 True 表示需要重绘。在 tk 线程内调用。"""
        return False

    def render(self, pal, style):
        """构建整帧 RGBA（pal = widget_style.palette(bg)）。在 tk 线程内调用。"""
        raise NotImplementedError

    def on_zone(self, name, event):
        pass

    def on_body_click(self, event):
        pass

    # ---------- 字体/工具（tk 线程内） ----------
    def font(self, size, bold=False):
        from PIL import ImageFont

        key = ("ui", size, bold)
        if key not in self._fonts:
            path = "C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc"
            try:
                self._fonts[key] = ImageFont.truetype(path, size)
            except Exception:
                self._fonts[key] = ImageFont.load_default()
        return self._fonts[key]

    def mono_font(self, size, bold=False):
        from PIL import ImageFont

        key = ("mono", size, bold)
        if key not in self._fonts:
            path = "C:/Windows/Fonts/consolab.ttf" if bold else "C:/Windows/Fonts/consola.ttf"
            try:
                self._fonts[key] = ImageFont.truetype(path, size)
            except Exception:
                self._fonts[key] = ImageFont.load_default()
        return self._fonts[key]

    def ellipsis(self, d, text, font, max_w):
        """按测量宽度截断文字（加省略号）。"""
        if d.textlength(text, font=font) <= max_w:
            return text
        ell = "…"
        while text and d.textlength(text + ell, font=font) > max_w:
            text = text[:-1]
        return text + ell

    def mark_dirty(self):
        self._dirty = True

    # ---------- tk 线程 ----------
    def _tk_main(self):
        self._tk_ok = True
        try:
            # 注意：不要在本线程用 SetThreadDpiAwarenessContext 切 DPI 上下文——
            # 实测（2026-10-07）Per-Monitor Aware 线程创建的窗口调用 UpdateLayeredWindow
            # 会稳定返回 0（GetLastError=87 参数错误），ULW 完全不可用；保持进程默认
            # 虚拟化即可（100% 缩放屏幕上无差异）。
            root = tk.Tk()
            root.title(self.TITLE)
            root.overrideredirect(True)
            root.attributes("-topmost", True)
            root.geometry(f"{self.W}x{self.H}+{-10000}+{-10000}")
            root.update_idletasks()
        except Exception as e:
            print(f"[pill-{self.KEY}] tk init failed: {e}")
            self._tk_ok = False
            return
        try:
            self._root = root
            self._hwnd = root_hwnd(root)
            try:
                self._scale = max(1.0, user32.GetDpiForWindow(self._hwnd) / 96.0)
            except Exception:
                self._scale = 1.0
            ex = user32.GetWindowLongW(self._hwnd, -20)
            user32.SetWindowLongW(self._hwnd, -20, ex | 0x80000)  # WS_EX_LAYERED
            root.bind("<Button-1>", self._on_press)
            root.bind("<B1-Motion>", self._on_move)
            root.bind("<ButtonRelease-1>", self._on_release)
            root.bind("<Motion>", self._on_hover)
            root.bind("<Leave>", self._on_leave)
            root.withdraw()
            root.after(120, self._loop)
            root.mainloop()
        except Exception as e:
            print(f"[pill-{self.KEY}] tk main failed: {e}")
            self._tk_ok = False
        finally:
            with self._lock:
                self._state["active"] = False
            try:
                root.destroy()
            except Exception:
                pass

    # ---------- 主循环与命令 ----------
    def _loop(self):
        try:
            with self._lock:
                pending = list(self._cmds)
                self._cmds.clear()
            for c in pending:
                self._handle(c)
            with self._lock:
                active = self._state["active"]
            if active:
                now = time.monotonic()
                if now - self._last_tb_raise >= 0.5:
                    self._last_tb_raise = now
                    self._maybe_raise_topmost(taskbar_only=True)
                if now - self._last_raise >= 2.0:
                    self._last_raise = now
                    self._maybe_raise_topmost()
                if now - self._last_style >= self.STYLE_MS / 1000:
                    self._last_style = now
                    self._refresh_style()
                try:
                    if self.poll():
                        self._dirty = True
                except Exception as e:
                    print(f"[pill-{self.KEY}] poll failed: {e}")
                if self._dirty:
                    self._dirty = False
                    try:
                        self._redraw()
                    except Exception as e:
                        print(f"[pill-{self.KEY}] redraw failed: {e}")
        except Exception as e:
            print(f"[pill-{self.KEY}] loop error: {e}")
        self._root.after(self.TICK_MS, self._loop)

    def _handle(self, c):
        t = c["t"]
        if t == "show":
            with self._lock:
                self._state["active"] = True
            self._refresh_style()
            self._place()
            self._dirty = True
            # 顺序要点：deiconify 后必须重设一次 WS_EX_LAYERED（withdraw 过的窗口
            # layered surface 失效，不重设 ULW 会稳定失败），然后才提交帧
            self._root.deiconify()
            self._reset_layered()
            self._redraw()
            try:
                self._root.attributes("-topmost", True)
            except Exception:
                pass
            self._raise_topmost()
        elif t == "hide":
            with self._lock:
                self._state["active"] = False
            self._root.withdraw()
        elif t == "style":
            # 设置页改颜色/透明度后立即生效（不等 STYLE_MS 轮询）
            self._last_style = 0
            self._refresh_style()
            self._dirty = True
        elif t == "topmost":
            try:
                self._root.attributes("-topmost", bool(c.get("v")))
            except Exception:
                pass

    def _place(self):
        pref = self._read_pref()
        Wp, Hp = self.phys_size()
        x, y = pref.get("x"), pref.get("y")
        if x is None or y is None:
            sw, sh = self._root.winfo_screenwidth(), self._root.winfo_screenheight()
            x, y = self.default_pos(sw, sh)
        x, y = self._clamp_pos(x, y)
        self._root.geometry(f"{Wp}x{Hp}+{int(x)}+{int(y)}")

    def _monitor_area(self) -> tuple:
        """当前显示器整屏范围（含任务栏带；支持任务栏在任意边）。失败回退整屏。"""
        try:
            hmon = user32.MonitorFromWindow(self._hwnd, MONITOR_DEFAULTTONEAREST)
            mi = MONITORINFO()
            mi.cbSize = ctypes.sizeof(MONITORINFO)
            if user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
                m = mi.rcMonitor
                return m.left, m.top, m.right, m.bottom
        except Exception:
            pass
        return 0, 0, self._root.winfo_screenwidth(), self._root.winfo_screenheight()

    def _clamp_pos(self, x, y) -> tuple:
        """限制位置在整屏范围内——允许叠放在任务栏带（2026-10-14 用户指定），
        纵向必须完整可见，横向至少 80px 可见。

        历史 bug（2026-10-07）：胶囊被拖到任务栏区域后，任务栏在 z-order 上盖住
        胶囊，鼠标命中全被 Shell_TrayWnd 吃掉（窗口照常刷新却「怎么点都没反应」）。
        当次以「纵向强制不出工作区」规避；用户希望胶囊就能放在任务栏带内（红框
        位置），故改为两者配合根治：允许放入 + 被任务栏盖住时快速重抬。
        """
        Wp, Hp = self.phys_size()
        l, t, r, b = self._monitor_area()
        x = max(l - Wp + 80, min(int(x), r - 80))
        y = max(t, min(int(y), b - Hp))
        return x, y

    def _raise_topmost(self):
        """把窗口重新抬到 topmost 带最前（不激活/不移动/不改大小）。

        任务栏等系统置顶窗口会在 z-order 变化时跑到胶囊上面（被盖住时点击全部
        落到对方窗口上）；每个胶囊存活期间定期重抬，保证始终可见可点。
        """
        try:
            user32.SetWindowPos(self._hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                                SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE)
        except Exception:
            pass

    def _covering_root(self):
        """盖住胶囊中心点的窗口根句柄；未被盖住时返回 None。"""
        try:
            r = wintypes.RECT()
            user32.GetWindowRect(self._hwnd, ctypes.byref(r))
            pt = wintypes.POINT((r.left + r.right) // 2, (r.top + r.bottom) // 2)
            hit = user32.WindowFromPoint(pt)
            if not hit:
                return None
            root = user32.GetAncestor(hit, 2)
            if root == self._hwnd:
                return None
            return root
        except Exception:
            return None

    def _maybe_raise_topmost(self, taskbar_only=False):
        """被其他窗口（任务栏/置顶窗）盖住时才重抬——既保证可点，又不无谓抢 z-order。

        taskbar_only：任务栏快速通道（_loop 每 0.5s 跑）——胶囊叠放在任务栏带内时，
        任务栏 z-order 变化会盖住胶囊、吃掉全部点击，必须尽快恢复；其余窗口保持
        2s 兜底节奏，避免与用户的菜单/浮层无谓抢 z-order。
        """
        try:
            cov = self._covering_root()
            if cov is None:
                return
            if taskbar_only and not is_taskbar_window(cov):
                return
            self._raise_topmost()
        except Exception:
            pass

    def _refresh_style(self):
        from . import widget_style

        try:
            st = widget_style.fetch_cap_style(self.KEY, self.DEFAULT_BG, self.DEFAULT_OPACITY)
        except Exception as e:
            print(f"[pill-{self.KEY}] style load failed: {e}")
            st = {"bg": self.DEFAULT_BG, "opacity": self.DEFAULT_OPACITY}
        if st != self._style:
            self._style = st
            self._dirty = True

    def _reset_layered(self):
        """重设 WS_EX_LAYERED（先去掉再加回）：治愈 withdraw 后失效的 layered surface。"""
        reset_layered(self._hwnd)

    def _redraw(self):
        from . import widget_style

        # 窗口隐藏（withdrawn/iconic）时绝不能提交：ULW 会失败并弄坏 layered surface，等可见后补帧
        try:
            if self._root.state() != "normal":
                self._dirty = True
                return
        except Exception:
            self._dirty = True
            return
        if self._style is None:
            self._refresh_style()
        img = self.render(widget_style.palette(self._style["bg"]), self._style)
        if img is None:
            return
        want = self.phys_size()
        if img.size != want:
            img = img.resize(want, Image.LANCZOS)
        op = self._style.get("opacity", 100)
        if op < 100:
            img = img.convert("RGBA")
            a = img.getchannel("A").point(lambda v: int(v * op / 100))
            img.putalpha(a)
        if not push_frame(self._hwnd, img):
            # 自愈：重设 layered 后重试一次（正常不应走到）
            self._reset_layered()
            if not push_frame(self._hwnd, img):
                print(f"[pill-{self.KEY}] push frame failed")

    # ---------- 鼠标 ----------
    def _hit(self, x, y):
        # 事件坐标是物理像素；分区按逻辑坐标登记（支持 DPI 缩放）
        s = self._scale or 1.0
        xl, yl = x / s, y / s
        for name, x1, y1, x2, y2 in self._zones:
            if x1 <= xl <= x2 and y1 <= yl <= y2:
                return name
        return None

    def _on_press(self, e):
        self._drag.update(on=True, dx=e.x_root - self._root.winfo_x(),
                          dy=e.y_root - self._root.winfo_y(),
                          px=e.x_root, py=e.y_root, moved=False,
                          zone=self._hit(e.x, e.y))

    def _on_move(self, e):
        if not self._drag["on"]:
            return
        if not self._drag["moved"]:
            dx = e.x_root - self._drag["px"]
            dy = e.y_root - self._drag["py"]
            # 6px 阈值（欧氏距离）：手抖的小位移仍算点击，避免「点击被当成拖动吃掉」
            if dx * dx + dy * dy > 36:
                self._drag["moved"] = True
        if self._drag["moved"]:
            x, y = self._clamp_pos(e.x_root - self._drag["dx"], e.y_root - self._drag["dy"])
            self._root.geometry(f"+{x}+{y}")

    def _on_release(self, e):
        if not self._drag["on"]:
            return
        self._drag["on"] = False
        if self._drag["moved"]:
            self._raise_topmost()  # 拖动中 z-order 可能被任务栏等抢走，拖完重抬
            try:
                self._save_pref(x=self._root.winfo_x(), y=self._root.winfo_y())
            except Exception:
                pass
            return
        zone = self._drag["zone"]
        try:
            if zone:
                self.on_zone(zone, e)
            else:
                self.on_body_click(e)
        except Exception as ex:
            print(f"[pill-{self.KEY}] click action failed: {ex}")

    def _on_hover(self, e):
        changed = False
        if not self._inside:
            self._inside = True
            changed = True
        z = self._hit(e.x, e.y)
        if z != self._hover:
            self._hover = z
            changed = True
        if changed:
            self._dirty = True

    def _on_leave(self, _e=None):
        """鼠标移出窗口：重置悬停态（否则高亮会残留——没有后续 Motion 事件恢复）。"""
        if self._inside or self._hover is not None:
            self._inside = False
            self._hover = None
            self._dirty = True
