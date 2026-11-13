#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""产物自检脚本的测试。

verify_package.py 是发布前的最后一道闸：确认包里该有的有、
不该有的没有。这一轮挖出的三个缺陷都属于「不报错但结果不对」，
只能靠这种断言守住 —— 所以这个脚本本身也要被测。
"""

import os
import shutil
import sys
import tempfile
import unittest

# 让控制台输出不依赖系统编码：Windows 是 cp1252，
# 打印中文断言消息时会抛 UnicodeEncodeError，
# 把「测试失败」变成「测试崩溃」，真正的失败原因反而看不见。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _utf8_console  # noqa: F401,E402

import zipfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

import verify_package  # noqa: E402


def _make_theme(root):
    """造一个合法的 CTK 主题文件。"""
    d = os.path.join(root, "_internal", "customtkinter", "assets", "themes")
    os.makedirs(d, exist_ok=True)
    for name in ("blue", "green", "gold", "dark-blue"):
        with open(os.path.join(d, name + ".json"), "w", encoding="utf-8") as fh:
            fh.write("{}")


class TestVerifyPackage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="hfverify_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    # ---------- 目录型产物（macOS .app / Linux onedir） ----------

    def test_valid_directory_passes(self):
        root = os.path.join(self.tmp, "pkg")
        _make_theme(root)
        self.assertIsNone(verify_package._check_dir(root))

    def test_missing_themes_is_rejected(self):
        root = os.path.join(self.tmp, "pkg")
        os.makedirs(os.path.join(root, "_internal"))
        error = verify_package._check_dir(root)
        self.assertIsNotNone(error)
        self.assertIn("CustomTkinter", error)

    def test_pillow_in_directory_is_rejected(self):
        root = os.path.join(self.tmp, "pkg")
        _make_theme(root)
        pil_dir = os.path.join(root, "_internal", "PIL")
        os.makedirs(pil_dir)
        with open(os.path.join(pil_dir, "_imaging.so"), "w") as fh:
            fh.write("x")
        error = verify_package._check_dir(root)
        self.assertIsNotNone(error)
        self.assertIn("Pillow", error)

    def test_avif_extension_is_rejected(self):
        """Pillow 的 _avif 扩展是 universal2 构建失败的直接元凶。"""
        root = os.path.join(self.tmp, "pkg")
        _make_theme(root)
        pil_dir = os.path.join(root, "_internal", "PIL")
        os.makedirs(pil_dir)
        with open(os.path.join(pil_dir, "_avif.cpython-312-darwin.so"), "w") as fh:
            fh.write("x")
        error = verify_package._check_dir(root)
        self.assertIsNotNone(error)
        self.assertIn("Pillow", error)

    # ---------- zip 型产物（Windows） ----------

    def _make_zip(self, name, entries):
        path = os.path.join(self.tmp, name)
        with zipfile.ZipFile(path, "w") as z:
            for entry in entries:
                z.writestr(entry, "x")
        return path

    def test_valid_zip_passes(self):
        path = self._make_zip(
            "ok.zip",
            [
                "Health Float/Health Float.exe",
                "Health Float/_internal/customtkinter/assets/themes/blue.json",
                "Health Float/_internal/customtkinter/assets/themes/green.json",
            ],
        )
        self.assertIsNone(verify_package._check_windows(path))

    def test_base_library_zip_is_allowed(self):
        """PyInstaller 自带的 base_library.zip 不是自包含，不能误报。"""
        path = self._make_zip(
            "base.zip",
            [
                "Health Float/Health Float.exe",
                "Health Float/_internal/base_library.zip",
                "Health Float/_internal/customtkinter/assets/themes/blue.json",
            ],
        )
        self.assertIsNone(verify_package._check_windows(path))

    def test_self_included_zip_is_rejected(self):
        path = self._make_zip(
            "self.zip",
            [
                "Health Float/Health Float.exe",
                "Health Float/_internal/customtkinter/assets/themes/blue.json",
                "HealthFloat-Windows.zip",
            ],
        )
        error = verify_package._check_windows(path)
        self.assertIsNotNone(error)
        self.assertIn("contains itself", error)

    def test_missing_themes_in_zip_is_rejected(self):
        path = self._make_zip("nothemes.zip", ["Health Float/Health Float.exe"])
        error = verify_package._check_windows(path)
        self.assertIsNotNone(error)
        self.assertIn("CustomTkinter", error)

    def test_pillow_in_zip_is_rejected(self):
        path = self._make_zip(
            "pil.zip",
            [
                "Health Float/_internal/customtkinter/assets/themes/blue.json",
                "Health Float/_internal/PIL/_imaging.so",
            ],
        )
        error = verify_package._check_windows(path)
        self.assertIsNotNone(error)
        self.assertIn("Pillow", error)

    # ---------- 入口 ----------

    def test_main_rejects_missing_target(self):
        self.assertEqual(
            verify_package.main(["verify_package.py", os.path.join(self.tmp, "nope.zip")]),
            1,
        )

    def test_main_accepts_valid_zip(self):
        path = self._make_zip(
            "main.zip",
            ["Health Float/_internal/customtkinter/assets/themes/blue.json"],
        )
        self.assertEqual(verify_package.main(["verify_package.py", path]), 0)


class TestReleaseWorkflowUsesVerifier(unittest.TestCase):
    """release.yml 的三个平台都要调用这个自检脚本。"""

    def setUp(self):
        with open(os.path.join(REPO_ROOT, ".github", "workflows", "release.yml"), encoding="utf-8") as fh:
            self.release = fh.read()

    def test_all_platforms_verify_their_output(self):
        self.assertEqual(
            self.release.count("scripts/verify_package.py"),
            3,
            "all three platforms must call verify_package.py",
        )

    def test_verifier_script_exists(self):
        self.assertTrue(
            os.path.exists(os.path.join(REPO_ROOT, "scripts", "verify_package.py")),
            "verify_package.py 不存在",
        )


if __name__ == "__main__":
    unittest.main()
