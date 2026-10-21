# -*- coding: utf-8 -*-
"""桌面窗口自绘标题栏的窗口控制（frameless 窗口）。

前端通过 ``window.pywebview.api.*`` 调到本类。关键实现约束（2026-10-10 PoC 实证）：

- **拖动 / 缩放必须在 UI 线程触发**：工作线程直接 ``SendMessage(WM_NCLBUTTONDOWN)``
  时 Windows 移动循环会立即退出（窗口不动），必须经 ``window.native.BeginInvoke``
  调度到 UI 线程执行（UI 线程触发则进入系统原生移动/缩放循环，手感与原生标题栏一致，
  支持贴边分屏）。
- 使用 ``FindWindowW`` 按窗口标题取 HWND；标题可由构造参数覆盖（测试用独立标题，
  避免误操作真实窗口——同坑 #91 教训）。
"""

import ctypes
import threading
import time

WINDOW_TITLE = "研究生工作台"

_WM_NCLBUTTONDOWN = 0xA1
_HTCAPTION = 2
_RESIZE_CODES = {
    "left": 10, "right": 11, "top": 12, "topleft": 13, "topright": 14,
    "bottom": 15, "bottomleft": 16, "bottomright": 17,
}


def find_hwnd(title: str = WINDOW_TITLE) -> int:
    try:
        return ctypes.windll.user32.FindWindowW(None, title) or 0
    except Exception:
        return 0


def _is_zoomed(hwnd: int) -> bool:
    try:
        return bool(ctypes.windll.user32.IsZoomed(ctypes.c_void_p(hwnd))) if hwnd else False
    except Exception:
        return False


def _is_topmost(hwnd: int) -> bool:
    try:
        ex = ctypes.windll.user32.GetWindowLongW(ctypes.c_void_p(hwnd), -20)  # GWL_EXSTYLE
        return bool(ex & 0x8)  # WS_EX_TOPMOST
    except Exception:
        return False


class WindowApi:
    """自绘标题栏 ↔ 桌面窗口控制桥（js_api 对象）。"""

    def __init__(self, title: str = WINDOW_TITLE):
        self._window = None  # create_window 之后注入
        self._title = title
        self._on_hide = None  # 隐藏到托盘后的回调（desktop.py 注入；下划线=不进 js_api 桥）

    # ---------------------------------------------------------------- 内部
    def _hwnd(self) -> int:
        return find_hwnd(self._title)

    def _ui_invoke(self, fn) -> bool:
        """把原生移动/缩放循环调度到 UI 线程执行（工作线程调用不生效）。"""
        try:
            from System import Action  # pythonnet，pywebview 启动后才可用

            self._window.native.BeginInvoke(Action(fn))
            return True
        except Exception as e:
            print(f"[titlebar] ui invoke failed: {e}")
            return False

    # ---------------------------------------------------------------- 状态
    def get_state(self):
        hwnd = self._hwnd()
        return {
            "on_top": bool(self._window.on_top) if self._window else False,
            "maximized": _is_zoomed(hwnd),
        }

    # ---------------------------------------------------------------- 操作
    def toggle_pin(self) -> bool:
        """置顶开关：切换后返回新状态。"""
        if not self._window:
            return False
        self._window.on_top = not self._window.on_top
        return bool(self._window.on_top)

    def minimize(self) -> bool:
        if self._window:
            self._window.minimize()
        return True

    def toggle_maximize(self) -> bool:
        """最大化/还原切换：切换后返回是否最大化。"""
        if not self._window:
            return False
        hwnd = self._hwnd()
        if _is_zoomed(hwnd):
            self._window.restore()
            return False
        self._window.maximize()
        return True

    def hide_to_tray(self) -> bool:
        """自定义「关闭」按钮：与原生 X 一致——最小化到系统托盘。"""
        if self._window:
            self._window.hide()
        if self._on_hide:
            try:
                self._on_hide()
            except Exception:
                pass
        return True

    def start_drag(self) -> bool:
        """原生拖动（WM_NCLBUTTONDOWN + HTCAPTION）：手感与系统标题栏一致。"""
        def _go():
            hwnd = self._hwnd()
            if not hwnd:
                return
            user32 = ctypes.windll.user32
            user32.ReleaseCapture()
            user32.SendMessageW(ctypes.c_void_p(hwnd), _WM_NCLBUTTONDOWN, _HTCAPTION, 0)
        return self._ui_invoke(_go)

    def start_resize(self, edge: str) -> bool:
        """原生四边/四角缩放（HT* 命中码），edge ∈ left/right/top/…/bottomright。"""
        code = _RESIZE_CODES.get(str(edge or "").lower())
        if not code:
            return False

        def _go():
            hwnd = self._hwnd()
            if not hwnd:
                return
            user32 = ctypes.windll.user32
            user32.ReleaseCapture()
            user32.SendMessageW(ctypes.c_void_p(hwnd), _WM_NCLBUTTONDOWN, code, 0)
        return self._ui_invoke(_go)


def polish_frameless_window(delay: float = 3.0, title: str = WINDOW_TITLE) -> None:
    """Win11 圆角（DWMWA_WINDOW_CORNER_PREFERENCE），尽力而为，失败忽略。"""
    def _run():
        time.sleep(delay)
        hwnd = find_hwnd(title)
        if not hwnd:
            return
        try:
            val = ctypes.c_int(2)  # DWMWCP_ROUND
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                ctypes.c_void_p(hwnd), 33, ctypes.byref(val), ctypes.sizeof(val)
            )
        except Exception as e:
            print(f"[window] round corners failed: {e}")

    threading.Thread(target=_run, daemon=True).start()
