#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
✈️ 大水大睡大健康 — Health Float
桌面常驻的「飞机舷窗」小浮窗：
- 固定尺寸，不缩放不变形；文字精排在舷窗下方灰区
- 首次启动自动弹出引导，闹钟式上下拨动设置洗澡/睡觉时间
- 双击浮窗随时打开设置面板（同样的拨轮）
- 洗澡/睡觉提醒前可全屏黑屏 10 秒（blackout_seconds）
- 所有时间读本机系统时钟，换电脑无需配置

用法： python3 health_float.py   （Windows 用 pythonw）
"""

import glob
import json
import math
import os
import re
import subprocess
import sys
import tkinter as tk
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
SOUND = "/System/Library/Sounds/Ping.aiff"

DEFAULT_CONFIG = {
    "eye_minutes": 20,          # 每 N 分钟：看远方（0 = 关闭）
    "move_minutes": 60,         # 每 N 分钟：站起来动一动（0 = 关闭）
    "water_minutes": 120,       # 每 N 分钟：喝杯水（0 = 关闭）
    "shower_time": "21:30",     # 每天提醒洗澡（"" = 关闭）
    "sleep_time": "22:30",      # 每天提醒睡觉（"" = 关闭）
    "prewarn_seconds": 120,     # 提前多少秒开始呼吸提示（0 = 关闭）
    "blackout_seconds": 10,     # 洗澡/睡觉提醒先黑屏 N 秒（0 = 关闭）
    "blackout_brief_seconds": 2,  # 眺望/站立提醒先黑屏 N 秒（0 = 关闭）
    "meeting_mode": False,      # 会议模式：开启后提醒永不黑屏
    "sound": True,              # 提醒时是否播放提示音（仅 macOS）
    "opacity": 0.96             # 舷窗透明度 0~1
}

# 设置面板字段：(config key, 标题, 说明, 类型)
SETT_ITEMS = [
    ("eye_minutes", "看远方 🪟", "每几分钟一次（0=关）", "int"),
    ("move_minutes", "起来动一动 🧘", "每几分钟一次（0=关）", "int"),
    ("water_minutes", "喝水 💧", "每几分钟一次（0=关）", "int"),
    ("shower_time", "洗澡提醒 🛁", "每天几点提醒", "time"),
    ("sleep_time", "睡觉提醒 🌙", "每天几点提醒", "time"),
    ("prewarn_seconds", "提前预告 ⏰", "提前几秒开始提示（0=关）", "int"),
    ("blackout_seconds", "洗澡/睡觉黑屏 🖥", "先黑屏几秒（0=关）", "int"),
    ("blackout_brief_seconds", "眺望/站立黑屏 🌑", "先黑屏几秒（0=关）", "int"),
    ("meeting_mode", "会议模式 🎙", "开启后提醒永不黑屏", "bool"),
    ("sound", "提示音 🔔", "提醒时播放提示音", "bool"),
]


# ---------------- 工具函数 ----------------
def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
            cfg.update({k: v for k, v in user_cfg.items() if k in DEFAULT_CONFIG})
        except (json.JSONDecodeError, OSError) as e:
            print(f"[health-float] 配置读取失败，使用默认配置: {e}")
    return cfg


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return True
    except OSError as e:
        print(f"[health-float] 配置保存失败: {e}")
        return False


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


def round_rect(cv, x1, y1, x2, y2, r, **kw):
    return cv.create_polygon(round_rect_pts(x1, y1, x2, y2, r), smooth=True, **kw)


def round_rect_pts(x1, y1, x2, y2, r):
    return [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
            x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]


# key -> (标题, 副文案, icon, 自动关闭秒数, 黑屏时长类别)
ALERT_META = {
    "eye":    ("该看远方啦", "望向 6 米外 20 秒\n让眼睛休息一下", "👀", 20, "brief"),
    "move":   ("起来动一动", "站起来伸展 1 分钟\n久坐是慢性刺客", "🧘", 90, "brief"),
    "water":  ("喝杯水吧",   "水是身体的\n第一供应商", "💧", 60, None),
    "shower": ("去洗澡啦",   "早点洗澡\n晚上睡得更香", "🛁", 120, "long"),
    "sleep":  ("该睡觉啦",   "放下屏幕\n明天还有满格的自己", "🌙", 120, "long"),
}

# —— 配色 / 尺寸（固定，不缩放）——
C_CABIN = "#b8bdc4"
C_TEXT = "#33465c"
C_DIM = "#5c6b7a"
C_PANEL = "#f4f6f9"
C_BTN_FG = "#f2f6fa"
BUBBLE = (140, 241)          # 常驻泡泡 = 素材图 140x193 + 下方文字条 48
BUBBLE_IMG = (140, 193)      # 素材图尺寸
STRIP_H = 48                 # 图下文字条高度（画布灰底，与图四角同色）
ALERT = (272, 230)
ALERT_IMG = (132, 182)
ALERT_IMG_XY = (10, 12)
PANEL = (152, 12, 262, 218)
PANEL_CX = 207


# ---------------- 闹钟式拨轮控件 ----------------
class TimeDial(tk.Frame):
    """HH : MM 两个可上下拨动的 Spinbox，像设闹钟一样"""

    def __init__(self, master, hhmm="21:30", changed=None):
        super().__init__(master)
        hm = parse_hhmm(hhmm) or (21, 30)
        self.var_h = tk.StringVar(value=f"{hm[0]:02d}")
        self.var_m = tk.StringVar(value=f"{hm[1]:02d}")
        self.changed = changed
        sb_kw = dict(width=3, font=ui_font(15, True), justify="center",
                     wrap=True, buttonbackground="#dfe5ec", relief="flat",
                     readonlybackground="#ffffff", bg="#ffffff",
                     fg=C_TEXT, insertbackground=C_TEXT)
        self.sp_h = tk.Spinbox(self, from_=0, to=23, textvariable=self.var_h,
                               command=self._on_change, **sb_kw)
        self.sp_m = tk.Spinbox(self, from_=0, to=55, increment=5,
                               textvariable=self.var_m, command=self._on_change,
                               **sb_kw)
        colon = tk.Label(self, text=":", font=ui_font(15, True), bg=master["bg"])
        self.sp_h.pack(side="left")
        colon.pack(side="left", padx=2)
        self.sp_m.pack(side="left")
        for sp in (self.sp_h, self.sp_m):
            sp.bind("<KeyRelease>", lambda e: self._on_change())

    def _on_change(self, *_):
        if self.changed:
            try:
                self.changed(self.get())
            except ValueError:
                pass

    def get(self):
        h = max(0, min(23, int(float(self.var_h.get() or 0))))
        m = max(0, min(59, int(float(self.var_m.get() or 0))))
        return f"{h:02d}:{m:02d}"


class NumDial(tk.Frame):
    """数字拨轮（上下箭头增减）"""

    def __init__(self, master, value=60, lo=0, hi=1440, step=5, unit="分钟",
                 width=5, changed=None):
        super().__init__(master)
        self.lo, self.hi = lo, hi
        self.var = tk.StringVar(value=str(int(value)))
        self.changed = changed
        self.sp = tk.Spinbox(self, from_=lo, to=hi, increment=step,
                             textvariable=self.var, width=width,
                             font=ui_font(12), justify="center", wrap=False,
                             buttonbackground="#dfe5ec", relief="flat",
                             bg="#ffffff", fg=C_TEXT, command=self._on_change)
        self.sp.pack(side="left")
        if unit:
            tk.Label(self, text=unit, font=ui_font(9), bg=master["bg"],
                     fg=C_DIM).pack(side="left", padx=(4, 0))
        self.sp.bind("<KeyRelease>", lambda e: self._on_change())

    def _on_change(self, *_):
        if self.changed:
            try:
                self.changed(self.get())
            except ValueError:
                pass

    def get(self):
        try:
            v = int(float(self.var.get() or 0))
        except ValueError:
            v = self.lo
        return max(self.lo, min(self.hi, v))


# ---------------- 设置窗口（双击浮窗打开 / 首次引导共用） ----------------
class SettingsDialog(tk.Toplevel):
    """所有提醒时间可视化设置：int 用数字拨轮，time 用闹钟拨轮"""

    def __init__(self, master, cfg, title="Health Float 设置",
                 intro="双击浮窗随时能回到这里修改"):
        super().__init__(master)
        self.cfg = cfg
        self.on_saved = None
        self.title(title)
        self.configure(bg="#ffffff")
        self.resizable(False, False)
        self.transient(master)

        tk.Label(self, text="🌿 大水大睡大健康", font=ui_font(15, True),
                 bg="#ffffff", fg=C_TEXT).pack(pady=(16, 2))
        tk.Label(self, text=intro, font=ui_font(9), bg="#ffffff",
                 fg=C_DIM).pack(pady=(0, 10))

        body = tk.Frame(self, bg="#ffffff", padx=22)
        body.pack()
        self.widgets = {}
        for i, (key, label, hint, kind) in enumerate(SETT_ITEMS):
            row = tk.Frame(body, bg="#ffffff")
            row.grid(row=i, column=0, sticky="w", pady=7)
            tk.Label(row, text=label, font=ui_font(11), bg="#ffffff",
                     fg=C_TEXT, width=12, anchor="w").pack(side="left")
            if kind == "int":
                w = NumDial(row, value=cfg.get(key, 0) or 0,
                            unit=("" if key == "sound" else
                                  "秒" if "seconds" in key else "分钟"))
                w.pack(side="left")
            elif kind == "time":
                w = TimeDial(row, hhmm=cfg.get(key) or "21:30")
                w.pack(side="left")
                tk.Label(row, text="(留 00:00 关)" if False else "",
                         bg="#ffffff").pack(side="left")
            else:  # bool
                var = tk.BooleanVar(value=bool(cfg.get(key)))
                w = tk.Checkbutton(row, variable=var, bg="#ffffff",
                                   activebackground="#ffffff")
                w.var = var
                w.pack(side="left")
            self.widgets[key] = w
            tk.Label(row, text=hint, font=ui_font(8), bg="#ffffff",
                     fg=C_DIM).pack(side="left", padx=(10, 0))

        btns = tk.Frame(self, bg="#ffffff")
        btns.pack(pady=(14, 18))
        ok = tk.Label(btns, text="保存 ✓", font=ui_font(11, True),
                      bg=C_TEXT, fg=C_BTN_FG, cursor="hand2",
                      padx=18, pady=5)
        ok.pack(side="left", padx=6)
        ok.bind("<Button-1>", lambda e: self._save())
        reset = tk.Label(btns, text="恢复默认", font=ui_font(10),
                         bg="#e9edf2", fg=C_DIM, cursor="hand2",
                         padx=12, pady=5)
        reset.pack(side="left", padx=6)
        reset.bind("<Button-1>", lambda e: self._reset())

        self.bind("<Return>", lambda e: self._save())
        self.bind("<Escape>", lambda e: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def collect(self):
        """读出表单 → dict；非法值返回 None"""
        out = {}
        for key, _, _, kind in SETT_ITEMS:
            w = self.widgets[key]
            if kind == "int":
                out[key] = w.get()
            elif kind == "time":
                out[key] = w.get()
            else:
                out[key] = bool(w.var.get())
        return out

    def _reset(self):
        for key, val in DEFAULT_CONFIG.items():
            if key not in self.widgets:
                continue
            w = self.widgets[key]
            if hasattr(w, "var_m"):          # TimeDial
                hm = parse_hhmm(str(val)) or (21, 30)
                w.var_h.set(f"{hm[0]:02d}")
                w.var_m.set(f"{hm[1]:02d}")
            elif hasattr(w, "var"):           # NumDial
                w.var.set(str(int(val)))
            else:                             # Checkbutton
                w.var.set(bool(val))

    def _save(self):
        out = self.collect()
        self.cfg.update(out)
        save_config(self.cfg)
        if self.on_saved:
            self.on_saved()
        self.destroy()


# ---------------- 主应用 ----------------
class FloatApp:
    def __init__(self, root, cfg):
        self.root = root
        self.cfg = cfg
        self.base_opacity = float(cfg.get("opacity", 0.96))
        self.queue = []
        self.current = None
        self.auto_left = 0
        self.hover = False
        self.prewarn = False
        self.phase = 0.0
        self.last_bob = 0.0
        self.blackout = None
        self.black_left = 0
        self.settings_win = None
        self.next_run = self._build_schedule()
        self.images = self._load_images()

        root.title("Health Float")
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        try:
            root.attributes("-alpha", self.base_opacity)
        except (tk.TclError, ValueError):
            pass
        root.configure(bg=C_CABIN)
        # macOS 有时会把无边框窗口重置回带红绿灯的标准窗口
        root.bind("<Map>", self._ensure_borderless, add="+")
        root.after(200, self._ensure_borderless)
        root.after(1200, self._ensure_borderless)

        self.w, self.h = BUBBLE
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        self.x, self.y = sw - 200, sh - 290
        root.geometry(f"{self.w}x{self.h}+{self.x}+{self.y}")

        self.cv = tk.Canvas(root, width=self.w, height=self.h,
                            bg=C_CABIN, highlightthickness=0, takefocus=0)
        self.cv.pack(fill="both", expand=True)
        self.cv.bind("<Button-1>", self._drag_start, add="+")
        self.cv.bind("<B1-Motion>", self._drag_move, add="+")
        self.cv.bind("<Double-Button-1>",
                     lambda e: self._open_settings(), add="+")
        self.cv.bind("<Button-3>", self._toggle_meeting, add="+")
        self.cv.bind("<Enter>", lambda e: self._set_hover(True), add="+")
        self.cv.bind("<Leave>", lambda e: self._set_hover(False), add="+")

        self._create_items()
        self._layout()

        root.after(50, self._animate)
        root.after(1000, self._tick)

    def _ensure_borderless(self, *_):
        try:
            if not self.root.overrideredirect():
                self.root.overrideredirect(True)
            self.root.attributes("-topmost", True)
        except tk.TclError:
            pass

    # ---------- 素材 ----------
    def _load_images(self):
        imgs = {}
        for path in glob.glob(os.path.join(ASSETS_DIR, "sz_*.png")):
            m = re.search(r"sz_(\d+)x(\d+)\.png$", path)
            if m:
                imgs[(int(m.group(1)), int(m.group(2)))] = tk.PhotoImage(file=path)
        return imgs

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
            if hm and (hm[0], hm[1]) != (0, 0):
                schedule[key] = next_daily(*hm)
                self.reschedule[key] = ("daily", hm)
        return schedule

    def _next_event(self):
        if not self.next_run:
            return None, 0
        key = min(self.next_run, key=lambda k: self.next_run[k])
        return key, int((self.next_run[key] - datetime.now()).total_seconds())

    # ---------- 常驻元素（只创建一次） ----------
    def _create_items(self):
        cv = self.cv
        self.img_id = cv.create_image(0, 0, anchor="nw")
        self.icon_id = cv.create_text(
            0, 0, text="🌿", font=ui_font(28), fill=C_TEXT, tags=("icon",))
        # 泡泡文字：素材灰区（GRAY_Y 之下）两行，行距舒展
        self.time_id = cv.create_text(0, 0, text="", font=ui_font(10, True),
                                      fill=C_TEXT)
        self.name_id = cv.create_text(0, 0, text="", font=ui_font(8),
                                      fill=C_DIM)
        # 提醒卡右栏（白色圆角面板）
        self.panel_id = round_rect(cv, *PANEL, 10, fill=C_PANEL,
                                   outline="#dde3ea")
        self.a_title_id = cv.create_text(0, 0, text="", font=ui_font(13, True),
                                         fill=C_TEXT)
        self.a_sub_id = cv.create_text(0, 0, text="", font=ui_font(10),
                                       fill=C_DIM, justify="center")
        self.a_count_id = cv.create_text(0, 0, text="",
                                         font=ui_font(13, True), fill=C_TEXT)
        self.a_btn_id = round_rect(cv, 0, 0, 10, 10, 8, fill=C_TEXT,
                                   outline="", tags=("btn",))
        self.a_btn_txt = cv.create_text(0, 0, text="知道了 ✓",
                                        font=ui_font(10, True), fill=C_BTN_FG)
        self.a_hint_id = cv.create_text(0, 0, text="", font=ui_font(8),
                                        fill=C_DIM)
        cv.tag_bind("btn", "<Button-1>", lambda e: self._dismiss())
        cv.tag_bind("a_btn_txt", "<Button-1>", lambda e: self._dismiss())

    def _hide(self, *ids):
        for i in ids:
            self.cv.itemconfig(i, state="hidden")

    def _show(self, *ids):
        for i in ids:
            self.cv.itemconfig(i, state="normal")

    # ---------- 布局（固定尺寸） ----------
    def _layout(self):
        if self.current:
            self._layout_alert()
        else:
            self._layout_bubble()

    def _layout_bubble(self):
        cv = self.cv
        w, h = self.w, self.h
        self._hide(self.a_title_id, self.a_sub_id, self.a_count_id,
                   self.a_btn_id, self.a_btn_txt, self.a_hint_id,
                   self.panel_id)
        self._show(self.icon_id, self.time_id, self.name_id)
        img = self.images.get(BUBBLE_IMG)
        if img:
            cv.itemconfig(self.img_id, image=img)
        cv.coords(self.img_id, 0, 0)
        cv.coords(self.icon_id, BUBBLE_IMG[0] * 0.535, BUBBLE_IMG[1] * 0.46)
        # 文字条在图片下方（y >= 193），与图物理隔离，行距舒展
        cv.coords(self.time_id, w / 2, BUBBLE_IMG[1] + 12)
        cv.coords(self.name_id, w / 2, BUBBLE_IMG[1] + 34)
        self._update_countdown()

    def _layout_alert(self):
        cv = self.cv
        key = self.current
        title, sub, icon, _, _ = ALERT_META[key]
        ix, iy = ALERT_IMG_XY
        self._show(self.panel_id)   # 面板位置固定，创建时已定，无需重设坐标
        self._hide(self.time_id, self.name_id)
        self._show(self.icon_id)
        cv.itemconfig(self.icon_id, font=ui_font(26))
        cv.coords(self.icon_id,
                  ix + ALERT_IMG[0] * 0.535, iy + ALERT_IMG[1] * 0.46)
        img = self.images.get(ALERT_IMG)
        if img:
            cv.itemconfig(self.img_id, image=img)
        cv.coords(self.img_id, ix, iy)
        self._show(self.a_title_id, self.a_sub_id, self.a_hint_id)
        cv.coords(self.a_title_id, PANEL_CX, 38)
        cv.itemconfig(self.a_title_id, text=f"{icon} {title}")
        cv.coords(self.a_sub_id, PANEL_CX, 74)
        cv.itemconfig(self.a_sub_id, text=sub, width=100)
        if key == "eye":
            self._hide(self.a_btn_id, self.a_btn_txt)
            self._show(self.a_count_id)
            cv.coords(self.a_count_id, PANEL_CX, 132)
        else:
            self._hide(self.a_count_id)
            self._show(self.a_btn_id, self.a_btn_txt)
            bb = cv.bbox(self.a_btn_id)
            if bb:
                cv.move(self.a_btn_id, 169 - bb[0], 156 - bb[1])
            else:
                cv.coords(self.a_btn_id, *round_rect_pts(169, 156, 245, 180, 8))
        cv.coords(self.a_hint_id, PANEL_CX, 203)

    def _resize_to(self, w, h):
        self.x += self.w - w
        self.y += self.h - h
        self.w, self.h = w, h
        self.root.geometry(f"{w}x{h}+{self.x}+{self.y}")
        self.cv.config(width=w, height=h)
        self._ensure_borderless()

    # ---------- 动画（icon 漂浮 + 呼吸） ----------
    def _animate(self):
        try:
            self._animate_step()
        except Exception as e:
            print(f"[health-float] 动画帧异常（已跳过）: {e}")
        finally:
            self.root.after(50, self._animate)

    def _animate_step(self):
        cv = self.cv
        self.phase += 0.06
        amp = 3.2 if self.prewarn else 2.2
        bob = math.sin(self.phase) * amp
        cv.move("icon", 0, bob - self.last_bob)
        self.last_bob = bob
        try:
            if self.prewarn and not self.current:
                glow = (math.sin(self.phase * 2) + 1) / 2
                self.root.attributes(
                    "-alpha", self.base_opacity - 0.08 + 0.08 * glow)
            elif self.hover:
                self.root.attributes("-alpha", min(1.0, self.base_opacity + 0.04))
            else:
                self.root.attributes("-alpha", self.base_opacity)
        except tk.TclError:
            pass

    # ---------- 每秒逻辑 ----------
    def _tick(self):
        try:
            self._tick_step()
        except Exception as e:
            print(f"[health-float] 秒帧异常（已跳过）: {e}")
        finally:
            self.root.after(1000, self._tick)

    def _tick_step(self):
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
            self.auto_left = ALERT_META[self.current][3]
            self._play_sound()
            secs = self._blackout_for(self.current)
            if secs > 0:
                self._show_blackout(self.current, secs)
            self._resize_to(*ALERT)
            self._layout()

        if self.current is not None:
            if self.auto_left > 0:
                self.auto_left -= 1
            if self.auto_left == 0:
                self._dismiss()
            else:
                self._update_auto_hint()
        else:
            key, left = self._next_event()
            pre = int(self.cfg.get("prewarn_seconds", 120) or 0)
            new_prewarn = bool(key and pre > 0 and 0 < left <= pre)
            self.prewarn = new_prewarn
            self._update_countdown()

        self.root.lift()

    def _blackout_for(self, key):
        """该提醒的黑屏秒数（会议模式下恒为 0）"""
        if self.cfg.get("meeting_mode"):
            return 0
        kind = ALERT_META[key][4]
        if kind is None:
            return 0
        cfg_key = ("blackout_seconds" if kind == "long"
                   else "blackout_brief_seconds")
        try:
            return int(self.cfg.get(cfg_key, 0) or 0)
        except (TypeError, ValueError):
            return 0

    def _update_countdown(self):
        if self.current:
            return
        key, left = self._next_event()
        if not key:
            self.cv.itemconfig(self.time_id, text="🌿")
            self.cv.itemconfig(self.name_id, text="双击可设置提醒")
            return
        m, s = left // 60, left % 60
        short = f"{m} 分{s:02d}秒" if m else f"{s} 秒"
        if self.cfg.get("meeting_mode"):
            short = f"🔇 {short}"          # 会议模式指示
        name = ALERT_META[key][0]
        if self.prewarn:
            self.cv.itemconfig(self.time_id, text=f"{short}后")
            self.cv.itemconfig(self.name_id, text=f"{name} · 准备一下")
        else:
            self.cv.itemconfig(self.time_id, text=short)
            self.cv.itemconfig(self.name_id, text=name)

    def _update_auto_hint(self):
        if self.current == "eye":
            self.cv.itemconfig(self.a_count_id,
                               text=f"{max(self.auto_left, 0)} 秒")
        else:
            self.cv.itemconfig(self.a_hint_id,
                               text=f"{self.auto_left} 秒后自动消失"
                               if self.auto_left > 0 else "")

    # ---------- 黑屏遮罩 ----------
    def _show_blackout(self, key, secs):
        if self.blackout and self.blackout.winfo_exists():
            return
        title, sub, icon, _, kind = ALERT_META[key]
        self.black_left = secs
        self._bo_exts = 0                      # 鼠标活动延长次数
        self._bo_persist = (kind == "long")    # 洗澡/睡觉：鼠标还在动就继续黑

        bw = tk.Toplevel(self.root)
        self.blackout = bw
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        bw.overrideredirect(True)
        bw.attributes("-topmost", True)
        try:
            bw.attributes("-alpha", 0.97)
        except tk.TclError:
            pass
        bw.configure(bg="#000000")
        bw.geometry(f"{sw}x{sh}+0+0")
        tk.Label(bw, text=icon, font=ui_font(64), bg="#000000",
                 fg="#ffffff").pack(pady=(sh // 4 - 130, 8))
        tk.Label(bw, text=title, font=ui_font(26, True), bg="#000000",
                 fg="#ffffff").pack()
        tk.Label(bw, text=sub.replace("\n", "  ·  "), font=ui_font(13),
                 bg="#000000", fg="#9aa3b0").pack(pady=(6, 18))
        self.bo_count = tk.Label(bw, text="", font=ui_font(16, True),
                                 bg="#000000", fg="#5c6b7a")
        self.bo_count.pack()
        foot = ("还在动鼠标就继续黑屏 · 点一下跳过" if self._bo_persist
                else "点任意处跳过")
        tk.Label(bw, text=foot, font=ui_font(10), bg="#000000",
                 fg="#3a414d").pack(side="bottom", pady=28)
        bw.bind("<Button-1>", lambda e: self._close_blackout())
        if self._bo_persist:
            # 遮罩盖满全屏：鼠标一动（还在工作）就重置黑屏倒计时
            bw.bind("<Motion>", self._on_bo_motion, add="+")
        for w in bw.winfo_children():
            w.bind("<Button-1>", lambda e: self._close_blackout())
            if self._bo_persist:
                w.bind("<Motion>", self._on_bo_motion, add="+")
        self.bo_count.config(text=f"{secs} 秒后回来")
        self.root.after(1000, self._bo_tick)
        bw.lift()
        bw.focus_force()

    def _on_bo_motion(self, e):
        if not (self.blackout and self.blackout.winfo_exists()):
            return
        if self._bo_exts >= 30:      # 安全阀：最多延长 30 次，防永久锁屏
            return
        self._bo_exts += 1
        self.black_left = self._blackout_for(self.current)
        self.bo_count.config(text="检测到你还在工作 · 继续黑屏休息")

    def _bo_tick(self):
        if not (self.blackout and self.blackout.winfo_exists()):
            return
        if self.black_left > 0:
            self.black_left -= 1
            self.bo_count.config(text=f"{max(self.black_left, 0)} 秒后回来")
        if self.black_left <= 0:
            self._close_blackout()
            return
        self.root.after(1000, self._bo_tick)

    def _close_blackout(self):
        if self.blackout and self.blackout.winfo_exists():
            self.blackout.destroy()
        self.blackout = None

    # ---------- 设置面板 ----------
    def _open_settings(self):
        if self.settings_win and self.settings_win.winfo_exists():
            self.settings_win.lift()
            self.settings_win.focus_force()
            return self.settings_win
        dlg = SettingsDialog(self.root, self.cfg,
                             intro="双击浮窗随时能回到这里修改")
        dlg.on_saved = self._apply_settings
        self.settings_win = dlg
        return dlg

    def _apply_settings(self):
        self.next_run = self._build_schedule()
        self.queue.clear()
        self.current = None
        self.prewarn = False
        self._resize_to(*BUBBLE)
        self._layout()

    # ---------- 交互 ----------
    def _toggle_meeting(self, e=None):
        self.cfg["meeting_mode"] = not bool(self.cfg.get("meeting_mode"))
        save_config(self.cfg)
        self._update_countdown()

    def _set_hover(self, on):
        self.hover = on

    def _drag_start(self, e):
        self.dx, self.dy = e.x, e.y

    def _drag_move(self, e):
        self.x = self.root.winfo_x() + e.x - self.dx
        self.y = self.root.winfo_y() + e.y - self.dy
        self.root.geometry(f"+{self.x}+{self.y}")

    def _dismiss(self):
        self.current = None
        self.prewarn = False
        self._close_blackout()
        self._resize_to(*BUBBLE)
        self._layout()
        self._update_countdown()

    def _play_sound(self):
        if not self.cfg.get("sound") or sys.platform != "darwin":
            return
        try:
            subprocess.Popen(["afplay", SOUND],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass


# ---------------- 入口 ----------------
def main():
    first_run = not os.path.exists(CONFIG_PATH)
    cfg = load_config()
    root = tk.Tk()
    if first_run:
        root.withdraw()
        dlg = SettingsDialog(
            root, cfg, title="欢迎 🌿 首次设置",
            intro="设好时间就开始 · 以后双击浮窗随时改")
        dlg.on_saved = lambda: None
        root.wait_window(dlg)
        save_config(cfg)
        root.deiconify()
        root.geometry(f"{BUBBLE[0]}x{BUBBLE[1]}+"
                      f"{root.winfo_screenwidth() - 200}+"
                      f"{root.winfo_screenheight() - 290}")
    FloatApp(root, cfg)
    root.mainloop()


if __name__ == "__main__":
    main()
