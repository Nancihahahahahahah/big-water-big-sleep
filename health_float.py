#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🌿 Health Float — 健康浮窗
一个永远置顶的桌面小卡片，温柔地提醒你：
看远方、起来动一动、喝水、洗澡、睡觉。

所有提醒间隔和定时点都在 config.json 里改，无需动代码。

用法：
    python3 health_float.py
（Windows 用 pythonw 运行可隐藏控制台）
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
    "shower_time": "21:30",     # 每天提醒洗澡的时间（"" = 关闭）
    "sleep_time": "22:30",      # 每天提醒睡觉的时间（"" = 关闭）
    "sound": True,              # 提醒时是否播放提示音（仅 macOS）
    "opacity": 0.88             # 待机时透明度 0~1
}


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
            cfg.update({k: v for k, v in user_cfg.items() if k in DEFAULT_CONFIG})
        except (json.JSONDecodeError, OSError) as e:
            print(f"[health-float] 配置文件读取失败，使用默认配置: {e}")
    else:
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
        except OSError:
            pass
    return cfg


def parse_hhmm(s):
    """'21:30' -> (21, 30)；解析失败返回 None"""
    try:
        h, m = s.strip().split(":")
        h, m = int(h), int(m)
        if 0 <= h <= 23 and 0 <= m <= 59:
            return h, m
    except (ValueError, AttributeError):
        pass
    return None


def next_daily(h, m):
    """下一个每日定时点（今天已过则算明天）"""
    now = datetime.now()
    t = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if t <= now:
        t += timedelta(days=1)
    return t


class FloatApp:
    # ---------- 主题 ----------
    C_BG = "#1f2430"
    C_BG_HOT = "#2b3550"
    C_FG = "#e8ecf4"
    C_DIM = "#8b93a7"
    C_ACCENT = "#7fd1a8"

    def __init__(self, root, cfg):
        self.root = root
        self.cfg = cfg
        self.queue = []          # 待展示提醒 key 队列
        self.current = None      # 当前展示的提醒 key
        self.auto_left = 0
        self.collapsed = False
        self.next_run = self._build_schedule()
        self.reschedule = {}     # key -> (类型, 参数)，触发后用来排下一次

        root.title("Health Float")
        root.overrideredirect(True)          # 无边框
        root.attributes("-topmost", True)    # 永远置顶
        try:
            root.attributes("-alpha", float(cfg.get("opacity", 0.88)))
        except (tk.TclError, ValueError):
            pass
        root.configure(bg=self.C_BG)

        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        self.x, self.y = sw - 280, sh - 220
        root.geometry(f"+{self.x}+{self.y}")

        self._build_idle()
        self._drag_bind()
        root.after(1000, self._tick)

    # ---------- 调度 ----------
    def _build_schedule(self):
        cfg, now = self.cfg, datetime.now()
        schedule, self.reschedule = {}, {}
        for key, cfg_key, minutes in (("eye", "eye_minutes", None),
                                      ("move", "move_minutes", None),
                                      ("water", "water_minutes", None)):
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

    # ---------- UI ----------
    def _clear(self):
        for w in self.root.winfo_children():
            w.destroy()

    def _build_idle(self):
        self._clear()
        self.root.configure(bg=self.C_BG)
        f = tk.Frame(self.root, bg=self.C_BG, padx=14, pady=10)
        f.pack()
        top = tk.Frame(f, bg=self.C_BG)
        top.pack(fill="x")
        tk.Label(top, text="🌿 Health Float", font=("PingFang SC", 13, "bold"),
                 bg=self.C_BG, fg=self.C_FG).pack(side="left")
        minus = tk.Label(top, text="—", font=("PingFang SC", 11),
                         bg=self.C_BG, fg=self.C_DIM, cursor="hand2")
        minus.pack(side="right")
        minus.bind("<Button-1>", lambda e: self._collapse())
        self.next_label = tk.Label(f, text="", font=("PingFang SC", 10),
                                   bg=self.C_BG, fg=self.C_DIM, justify="left")
        self.next_label.pack(anchor="w", pady=(6, 0))
        self._update_next_label()

    def _build_collapsed(self):
        self._clear()
        dot = tk.Label(self.root, text=" 🌿 ", font=("PingFang SC", 14),
                       bg=self.C_BG, fg=self.C_FG, cursor="hand2")
        dot.pack(padx=4, pady=3)
        dot.bind("<Button-1>", lambda e: self._expand())

    def _build_alert(self, key):
        title, sub, emoji, auto_secs = ALERT_META[key]
        self._clear()
        self.root.configure(bg=self.C_BG_HOT)
        f = tk.Frame(self.root, bg=self.C_BG_HOT, padx=18, pady=14)
        f.pack()
        tk.Label(f, text=f"{emoji}  {title}", font=("PingFang SC", 15, "bold"),
                 bg=self.C_BG_HOT, fg=self.C_ACCENT).pack()
        tk.Label(f, text=sub, font=("PingFang SC", 11),
                 bg=self.C_BG_HOT, fg=self.C_FG, wraplength=210,
                 justify="center").pack(pady=(6, 4))
        self.auto_left = auto_secs
        if key == "eye":
            self.count_label = tk.Label(f, text="", font=("PingFang SC", 13, "bold"),
                                        bg=self.C_BG_HOT, fg=self.C_FG)
            self.count_label.pack()
        else:
            btn = tk.Label(f, text="知道了 ✓", font=("PingFang SC", 11),
                           bg=self.C_ACCENT, fg="#14231b", cursor="hand2",
                           padx=14, pady=4)
            btn.pack(pady=(4, 0))
            btn.bind("<Button-1>", lambda e: self._dismiss())
        self.auto_hint = tk.Label(f, text="", font=("PingFang SC", 9),
                                  bg=self.C_BG_HOT, fg=self.C_DIM)
        self.auto_hint.pack()
        self._update_auto_hint()

    # ---------- 交互 ----------
    def _drag_bind(self):
        for w in self.root.winfo_children():
            self._bind_tree(w)

    def _bind_tree(self, w):
        w.bind("<Button-1>", self._drag_start, add="+")
        w.bind("<B1-Motion>", self._drag_move, add="+")
        for c in w.winfo_children():
            self._bind_tree(c)

    def _drag_start(self, e):
        self.dx, self.dy = e.x, e.y

    def _drag_move(self, e):
        self.x = self.root.winfo_x() + e.x - self.dx
        self.y = self.root.winfo_y() + e.y - self.dy
        self.root.geometry(f"+{self.x}+{self.y}")

    def _collapse(self):
        self.collapsed = True
        self._build_collapsed()

    def _expand(self):
        self.collapsed = False
        self._build_idle()

    def _dismiss(self):
        self.current = None
        try:
            self.root.attributes("-alpha", float(self.cfg.get("opacity", 0.88)))
        except (tk.TclError, ValueError):
            pass
        self._build_collapsed() if self.collapsed else self._build_idle()

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
        if self.current is None and self.queue:
            self.current = self.queue.pop(0)
            self._play_sound()
            self._build_alert(self.current)
            try:
                self.root.attributes("-alpha", 0.98)
            except tk.TclError:
                pass
        if self.current is not None:
            if self.auto_left > 0:
                self.auto_left -= 1
                self._update_auto_hint()
            if self.auto_left == 0:
                self._dismiss()
        if not self.collapsed and self.current is None:
            self._update_next_label()
        self.root.lift()
        self.root.after(1000, self._tick)

    def _update_auto_hint(self):
        if not getattr(self, "auto_hint", None) or not self.auto_hint.winfo_exists():
            return
        if self.current == "eye" and hasattr(self, "count_label"):
            self.count_label.config(text=f"{max(self.auto_left, 0)} 秒")
        if self.auto_left > 0:
            self.auto_hint.config(text=f"{self.auto_left} 秒后自动消失")
        else:
            self.auto_hint.config(text="")

    def _update_next_label(self):
        now = datetime.now()
        lines = []
        for key in ("eye", "move", "water", "shower", "sleep"):
            if key not in self.next_run:
                continue
            _, _, emoji, _ = ALERT_META[key]
            mins = int((self.next_run[key] - now).total_seconds() // 60)
            s = f"{mins // 60}时{mins % 60:02d}分" if mins >= 60 else f"{mins} 分钟"
            lines.append(f"{emoji} {s}")
        self.next_label.config(text="\n".join(lines) if lines else "（所有提醒已关闭）")

    def _play_sound(self):
        if not self.cfg.get("sound") or sys.platform != "darwin":
            return
        try:
            subprocess.Popen(["afplay", SOUND],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass


ALERT_META = {
    "eye":    ("该看远方啦", "望向 6 米外 20 秒，让眼睛休息一下", "👀", 20),
    "move":   ("起来动一动", "站起来伸展 1 分钟，久坐是慢性刺客", "🧘", 90),
    "water":  ("喝杯水吧",   "水是身体的第一供应商", "💧", 60),
    "shower": ("去洗澡啦",   "早点洗澡，晚上睡得更香", "🛁", 120),
    "sleep":  ("该睡觉啦",   "放下屏幕，明天还有满格的自己", "🌙", 120),
}


def main():
    cfg = load_config()
    root = tk.Tk()
    FloatApp(root, cfg)
    root.mainloop()


if __name__ == "__main__":
    main()
