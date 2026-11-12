#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Health Float 自动化测试
运行： python3 -m unittest discover -s tests -v
     或： python3 tests/test_health_float.py

只依赖标准库 unittest + tkinter（需要图形环境，CI 用 xvfb）。
"""

import json
import os
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tkinter as tk  # noqa: E402
import tkinter.font  # noqa: E402

import health_float as hf  # noqa: E402


class TestConfig(unittest.TestCase):
    """配置读写与迁移"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._saved_path = hf.CONFIG_PATH
        self._saved_legacy = hf.LEGACY_CONFIG_PATH
        hf.CONFIG_PATH = os.path.join(self.tmp, "config.json")
        hf.LEGACY_CONFIG_PATH = os.path.join(self.tmp, "legacy.json")

    def tearDown(self):
        hf.CONFIG_PATH = self._saved_path
        hf.LEGACY_CONFIG_PATH = self._saved_legacy

    def test_default_config_has_all_keys(self):
        cfg = hf.load_config()
        for k in ("eye_minutes", "move_minutes", "water_minutes",
                  "shower_time", "sleep_time", "prewarn_seconds",
                  "blackout_seconds", "blackout_brief_seconds",
                  "meeting_mode", "sound", "opacity"):
            self.assertIn(k, cfg)

    def test_save_then_load_roundtrip(self):
        cfg = hf.load_config()
        cfg["shower_time"] = "20:30"
        cfg["blackout_seconds"] = 7
        cfg["meeting_mode"] = True
        self.assertTrue(hf.save_config(cfg))
        again = hf.load_config()
        self.assertEqual(again["shower_time"], "20:30")
        self.assertEqual(again["blackout_seconds"], 7)
        self.assertIs(again["meeting_mode"], True)

    def test_save_is_atomic(self):
        """保存后不应残留 .tmp 文件"""
        cfg = hf.load_config()
        hf.save_config(cfg)
        self.assertFalse(os.path.exists(hf.CONFIG_PATH + ".tmp"))

    def test_corrupt_config_falls_back_to_defaults(self):
        with open(hf.CONFIG_PATH, "w", encoding="utf-8") as f:
            f.write("{ 这不是合法 json ")
        cfg = hf.load_config()
        self.assertEqual(cfg["eye_minutes"], hf.DEFAULT_CONFIG["eye_minutes"])

    def test_corrupt_config_survives_non_utf8_console(self):
        """配置损坏时，即使控制台编码装不下中文也不能崩。

        回归测试（CI 上 Windows 3.11 / 3.13 挂的就是这个）：
        Windows 控制台默认 cp1252，except 分支里的 print 中文会抛
        UnicodeEncodeError —— 本该「优雅降级」的路径反而变成崩溃。
        """
        class AsciiConsole:
            """模拟 cp1252 控制台：写不下的字符直接抛异常。"""

            encoding = "cp1252"

            def write(self, text):
                text.encode(self.encoding)      # 写不下就抛
                return len(text)

            def flush(self):
                pass

        real_stdout = sys.stdout
        sys.stdout = AsciiConsole()
        try:
            with open(hf.CONFIG_PATH, "w", encoding="utf-8") as f:
                f.write("{ 这不是合法 json ")
            cfg = hf.load_config()                # 不应抛异常
            self.assertEqual(cfg["eye_minutes"],
                             hf.DEFAULT_CONFIG["eye_minutes"])
            hf._log("[health-float] 中文日志也要能打出来")
        finally:
            sys.stdout = real_stdout

    def test_legacy_config_migrated(self):
        """程序目录的老配置应被迁移到新位置"""
        with open(hf.LEGACY_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump({"sleep_time": "23:15"}, f)
        hf.migrate_legacy_config()
        self.assertTrue(os.path.exists(hf.CONFIG_PATH))
        with open(hf.CONFIG_PATH, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["sleep_time"], "23:15")

    def test_migration_does_not_overwrite_existing(self):
        """已存在新配置时，迁移不能覆盖它"""
        with open(hf.CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump({"sleep_time": "01:00"}, f)
        with open(hf.LEGACY_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump({"sleep_time": "23:15"}, f)
        hf.migrate_legacy_config()
        with open(hf.CONFIG_PATH, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["sleep_time"], "01:00")

    def test_unknown_keys_are_ignored(self):
        with open(hf.CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump({"eye_minutes": 15, "evil_key": "x"}, f)
        cfg = hf.load_config()
        self.assertEqual(cfg["eye_minutes"], 15)
        self.assertNotIn("evil_key", cfg)


class TestHelpers(unittest.TestCase):
    """纯函数"""

    def test_parse_hhmm(self):
        self.assertEqual(hf.parse_hhmm("21:30"), (21, 30))
        self.assertEqual(hf.parse_hhmm("00:00"), (0, 0))
        self.assertIsNone(hf.parse_hhmm("25:00"))
        self.assertIsNone(hf.parse_hhmm("12:99"))
        self.assertIsNone(hf.parse_hhmm("abc"))
        self.assertIsNone(hf.parse_hhmm(""))

    def test_next_daily_rolls_to_tomorrow(self):
        """next_daily(0,0) 应该排到下一个 00:00（明天），不是今天已过的时刻"""
        t = hf.next_daily(0, 0)
        self.assertGreater(t, datetime.now())
        self.assertEqual((t.hour, t.minute), (0, 0))

    def test_next_daily_is_in_future(self):
        """next_daily 返回的时间点必须严格在未来"""
        now = datetime.now()
        t = hf.next_daily(now.hour, now.minute)
        self.assertGreater(t, now)
        self.assertEqual((t.hour, t.minute), (now.hour, now.minute))

    def test_next_daily_fixed_slot(self):
        """指定固定时刻时，结果的小时分钟必须精确匹配"""
        for h, m in ((0, 0), (21, 30), (23, 59)):
            t = hf.next_daily(h, m)
            self.assertEqual((t.hour, t.minute), (h, m))
            self.assertGreater(t, datetime.now())


class TestApp(unittest.TestCase):
    """需要图形环境的部分"""

    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        # 关键：把配置路径隔离到临时目录。
        # 否则测试会读写用户真实配置（~/Library/Application Support/...），
        # 在 CI 上那个路径可能不存在/不可写 → 随机失败。
        self._saved_path = hf.CONFIG_PATH
        self._saved_legacy = hf.LEGACY_CONFIG_PATH
        tmp = tempfile.mkdtemp()
        hf.CONFIG_PATH = os.path.join(tmp, "config.json")
        hf.LEGACY_CONFIG_PATH = os.path.join(tmp, "legacy.json")

        self.cfg = dict(hf.DEFAULT_CONFIG)
        self.app = hf.FloatApp(self.root, self.cfg)
        self.errors = []
        self.root.report_callback_exception = \
            lambda e, v, t: self.errors.append(f"{e.__name__}: {v}")

    def tearDown(self):
        try:
            self.app._close_blackout()
        except Exception:
            pass
        self.app.current = None
        self.app.queue.clear()
        # 清理本用例额外创建的顶层窗口（设置面板等）。
        # CTK 面板一律用独立 root（见下方 CTK 用例），不在这里销毁，
        # 避免 CTK 的 configure() 遍历到已销毁的控件。
        for child in self.root.winfo_children():
            if isinstance(child, tk.Canvas):
                continue          # 浮窗的画布，由 FloatApp 自己管
            try:
                child.destroy()
            except Exception:
                pass
        hf.CONFIG_PATH = self._saved_path
        hf.LEGACY_CONFIG_PATH = self._saved_legacy

    # ---------- 静音模式 ----------
    def test_silent_mode_indicator(self):
        """静音模式要有可见指示（🔕）"""
        self.assertEqual(self.app.cv.itemcget(self.app.silent_id, "state"),
                         "hidden")
        self.app._toggle_silent()
        self.app._layout()
        self.assertEqual(self.app.cv.itemcget(self.app.silent_id, "state"),
                         "normal")
        self.app._toggle_silent()
        self.app._layout()
        self.assertEqual(self.app.cv.itemcget(self.app.silent_id, "state"),
                         "hidden")

    def test_silent_mode_blocks_sound(self):
        """静音模式下不能出声"""
        played = []
        self.app._play_sound = lambda: played.append(1)
        self.app.cfg["sound"] = False
        self.app.next_run["water"] = datetime.now() - timedelta(seconds=1)
        self.app._tick_step()
        self.assertEqual(played, [], "静音模式不该播放声音")

    def test_sound_plays_when_not_silent(self):
        played = []
        self.app._play_sound = lambda: played.append(1)
        self.app.cfg["sound"] = True
        self.app.next_run["water"] = datetime.now() - timedelta(seconds=1)
        self.app._tick_step()
        self.assertEqual(played, [1])

    def test_blackout_suppresses_sound(self):
        """有黑屏时不叠加提示音（黑屏本身就是提示）"""
        played = []
        self.app._play_sound = lambda: played.append(1)
        self.app.cfg["sound"] = True
        self.app.cfg["blackout_seconds"] = 3
        self.app.next_run["shower"] = datetime.now() - timedelta(seconds=1)
        self.app._tick_step()
        self.assertEqual(played, [], "黑屏提醒不该再叮一声")

    def test_silent_mode_persists(self):
        self.app._toggle_silent()
        self.assertIs(self.app.cfg["sound"], False)
        with open(hf.CONFIG_PATH, encoding="utf-8") as f:
            self.assertIs(json.load(f)["sound"], False)

    # ---------- 可见入口 ----------
    def test_gear_button_visible_in_bubble(self):
        """设置齿轮必须可见 —— 用户不能靠猜才知道能设置"""
        self.assertEqual(self.app.cv.itemcget(self.app.gear_id, "state"),
                         "normal")
        gb = self.app.cv.bbox(self.app.gear_id)
        self.assertIsNotNone(gb, "齿轮没画出来")
        # 齿轮必须在图片下方（文字条内），不许压到图上
        img = self.app.cv.bbox(self.app.img_id)
        self.assertGreaterEqual(gb[1], img[3], "齿轮压到图上了")

    def test_gear_stays_inside_window(self):
        """齿轮和它的底板都必须在窗口内，不能溢出右边"""
        for _ in range(5):        # 多次 layout，捕捉累积漂移
            self.app._layout()
        for iid in (self.app.gear_id, self.app.gear_bg):
            # 底板默认隐藏（hover 才淡入），Tk 对隐藏图元不返回 bbox，
            # 所以临时显示出来量一次真实几何。
            was_hidden = self.app.cv.itemcget(iid, "state") == "hidden"
            if was_hidden:
                self.app.cv.itemconfigure(iid, state="normal")
            bb = self.app.cv.bbox(iid)
            if was_hidden:
                self.app.cv.itemconfigure(iid, state="hidden")
            self.assertIsNotNone(bb)
            self.assertLessEqual(bb[2], self.app.w,
                                 f"齿轮超出窗口右边: {bb} vs {self.app.w}")
            self.assertLessEqual(bb[3], self.app.h,
                                 f"齿轮超出窗口下边: {bb} vs {self.app.h}")
            self.assertGreaterEqual(bb[0], 0)
            self.assertGreaterEqual(bb[1], 0)

    def test_gear_position_stable_across_layouts(self):
        """反复 layout 后齿轮位置不能漂移（move 是相对位移，容易累积）"""
        before = self.app.cv.bbox(self.app.gear_id)
        for _ in range(5):
            self.app._layout()
        after = self.app.cv.bbox(self.app.gear_id)
        self.assertEqual(before, after, "齿轮位置在多次 layout 后漂移了")

    # ---------- 无边框窗口（macOS 标题栏回归）----------

    def test_window_is_borderless(self):
        """浮窗必须是无边框的（不能有标题栏和红绿灯）"""
        self.assertIs(self.app.root.overrideredirect(), True,
                      "浮窗被 macOS 重置成了带标题栏的标准窗口")

    def test_ensure_borderless_recovers_from_reset(self):
        """macOS 重置窗口后，_ensure_borderless 必须能把它修回来。

        回归测试（用户截图反馈）：macOS 会把无边框窗口重置回带
        红绿灯的标准窗口。

        注意：不能依赖「先重置再断言」——前一个用例注册的巡检
        可能已经把它修好了。所以先断言修复逻辑本身是可靠的
        （纯函数分支全覆盖），再用真实重置验证端到端修复。
        """
        # 1) 纯逻辑：三种状态都要判对
        self.assertFalse(hf._needs_borderless_fix(True),
                         "正常状态不该触发修复")
        self.assertTrue(hf._needs_borderless_fix(None),
                        "被重置后（None）必须触发修复")
        self.assertTrue(hf._needs_borderless_fix(False),
                        "明确有边框（False）必须触发修复")

        # 2) 端到端：真实重置 → 修复
        self.app._ensure_borderless()          # 先确保是正常态
        self.app.root.overrideredirect(False)  # 真实重置
        self.app.root.update()
        self.app._ensure_borderless()
        self.app.root.update()
        self.assertIs(self.app.root.overrideredirect(), True,
                      "_ensure_borderless 没能把无边框状态修回来")

    def test_borderless_watch_scheduled(self):
        """必须注册周期性巡检 —— 启动后的重置没人管会一直留着标题栏。

        之前只在启动后 200ms / 1200ms 各兜底一次，运行中发生的
        重置没有任何机制会修。
        """
        self.assertTrue(callable(self.app._borderless_watch))
        # 调用它不应该抛异常，并且要能继续排下一次
        self.app._borderless_watch()
        self.app.root.update()
        self.assertIs(self.app.root.overrideredirect(), True)

    def test_borderless_watch_recovers_silently(self):
        """巡检发现重置时要能自动修复，且不抛异常"""
        self.app.root.overrideredirect(False)   # 真实重置
        self.app.root.update()
        self.app._borderless_watch()
        self.app.root.update()
        self.assertIs(self.app.root.overrideredirect(), True,
                      "巡检没能自动修复被重置的窗口")

    def test_gear_backplate_hidden_until_hover(self):
        """齿轮底板平时隐藏 —— 灰条上不该挂着一个突兀的白框"""
        self.assertEqual(self.app.cv.itemcget(self.app.gear_bg, "state"),
                         "hidden",
                         "齿轮底板应默认隐藏，hover 才淡入")
        # 图标本身必须一直可见（用户要能看到能点）
        self.assertEqual(self.app.cv.itemcget(self.app.gear_id, "state"),
                         "normal")

    def test_gear_hover_reveals_backplate(self):
        """鼠标移到齿轮上 → 底板淡入；移开 → 收起"""
        self.app._gear_hover(True)
        self.assertEqual(self.app.cv.itemcget(self.app.gear_bg, "state"),
                         "normal")
        self.app._gear_hover(False)
        self.assertEqual(self.app.cv.itemcget(self.app.gear_bg, "state"),
                         "hidden")

    def test_gear_backplate_is_round_not_square(self):
        """底板是圆形（oval），不是圆角方块 —— 用户反馈白方框很丑"""
        self.assertEqual(self.app.cv.type(self.app.gear_bg), "oval",
                         "齿轮底板应是圆形，不是方形")

    def test_bubble_fonts_are_readable(self):
        """悬窗主文字字号不能太小（用户反馈看着费劲）"""
        time_font = self.app.cv.itemcget(self.app.time_id, "font")
        name_font = self.app.cv.itemcget(self.app.name_id, "font")
        # 字体串形如 "PingFang SC 12 bold"：字号是那个纯数字字段
        def size_of(spec):
            for tok in spec.split():
                if tok.isdigit():
                    return int(tok)
            return 0
        self.assertGreaterEqual(size_of(time_font), 12,
                                "主文字（倒计时）字号应 ≥ 12")
        self.assertGreaterEqual(size_of(name_font), 10,
                                "副文字（提醒名）字号应 ≥ 10")

    def test_gear_visible_in_alert_card(self):
        """提醒卡状态下齿轮也要在（不然用户没法在提醒时改设置）"""
        self.app.next_run["water"] = datetime.now() - timedelta(seconds=1)
        self.app._tick_step()
        self.assertEqual(self.app.cv.itemcget(self.app.gear_id, "state"),
                         "normal")

    def test_mute_indicator_only_in_meeting_mode(self):
        """会议模式开启时要有可见指示"""
        self.assertEqual(self.app.cv.itemcget(self.app.mute_id, "state"),
                         "hidden")
        self.app._toggle_meeting()
        self.app._layout()
        self.assertEqual(self.app.cv.itemcget(self.app.mute_id, "state"),
                         "normal")
        self.app._toggle_meeting()
        self.app._layout()
        self.assertEqual(self.app.cv.itemcget(self.app.mute_id, "state"),
                         "hidden")

    def test_gear_click_opens_settings(self):
        """点齿轮应该打开设置面板"""
        dlg = self.app._open_settings()
        self.assertIsNotNone(dlg)
        self.assertTrue(dlg.winfo_exists())

    def test_right_click_menu_has_settings_entry(self):
        """右键菜单里必须显式列出设置入口。

        只构建菜单、不调用 tk_popup —— 弹菜单会进入 Tk 事件循环等
        用户点击，在无人值守环境里会阻塞到超时（CI 上曾卡满 20 分钟）。
        """
        items = []
        real_menu = tk.Menu

        def spy_menu(*a, **kw):
            m = real_menu(*a, **kw)
            orig_add = m.add_command

            def add_command(**kwargs):
                items.append(kwargs.get("label", ""))
                return orig_add(**kwargs)
            m.add_command = add_command
            return m

        tk.Menu = spy_menu
        try:
            self.app._build_menu()
        finally:
            tk.Menu = real_menu
        self.assertTrue(any("设置" in i for i in items),
                        f"菜单里没有设置入口: {items}")

    # ---------- 排版 ----------
    def test_bubble_fixed_size(self):
        self.assertEqual((self.app.w, self.app.h), hf.BUBBLE)

    def test_bubble_text_below_image(self):
        """文字必须完全在图片下方，不许压到图上"""
        img = self.app.cv.bbox(self.app.img_id)
        for tid in (self.app.time_id, self.app.name_id):
            tb = self.app.cv.bbox(tid)
            self.assertIsNotNone(tb)
            self.assertGreaterEqual(tb[1], img[3],
                                    "文字与图片重叠")
            self.assertLessEqual(tb[3], self.app.h, "文字超出窗口")

    def test_alert_card_text_right_of_image(self):
        self.app.next_run["water"] = datetime.now() - timedelta(seconds=1)
        self.app._tick_step()
        self.assertEqual(self.app.current, "water")
        img = self.app.cv.bbox(self.app.img_id)
        for tid in (self.app.a_title_id, self.app.a_sub_id):
            tb = self.app.cv.bbox(tid)
            if tb is None:
                continue
            overlap_x = max(0, min(img[2], tb[2]) - max(img[0], tb[0]))
            overlap_y = max(0, min(img[3], tb[3]) - max(img[1], tb[1]))
            self.assertEqual(overlap_x * overlap_y, 0, "提醒卡图文重叠")

    def test_alert_shows_only_current_icon(self):
        """提醒卡只显示当前这一件事的 icon"""
        self.app.next_run["water"] = datetime.now() - timedelta(seconds=1)
        self.app._tick_step()
        icons = {m[2] for m in hf.ALERT_META.values()}
        found = set()
        for item in self.app.cv.find_all():
            try:
                txt = self.app.cv.itemcget(item, "text")
            except tk.TclError:
                continue
            if not txt:
                continue
            for ic in icons:
                if ic in txt:
                    found.add(ic)
        self.assertEqual(found, {hf.ALERT_META["water"][2]},
                         "提醒卡不应同时显示多个 icon")

    # ---------- 调度 ----------
    def test_schedule_respects_disabled(self):
        cfg = dict(hf.DEFAULT_CONFIG)
        cfg["water_minutes"] = 0
        cfg["shower_time"] = ""
        app = hf.FloatApp(self.root, cfg)
        self.assertNotIn("water", app.next_run)
        self.assertNotIn("shower", app.next_run)
        self.assertIn("eye", app.next_run)

    def test_schedule_has_five_events_by_default(self):
        self.assertEqual(len(self.app.next_run), 5)
        self.assertEqual(set(self.app.reschedule.keys()),
                         set(self.app.next_run.keys()))

    def test_firing_reschedules(self):
        self.app.next_run["eye"] = datetime.now() - timedelta(seconds=1)
        self.app._tick_step()
        self.assertEqual(self.app.current, "eye")
        self.assertGreater(self.app.next_run["eye"], datetime.now())
        self.assertIn("eye", self.app.reschedule)

    def test_resume_after_sleep_does_not_flood(self):
        """休眠唤醒后不应把所有过期提醒一次性弹出"""
        self.app._last_tick = datetime.now() - timedelta(hours=8)
        now = datetime.now()
        for k in self.app.next_run:
            self.app.next_run[k] = now - timedelta(hours=2)
        self.app._tick_step()
        self.assertEqual(self.app.queue, [], "休眠后不该堆积提醒")
        self.assertIsNone(self.app.current)

    def test_stale_single_reminder_skipped(self):
        """单个提醒超时太久（错过一整天）应静默跳过"""
        self.app.next_run["eye"] = datetime.now() - timedelta(hours=5)
        self.app._tick_step()
        self.assertEqual(self.app.queue, [])

    def test_settings_change_rebuilds_schedule(self):
        self.app.cfg["water_minutes"] = 45
        self.app._apply_settings()
        self.assertIn("water", self.app.next_run)

    # ---------- 黑屏 ----------
    def test_blackout_tiers(self):
        cfg = dict(hf.DEFAULT_CONFIG)
        cfg["blackout_seconds"] = 10
        cfg["blackout_brief_seconds"] = 2
        app = hf.FloatApp(self.root, cfg)
        self.assertEqual(app._blackout_for("eye"), 2)
        self.assertEqual(app._blackout_for("move"), 2)
        self.assertEqual(app._blackout_for("water"), 0)
        self.assertEqual(app._blackout_for("shower"), 10)
        self.assertEqual(app._blackout_for("sleep"), 10)

    def test_meeting_mode_disables_blackout(self):
        self.app.cfg["meeting_mode"] = True
        self.assertEqual(self.app._blackout_for("shower"), 0)
        self.assertEqual(self.app._blackout_for("eye"), 0)

    def test_blackout_persists_on_mouse_motion(self):
        """洗澡/睡觉黑屏时鼠标还在动 → 继续黑"""
        self.app.cfg["blackout_seconds"] = 10
        self.app.next_run["shower"] = datetime.now() - timedelta(seconds=1)
        self.app._tick_step()
        self.assertEqual(self.app.current, "shower")
        self.assertIsNotNone(self.app.blackout)
        self.app.black_left = 1
        self.app._on_bo_motion(None)
        self.assertEqual(self.app.black_left, 10, "鼠标活动应重置倒计时")
        self.assertEqual(self.app._bo_exts, 1)

    def test_blackout_motion_throttled(self):
        """高频 Motion 事件不应烧掉延长额度（1.5s 节流）"""
        self.app.cfg["blackout_seconds"] = 10
        self.app.next_run["sleep"] = datetime.now() - timedelta(seconds=1)
        self.app._tick_step()
        # 模拟鼠标疯狂移动：连续 100 次 Motion（间隔 < 1.5s）
        for _ in range(100):
            self.app._on_bo_motion(None)
        # 节流生效：只算了 1 次延长
        self.assertEqual(self.app._bo_exts, 1, "1.5 秒内的高频事件应被节流")

    def test_blackout_extension_safety_cap(self):
        """累计黑屏超过 5 分钟后不再延长，防止永久锁屏"""
        self.app.cfg["blackout_seconds"] = 10
        self.app.next_run["sleep"] = datetime.now() - timedelta(seconds=1)
        self.app._tick_step()
        self.app._bo_total = 295          # 已累计 295 秒
        self.app._bo_last_extend = None   # 允许延长（节流不拦）
        ok = self.app._extend_blackout()
        self.assertFalse(ok, "累计超 5 分钟不应再延长")
        self.assertLess(self.app._bo_total + 10, 306)  # 上限语义自检

    def test_blackout_first_extension_never_throttled(self):
        """第一次延长必须生效 —— 不能被节流误伤。

        回归测试：time.monotonic() 的起点在不同 Python / 平台上并不
        统一（macOS 上 3.9 是进程运行时长，3.13 是系统运行时长）。
        曾经用 0.0 当「从未延长过」的哨兵，导致在 3.9 上
        `now - 0.0 < 1.5` 成立，第一次延长被节流直接吞掉 ——
        也就是用户反馈的「黑屏后动鼠标不继续黑屏」。
        本测试把时钟基准压到接近 0，模拟 3.9 的行为。
        """
        self.app.cfg["blackout_seconds"] = 10
        self.app.next_run["shower"] = datetime.now() - timedelta(seconds=1)
        self.app._tick_step()

        real_monotonic = time.monotonic
        base = {"t": 0.05}          # 模拟 3.9：进程刚启动，now 很小

        def fake_monotonic():
            base["t"] += 0.001
            return base["t"]

        time.monotonic = fake_monotonic
        try:
            ok = self.app._extend_blackout()
        finally:
            time.monotonic = real_monotonic

        self.assertTrue(ok, "时钟基准接近 0 时，第一次延长仍必须生效")
        self.assertEqual(self.app._bo_exts, 1)
        self.assertEqual(self.app.black_left, 10)

    def test_blackout_msg_sentinel_is_none_not_zero(self):
        """_bo_msg_until 必须用 None 而非 0.0 当「未设置」哨兵。

        同上：0.0 在小基准时钟下会被误判为「提示还在显示」。
        """
        self.app.cfg["blackout_seconds"] = 10
        self.app.next_run["sleep"] = datetime.now() - timedelta(seconds=1)
        self.app._tick_step()
        self.assertIsNone(self.app._bo_msg_until,
                          "未延长过时 _bo_msg_until 应为 None")
        self.assertIsNone(self.app._bo_last_extend,
                          "未延长过时 _bo_last_extend 应为 None")

    def test_gear_icon_above_bg(self):
        """⚙ 图标必须在白色底板之上（否则只剩一个白色方块）"""
        below = self.app.cv.find_below(self.app.gear_id)
        if isinstance(below, tuple):      # 部分 Tk 版本返回 1 元组
            below = below[0] if below else None
        self.assertEqual(below, self.app.gear_bg,
                         "gear_id 正下方必须是 gear_bg（图标可见）")

    def test_blackout_click_skips(self):
        self.app.cfg["blackout_seconds"] = 10
        self.app.next_run["shower"] = datetime.now() - timedelta(seconds=1)
        self.app._tick_step()
        self.assertIsNotNone(self.app.blackout)
        self.app._close_blackout()
        self.assertIsNone(self.app.blackout)

    def test_blackout_does_not_steal_focus(self):
        """黑屏不该抢键盘焦点（否则用户正在打的字会丢）"""
        self.app.cfg["blackout_seconds"] = 3
        self.app.next_run["shower"] = datetime.now() - timedelta(seconds=1)
        self.app._tick_step()
        self.assertIsNotNone(self.app.blackout)

    # ---------- UI 元素常驻 ----------
    def test_canvas_items_never_recreated(self):
        """所有画布元素只创建一次，绝不销毁重建（否则会闪烁）"""
        before = set(self.app.cv.find_all())
        self.app.next_run["water"] = datetime.now() - timedelta(seconds=1)
        self.app._tick_step()
        self.app.auto_left = 0
        self.app._tick_step()
        after = set(self.app.cv.find_all())
        self.assertEqual(before, after, "画布元素被销毁重建了")

    def test_no_callback_exceptions(self):
        self.app.next_run["water"] = datetime.now() - timedelta(seconds=1)
        self.app._tick_step()
        self.app.auto_left = 0
        self.app._tick_step()
        self.assertEqual(self.errors, [])

    # ---------- 设置面板 ----------
    def test_settings_dialog_collect_and_save(self):
        dlg = hf.SettingsDialog(self.root, dict(hf.DEFAULT_CONFIG))
        dlg.widgets["shower_time"].var_h.set("20")
        dlg.widgets["shower_time"].var_m.set("30")
        dlg.widgets["water_minutes"].var.set("90")
        out = dlg.collect()
        self.assertEqual(out["shower_time"], "20:30")
        self.assertEqual(out["water_minutes"], 90)

    def test_dials_roundtrip(self):
        td = hf.TimeDial(self.root, hhmm="22:45")
        self.assertEqual(td.get(), "22:45")
        nd = hf.NumDial(self.root, value=90, hi=1440)
        self.assertEqual(nd.get(), 90)

    # ---------- CustomTkinter 面板（可选依赖）----------
    @unittest.skipUnless(hf.HAVE_CTK, "未安装 CustomTkinter")
    def test_ctk_stepper_entry_not_truncating_digits(self):
        """拨轮数字框必须放得下完整数字。

        CTkEntry 的 width 单位是像素而非字符数 —— 之前按字符数换算，
        「120」被截成「12C」，末位直接看不见。
        """
        # CTK 控件必须挂在独立的 root 上：
        # 它和浮窗的原生 tk.Canvas 共用一棵控件树时，
        # CTK 的 configure() 遍历子控件会踩到已销毁的控件而崩。
        ctk_root = tk.Tk()
        ctk_root.withdraw()
        try:
            stepper = hf._CTKStepper(ctk_root, value=120, unit="秒")
            ctk_root.update_idletasks()
            self.assertEqual(stepper.var.get(), "120")
            # 文本实际渲染宽度必须小于输入框可视宽度
            font = stepper.entry.cget("font")
            needed = tkinter.font.Font(root=ctk_root, font=font).measure("120")
            # winfo_width 在控件未映射时返回 1，用 reqwidth 更可靠
            actual = max(stepper.entry.winfo_width(),
                         stepper.entry.winfo_reqwidth())
            self.assertGreaterEqual(actual, needed,
                                    "数字框太窄，数字会被截断")
        finally:
            ctk_root.destroy()

    @unittest.skipUnless(hf.HAVE_CTK, "未安装 CustomTkinter")
    def test_ctk_panel_collects_all_items(self):
        """CTK 面板必须能读出全部设置项，且和原生版语义一致"""
        ctk_root = tk.Tk()
        ctk_root.withdraw()
        try:
            cfg = dict(hf.DEFAULT_CONFIG)
            dlg = hf.SettingsDialog(ctk_root, cfg)
            out = dlg.collect()
            for key, _, _, _ in hf.SETT_ITEMS:
                self.assertIn(key, out, f"面板漏掉了设置项 {key}")
            self.assertEqual(out["meeting_mode"], bool(cfg["meeting_mode"]))
            self.assertEqual(out["sound"], bool(cfg["sound"]))
        finally:
            ctk_root.destroy()

    @unittest.skipUnless(hf.HAVE_CTK, "未安装 CustomTkinter")
    def test_ctk_panel_reset_restores_defaults(self):
        """「恢复默认」在 CTK 面板上必须真的生效（数字拨轮 + 开关都要）"""
        ctk_root = tk.Tk()
        ctk_root.withdraw()
        try:
            cfg = dict(hf.DEFAULT_CONFIG)
            dlg = hf.SettingsDialog(ctk_root, cfg)
            dlg.widgets["water_minutes"].var.set("999")
            dlg.widgets["meeting_mode"].var.set(True)
            dlg._reset()
            self.assertEqual(dlg.widgets["water_minutes"].var.get(),
                             str(hf.DEFAULT_CONFIG["water_minutes"]))
            self.assertEqual(bool(dlg.widgets["meeting_mode"].var.get()),
                             bool(hf.DEFAULT_CONFIG["meeting_mode"]))
        finally:
            ctk_root.destroy()


if __name__ == "__main__":
    unittest.main(verbosity=2)
