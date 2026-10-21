import os
import threading
from pathlib import Path

os.chdir(Path(__file__).resolve().parent)

import webview

import uvicorn

from backend.app.main import app
from backend.app.services import mem_trim
from backend.app.services.window_chrome import (
    WINDOW_TITLE,
    WindowApi,
    polish_frameless_window,
)

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8000

WINDOW_W = 1280
WINDOW_H = 760

BASE_DIR = Path(__file__).resolve().parent
ICON_ICO = BASE_DIR / "assets" / "workbench.ico"
ICON_PNG = BASE_DIR / "assets" / "icon-1024.png"

window = None
tray_icon = None


def _window_geometry():
    """窗口位置：主屏水平居中，垂直比「几何居中」再上移 5% 屏高（默认居中在
    高分辨率屏上显得偏下）。返回 (x, y)；失败时返回 None 交给 pywebview 默认居中。"""
    try:
        screens = webview.screens
        if not screens:
            return None
        primary = next((s for s in screens if s.x == 0 and s.y == 0), screens[0])
        x = primary.x + (primary.width - WINDOW_W) // 2
        y = primary.y + (primary.height - WINDOW_H) // 2 - max(16, int(primary.height * 0.05))
        if y < primary.y:
            y = primary.y
        return x, y
    except Exception as e:
        print(f"[window] geometry failed: {e}")
        return None


def run_server():
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT, log_level="warning")


def _make_icon_image(size: int = 256):
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # 渐变背景（深紫 -> 亮紫）
    c0, c1 = (74, 58, 191), (139, 108, 255)
    for y in range(size):
        t = y / size
        color = tuple(int(c0[i] + (c1[i] - c0[i]) * t) for i in range(3))
        d.line([(0, y), (size, y)], fill=(*color, 255))
    # 圆角遮罩
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size, size], radius=int(size * 0.25), fill=255)
    img.putalpha(mask)
    d = ImageDraw.Draw(img)
    cx = cy = size / 2
    white = (255, 255, 255, 230)
    # 外圈（准星）
    r1 = int(size * 0.30)
    d.ellipse([cx - r1, cy - r1, cx + r1, cy + r1], outline=white, width=max(2, int(size * 0.05)))
    # 四角刻度
    lw = max(2, int(size * 0.05))
    tick = int(size * 0.11)
    d.line([(cx, size * 0.06), (cx, size * 0.06 + tick)], fill=white, width=lw)
    d.line([(cx, size * 0.94 - tick), (cx, size * 0.94)], fill=white, width=lw)
    d.line([(size * 0.06, cy), (size * 0.06 + tick, cy)], fill=white, width=lw)
    d.line([(size * 0.94 - tick, cy), (size * 0.94, cy)], fill=white, width=lw)
    # 中心渐变核心
    rc = int(size * 0.11)
    d.ellipse([cx - rc, cy - rc, cx + rc, cy + rc], fill=(127, 231, 255, 255))
    rp = int(size * 0.045)
    d.ellipse([cx - rp, cy - rp, cx + rp, cy + rp], fill=(255, 255, 255, 255))
    return img


def _load_icon_image(size: int = 64):
    """托盘图标：优先用 assets 里的水晶图标，失败回退到内置准星。"""
    try:
        from PIL import Image

        img = Image.open(ICON_PNG).convert("RGBA")
        img.thumbnail((size, size), Image.LANCZOS)
        return img
    except Exception as e:
        print(f"[tray] icon load failed, fallback: {e}")
        return _make_icon_image()


def _on_show(icon, item):
    mem_trim.cancel_trim()  # 重新显示：取消未执行的内存归还
    if window:
        try:
            window.show()
        except Exception:
            pass


def _on_quit(icon, item):
    # 退出前统一收尾所有进行中的计时：考勤自动离开、任务番茄钟暂停快照
    # （下次启动恢复）、页面计时关账、自由番茄钟结算入账并结束
    try:
        import httpx

        httpx.post(
            f"http://{SERVER_HOST}:{SERVER_PORT}/api/maintenance/suspend-active",
            timeout=5,
        )
    except Exception as e:
        print(f"[quit] suspend-active failed: {e}")
    icon.stop()
    os._exit(0)


def _create_tray():
    global tray_icon
    try:
        import pystray

        menu = pystray.Menu(
            pystray.MenuItem("显示工作台", _on_show, default=True),
            pystray.MenuItem("退出", _on_quit),
        )
        tray_icon = pystray.Icon("workbench", _load_icon_image(), "研究生工作台", menu)
        tray_icon.run_detached()
    except Exception as e:
        print(f"[tray] failed: {e}")


def _on_closing():
    if window:
        try:
            window.hide()
        except Exception:
            pass
    # 隐藏到托盘后延迟归还内存（60 秒内重新显示则取消；见 mem_trim）
    mem_trim.schedule_trim()
    return False


def _port_in_use(port: int) -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def main():
    global window
    # 防双开：端口被占用 = 已有一个实例在运行。双开会同时触发 AI 每日任务/通知等重复行为，
    # 且第二个实例的后端实际无法服务（抢不到 8000），只留一个迷惑窗口（见坑 #77 / 2026-09-30）。
    if _port_in_use(SERVER_PORT):
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(
                0,
                "研究生工作台已经在运行。\n请在任务栏或系统托盘里找到已打开的窗口，不要重复启动。",
                "研究生工作台",
                0x40,
            )
        except Exception:
            pass
        return
    t = threading.Thread(target=run_server, daemon=True)
    t.start()
    _create_tray()
    geo = _window_geometry()
    # 自绘标题栏：窗口改为无边框（置顶/最小化/最大化/关闭由前端标题栏调用 js_api 控制），
    # easy_drag 必须关闭——pywebview 的 easy_drag 会劫持全窗口任意位置的拖动
    # （包括文本选择/滑杆拖动），拖动改由标题栏单独触发（window_chrome）。
    win_kw = dict(
        width=WINDOW_W, height=WINDOW_H, min_size=(1000, 700),
        frameless=True, easy_drag=False,
    )
    if geo:
        win_kw["x"], win_kw["y"] = geo
    api = WindowApi()
    api._on_hide = mem_trim.schedule_trim  # 标题栏「关闭」= 隐藏到托盘 → 延迟归还内存
    window = webview.create_window(
        WINDOW_TITLE,
        f"http://{SERVER_HOST}:{SERVER_PORT}",
        js_api=api,
        **win_kw,
    )
    api._window = window
    polish_frameless_window()  # Win11 圆角（尽力而为）
    try:
        from backend.app.services.notification import set_open_handler

        def _open_workbench_page(target=None):
            # 点击胶囊条身 / 通知「去处理」：先把主窗口恢复并带到前台，再切页面。
            # 否则主窗口被其他窗口挡住时只是后台悄悄换页，用户以为「点了没反应」。
            # 本函数由 notification.open_page 在后台线程调用，阻塞不影响胶囊线程。
            mem_trim.cancel_trim()  # 重新显示：取消未执行的内存归还
            try:
                window.restore()
            except Exception:
                pass
            try:
                window.show()
            except Exception:
                pass
            window.evaluate_js(f"location.hash = '{target or '#/reminders'}'")

        set_open_handler(_open_workbench_page)
    except Exception as e:
        print(f"[notification] open handler failed: {e}")
    try:
        window.events.closing += _on_closing
    except Exception as e:
        print(f"[closing] hook failed: {e}")
    # 后台内存归还：最小化 3 分钟后归还工作集；还原/重新显示即取消（见 mem_trim）
    try:
        window.events.minimized += lambda: mem_trim.schedule_trim(180.0)
        window.events.restored += lambda: mem_trim.cancel_trim()
        window.events.shown += lambda: mem_trim.cancel_trim()
    except Exception as e:
        print(f"[mem] event hooks failed: {e}")
    start_kw = {}
    if ICON_ICO.exists():
        start_kw["icon"] = str(ICON_ICO)
    # 关闭 pywebview 隐私模式：默认 private_mode=True 时窗口关闭会删除 WebView2
    # 用户数据目录（clear_user_data → rmtree），localStorage（主题色/明暗/仪表盘布局）每次启动
    # 都被清空。storage_path 固定到项目数据目录，保证跨启动保留。
    from backend.app.config import DATA_DIR as WB_DATA_DIR

    storage_dir = WB_DATA_DIR / "webview"
    storage_dir.mkdir(parents=True, exist_ok=True)
    webview.start(private_mode=False, storage_path=str(storage_dir), **start_kw)


if __name__ == "__main__":
    main()
