#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
✈️ 大水大睡大健康 — Health Float
桌面常驻的「飞机舷窗」小浮窗（视觉素材：assets/）：
- 窗外天空里，下一个提醒的 icon 在云间轻轻漂浮
- 鼠标移过去，舷窗平滑放大浮出，显示提醒名和倒计时
- 快到点时整窗轻微呼吸；到点弹出提醒卡，一次只讲一件事
- 窗口元素常驻不重建，不会一闪一闪
- 所有时间读本机系统时钟，换电脑无需配置

提醒项与频率在 config.json 里改。
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
    "sound": True,              # 提醒时是否播放提示音（仅 macOS）
    "opacity": 0.96             # 舷窗透明度 0~1
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
    "eye":    ("该看远方啦", "望向 6 米外 20 秒\n让眼睛休息一下", "👀", 20),
    "move":   ("起来动一动", "站起来伸展 1 分钟\n久坐是慢性刺客", "🧘", 90),
    "water":  ("喝杯水吧",   "水是身体的\n第一供应商", "💧", 60),
    "shower": ("去洗澡啦",   "早点洗澡\n晚上睡得更香", "🛁", 120),
    "sleep":  ("该睡觉啦",   "放下屏幕\n明天还有满格的自己", "🌙", 120),
}

# —— 与素材图对应的布局比例（原图 342x472 分析得出）——
C_CABIN = "#b8bdc4"        # 机舱壁灰（画布底色，与素材四角一致）
C_TEXT = "#33465c"         # 深蓝灰文字
C_DIM = "#5c6b7a"
C_BTN_FG = "#f2f6fa"
SKY_CX, SKY_CY = 0.535, 0.46   # 天空中心（占图比例）

# 尺寸（图与文字严格分区：图在上，文字条在下，不重叠）
SIZE_IDLE = (104, 144)        # 待机舷窗图尺寸
SIZE_HOVER = (168, 232)       # 悬停舷窗图尺寸
STRIP_IDLE = 34               # 待机文字条高（图下方）
STRIP_HOVER = 50              # 悬停文字条高
SIZE_ALERT = (272, 196)       # 提醒卡：左舷窗图 + 右文字栏
ALERT_IMG = (132, 182)        # 提醒卡左侧舷窗尺寸
ALERT_IMG_XY = (8, 7)         # 提醒卡舷窗位置
ALERT_TEXT_X = 208            # 右栏中心线（图右缘 140 之后）


def round_rect_pts(x1, y1, x2, y2, r):
    return [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
            x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]


def round_rect(cv, x1, y1, x2, y2, r, **kw):
    return cv.create_polygon(round_rect_pts(x1, y1, x2, y2, r), smooth=True, **kw)


class FloatApp:
    def __init__(self, root, cfg):
        self.root = root
        self.cfg = cfg
        self.base_opacity = float(cfg.get("opacity", 0.96))
        self.queue = []
        self.current = None      # 当前提醒 key（None = 舷窗模式）
        self.auto_left = 0
        self.hover = False
        self.prewarn = False
        self.phase = 0.0
        self.last_bob = 0.0
        self.ladder = self._load_images()     # {（w,h): PhotoImage}
        self.next_run = self._build_schedule()

        root.title("Health Float")
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        try:
            root.attributes("-alpha", self.base_opacity)
        except (tk.TclError, ValueError):
            pass
        root.configure(bg=C_CABIN)

        self.w, self.h = SIZE_IDLE[0], SIZE_IDLE[1] + STRIP_IDLE
        self.img_w, self.img_h = SIZE_IDLE          # 当前舷窗图尺寸（窗口=图+文字条）
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        self.x, self.y = sw - 190, sh - 300
        root.geometry(f"{self.w}x{self.h}+{self.x}+{self.y}")

        self.cv = tk.Canvas(root, width=self.w, height=self.h,
                            bg=C_CABIN, highlightthickness=0, takefocus=0)
        self.cv.pack(fill="both", expand=True)
        self.cv.bind("<Button-1>", self._drag_start, add="+")
        self.cv.bind("<B1-Motion>", self._drag_move, add="+")
        self.cv.bind("<Enter>", lambda e: self._set_hover(True), add="+")
        self.cv.bind("<Leave>", lambda e: self._set_hover(False), add="+")

        self._create_items()
        self._layout()

        root.after(50, self._animate)
        root.after(1000, self._tick)

    # ---------- 素材 ----------
    def _load_images(self):
        imgs = {}
        for path in glob.glob(os.path.join(ASSETS_DIR, "sz_*.png")):
            m = re.search(r"sz_(\d+)x(\d+)\.png$", path)
            if m:
                w, h = int(m.group(1)), int(m.group(2))
                imgs[(w, h)] = tk.PhotoImage(file=path)
        if not imgs:  # 素材缺失兜底：纯色矩形
            imgs[SIZE_IDLE] = None
        self.ladder_keys = sorted(imgs.keys())
        return imgs

    def _image_for(self, w, h):
        im = self.ladder.get((w, h))
        if im is None:
            # 取不超过目标的最大梯度档（保持平滑动画）
            cands = [k for k in self.ladder if k != ALERT_IMG]
            best = min(cands, key=lambda k: abs(k[0] - w) + abs(k[1] - h))
            im = self.ladder[best]
        return im

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

    # ---------- 常驻元素（只创建这一次） ----------
    def _create_items(self):
        cv = self.cv
        self.img_id = cv.create_image(0, 0, anchor="nw")
        self.icon_id = cv.create_text(
            0, 0, text="🌿", font=ui_font(26), fill=C_TEXT, tags=("icon",))
        # 舷窗模式文字（窗下灰区）
        self.title_id = cv.create_text(0, 0, text="", font=ui_font(11, True),
                                       fill=C_TEXT)
        self.count_id = cv.create_text(0, 0, text="", font=ui_font(10),
                                       fill=C_DIM)
        # 提醒卡右栏
        self.a_icon_id = cv.create_text(0, 0, text="", font=ui_font(30))
        self.a_title_id = cv.create_text(0, 0, text="", font=ui_font(14, True),
                                         fill=C_TEXT, justify="center")
        self.a_sub_id = cv.create_text(0, 0, text="", font=ui_font(10),
                                       fill=C_DIM, justify="center")
        self.a_count_id = cv.create_text(0, 0, text="",
                                         font=ui_font(13, True), fill=C_TEXT)
        self.a_btn_id = round_rect(cv, 0, 0, 10, 10, 8, fill=C_TEXT,
                                   outline="", tags=("btn",))
        self.a_btn_txt = cv.create_text(0, 0, text="知道了 ✓",
                                        font=ui_font(10, True),
                                        fill=C_BTN_FG)
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

    # ---------- 布局（每帧重排坐标，元素永不销毁；图与文字严格分区） ----------
    def _layout(self):
        cv = self.cv
        w, h = self.w, self.h
        if self.current:
            # —— 提醒卡：左舷窗图（x 8~140）+ 右文字栏（x 148~264） ——
            ix, iy = ALERT_IMG_XY
            cv.coords(self.img_id, ix, iy)
            img = self.ladder.get(ALERT_IMG)
            if img:
                cv.itemconfig(self.img_id, image=img)
            key = self.current
            title, sub, icon, _ = ALERT_META[key]
            # icon 漂在左侧舷窗的天空里
            self._show(self.icon_id)
            cv.itemconfig(self.icon_id, font=ui_font(26))
            cv.coords(self.icon_id,
                      ix + ALERT_IMG[0] * SKY_CX, iy + ALERT_IMG[1] * SKY_CY)
            self._hide(self.title_id, self.count_id, self.a_icon_id)
            self._show(self.a_title_id, self.a_sub_id, self.a_hint_id)
            cv.coords(self.a_title_id, ALERT_TEXT_X, 30)
            cv.itemconfig(self.a_title_id, text=f"{icon} {title}")
            cv.coords(self.a_sub_id, ALERT_TEXT_X, 64)
            cv.itemconfig(self.a_sub_id, text=sub, width=112)
            if key == "eye":
                self._hide(self.a_btn_id, self.a_btn_txt)
                self._show(self.a_count_id)
                cv.coords(self.a_count_id, ALERT_TEXT_X, 124)
            else:
                self._hide(self.a_count_id)
                self._show(self.a_btn_id, self.a_btn_txt)
                bb = cv.bbox(self.a_btn_id)
                if bb:
                    cv.move(self.a_btn_id, 168 - bb[0], 138 - bb[1])
                else:
                    cv.coords(self.a_btn_id,
                              *round_rect_pts(168, 138, 248, 162, 8))
                cv.coords(self.a_btn_txt, 208, 150)
            cv.coords(self.a_hint_id, ALERT_TEXT_X, 182)
        else:
            # —— 舷窗模式：图在上（0 ~ img_h），文字条在下（img_h ~ h） ——
            self._hide(self.a_title_id, self.a_sub_id, self.a_count_id,
                       self.a_btn_id, self.a_btn_txt, self.a_hint_id,
                       self.a_icon_id)
            self._show(self.icon_id, self.title_id, self.count_id)
            iw, ih = self.img_w, self.img_h
            img = self._image_for(iw, ih)
            if img:
                cv.itemconfig(self.img_id, image=img)
            cv.coords(self.img_id, 0, 0)
            big = self.hover or self.prewarn
            cv.itemconfig(self.icon_id, font=ui_font(30 if big else 26))
            cv.coords(self.icon_id, iw * SKY_CX, ih * SKY_CY)
            if big:
                # 悬停/预告：两行文字条
                cv.itemconfig(self.title_id, font=ui_font(12, True))
                cv.coords(self.title_id, iw / 2, ih + 18)
                cv.itemconfig(self.count_id, font=ui_font(9))
                cv.coords(self.count_id, iw / 2, ih + 38)
            else:
                # 待机：一行时间 + 一行事件名，都在图下方
                cv.itemconfig(self.title_id, font=ui_font(10, True))
                cv.coords(self.title_id, iw / 2, ih + 13)
                cv.itemconfig(self.count_id, font=ui_font(8))
                cv.coords(self.count_id, iw / 2, ih + 26)
            self._update_countdown()

    # ---------- 动画（每 50ms） ----------
    def _animate(self):
        try:
            self._animate_step()
        except Exception as e:  # 任何一帧出错都不许停跳
            print(f"[health-float] 动画帧异常（已跳过）: {e}")
        finally:
            self.root.after(50, self._animate)

    def _animate_step(self):
        cv = self.cv
        # 尺寸平滑趋近（沿素材梯度；窗口 = 图 + 文字条）
        if not self.current:
            big = self.hover or self.prewarn
            tgt = SIZE_HOVER if big else SIZE_IDLE
            strip = STRIP_HOVER if big else STRIP_IDLE
            if (self.w, self.h) != (tgt[0], tgt[1] + strip):
                ni = self._nearest_larger(tgt)
                self.img_w, self.img_h = ni
                self._resize_to(ni[0], ni[1] + strip)
                self._layout()
        # icon 漂浮（含呼吸幅度）
        self.phase += 0.06
        amp = 3.2 if self.prewarn else 2.2
        bob = math.sin(self.phase) * amp
        cv.move("icon", 0, bob - self.last_bob)
        self.last_bob = bob
        # 预告呼吸：整窗透明度轻搏动
        try:
            if self.prewarn and not self.current:
                glow = (math.sin(self.phase * 2) + 1) / 2
                self.root.attributes(
                    "-alpha", self.base_opacity - 0.08 + 0.08 * glow)
            else:
                self.root.attributes("-alpha", self.base_opacity)
        except tk.TclError:
            pass

    def _nearest_larger(self, tgt):
        """沿图尺寸梯度走一步（不跳档）"""
        keys = [k for k in self.ladder_keys if k != ALERT_IMG]
        cur = (self.img_w, self.img_h)
        if cur in keys:
            i = keys.index(cur)
            if tgt == keys[-1] and i < len(keys) - 1:
                return keys[i + 1]
            if tgt == keys[0] and i > 0:
                return keys[i - 1]
            return keys[i]
        # 不在梯度上（如刚从提醒卡回来）：直接落到离目标最近的一档
        return min(keys, key=lambda k: abs(k[0] - tgt[0]) + abs(k[1] - tgt[1]))

    def _resize_to(self, w, h):
        """以右下角为锚点调整窗口尺寸（向左上生长）"""
        self.x += self.w - w
        self.y += self.h - h
        self.w, self.h = w, h
        self.root.geometry(f"{w}x{h}+{self.x}+{self.y}")
        self.cv.config(width=w, height=h)

    # ---------- 每秒逻辑 ----------
    def _tick(self):
        try:
            self._tick_step()
        except Exception as e:  # 任何一秒出错都不许停跳
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
            # 提醒卡立即弹出（左图右文，固定尺寸）
            self.img_w, self.img_h = ALERT_IMG
            self._resize_to(*SIZE_ALERT)
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
            pre = int(self.cfg.get("prewarn_seconds", 120))
            new_prewarn = bool(key and pre > 0 and 0 < left <= pre)
            if new_prewarn != self.prewarn:
                self.prewarn = new_prewarn
                self._update_countdown()
                self._layout()
            else:
                self._update_countdown()

        self.root.lift()

    def _update_countdown(self):
        if self.current:
            return
        key, left = self._next_event()
        if not key:
            return
        m, s = left // 60, left % 60
        short = f"{m} 分{s:02d}秒" if m else f"{s} 秒"
        if self.hover or self.prewarn:
            self.cv.itemconfig(self.title_id,
                               text=f"{ALERT_META[key][0]} · {short}")
            self.cv.itemconfig(self.count_id,
                               text=f"{ALERT_META[key][2]} 快到了，准备一下")
        else:
            self.cv.itemconfig(self.title_id, text=short)
            self.cv.itemconfig(self.count_id, text=ALERT_META[key][0])

    def _update_auto_hint(self):
        if self.current == "eye":
            self.cv.itemconfig(self.a_count_id,
                               text=f"{max(self.auto_left, 0)} 秒")
        else:
            self.cv.itemconfig(self.a_hint_id,
                               text=f"{self.auto_left} 秒后自动消失"
                               if self.auto_left > 0 else "")

    # ---------- 交互 ----------
    def _set_hover(self, on):
        self.hover = on
        self._update_countdown()

    def _drag_start(self, e):
        self.dx, self.dy = e.x, e.y

    def _drag_move(self, e):
        self.x = self.root.winfo_x() + e.x - self.dx
        self.y = self.root.winfo_y() + e.y - self.dy
        self.root.geometry(f"+{self.x}+{self.y}")

    def _dismiss(self):
        self.current = None
        self.prewarn = False
        big = self.hover
        self.img_w, self.img_h = SIZE_HOVER if big else SIZE_IDLE
        strip = STRIP_HOVER if big else STRIP_IDLE
        self._resize_to(self.img_w, self.img_h + strip)
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


def main():
    cfg = load_config()
    root = tk.Tk()
    FloatApp(root, cfg)
    root.mainloop()


if __name__ == "__main__":
    main()
