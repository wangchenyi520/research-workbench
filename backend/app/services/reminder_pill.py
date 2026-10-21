"""提醒胶囊：桌面「下一个提醒」小条（独立 ULW 窗口，逐像素 alpha）。

- 常驻显示最近一个待提醒事项：已到点显示「现在 · 标题」，未到显示倒计时
  （「12 分钟后 / 1h05m 后 / 明天 16:00」），无提醒时显示「暂无提醒」；
- 点击条身打开提醒事项页；✕ 收起胶囊；
- 可拖动移动（位置记忆）；颜色/透明度走设置页「桌面胶囊」模块（cap_reminder_*）。
"""

import time

from PIL import Image, ImageDraw

from .pill_window import PillWindow


class ReminderPill(PillWindow):
    KEY = "reminder"
    TITLE = "提醒胶囊"
    W, H = 280, 48
    DEFAULT_BG = "#ffffff"
    DEFAULT_OPACITY = 100

    def __init__(self):
        super().__init__()
        self._data = None
        self._last_key = None
        self._last_load = 0.0

    def default_pos(self, sw, sh):
        Wp, Hp = self.phys_size()
        return sw - Wp - 24, sh - Hp - 152

    # ---------- 数据 ----------
    def _fetch(self):
        from datetime import datetime

        from ..database import SessionLocal
        from ..models import Reminder
        from ..routers.reminders import serialize

        db = SessionLocal()
        try:
            now = datetime.now()
            rows = db.query(Reminder).filter(Reminder.status == "pending").all()
            items = [serialize(r, now) for r in rows]
        finally:
            db.close()
        overdue = [i for i in items if i["overdue"]]
        if overdue:
            overdue.sort(key=lambda x: x["remind_at"])
            top = overdue[0]
            return {"kind": "overdue", "title": top["title"], "at": top["remind_at"], "n": len(items)}
        best = None
        for i in items:
            t = i.get("next_trigger") or i.get("remind_at")
            if not t:
                continue
            if best is None or t < best[0]:
                best = (t, i)
        if best:
            return {"kind": "future", "title": best[1]["title"], "at": best[0], "n": len(items)}
        return {"kind": "none", "title": "", "at": None, "n": 0}

    def poll(self):
        now = time.monotonic()
        if now - self._last_load >= 10.0:
            self._last_load = now
            try:
                self._data = self._fetch()
            except Exception as e:
                print(f"[pill-reminder] fetch failed: {e}")
        d = self._data
        if d is None:
            return False
        from datetime import datetime

        if d["kind"] == "overdue":
            key = ("overdue", d["at"], d["title"])
        elif d["kind"] == "future":
            left = int((datetime.fromisoformat(d["at"]) - datetime.now()).total_seconds())
            key = ("future", d["at"], max(0, left) // 60, d["title"])
        else:
            key = ("none", d.get("n"))
        if key != self._last_key:
            self._last_key = key
            return True
        return False

    def _fmt_left(self, at_iso, now):
        from datetime import datetime

        try:
            at = datetime.fromisoformat(at_iso)
        except Exception:
            return ""
        left = (at - now).total_seconds()
        if left <= 0:
            return "现在"
        if left < 3600:
            return f"{max(1, int(left // 60))} 分钟后"
        if left < 86400:
            h = int(left // 3600)
            m = int((left % 3600) // 60)
            return f"{h}h{m:02d}m 后" if m else f"{h} 小时后"
        d = at.date()
        hm = f"{at.hour:02d}:{at.minute:02d}"
        days = (d - now.date()).days
        if days == 1:
            return f"明天 {hm}"
        return f"{at.month}月{at.day}日 {hm}"

    # ---------- 渲染 ----------
    def render(self, pal, style):
        from datetime import datetime

        SS = 3
        W, H = self.W * SS, self.H * SS
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)

        def P(x, y):
            return (x * SS, y * SS)

        # 胶囊底（悬停微亮）
        body_bg = pal["hover"] if self._inside else pal["bg"]
        d.rounded_rectangle([0, 0, W - 1, H - 1], radius=H // 2, fill=body_bg)
        d.rounded_rectangle([0, 0, W - 1, H - 1], radius=H // 2, outline=pal["border"], width=SS)

        data = self._data or {"kind": "none", "title": "", "at": None}
        kind = data["kind"]
        dot_col = {"overdue": pal["red"], "future": pal["accent"]}.get(kind, pal["disabled"])
        cx, cy, r = 18 * SS, H // 2, 5 * SS
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=dot_col)

        if kind == "none":
            f = self.font(12 * SS)
            d.text(P(32, self.H / 2), "暂无提醒", font=f, fill=pal["sub"], anchor="lm")
        else:
            now = datetime.now()
            if kind == "overdue":
                left_txt, left_col = "现在", pal["red"]
            else:
                left_txt, left_col = self._fmt_left(data["at"], now), pal["txt"]
            f1 = self.font(12 * SS, bold=True)
            d.text(P(32, self.H / 2), left_txt, font=f1, fill=left_col, anchor="lm")
            w1 = d.textlength(left_txt, font=f1) / SS
            f2 = self.font(11 * SS)
            remain = (self.W - 52) - (32 + w1 + 8)
            txt = self.ellipsis(d, f"· {data['title']}", f2, max(0, remain * SS)) if remain > 10 else ""
            d.text(P(32 + w1 + 8, self.H / 2), txt, font=f2, fill=pal["sub"], anchor="lm")

        # ✕ 关闭
        ccx, ccy = self.W - 21, self.H / 2
        cross_col = pal["red"] if self._hover == "close" else pal["icon"]
        d.line([P(ccx - 4.5, ccy - 4.5), P(ccx + 4.5, ccy + 4.5)], fill=cross_col,
               width=max(1, int(1.6 * SS)))
        d.line([P(ccx - 4.5, ccy + 4.5), P(ccx + 4.5, ccy - 4.5)], fill=cross_col,
               width=max(1, int(1.6 * SS)))

        self._zones = [("close", self.W - 40, 6, self.W - 4, 42)]
        return img.resize(self.phys_size(), Image.LANCZOS)

    # ---------- 交互 ----------
    def on_zone(self, name, event):
        if name == "close":
            self.hide()

    def on_body_click(self, event):
        from .notification import open_page

        open_page("#/reminders")


PILL = ReminderPill()
