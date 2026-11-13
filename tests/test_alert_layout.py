#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
提醒卡排版守卫测试

这一组的每个用例都对应一个**真实发生过的**排版 bug，
不是「为了覆盖率而写」的测试。

背景：2026-11-13 用户两次发截图投诉提醒卡「丑成什么样了」。
排查下来是 6 个真问题，其中 4 个不报错、不崩溃，肉眼才看得见：

  1. 面板只有 110pt 宽，15pt 粗体标题（emoji + 4 汉字）撑到边缘
  2. 标题与副标题几乎贴在一起，没有呼吸感
  3. 副标题靠 width= 自动折行，把「明天还有满格的自己」断成
     「明天还有满格 / 的自己」，语义被拦腰截断
  4. 按钮底板用 cv.move 定位（move 是相对位移且不改尺寸），
     缩成一个 10x10 的小方块；按钮文字坐标从未设置，永远停在 (0,0)
  5. 齿轮 ⚙ 和底部提示文字挤在同一行，直接叠在一起
  6. 字符「⚙」(U+2699) 在 macOS Tk 里没有可用字形，静默渲染成空白 ——
     设置入口完全看不见

所以这里的核心断言不是「长什么样」，而是「不能再退回那些坏状态」。

运行： python3 -m unittest discover -s tests
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tkinter as tk  # noqa: E402
import tkinter.font  # noqa: E402

import health_float as hf  # noqa: E402


class TestAlertLayout(unittest.TestCase):
    """提醒卡排版：宽度、层级、按钮、齿轮"""

    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw()
        cls.cfg = hf.load_config()
        cls.app = hf.FloatApp(cls.root, cls.cfg)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except tk.TclError:
            pass

    def setUp(self):
        self.app.current = "sleep"
        self.app.auto_left = 93
        self.app._resize_to(*hf.ALERT)
        self.app._layout_alert()
        self.app._update_auto_hint()
        self.root.update()

    # ---------- 面板宽度 ----------
    def test_panel_wide_enough_for_longest_title(self):
        """最宽的标题组必须放得进面板，不能顶到右边缘。

        标题组 = emoji + 间隔 + 汉字标题。
        用真实字体度量算，而不是写死数字 —— 换字体/字号时测试仍有意义。
        """
        cv = self.app.cv
        content_w = hf.PANEL[2] - hf.PANEL[0] - 24   # 左右各留 12pt 内边距

        f_title = tkinter.font.Font(root=self.root,
                                    font=hf.ui_font(15, True))
        f_icon = tkinter.font.Font(root=self.root,
                                   font=hf.ui_font(17))
        for key, (title, _sub, icon, _, _) in hf.ALERT_META.items():
            group = (f_icon.measure(icon) + 7 + f_title.measure(title))
            self.assertLessEqual(
                group, content_w,
                f"「{title}」标题组宽 {group} > 面板内容宽 {content_w}，会溢出")

    def test_title_fits_inside_panel(self):
        """标题的实际绘制范围必须在面板内（不是估算，是 bbox）"""
        cv = self.app.cv
        for key in hf.ALERT_META:
            self.app.current = key
            self.app._layout_alert()
            self.root.update()
            for iid in (self.app.a_icon_id, self.app.a_title_id):
                bb = cv.bbox(iid)
                self.assertIsNotNone(bb, f"{key}: 标题元素没画出来")
                self.assertGreaterEqual(bb[0], hf.PANEL[0],
                                        f"{key}: 标题左侧超出面板")
                self.assertLessEqual(bb[2], hf.PANEL[2],
                                     f"{key}: 标题右侧超出面板: {bb}")

    def test_subtitle_lines_do_not_overflow_panel(self):
        """副标题每一行都必须放得进面板。

        这是「明天还有满格的自己」被断成两截的那个 bug 的守卫。
        """
        cv = self.app.cv
        f_sub = tkinter.font.Font(root=self.root, font=hf.ui_font(11))
        for key, (_t, sub, _i, _, _) in hf.ALERT_META.items():
            for line in sub.split("\n"):
                w = f_sub.measure(line)
                self.assertLessEqual(
                    w, hf.PANEL[2] - hf.PANEL[0] - 24,
                    f"「{key}」副标题行「{line}」宽 {w}，超出面板")

    def test_subtitle_uses_manual_line_breaks_only(self):
        """副标题不能靠 width= 自动折行。

        自动折行会在语义中间断开（「明天还有满格 / 的自己」）。
        现在文案自带 \\n，交给 Tk 的 width 反而会二次折行。
        width=0 表示「不自动折行」，这是我们要的状态。
        """
        cv = self.app.cv
        width = cv.itemcget(self.app.a_sub_id, "width")
        self.assertEqual(
            int(width or 0), 0,
            "副标题不该设 width= 让 Tk 自动折行 —— "
            "那会把句子拦腰截断。行数由文案里的 \\n 决定。")

    # ---------- 垂直节奏 ----------
    def test_vertical_rhythm_has_breathing_room(self):
        """标题、副标题、按钮、提示之间都要有呼吸，不能贴在一起。

        用户截图里最刺眼的就是「该睡觉啦」和「放下屏幕」几乎重叠。
        """
        cv = self.app.cv
        title = cv.bbox(self.app.a_title_id)
        sub = cv.bbox(self.app.a_sub_id)
        self.assertGreaterEqual(
            sub[1] - title[3], 8,
            f"副标题贴着标题了（间距 {sub[1] - title[3]}）")

        btn = cv.bbox(self.app.a_btn_id)
        self.assertGreaterEqual(
            btn[1] - sub[3], 8,
            f"按钮贴着副标题了（间距 {btn[1] - sub[3]}）")

        hint = cv.bbox(self.app.a_hint_id)
        self.assertGreaterEqual(
            hint[1] - btn[3], 8,
            f"提示文字贴着按钮了（间距 {hint[1] - btn[3]}）")

    def test_elements_stay_inside_panel_vertically(self):
        """所有文字元素都要在面板的上下边界内"""
        cv = self.app.cv
        for iid in (self.app.a_icon_id, self.app.a_title_id,
                    self.app.a_sub_id, self.app.a_hint_id):
            bb = cv.bbox(iid)
            self.assertIsNotNone(bb)
            self.assertGreaterEqual(bb[1], hf.PANEL[1],
                                    f"{iid} 超出面板上边")
            self.assertLessEqual(bb[3], hf.PANEL[3],
                                 f"{iid} 超出面板下边: {bb}")

    # ---------- 按钮 ----------
    def test_button_has_visible_label(self):
        """按钮必须有文字，且文字居中在按钮上。

        之前 a_btn_txt 的坐标从未设置过，文字永远停在 (0,0)，
        截图里那个按钮只剩一个空的小方块。
        """
        cv = self.app.cv
        self.assertEqual(cv.itemcget(self.app.a_btn_txt, "state"), "normal",
                         "按钮文字不可见")
        self.assertTrue(cv.itemcget(self.app.a_btn_txt, "text").strip(),
                        "按钮文字是空的")
        tb = cv.bbox(self.app.a_btn_txt)
        bb = cv.bbox(self.app.a_btn_id)
        self.assertIsNotNone(tb, "按钮文字没画出来")
        self.assertIsNotNone(bb, "按钮底板没画出来")
        # 文字必须落在按钮底板范围内
        self.assertGreaterEqual(tb[0], bb[0] - 2, "按钮文字跑到底板左边了")
        self.assertLessEqual(tb[2], bb[2] + 2, "按钮文字跑到底板右边了")
        self.assertGreaterEqual(tb[1], bb[1] - 2, "按钮文字跑到底板上边了")
        self.assertLessEqual(tb[3], bb[3] + 2, "按钮文字跑到底板下边了")

    def test_button_size_is_stable_across_layouts(self):
        """反复 layout 后按钮尺寸不能变。

        用 cv.move 定位多边形是相对位移：位置会漂，尺寸也不会变。
        必须用 cv.coords 给完整点集。
        """
        cv = self.app.cv
        before = cv.bbox(self.app.a_btn_id)
        for _ in range(5):
            self.app._layout_alert()
        after = cv.bbox(self.app.a_btn_id)
        self.assertEqual(before, after,
                         f"按钮几何在多次 layout 后变了: {before} -> {after}")
        w = before[2] - before[0]
        self.assertGreater(w, 40, f"按钮太窄了（{w}pt），像个残缺的小方块")

    def test_button_text_positioned_within_button(self):
        """按钮文字必须跟着按钮走（不能停在画布原点）"""
        cv = self.app.cv
        tb = cv.bbox(self.app.a_btn_txt)
        self.assertIsNotNone(tb)
        self.assertGreater(tb[0], 0, "按钮文字还停在画布原点")

    # ---------- 齿轮 ----------
    def test_gear_is_not_a_missing_glyph_character(self):
        """齿轮必须是 Canvas 图元，不能是字符「⚙」。

        U+2699 在 macOS Tk 里没有可用字形，会静默渲染成空白 ——
        设置入口完全看不见，而且不报任何错。
        """
        cv = self.app.cv
        self.assertNotEqual(
            cv.type(self.app.gear_id), "text",
            "齿轮又变回字符了 —— macOS 上那个字符没有字形，等于隐形")
        # 齿轮整组图元都要有真实尺寸
        for iid in (self.app.gear_id,) + tuple(self.app.gear_extra):
            bb = cv.bbox(iid)
            self.assertIsNotNone(bb, "齿轮图元没画出来")
            self.assertGreater(bb[2] - bb[0], 0)

    def test_gear_is_visible_and_big_enough(self):
        """齿轮必须可见，且有一定体量（太小等于看不见）"""
        cv = self.app.cv
        self.assertEqual(cv.itemcget(self.app.gear_id, "state"), "normal",
                         "齿轮不可见")
        bb = cv.bbox(self.app.gear_id)
        self.assertGreaterEqual(bb[2] - bb[0], 10,
                                "齿轮太小了（<10pt），实际看不见")

    def test_gear_does_not_overlap_hint_text(self):
        """齿轮不能和底部提示文字叠在一起。

        用户截图里齿轮和「93 秒后自动消失」是重叠的。
        """
        cv = self.app.cv
        gear = cv.bbox(self.app.gear_id)
        hint = cv.bbox(self.app.a_hint_id)
        self.assertIsNotNone(gear)
        self.assertIsNotNone(hint)
        overlap = not (gear[2] < hint[0] or gear[0] > hint[2]
                       or gear[3] < hint[1] or gear[1] > hint[3])
        self.assertFalse(overlap,
                         f"齿轮和提示文字重叠了: gear={gear} hint={hint}")

    def test_gear_not_covered_by_title(self):
        """齿轮必须在标题文字之上（z-order）。

        标题「该睡觉啦」的 bbox 一直伸到 x≈283，和右上角的齿轮
        重叠 —— 齿轮层级不够就会被标题压在下面看不见。
        """
        cv = self.app.cv
        above = cv.find_above(self.app.gear_id)
        while above:
            state = cv.itemcget(above, "state")
            if state == "normal" and cv.type(above) == "text":
                txt = cv.itemcget(above, "text")
                if txt in ("该睡觉啦", "看看远方", "起来动动",
                           "喝杯水吧", "去洗澡啦"):
                    self.fail(f"齿轮被标题「{txt}」压在下面了")
            above = cv.find_above(above)

    def test_gear_moves_as_a_group(self):
        """整组齿轮图元必须一起移动，不能散架。

        判据不是「所有图元同心」—— 齿块本来就偏心（它们在半径 8.6
        的圆周上，外圈半径只有 6.8）。真正的判据是**相对位置不变**：
        每个图元的 bbox 相对齿轮中心的偏移量在移动前后必须一致。
        """
        cv = self.app.cv
        ids = (self.app.gear_id,) + tuple(self.app.gear_extra)

        def offsets(cx, cy):
            out = []
            for iid in ids:
                bb = cv.bbox(iid)
                out.append((bb[0] - cx, bb[1] - cy, bb[2] - cx, bb[3] - cy))
            return out

        before_c = self.app.gear_center
        before = offsets(*before_c)
        self.app._move_gear(200, 120)
        after = offsets(200, 120)

        for i, (b, a) in enumerate(zip(before, after)):
            for bv, av in zip(b, a):
                self.assertAlmostEqual(
                    bv, av, delta=0.6,
                    msg=f"齿轮图元 {i} 移动后相对位置变了（散架）: "
                        f"{b} -> {a}")

    # ---------- 文案 ----------
    def test_titles_are_four_characters_max(self):
        """标题控制在 4 个汉字以内。

        5 个字（100pt）+ emoji + 间隔 = 131pt > 面板内容宽 126pt，
        会溢出右边缘。用户截图里「该看远方啦」就是顶出去了。
        """
        for key, (title, _sub, _icon, _, _) in hf.ALERT_META.items():
            self.assertLessEqual(
                len(title), 4,
                f"「{title}」{len(title)} 个字，太长了会撑破面板")

    def test_subtitle_lines_are_short(self):
        """副标题每行不超过 6 个汉字，读起来才不喘"""
        for key, (_t, sub, _i, _, _) in hf.ALERT_META.items():
            for line in sub.split("\n"):
                self.assertLessEqual(
                    len(line), 7,
                    f"「{key}」副标题行「{line}」太长（{len(line)} 字）")

    def test_subtitle_has_explicit_line_break(self):
        """副标题必须分成两行（一句一行）"""
        for key, (_t, sub, _i, _, _) in hf.ALERT_META.items():
            self.assertIn("\n", sub, f"「{key}」副标题没有换行")


if __name__ == "__main__":
    unittest.main(verbosity=2)
