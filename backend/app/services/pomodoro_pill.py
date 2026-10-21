"""番茄钟胶囊：悬浮钟最小化后的桌面小条（独立 ULW 窗口，逐像素 alpha）。

- 由悬浮钟左上角「—」按钮触发（隐藏大钟、显示本胶囊）；
- 点击小条 = 展开大钟；点击右侧按钮 = 暂停/继续（与页面卡片同一条 control 路径）；
- 计时结束（完成/放弃/自动流转）时胶囊自动隐藏；
- 颜色/透明度走设置页「桌面胶囊」模块（cap_pomodoro_*，默认深色玻璃底）。
"""

from PIL import Image, ImageDraw

from .pill_window import PillWindow


class PomodoroPill(PillWindow):
    KEY = "pomodoro"
    TITLE = "番茄钟胶囊"
    W, H = 240, 48
    DEFAULT_BG = "#1f1f33"
    DEFAULT_OPACITY = 97

    def __init__(self):
        super().__init__()
        self._s = {}
        self._last_key = None

    def default_pos(self, sw, sh):
        Wp, Hp = self.phys_size()
        return sw - Wp - 44, sh - Hp - 144

    def poll(self):
        from . import pomodoro_widget as pw

        s = pw.public_state()
        if not s.get("active") or not s.get("mini"):
            # 计时结束 / 大钟已展开 → 胶囊自动收起（自愈保险）
            if self.is_active():
                self.hide()
            return False
        key = (s.get("mode"), s.get("phase"), bool(s.get("paused")),
               int(s.get("remaining") or 0), int(s.get("elapsed") or 0), s.get("title") or "")
        if key != self._last_key:
            self._last_key = key
            self._s = s
            return True
        return False

    def render(self, pal, style):
        from . import widget_style

        s = self._s
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
        # 状态圆点：工作=主题色 / 休息=绿 / 暂停=黄
        paused = bool(s.get("paused"))
        if paused:
            col = pal["yellow"]
        elif s.get("phase") == "break":
            col = pal["green"]
        else:
            col = pal["accent"]
        cx, cy, r = 18 * SS, H // 2, 5 * SS
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)
        # 剩余时间（番茄=倒计时 / 自由=正计时）
        if s.get("mode") == "free":
            t = widget_style.fmt_clock(s.get("elapsed") or 0)
        else:
            t = widget_style.fmt_clock(s.get("remaining") or 0)
        ft = self.mono_font(14 * SS, bold=True)
        d.text((32 * SS, H // 2), t, font=ft, fill=pal["txt"], anchor="lm")
        # 标题
        title = s.get("title") or "番茄钟"
        head_w = d.textlength(t, font=ft)
        f2 = self.font(11 * SS)
        max_w = (self.W - 62) * SS - (32 * SS + head_w + 8 * SS)
        d.text((32 * SS + head_w + 8 * SS, H // 2), self.ellipsis(d, title, f2, max(0, max_w)),
               font=f2, fill=pal["sub"], anchor="lm")
        # 右侧暂停/继续按钮（PIL 直接画图形，不依赖符号字体）
        pcx, pcy, pr = (self.W - 30) * SS, H // 2, 14 * SS
        base = pal["btn_hover"] if self._hover == "pause" else pal["btn_bg"]
        d.ellipse([pcx - pr, pcy - pr, pcx + pr, pcy + pr], fill=base, outline=pal["border"], width=SS)
        icon_col = pal["txt"]
        if paused:
            d.polygon([P(self.W - 34, 18), P(self.W - 34, 30), P(self.W - 24, 24)], fill=icon_col)
        else:
            d.rectangle([P(self.W - 35, 18), P(self.W - 32.5, 30)], fill=icon_col)
            d.rectangle([P(self.W - 28, 18), P(self.W - 25.5, 30)], fill=icon_col)
        self._zones = [("pause", self.W - 46, 2, self.W - 2, self.H - 2)]
        return img.resize(self.phys_size(), Image.LANCZOS)

    def on_zone(self, name, event):
        if name == "pause":
            from . import pomodoro_widget as pw

            pw.toggle_pause()

    def on_body_click(self, event):
        from . import pomodoro_widget as pw

        pw.restore_from_pill()


PILL = PomodoroPill()
