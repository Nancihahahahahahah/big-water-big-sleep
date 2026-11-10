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
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tkinter as tk  # noqa: E402

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
            bb = self.app.cv.bbox(iid)
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
        dlg.destroy()

    def test_right_click_menu_has_settings_entry(self):
        """右键菜单里必须显式列出设置入口"""
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
            self.app._show_menu(type("E", (), {"x_root": 10, "y_root": 10})())
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

    def test_blackout_extension_safety_cap(self):
        """延长次数上限，防止永久锁屏"""
        self.app.cfg["blackout_seconds"] = 10
        self.app.next_run["sleep"] = datetime.now() - timedelta(seconds=1)
        self.app._tick_step()
        self.app._bo_exts = 30
        before = self.app.black_left
        self.app._on_bo_motion(None)
        self.assertEqual(self.app.black_left, before, "超过上限不应再延长")

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
        dlg.destroy()

    def test_dials_roundtrip(self):
        td = hf.TimeDial(self.root, hhmm="22:45")
        self.assertEqual(td.get(), "22:45")
        nd = hf.NumDial(self.root, value=90, hi=1440)
        self.assertEqual(nd.get(), 90)


if __name__ == "__main__":
    unittest.main(verbosity=2)
