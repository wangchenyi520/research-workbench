"""今日清单胶囊：悬浮清单最小化后的桌面小条（独立 ULW 窗口，逐像素 alpha）。

- 由 checklist_widget 的「− 最小化」/ 启动恢复（pref.minimized）触发显示；
- 点击小条任意处 → 还原悬浮小窗；可拖动移动（位置记忆）；
- 颜色/透明度走设置页「桌面胶囊」模块（cap_checklist_*），未设置跟随默认白卡。
"""

import time

from PIL import Image, ImageDraw

from .pill_window import PillWindow


class ChecklistPill(PillWindow):
    KEY = "checklist"
    TITLE = "今日清单"
    W, H = 200, 40
    DEFAULT_BG = "#ffffff"
    DEFAULT_OPACITY = 100

    def __init__(self):
        super().__init__()
        self._done = 0
        self._total = 0
        self._last_load = 0.0

    def default_pos(self, sw, sh):
        return sw - self.W - 24, sh - self.H - 48

    def _refresh_style(self):
        """清单胶囊外观：单独设置过用独立值，否则跟随「桌面清单」小窗的背景色/透明度。"""
        from ..database import SessionLocal
        from ..models import Setting
        from . import widget_style

        raw_bg, raw_op = widget_style.fetch_cap_raw("checklist")
        rows = {}
        db = SessionLocal()
        try:
            for r in db.query(Setting).filter(
                Setting.key.in_(["checklist_widget_bg", "checklist_widget_opacity"])
            ).all():
                rows[r.key] = (r.value or "").strip()
        finally:
            db.close()
        bg = widget_style.normalize_bg(raw_bg or rows.get("checklist_widget_bg"), "#ffffff")
        op = widget_style.clamp_opacity(raw_op, fallback=widget_style.clamp_opacity(rows.get("checklist_widget_opacity"), 100))
        st = {"bg": bg, "opacity": op}
        if st != self._style:
            self._style = st
            self._dirty = True

    def poll(self):
        now = time.monotonic()
        if now - self._last_load < 2.0:
            return False
        self._last_load = now
        try:
            from ..database import SessionLocal
            from .daily_ops import fetch_checklist

            db = SessionLocal()
            try:
                data = fetch_checklist(db)
            finally:
                db.close()
            pend = data.get("pending", [])
            done = data.get("done", [])
            nd, nt = len(done), len(done) + len(pend)
            if (nd, nt) != (self._done, self._total):
                self._done, self._total = nd, nt
                return True
        except Exception as e:
            print(f"[pill-checklist] fetch failed: {e}")
        return False

    def render(self, pal, style):
        SS = 3
        W, H = self.W * SS, self.H * SS
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)

        def P(x, y):
            return (x * SS, y * SS)

        # 胶囊底（悬停微亮）
        bg = pal["hover"] if self._inside else pal["bg"]
        d.rounded_rectangle([0, 0, W - 1, H - 1], radius=H // 2, fill=bg)
        d.rounded_rectangle([0, 0, W - 1, H - 1], radius=H // 2, outline=pal["border"], width=SS)
        # 圆形勾选图标
        cx, cy, r = 20 * SS, H // 2, 8 * SS
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=pal["accent"])
        d.line([P(16, 20.2), P(18.8, 23), P(24.4, 16.6)], fill="#ffffff",
               width=max(2, int(2.1 * SS)), joint="curve")
        # 文案
        f = self.font(12 * SS)
        d.text((33 * SS, H // 2), f"今日清单 {self._done}/{self._total}", font=f,
               fill=pal["txt"], anchor="lm")
        # 右侧展开箭头（向上）
        ax, ay = self.W - 18, self.H / 2
        d.line([P(ax - 4, ay + 2.5), P(ax, ay - 2), P(ax + 4, ay + 2.5)], fill=pal["icon"],
               width=max(1, int(1.8 * SS)), joint="curve")
        self._zones = []
        return img.resize(self.phys_size(), Image.LANCZOS)

    def on_body_click(self, event):
        from . import checklist_widget

        checklist_widget.restore_from_pill()


PILL = ChecklistPill()
