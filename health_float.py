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
import shutil
import subprocess
import sys
import time
import tkinter as tk
from datetime import datetime, timedelta

# CustomTkinter（13.6k★，tkinter 生态 star 最高的现代 UI 库）：
# 用它把设置面板重做成卡片式圆角界面。
# 但它是可选依赖 —— 源码直接跑时若没装，自动降级回原生 tk 面板，
# 保证「下载源码就能跑」这条底线不被破坏。
try:
    import customtkinter as ctk
    HAVE_CTK = True
except ImportError:      # pragma: no cover - 环境没装 CTK 时的降级路径
    ctk = None
    HAVE_CTK = False

def _base_dir():
    """程序根目录。

    源码运行时 = 脚本所在目录；
    PyInstaller 打包后 = sys._MEIPASS（解包后的资源目录），
    否则素材（舷窗图）会找不到，浮窗会开成白板。
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return meipass
    return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = _base_dir()
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
SOUND = "/System/Library/Sounds/Ping.aiff"

VERSION = "1.2.0"


def _log(msg):
    """安全地打印一条日志。

    直接 print 中文会在 Windows 的默认 cp1252 控制台上抛
    UnicodeEncodeError —— 而这些 print 几乎都在 except 分支里，
    本意是「优雅降级」，结果打印本身又炸掉，把降级变成了崩溃
    （CI 上 Windows 的两个配置测试就是这么挂的）。
    所以：编码不支持就替换字符，绝不让日志影响主流程。
    """
    try:
        print(msg)
    except UnicodeEncodeError:
        try:
            enc = sys.stdout.encoding or "ascii"
            print(msg.encode(enc, errors="replace").decode(enc, errors="replace"))
        except Exception:
            pass
    except Exception:
        pass


# 两次 tick 间隔超过这个秒数，判定为「电脑睡过了」，醒来的过期提醒静默重排
MAX_RESUME_GAP = 300


def user_config_dir():
    """用户配置目录（各平台标准位置），跟程序安装目录分离。

    配置放这里的原因：程序目录可能被覆盖升级（打包 .app / git pull /
    重装），用户设置不能跟着一起没。
    """
    if sys.platform == "darwin":
        base = os.path.join(os.path.expanduser("~"), "Library",
                            "Application Support", "HealthFloat")
    elif os.name == "nt":
        base = os.path.join(os.environ.get("APPDATA",
                     os.path.expanduser("~")), "HealthFloat")
    else:
        base = os.path.join(os.environ.get("XDG_CONFIG_HOME",
                     os.path.expanduser("~/.config")), "health-float")
    try:
        os.makedirs(base, exist_ok=True)
    except OSError:
        base = BASE_DIR
    return base


USER_DIR = user_config_dir()
CONFIG_PATH = os.path.join(USER_DIR, "config.json")
LEGACY_CONFIG_PATH = os.path.join(BASE_DIR, "config.json")   # 老版本位置（程序目录）


def migrate_legacy_config():
    """老版本把配置存在程序目录：迁移到用户目录，只迁一次。"""
    if os.path.abspath(LEGACY_CONFIG_PATH) == os.path.abspath(CONFIG_PATH):
        return
    if os.path.exists(CONFIG_PATH) or not os.path.exists(LEGACY_CONFIG_PATH):
        return
    try:
        with open(LEGACY_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        _log(f"[health-float] 已把旧配置迁移到 {CONFIG_PATH}")
    except (OSError, json.JSONDecodeError) as e:
        _log(f"[health-float] 旧配置迁移失败（忽略）: {e}")

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
# label 里的 emoji 前后都留空格：Tk 对 emoji 的宽度计算不准，
# 不留空隙时 emoji 会紧贴文字（截图里「看远方🪟」那样）。
SETT_ITEMS = [
    ("eye_minutes", "看远方 🪟 ", "每几分钟一次（0=关）", "int"),
    ("move_minutes", "起来动一动 🧘 ", "每几分钟一次（0=关）", "int"),
    ("water_minutes", "喝水 💧 ", "每几分钟一次（0=关）", "int"),
    ("shower_time", "洗澡提醒 🛁 ", "每天几点提醒", "time"),
    ("sleep_time", "睡觉提醒 🌙 ", "每天几点提醒", "time"),
    ("prewarn_seconds", "提前预告 ⏰ ", "提前几秒开始提示（0=关）", "int"),
    ("blackout_seconds", "洗澡/睡觉黑屏 🖥 ", "先黑屏几秒（0=关）", "int"),
    ("blackout_brief_seconds", "眺望/站立黑屏 🌑 ", "先黑屏几秒（0=关）", "int"),
    ("meeting_mode", "会议模式 🎙 ", "开启后提醒永不黑屏", "bool"),
    ("sound", "提示音 🔔 ", "关掉就是静音模式", "bool"),
]


# ---------------- 工具函数 ----------------
def load_config():
    cfg = dict(DEFAULT_CONFIG)
    migrate_legacy_config()
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
            cfg.update({k: v for k, v in user_cfg.items() if k in DEFAULT_CONFIG})
        except (json.JSONDecodeError, OSError) as e:
            _log(f"[health-float] 配置读取失败，使用默认配置: {e}")
    return cfg


def save_config(cfg):
    """保存配置：先写临时文件再原子替换，避免写一半断电损坏配置。"""
    try:
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        tmp = CONFIG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        os.replace(tmp, CONFIG_PATH)
        return True
    except OSError as e:
        _log(f"[health-float] 配置保存失败: {e}")
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
# 设计 token：一套低饱和莫兰迪灰蓝，跨浮窗/提醒卡/设置面板统一。
# 参照项目「tayu-design-system」的降饱和思路：不用高饱和强调色。
C_CABIN = "#b8bdc4"       # 舷窗外框灰（与素材图四角一致）
C_TEXT = "#33465c"        # 主文字：深灰蓝
C_DIM = "#5c6b7a"         # 次文字：中灰蓝
C_PANEL = "#f4f6f9"       # 卡片底：极浅灰蓝
C_BTN_FG = "#f2f6fa"      # 深色按钮上的文字
C_ACCENT = "#4a6076"      # 主强调色（比主文字略亮一档）
C_ACCENT_HOVER = "#3d5266"
C_SOFT = "#e6ebf1"        # 浅色底板：比 C_PANEL 稍深，用于次级按钮
C_LINE = "#dbe2ea"        # 描边：更淡，不再是突兀的深框
C_HOVER_TINT = "#c9d0d8"  # 齿轮底板 hover 色
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


# ---------------- CustomTkinter 控件层 ----------------
# 13.6k★ 的 CustomTkinter 提供现代圆角控件（CTkButton / CTkSwitch /
# CTkEntry），用来把设置面板从「tk.Label 拼出来的按钮」升级成
# 真正的现代卡片式界面。
#
# 兼容性：CTK 控件可安全挂在原生 tk 父级下（已验证），因此
# 浮窗本体仍用原生 tk.Canvas —— 那是画布渲染，CTK 管不到，
# 硬套反而会破坏舷窗的自定义绘制。
if HAVE_CTK:
    ctk.set_appearance_mode("light")

    class _CTKStepper(ctk.CTkFrame):
        """CTK 版数字拨轮：上下箭头 + 可输入的数字框。

        保留原 NumDial 的外部接口（.var / .get()），
        所以设置面板的 collect/reset 逻辑两边通用。
        """

        def __init__(self, master, value=60, lo=0, hi=1440, step=5,
                     unit="分钟", width=4, changed=None):
            super().__init__(master, fg_color="transparent")
            self.lo, self.hi = lo, hi
            self.step = step
            self.unit = unit
            self.changed = changed
            self.var = tk.StringVar(value=str(int(value)))
            # 注意：绝不能设 self.var_m = None。
            # 面板的 _reset 用 hasattr(w, "var_m") 区分「时间拨轮」和
            # 「数字拨轮」；哪怕赋 None，hasattr 也会返回 True，
            # 数字拨轮会被误当成时间拨轮去取 var_h 而崩。

            # CTkEntry 的 width 单位是像素，不是字符数。
            # 按字符数换算会导致「120」被截成「12C」（末位被切掉）。
            self.entry = ctk.CTkEntry(
                self, textvariable=self.var, width=56,
                font=ui_font(14, True), justify="center",
                corner_radius=8, border_width=1, border_color=C_LINE,
                fg_color="#ffffff", text_color=C_TEXT)
            self.entry.pack(side="left")

            arrow_col = ctk.CTkFrame(self, fg_color="transparent")
            arrow_col.pack(side="left", padx=(3, 0))
            up = ctk.CTkButton(arrow_col, text="▲", width=18, height=13,
                                corner_radius=4, fg_color=C_SOFT,
                                hover_color="#d3dae3", text_color=C_DIM,
                                font=ui_font(8), command=self._up)
            up.pack()
            down = ctk.CTkButton(arrow_col, text="▼", width=18, height=13,
                                  corner_radius=4, fg_color=C_SOFT,
                                  hover_color="#d3dae3", text_color=C_DIM,
                                  font=ui_font(8), command=self._down)
            down.pack()

            if unit:
                ctk.CTkLabel(self, text=unit, font=ui_font(11),
                             text_color=C_DIM).pack(side="left", padx=(6, 0))

            self.entry.bind("<KeyRelease>", lambda e: self._on_change())
            self.entry.bind("<FocusOut>", lambda e: self._on_change())

        def _bump(self, delta):
            try:
                v = int(float(self.var.get() or 0))
            except (TypeError, ValueError):
                v = self.lo
            v = max(self.lo, min(self.hi, v + delta))
            self.var.set(str(v))
            self._on_change()

        def _up(self):
            self._bump(self.step)

        def _down(self):
            self._bump(-self.step)

        def _on_change(self, *_):
            if self.changed:
                try:
                    self.changed(self.get())
                except ValueError:
                    pass

        def get(self):
            try:
                v = int(float(self.var.get() or 0))
            except (TypeError, ValueError):
                v = self.lo
            return max(self.lo, min(self.hi, v))

    class _CTKTimeDial(ctk.CTkFrame):
        """CTK 版闹钟拨轮：HH : MM，保留 .var_h / .var_m / .get()。"""

        def __init__(self, master, hhmm="21:30", changed=None):
            super().__init__(master, fg_color="transparent")
            hm = parse_hhmm(hhmm) or (21, 30)
            self.var_h = tk.StringVar(value=f"{hm[0]:02d}")
            self.var_m = tk.StringVar(value=f"{hm[1]:02d}")
            self.changed = changed

            self.eh = ctk.CTkEntry(self, textvariable=self.var_h, width=52,
                                   font=ui_font(15, True), justify="center",
                                   corner_radius=8, border_width=1,
                                   border_color=C_LINE, fg_color="#ffffff",
                                   text_color=C_TEXT)
            self.eh.pack(side="left")
            ctk.CTkLabel(self, text=":", font=ui_font(15, True),
                         text_color=C_DIM, width=12).pack(side="left")
            self.em = ctk.CTkEntry(self, textvariable=self.var_m, width=52,
                                   font=ui_font(15, True), justify="center",
                                   corner_radius=8, border_width=1,
                                   border_color=C_LINE, fg_color="#ffffff",
                                   text_color=C_TEXT)
            self.em.pack(side="left")

            arrow_col = ctk.CTkFrame(self, fg_color="transparent")
            arrow_col.pack(side="left", padx=(4, 0))
            ctk.CTkButton(arrow_col, text="▲", width=18, height=13,
                          corner_radius=4, fg_color=C_SOFT,
                          hover_color="#d3dae3", text_color=C_DIM,
                          font=ui_font(8),
                          command=self._bump_h).pack()
            ctk.CTkButton(arrow_col, text="▼", width=18, height=13,
                          corner_radius=4, fg_color=C_SOFT,
                          hover_color="#d3dae3", text_color=C_DIM,
                          font=ui_font(8),
                          command=self._bump_m).pack()

            self.eh.bind("<KeyRelease>", lambda e: self._on_change())
            self.em.bind("<KeyRelease>", lambda e: self._on_change())

        def _bump_h(self):
            hm = parse_hhmm(self.get()) or (21, 30)
            self.var_h.set(f"{(hm[0] + 1) % 24:02d}")
            self._on_change()

        def _bump_m(self):
            hm = parse_hhmm(self.get()) or (21, 30)
            self.var_m.set(f"{(hm[1] + 5) % 60:02d}")
            self._on_change()

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


# ---------------- 设置窗口（双击浮窗打开 / 首次引导共用） ----------------
class LegacySettingsDialog(tk.Toplevel):
    """原生 tk 版设置面板 —— CustomTkinter 不可用时的降级路径。

    界面朴素，但功能与 CTK 版完全一致（同一套 SETT_ITEMS、
    同样的 collect/_reset 语义）。
    """

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

        # —— 使用说明：让用户知道还有哪些入口 ——
        help_box = tk.Frame(self, bg="#f4f6f9")
        help_box.pack(fill="x", padx=22, pady=(12, 0))
        tk.Label(help_box,
                 text="⚙ 点舷窗右下角齿轮  ·  右键舷窗 = 快捷菜单\n"
                      "🎙 会议模式（不黑屏）  ·  🔕 静音模式（只弹窗不出声）\n"
                      "间隔填 0 = 关闭该提醒  ·  时间留空 = 不提醒",
                 font=ui_font(8), bg="#f4f6f9", fg=C_DIM,
                 justify="left", anchor="w").pack(padx=12, pady=10, fill="x")

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


if HAVE_CTK:
    class SettingsDialog(ctk.CTkToplevel):
        """CustomTkinter 版设置面板（13.6k★ 库）。

        相比原生 tk 版：
        - 卡片分组（间隔 / 每日 / 黑屏 / 开关），信息层次清楚
        - 真圆角按钮 + hover 反馈，不再是「用 Label 假装按钮」
        - 开关用 CTkSwitch，视觉上比系统 Checkbutton 干净
        - 拨轮用 CTkEntry + 圆角箭头按钮
        """

        def __init__(self, master, cfg, title="Health Float 设置",
                     intro="双击浮窗随时能回到这里修改"):
            super().__init__(master)
            self.cfg = cfg
            self.on_saved = None
            self.title(title)
            self.configure(fg_color="#ffffff")
            self.resizable(False, False)
            self.transient(master)

            # —— 标题区 ——
            ctk.CTkLabel(self, text="🌿 大水大睡大健康", font=ui_font(17, True),
                         text_color=C_TEXT).pack(pady=(18, 2))
            ctk.CTkLabel(self, text=intro, font=ui_font(11),
                         text_color=C_DIM).pack(pady=(0, 12))

            # —— 卡片容器：按语义分组，不再是 10 行平铺 ——
            groups = [
                ("⏱  间隔提醒", ["eye_minutes", "move_minutes", "water_minutes"]),
                ("🌙  每日提醒", ["shower_time", "sleep_time"]),
                ("🖥  黑屏时长", ["prewarn_seconds", "blackout_seconds",
                                 "blackout_brief_seconds"]),
                ("🎙  模式开关", ["meeting_mode", "sound"]),
            ]
            meta = {k: (lb, hint, kind) for k, lb, hint, kind in SETT_ITEMS}
            self.widgets = {}

            for gi, (gname, keys) in enumerate(groups):
                card = ctk.CTkFrame(self, fg_color="#f7f9fb",
                                    corner_radius=14,
                                    border_width=1, border_color="#e9eef4")
                card.pack(fill="x", padx=20, pady=(0, 9))
                ctk.CTkLabel(card, text=gname, font=ui_font(12, True),
                             text_color=C_ACCENT, anchor="w").pack(
                                 fill="x", padx=14, pady=(10, 2))

                for ri, key in enumerate(keys):
                    label, hint, kind = meta[key]
                    row = ctk.CTkFrame(card, fg_color="transparent")
                    row.pack(fill="x", padx=14, pady=4)

                    ctk.CTkLabel(row, text=label, font=ui_font(12),
                                 text_color=C_TEXT, width=15,
                                 anchor="w").pack(side="left")

                    if kind == "int":
                        w = _CTKStepper(
                            row, value=cfg.get(key, 0) or 0,
                            unit=("" if key == "sound" else
                                  "秒" if "seconds" in key else "分钟"))
                        w.pack(side="left")
                    elif kind == "time":
                        w = _CTKTimeDial(row, hhmm=cfg.get(key) or "21:30")
                        w.pack(side="left")
                    else:  # bool → 开关
                        var = tk.BooleanVar(value=bool(cfg.get(key)))
                        w = ctk.CTkSwitch(
                            row, text="", variable=var,
                            onvalue=True, offvalue=False, width=40,
                            progress_color=C_ACCENT, fg_color="#c3ccd6",
                            button_color="#ffffff",
                            button_hover_color="#eef2f7")
                        w.var = var
                        w.pack(side="left")
                    self.widgets[key] = w

                    ctk.CTkLabel(row, text=hint, font=ui_font(10),
                                 text_color="#8a97a6", anchor="w").pack(
                                     side="left", padx=(12, 0))

            # —— 使用说明卡片 ——
            help_box = ctk.CTkFrame(self, fg_color="#f4f6f9", corner_radius=14,
                                     border_width=1, border_color="#e9eef4")
            help_box.pack(fill="x", padx=20, pady=(4, 0))
            ctk.CTkLabel(
                help_box,
                text="⚙ 点舷窗右下角齿轮  ·  右键舷窗 = 快捷菜单\n"
                     "🎙 会议模式（不黑屏）  ·  🔕 静音模式（只弹窗不出声）\n"
                     "间隔填 0 = 关闭该提醒  ·  时间留空 = 不提醒",
                font=ui_font(10), text_color=C_DIM, justify="left",
                anchor="w").pack(padx=14, pady=11, fill="x")

            # —— 底部按钮 ——
            btns = ctk.CTkFrame(self, fg_color="transparent")
            btns.pack(pady=(14, 18))
            reset = ctk.CTkButton(btns, text="恢复默认", width=96, height=34,
                                   corner_radius=10, fg_color=C_SOFT,
                                   hover_color="#d3dae3", text_color=C_DIM,
                                   font=ui_font(12), command=self._reset)
            reset.pack(side="left", padx=6)
            ok = ctk.CTkButton(btns, text="保存 ✓", width=104, height=34,
                                corner_radius=10, fg_color=C_ACCENT,
                                hover_color=C_ACCENT_HOVER, text_color=C_BTN_FG,
                                font=ui_font(12, True), command=self._save)
            ok.pack(side="left", padx=6)

            self.bind("<Return>", lambda e: self._save())
            self.bind("<Escape>", lambda e: self.destroy())
            self.protocol("WM_DELETE_WINDOW", self.destroy)

        def collect(self):
            """读出表单 → dict"""
            out = {}
            for key, _, _, kind in SETT_ITEMS:
                w = self.widgets[key]
                if kind in ("int", "time"):
                    out[key] = w.get()
                else:
                    out[key] = bool(w.var.get())
            return out

        def _reset(self):
            for key, val in DEFAULT_CONFIG.items():
                if key not in self.widgets:
                    continue
                w = self.widgets[key]
                if hasattr(w, "var_m"):          # 时间拨轮
                    hm = parse_hhmm(str(val)) or (21, 30)
                    w.var_h.set(f"{hm[0]:02d}")
                    w.var_m.set(f"{hm[1]:02d}")
                elif isinstance(w.var, tk.BooleanVar):   # 开关
                    w.var.set(bool(val))
                elif hasattr(w, "var"):           # 数字拨轮
                    w.var.set(str(int(val)))

        def _save(self):
            out = self.collect()
            self.cfg.update(out)
            save_config(self.cfg)
            if self.on_saved:
                self.on_saved()
            self.destroy()
else:
    # CustomTkinter 不可用 → 降级到原生 tk 面板
    SettingsDialog = LegacySettingsDialog


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
        self._last_tick = None     # 上次 tick 时间（用于休眠唤醒检测）
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
        self.cv.bind("<Button-3>", self._show_menu, add="+")
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
        # 字号比原版放大一档（10/8 → 12/10）：悬窗远看小字吃力。
        self.time_id = cv.create_text(0, 0, text="", font=ui_font(12, True),
                                      fill=C_TEXT)
        self.name_id = cv.create_text(0, 0, text="", font=ui_font(10),
                                      fill=C_DIM)
        # —— 可见入口：设置齿轮 + 会议模式指示 ——
        # 之前只有隐藏手势（双击/右键），用户根本不知道它们存在。
        # 现在把入口画出来，点了就开设置面板。
        # 齿轮底板改成「无描边淡色圆」，不再是一个突兀的白框：
        # 旧的白色圆角方块 + 深描边浮在灰条上，像贴错了的控件。
        self.gear_id = cv.create_text(
            BUBBLE[0] - 16, BUBBLE_IMG[1] + 24, text="⚙", font=ui_font(14),
            fill=C_DIM, tags=("gear",))
        self.gear_bg = cv.create_oval(
            BUBBLE[0] - 29, BUBBLE_IMG[1] + 12,
            BUBBLE[0] - 3, BUBBLE_IMG[1] + 38,
            fill=C_HOVER_TINT, outline="", tags=("gear",))
        # 底板必须压在齿轮图标下面：后创建的画布元素层级更高，
        # 不降序的话白底板会把 ⚙ 完全盖住（只剩一个白色方块）。
        cv.tag_lower(self.gear_bg, self.gear_id)
        # 平时隐藏底板，只留图标；鼠标靠近时才淡入，避免灰条上挂个框。
        cv.itemconfigure(self.gear_bg, state="hidden")
        self.mute_id = cv.create_text(
            0, 0, text="🔇", font=ui_font(11), fill="#c8802f",
            tags=("mute",), state="hidden")
        # 静音指示：🔕 表示「提醒照弹，但不出声」
        self.silent_id = cv.create_text(
            0, 0, text="🔕", font=ui_font(11), fill=C_DIM,
            tags=("silent",), state="hidden")
        # 提醒卡右栏（白色圆角面板）
        self.panel_id = round_rect(cv, *PANEL, 10, fill=C_PANEL,
                                   outline=C_LINE)
        self.a_title_id = cv.create_text(0, 0, text="", font=ui_font(15, True),
                                         fill=C_TEXT)
        self.a_sub_id = cv.create_text(0, 0, text="", font=ui_font(11),
                                       fill=C_DIM, justify="center")
        self.a_count_id = cv.create_text(0, 0, text="",
                                         font=ui_font(15, True), fill=C_TEXT)
        self.a_btn_id = round_rect(cv, 0, 0, 10, 10, 8, fill=C_ACCENT,
                                   outline="", tags=("btn",))
        self.a_btn_txt = cv.create_text(0, 0, text="知道了 ✓",
                                        font=ui_font(11, True), fill=C_BTN_FG)
        self.a_hint_id = cv.create_text(0, 0, text="", font=ui_font(9),
                                        fill=C_DIM)
        cv.tag_bind("btn", "<Button-1>", lambda e: self._dismiss())
        cv.tag_bind("a_btn_txt", "<Button-1>", lambda e: self._dismiss())
        # 齿轮：可见的设置入口，点了直接开面板
        cv.tag_bind("gear", "<Button-1>", lambda e: self._open_settings())
        # 齿轮底板平时隐藏，鼠标移到齿轮上才淡入 —— 平时灰条上只有一个
        # 图标，不再挂着一个突兀的白色方框。
        cv.tag_bind("gear", "<Enter>", lambda e: self._gear_hover(True))
        cv.tag_bind("gear", "<Leave>", lambda e: self._gear_hover(False))

    def _gear_hover(self, on):
        """齿轮 hover：底板淡入 / 淡出，图标同步提亮。"""
        if not (self.gear_id and self.gear_bg):
            return
        try:
            self.cv.itemconfig(self.gear_bg, state="normal" if on else "hidden")
            self.cv.itemconfig(self.gear_id, fill=C_TEXT if on else C_DIM)
        except tk.TclError:
            pass

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
        # 字号放大后重新分配两行的基线：主行上移一点、副行下移一点，
        # 保持整体在 48px 文字条内居中，不顶边也不压边。
        cv.coords(self.time_id, w / 2, BUBBLE_IMG[1] + 14)
        cv.coords(self.name_id, w / 2, BUBBLE_IMG[1] + 35)
        # —— 可见入口：齿轮在文字条右下角（不压图），会议模式指示在左上 ——
        self._show(self.gear_id)
        # 圆角多边形的 coords 要给完整点集（move 是相对位移，
        # 反复 layout 会累积漂移）；用绝对坐标一次性定位
        gx, gy = w - 17, BUBBLE_IMG[1] + 24
        cv.coords(self.gear_id, gx, gy)
        # 底板是圆形（oval），默认隐藏，hover 齿轮时才显示
        cv.coords(self.gear_bg, gx - 14, gy - 14, gx + 14, gy + 14)
        if self.cfg.get("meeting_mode"):
            self._show(self.mute_id)
            cv.coords(self.mute_id, 14, BUBBLE_IMG[1] + 12)
        else:
            self._hide(self.mute_id)
        # 静音指示（🔕）：提醒照弹，只是不出声
        if not self.cfg.get("sound", True):
            self._show(self.silent_id)
            cv.coords(self.silent_id,
                      14 if not self.cfg.get("meeting_mode") else 32,
                      BUBBLE_IMG[1] + 12)
        else:
            self._hide(self.silent_id)
        self._update_countdown()

    def _layout_alert(self):
        cv = self.cv
        key = self.current
        title, sub, icon, _, _ = ALERT_META[key]
        ix, iy = ALERT_IMG_XY
        self._show(self.panel_id)   # 面板位置固定，创建时已定，无需重设坐标
        self._hide(self.time_id, self.name_id)
        # 提醒卡状态下齿轮挪到面板右下角，始终可点
        self._show(self.gear_id)
        gx, gy = PANEL[2] - 16, PANEL[3] - 16
        cv.coords(self.gear_id, gx, gy)
        cv.coords(self.gear_bg, gx - 14, gy - 14, gx + 14, gy + 14)
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
            _log(f"[health-float] 动画帧异常（已跳过）: {e}")
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
            _log(f"[health-float] 秒帧异常（已跳过）: {e}")
        finally:
            self.root.after(1000, self._tick)

    def _tick_step(self):
        now = datetime.now()
        # —— 休眠/唤醒检测 ——
        # 电脑合盖睡几小时后，所有提醒都过期了。若不处理，醒来会被
        # 5 条过期提醒连环轰炸（还各带一次黑屏），等于惩罚用户去睡觉。
        # 规则：距上次 tick 超过 MAX_GAP 秒 → 判定为休眠，期间错过的
        # 提醒直接重排到未来，不弹窗。
        resumed = False
        if self._last_tick is not None:
            gap = (now - self._last_tick).total_seconds()
            if gap > MAX_RESUME_GAP:
                resumed = True
        self._last_tick = now

        for key, t in list(self.next_run.items()):
            if now >= t:
                kind, param = self.reschedule[key]
                if kind == "daily":
                    self.next_run[key] = next_daily(*param)
                else:
                    self.next_run[key] = now + param
                # 休眠唤醒后的过期提醒：静默重排，不惊扰
                if resumed:
                    continue
                # 单个提醒超时太久：静默跳过
                #   间隔型：超过自身间隔的 2 倍
                #   每日型：超过 2 小时（错过了就等明天，不补弹）
                if kind == "daily":
                    if (now - t).total_seconds() > 7200:
                        continue
                elif (now - t).total_seconds() > param.total_seconds() * 2:
                    continue
                self.queue.append(key)

        if self.current is None and self.queue:
            self.current = self.queue.pop(0)
            self.auto_left = ALERT_META[self.current][3]
            secs = self._blackout_for(self.current)
            # 提示音的唯一决策点：
            #   静音模式 → 永远不响
            #   有黑屏   → 黑屏本身就是提示，不叠加"叮"（更安静）
            #   无黑屏   → 用提示音把人叫醒
            if secs <= 0 and self.cfg.get("sound", True):
                self._play_sound()
            if secs > 0:
                self._show_blackout(self.current, secs)
            self._resize_to(*ALERT)
            self._layout()
            # 提醒弹出的这一刻才真正抢层级（此时用户本就该看到它）
            try:
                self.root.lift()
                self.root.attributes("-topmost", True)
            except tk.TclError:
                pass

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

        # 置顶维护：不要每秒 lift()（会打断全屏演示/视频播放）。
        # 改为低频重申 -topmost 属性，必要时才真正提层。
        self._topmost_ticks = getattr(self, "_topmost_ticks", 0) + 1
        if self._topmost_ticks % 30 == 0:
            try:
                self.root.attributes("-topmost", True)
            except tk.TclError:
                pass

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
        # 注意：这两个时间戳的初值必须是 None，不能用 0.0。
        # time.monotonic() 的起点在不同 Python / 平台上并不一致
        # （macOS 上 3.9 返回进程运行时长，3.13 返回系统运行时长），
        # 用 0.0 当「从未延长过」的哨兵，会让 now - 0.0 落在节流窗口内，
        # 结果是第一次延长被直接吞掉 —— 也就是用户反馈的
        # 「动鼠标不继续黑屏」。None 才能表达「没有上次记录」。
        self._bo_last_extend = None           # 上次延长的时刻（时间节流）
        self._bo_total = 0                    # 累计黑屏秒数（总时长上限）
        self._bo_msg_until = None             # 「还在工作」提示显示到何时

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
        self._bo_last_pos = self._pointer_pos()
        self.root.after(1000, self._bo_tick)
        bw.lift()
        # 刻意不调用 focus_force()：那会把键盘焦点从用户正在输入的
        # 窗口抢走，导致正在打的字丢失。遮罩只做视觉+鼠标层面的强制。

    def _pointer_pos(self):
        """当前鼠标在屏幕上的坐标（用于检测「还在动鼠标」）"""
        try:
            return self.blackout.winfo_pointerxy()
        except Exception:
            return (0, 0)

    def _extend_blackout(self):
        """重置黑屏倒计时（鼠标还在动 = 人还在工作）。返回是否真的延长了。"""
        if not (self.blackout and self.blackout.winfo_exists()):
            return False
        if not self._bo_persist:
            return False
        now = time.monotonic()
        # 节流：距上次延长至少 1.5 秒才算一次，避免高频事件刷屏
        # （_bo_last_extend 为 None = 从未延长过，不受时钟基准影响）
        if (self._bo_last_extend is not None
                and now - self._bo_last_extend < 1.5):
            return False
        # 总时长上限：累计黑屏不超过 5 分钟，绝不把人锁死
        secs = self._blackout_for(self.current)
        if self._bo_total + secs > 300:
            self.bo_count.config(text="已经提醒很久啦 · 点一下关闭")
            return False
        self._bo_last_extend = now
        self._bo_exts += 1
        self._bo_total += secs
        self.black_left = secs
        self._bo_msg_until = now + 3      # 提示文字保持 3 秒
        return True

    def _on_bo_motion(self, e):
        """鼠标在遮罩上移动 = 人还在工作 → 重置黑屏倒计时。

        关键：不能用「事件次数」当安全阀。
        Tk 的 <Motion> 在鼠标移动时每秒能触发几十次，用次数计数的话
        不到 1 秒就把额度烧完，之后怎么动鼠标都不再延长（用户实测反馈）。
        改为「时间节流 + 累计黑屏总时长上限」。
        """
        self._extend_blackout()

    def _bo_tick(self):
        if not (self.blackout and self.blackout.winfo_exists()):
            return
        # 鼠标位置轮询：比 <Motion> 事件更可靠
        # （无边框顶层窗口在某些情况下收不到 Motion，但坐标一定变）
        extended = False
        if self._bo_persist:
            pos = self._pointer_pos()
            if pos != self._bo_last_pos:
                self._bo_last_pos = pos
                extended = self._extend_blackout()
        # 延长成功时这一拍不再递减（否则刚重置就被吃掉 1 秒）
        if not extended:
            if self.black_left > 0:
                self.black_left -= 1
        if self.black_left <= 0:
            self._close_blackout()
            return
        # 「还在工作」的提示保持几秒，别被倒计时立刻盖掉
        if (self._bo_msg_until is not None
                and time.monotonic() < self._bo_msg_until):
            self.bo_count.config(text="检测到你还在工作 · 继续黑屏休息")
        else:
            self.bo_count.config(text=f"{max(self.black_left, 0)} 秒后回来")
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
                             intro="这里改所有提醒时间 · 保存立即生效")
        dlg.on_saved = self._apply_settings
        self.settings_win = dlg
        return dlg

    def _build_menu(self):
        """构建右键菜单（与弹出分离，便于测试直接检查菜单项）。

        tk_popup() 会进入 Tk 的事件循环等待用户点击，在无人值守的
        环境（CI / 单元测试）里会阻塞到超时 —— 所以菜单内容必须
        能在不弹出的情况下被检查。
        """
        menu = tk.Menu(self.root, tearoff=0,
                       font=ui_font(10), bg="#ffffff", fg=C_TEXT,
                       activebackground="#e9edf2", relief="flat")
        menu.add_command(label="⚙  打开设置…",
                         command=self._open_settings)
        meeting = "🔇  会议模式：开（不黑屏）" if self.cfg.get("meeting_mode") \
            else "🎙  会议模式：关"
        menu.add_command(label=meeting, command=self._toggle_meeting)
        silent = "🔕  静音模式：开（只弹窗不出声）" \
            if not self.cfg.get("sound", True) else "🔔  静音模式：关（有提示音）"
        menu.add_command(label=silent, command=self._toggle_silent)
        menu.add_separator()
        menu.add_command(label="✕  退出", command=self._quit)
        return menu

    def _show_menu(self, e):
        """右键菜单：把所有能力显式列出来，不再依赖隐藏手势"""
        menu = self._build_menu()
        try:
            menu.tk_popup(e.x_root, e.y_root)
        finally:
            menu.grab_release()

    def _quit(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

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
        if not self.current:
            self._layout()          # 刷新 🔇 指示的显隐

    def _toggle_silent(self, e=None):
        """静音模式：提醒照弹，只是不出声（开会/图书馆/怕吵到别人）"""
        self.cfg["sound"] = not bool(self.cfg.get("sound", True))
        save_config(self.cfg)
        if not self.current:
            self._layout()          # 刷新 🔕 指示的显隐

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
        """播放提示音。调用方已判断静音/黑屏，这里再兜一道底。"""
        if not self.cfg.get("sound", True):
            return
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["afplay", SOUND],
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
            elif os.name == "nt":
                # Windows：winsound 是标准库，Beep 一定可用
                import winsound
                winsound.Beep(880, 220)
                winsound.Beep(1320, 260)
            else:
                # Linux：优先 paplay / aplay，都没有就安静跳过
                for cmd in (["paplay", SOUND], ["aplay", "-q", SOUND]):
                    if shutil.which(cmd[0]):
                        subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL)
                        break
        except Exception:
            pass          # 声音失败绝不能影响提醒本身


# ---------------- 入口 ----------------
def main():
    # 先迁移旧配置，再判断是否首次运行
    migrate_legacy_config()
    first_run = not os.path.exists(CONFIG_PATH)
    cfg = load_config()
    root = tk.Tk()
    if first_run:
        root.withdraw()
        dlg = SettingsDialog(
            root, cfg, title="欢迎 🌿 首次设置",
            intro="设好时间就开始 · 以后点舷窗右下角 ⚙ 随时能改")
        dlg.on_saved = lambda: None
        root.wait_window(dlg)
        save_config(cfg)          # 用户直接关窗也会存下默认值
        root.deiconify()
        root.geometry(f"{BUBBLE[0]}x{BUBBLE[1]}+"
                      f"{root.winfo_screenwidth() - 200}+"
                      f"{root.winfo_screenheight() - 290}")
    FloatApp(root, cfg)
    root.mainloop()


if __name__ == "__main__":
    main()
