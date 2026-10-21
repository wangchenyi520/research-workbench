"""考勤胶囊：桌面在岗状态小条（独立 ULW 窗口，逐像素 alpha）。

- 常驻显示今日考勤状态：未打卡 / 在岗（到秒跳动）/ 休息中 / 已结束；
- 在岗时点「离开」弹出原因菜单（上课/吃饭/其他/不填）→ 与考勤页同一后端逻辑；
- 非在岗时点「到位」直接开始计时；点击条身打开考勤页；✕ 收起胶囊；
- 可拖动移动（位置记忆）；颜色/透明度走设置页「桌面胶囊」模块（cap_attendance_*）。
"""

import time

from PIL import Image, ImageDraw

from .pill_window import PillWindow


class AttendancePill(PillWindow):
    KEY = "attendance"
    TITLE = "考勤胶囊"
    W, H = 252, 48
    DEFAULT_BG = "#ffffff"
    DEFAULT_OPACITY = 100

    def __init__(self):
        super().__init__()
        self._d = {}
        self._last_key = None
        self._last_load = 0.0

    def default_pos(self, sw, sh):
        Wp, Hp = self.phys_size()
        return sw - Wp - 24, sh - Hp - 100

    # ---------- 数据 ----------
    def _fetch(self):
        from datetime import datetime

        from ..database import SessionLocal
        from ..routers import attendance as att

        db = SessionLocal()
        try:
            now = datetime.now()
            att._auto_close(db, now)
            return att._serialize_today(db, now)
        finally:
            db.close()

    def poll(self):
        now = time.monotonic()
        if now - self._last_load < 1.0:
            return False
        self._last_load = now
        try:
            d = self._fetch()
        except Exception as e:
            print(f"[pill-attendance] fetch failed: {e}")
            return False
        key = (d.get("status"), int(d.get("today_seconds") or 0))
        if key != self._last_key:
            self._last_key = key
            self._d = d
            return True
        return False

    def _do_action(self, kind, reason=""):
        from datetime import datetime

        from ..database import SessionLocal
        from ..routers import attendance as att

        db = SessionLocal()
        try:
            now = datetime.now()
            if kind == "check-in":
                att.do_check_in(db, now)
            else:
                att.do_check_out(db, now, reason)
        except ValueError as e:
            print(f"[pill-attendance] {e}")
        except Exception as e:
            print(f"[pill-attendance] action failed: {e}")
        finally:
            db.close()
        self._last_load = 0  # 立即刷新
        self.mark_dirty()

    def _leave_menu(self):
        import tkinter as tk

        menu = tk.Menu(self._root, tearoff=0, font=("Microsoft YaHei UI", 9))
        for r in ("上课", "吃饭", "其他"):
            menu.add_command(label=r, command=lambda rr=r: self._do_action("check-out", rr))
        menu.add_separator()
        menu.add_command(label="不填原因直接离开", command=lambda: self._do_action("check-out", ""))
        try:
            menu.tk_popup(self._root.winfo_pointerx(), self._root.winfo_pointery())
        finally:
            try:
                menu.grab_release()
            except Exception:
                pass

    # ---------- 渲染 ----------
    def render(self, pal, style):
        SS = 3
        W, H = self.W * SS, self.H * SS
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)

        def P(x, y):
            return (x * SS, y * SS)

        # 胶囊底（悬停微亮：整条给出"选中"反馈）
        body_bg = pal["hover"] if self._inside else pal["bg"]
        d.rounded_rectangle([0, 0, W - 1, H - 1], radius=H // 2, fill=body_bg)
        d.rounded_rectangle([0, 0, W - 1, H - 1], radius=H // 2, outline=pal["border"], width=SS)

        st = self._d.get("status") or "idle"
        dot_col = {"working": pal["green"], "paused": pal["orange"]}.get(st, pal["disabled"])
        cx, cy, r = 18 * SS, H // 2, 5 * SS
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=dot_col)

        # 文案
        if st == "working":
            f1 = self.font(11 * SS)
            d.text(P(32, self.H / 2), "在岗", font=f1, fill=pal["sub"], anchor="lm")
            w1 = d.textlength("在岗", font=f1)
            f2 = self.mono_font(14 * SS, bold=True)
            secs = int(self._d.get("today_seconds") or 0)
            h_, rem = divmod(max(0, secs), 3600)
            m_, s_ = divmod(rem, 60)
            d.text(P(32 + w1 / SS + 6, self.H / 2), f"{h_}:{m_:02d}:{s_:02d}", font=f2,
                   fill=pal["txt"], anchor="lm")
        elif st == "paused":
            f1 = self.font(12 * SS)
            d.text(P(32, self.H / 2), "休息中", font=f1, fill=pal["orange"], anchor="lm")
        elif st == "closed":
            f1 = self.font(12 * SS)
            d.text(P(32, self.H / 2), "今日已结束", font=f1, fill=pal["sub"], anchor="lm")
        else:
            f1 = self.font(12 * SS)
            d.text(P(32, self.H / 2), "今日未打卡", font=f1, fill=pal["sub"], anchor="lm")

        # 主按钮（在岗=离开 / 其他=到位）
        bx1, by1, bx2, by2 = self.W - 98, 10, self.W - 42, 38
        hovered = self._hover == "action"
        if st == "working":
            btn_bg = pal["btn_hover"] if hovered else pal["btn_bg"]
            btn_fg = pal["txt"]
            label = "离开"
        else:
            btn_bg = pal["accent"]
            btn_fg = "#ffffff"
            label = "到位"
        d.rounded_rectangle([P(bx1, by1), P(bx2, by2)], radius=(by2 - by1) // 2 * SS, fill=btn_bg,
                            outline=pal["border"] if st == "working" else None, width=SS)
        f3 = self.font(11 * SS)
        d.text(P((bx1 + bx2) / 2, (by1 + by2) / 2), label, font=f3, fill=btn_fg, anchor="mm")

        # ✕ 关闭
        ccx, ccy = self.W - 21, self.H / 2
        cross_col = pal["red"] if self._hover == "close" else pal["icon"]
        d.line([P(ccx - 4.5, ccy - 4.5), P(ccx + 4.5, ccy + 4.5)], fill=cross_col,
               width=max(1, int(1.6 * SS)))
        d.line([P(ccx - 4.5, ccy + 4.5), P(ccx + 4.5, ccy - 4.5)], fill=cross_col,
               width=max(1, int(1.6 * SS)))

        self._zones = [
            ("action", self.W - 98, 8, self.W - 38, 40),
            ("close", self.W - 40, 6, self.W - 4, 42),
        ]
        return img.resize(self.phys_size(), Image.LANCZOS)

    # ---------- 交互 ----------
    def on_zone(self, name, event):
        if name == "close":
            self.hide()
            return
        if name == "action":
            st = self._d.get("status") or "idle"
            if st == "working":
                self._leave_menu()
            else:
                self._do_action("check-in")

    def on_body_click(self, event):
        from .notification import open_page

        open_page("#/attendance")


PILL = AttendancePill()
