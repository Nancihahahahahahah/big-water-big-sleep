#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🌿 大水大睡大健康 — Health Float
桌面浅蓝小泡泡：平时只显示下一个提醒的 icon，快到点时弹出来预告，
提醒时只展示当前这一件事。所有时间使用本机系统时钟，换电脑无需改任何配置。

提醒项与频率在 config.json 里改。
用法： python3 health_float.py   （Windows 用 pythonw）
"""

import json
import os
import subprocess
import sys
import tkinter as tk
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
SOUND = "/System/Library/Sounds/Ping.aiff"

DEFAULT_CONFIG = {
    "eye_minutes": 20,          # 每 N 分钟：看远方（0 = 关闭）
    "move_minutes": 60,         # 每 N 分钟：站起来动一动（0 = 关闭）
    "water_minutes": 120,       # 每 N 分钟：喝杯水（0 = 关闭）
    "shower_time": "21:30",     # 每天提醒洗澡（"" = 关闭）
    "sleep_time": "22:30",      # 每天提醒睡觉（"" = 关闭）
    "prewarn_seconds": 120,     # 提前多少秒弹出预告（0 = 不预告）
    "sound": True,              # 提醒时是否播放提示音（仅 macOS）
    "opacity": 0.92             # 泡泡透明度 0~1
}


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
            cfg.update({k: v for k, v in user_cfg.items() if k in DEFAULT_CONFIG})
        except (json.JSONDecodeError, OSError) as e:
            print(f"[health-float] 配置读取失败，使用默认配置: {e}")
    else:
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
        except OSError:
            pass
    return cfg


def parse_hhmm(s):
    try:
        h, m = s.strip().split(":")
        h, m = int(h), int(m)
        if 0 <= h <= 23 and 0 <= m <= 59:
            return h, m
    except (ValueError, AttributeError):
        pass
    return None


def next_daily(h, m):
    """下一个每日定时点（本机时区，今天已过则算明天）"""
    now = datetime.now()
    t = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if t <= now:
        t += timedelta(days=1)
    return t


def ui_font(size, bold=False):
    if sys.platform == "darwin":
        fam = "PingFang SC"
    elif os.name == "nt":
        fam = "Microsoft YaHei"
    else:
        fam = "Noto Sans CJK SC"
    return (fam, size, "bold" if bold else "normal")


# key -> (标题, 副文案, icon, 自动关闭秒数)
ALERT_META = {
    "eye":    ("该看远方啦", "望向 6 米外 20 秒，让眼睛休息一下", "👀", 20),
    "move":   ("起来动一动", "站起来伸展 1 分钟，久坐是慢性刺客", "🧘", 90),
    "water":  ("喝杯水吧",   "水是身体的第一供应商", "💧", 60),
    "shower": ("去洗澡啦",   "早点洗澡，晚上睡得更香", "🛁", 120),
    "sleep":  ("该睡觉啦",   "放下屏幕，明天还有满格的自己", "🌙", 120),
}

# ---------- 泡泡主题（浅蓝） ----------
C_BUBBLE = "#d3e8fb"      # 泡泡浅蓝
C_BUBBLE_EDGE = "#a9cdf0"
C_HOT = "#c2defc"         # 预告/提醒时稍深
C_ICON = "#1f4e79"        # 深蓝 icon/文字
C_DIM = "#5b84ad"
C_ACCENT_BG = "#1f4e79"   # 按钮底
C_ACCENT_FG = "#eaf4ff"


class FloatApp:
    BUBBLE = 84          # 泡泡直径（px）
    PRE = 104            # 预告时直径
    AW = 240             # 提醒卡宽
    AH = 178             # 提醒卡高

    def __init__(self, root, cfg):
        self.root = root
        self.cfg = cfg
        self.queue = []
        self.current = None
        self.auto_left = 0
        self.view = None         # (mode, key) 记录当前视图，避免每秒重建闪烁
        self.pulse = False
        self.next_run = self._build_schedule()

        root.title("Health Float")
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        try:
            root.attributes("-alpha", float(cfg.get("opacity", 0.92)))
        except (tk.TclError, ValueError):
            pass
        # 圆形透明支持（Windows/X11 可用；macOS 自动回退为浅蓝圆角观感）
        try:
            root.attributes("-transparentcolor", "#010203")
            self.circle = True
        except tk.TclError:
            self.circle = False

        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        self.x, self.y = sw - 160, sh - 200
        root.geometry(f"+{self.x}+{self.y}")

        self._drag_bind()
        root.after(1000, self._tick)

    # ---------- 调度 ----------
    def _build_schedule(self):
        cfg, now = self.cfg, datetime.now()
        schedule, self.reschedule = {}, {}
        for key, cfg_key in (("eye", "eye_minutes"), ("move", "move_minutes"),
                             ("water", "water_minutes")):
            v = cfg.get(cfg_key, 0)
            try:
                v = int(v)
            except (TypeError, ValueError):
                v = 0
            if v > 0:
                schedule[key] = now + timedelta(minutes=v)
                self.reschedule[key] = ("interval", timedelta(minutes=v))
        for key, cfg_key in (("shower", "shower_time"), ("sleep", "sleep_time")):
            hm = parse_hhmm(cfg.get(cfg_key, "") or "")
            if hm:
                schedule[key] = next_daily(*hm)
                self.reschedule[key] = ("daily", hm)
        return schedule

    def _next_event(self):
        if not self.next_run:
            return None, 0
        key = min(self.next_run, key=lambda k: self.next_run[k])
        return key, int((self.next_run[key] - datetime.now()).total_seconds())

    # ---------- 视图 ----------
    def _set_view(self, mode, key=None):
        if self.view == (mode, key):
            return
        self.view = (mode, key)
        if mode == "bubble":
            self._build_bubble(self.BUBBLE, False)
        elif mode == "pre":
            self._build_bubble(self.PRE, True)
        elif mode == "alert":
            self._build_alert(key)

    def _clear(self):
        for w in self.root.winfo_children():
            w.destroy()
        self.root.configure(bg="#010203" if self.circle else C_BUBBLE)

    def _build_bubble(self, size, pre):
        self._clear()
        pad = 3
        self.root.geometry(f"{size}x{size}+{self.x}+{self.y}")
        cv = tk.Canvas(self.root, width=size, height=size,
                       bg="#010203" if self.circle else C_BUBBLE,
                       highlightthickness=0)
        cv.pack()
        cv.create_oval(pad, pad, size - pad, size - pad,
                       fill=C_HOT if pre else C_BUBBLE,
                       outline=C_BUBBLE_EDGE, width=2)
        key, left = self._next_event()
        icon = ALERT_META[key][2] if key else "🌿"
        cv.create_text(size // 2, size // 2 - (8 if pre else 4),
                       text=icon, font=ui_font(30 if pre else 26), fill=C_ICON)
        if pre:
            label = "马上！" if left <= 10 else f"{left} 秒"
            cv.create_text(size // 2, size - 24, text=label,
                           font=ui_font(11, True), fill=C_ICON)
        else:
            m = left // 60
            text = f"{m}分" if m >= 1 else f"{left}秒"
            cv.create_text(size // 2, size - 22, text=text,
                           font=ui_font(10), fill=C_DIM)
        cv.bind("<Button-1>", self._drag_start, add="+")
        cv.bind("<B1-Motion>", self._drag_move, add="+")

    def _build_alert(self, key):
        title, sub, icon, _ = ALERT_META[key]
        self._clear()
        self.root.geometry(f"{self.AW}x{self.AH}+{self.x}+{self.y}")
        f = tk.Frame(self.root, bg=C_HOT, padx=16, pady=10)
        f.pack(expand=True)
        tk.Label(f, text=icon, font=ui_font(38), bg=C_HOT).pack()
        tk.Label(f, text=title, font=ui_font(15, True), bg=C_HOT,
                 fg=C_ICON).pack()
        tk.Label(f, text=sub, font=ui_font(11), bg=C_HOT, fg=C_DIM,
                 wraplength=200, justify="center").pack(pady=(2, 4))
        self.auto_left = ALERT_META[key][3]
        if key == "eye":
            self.count_label = tk.Label(f, text="", font=ui_font(13, True),
                                        bg=C_HOT, fg=C_ICON)
            self.count_label.pack()
            btn = None
        else:
            btn = tk.Label(f, text="知道了 ✓", font=ui_font(11, True),
                           bg=C_ACCENT_BG, fg=C_ACCENT_FG, cursor="hand2",
                           padx=14, pady=4)
            btn.pack(pady=(2, 0))
            btn.bind("<Button-1>", lambda e: self._dismiss())
        self.auto_hint = tk.Label(f, text="", font=ui_font(9), bg=C_HOT, fg=C_DIM)
        self.auto_hint.pack()
        for w in f.winfo_children():
            w.bind("<Button-1>", self._drag_start, add="+")
            w.bind("<B1-Motion>", self._drag_move, add="+")
        self._update_auto_hint()

    # ---------- 交互 ----------
    def _drag_bind(self):
        pass  # 拖拽绑定在各视图内部完成

    def _drag_start(self, e):
        self.dx, self.dy = e.x, e.y

    def _drag_move(self, e):
        self.x = self.root.winfo_x() + e.x - self.dx
        self.y = self.root.winfo_y() + e.y - self.dy
        self.root.geometry(f"+{self.x}+{self.y}")

    def _dismiss(self):
        self.current = None
        self.view = None
        try:
            self.root.attributes("-alpha", float(self.cfg.get("opacity", 0.92)))
        except (tk.TclError, ValueError):
            pass

    # ---------- 主循环 ----------
    def _tick(self):
        now = datetime.now()
        for key, t in list(self.next_run.items()):
            if now >= t:
                self.queue.append(key)
                kind, param = self.reschedule[key]
                if kind == "daily":
                    self.next_run[key] = next_daily(*param)
                else:
                    self.next_run[key] = now + param
                self.view = None   # 触发后强制刷新视图

        if self.current is None and self.queue:
            self.current = self.queue.pop(0)
            self._play_sound()
            self._set_view("alert", self.current)

        if self.current is not None:
            if self.auto_left > 0:
                self.auto_left -= 1
                self._update_auto_hint()
            if self.auto_left == 0:
                self._dismiss()
        else:
            key, left = self._next_event()
            if key:
                pre = int(self.cfg.get("prewarn_seconds", 120))
                if pre > 0 and 0 < left <= pre:
                    self._set_view("pre", key)
                else:
                    self._set_view("bubble", key)
        self.root.lift()
        self.root.after(1000, self._tick)

    def _update_auto_hint(self):
        if not getattr(self, "auto_hint", None) or not self.auto_hint.winfo_exists():
            return
        if self.current == "eye" and hasattr(self, "count_label"):
            self.count_label.config(text=f"{max(self.auto_left, 0)} 秒")
        self.auto_hint.config(
            text=f"{self.auto_left} 秒后自动消失" if self.auto_left > 0 else "")

    def _play_sound(self):
        if not self.cfg.get("sound") or sys.platform != "darwin":
            return
        try:
            subprocess.Popen(["afplay", SOUND],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass


def main():
    cfg = load_config()
    root = tk.Tk()
    FloatApp(root, cfg)
    root.mainloop()


if __name__ == "__main__":
    main()
