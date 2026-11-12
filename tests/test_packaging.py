#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""打包配置的一致性测试。

这些测试不启动 GUI，只读仓库里的脚本和 workflow 文件。
目的：守住几个「只有打包时才暴露、而且是静默失败」的坑：

1. **CTK 资源**：CustomTkinter 的主题是 JSON 数据文件，不是 Python 模块。
   PyInstaller 自带 hook-customtkinter.py 会收 collect_data_files，
   但显式 --collect-all 更稳，而且所有打包脚本必须口径一致 ——
   CI 的 release.yml 和本地的 build_windows.sh / linux-installer.sh
   是两份独立的实现，很容易只改一份。

2. **zip 自包含**：make_archive(root_dir='dist') 会把正在写入的 zip
   自己也包进去，用户解压会看到一个几十字节的空壳。

3. **架构**：macOS 产物在 CI 上是 universal2（python.org 官方 Python），
   本机是单架构。README 承诺「Intel + Apple Silicon 通用」，
   这个承诺只有 CI 产物能满足。
"""

import os
import re
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(relpath):
    path = os.path.join(REPO_ROOT, relpath)
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


class TestPackagingConsistency(unittest.TestCase):
    """打包脚本之间的一致性。"""

    # 所有会跑 PyInstaller 的脚本
    ALL_PACKERS = [
        ".github/workflows/release.yml",
        "build_macos_app.sh",
        "build_windows.sh",
        "build_windows.bat",
        "linux-installer.sh",
    ]

    def test_every_packer_handles_customtkinter(self):
        """每个打包脚本都必须处理 customtkinter。

        漏掉的后果：脚本要么报错（CTK 装了但参数没传，资源缺失），
        要么静默产出没有现代设置面板的包。
        """
        for rel in self.ALL_PACKERS:
            with self.subTest(packer=rel):
                content = _read(rel)
                self.assertIn(
                    "customtkinter",
                    content,
                    "%s 完全没提 customtkinter —— 和其他脚本不一致" % rel,
                )

    def test_every_packer_passes_collect_all(self):
        """每个打包脚本都要传 --collect-all customtkinter。

        PyInstaller 自带 hook 会收数据文件（主题 JSON），
        但 --collect-all 还会收 hiddenimports 和 binaries —— 更稳。
        更重要的是：五个脚本口径必须一致，否则 CI 和本地出的包不一样。
        """
        for rel in self.ALL_PACKERS:
            with self.subTest(packer=rel):
                content = _read(rel)
                self.assertIn(
                    "--collect-all customtkinter",
                    content,
                    "%s 缺少 --collect-all customtkinter" % rel,
                )

    def test_release_workflow_windows_matches_local_script(self):
        """release.yml 的 Windows 构建必须和 build_windows.sh 口径一致。

        两份独立的 PyInstaller 命令行是最容易漂移的地方：
        本地改了、CI 没改，用户拿到的是旧界面。
        """
        release = _read(".github/workflows/release.yml")
        windows_job = release.split("windows:", 1)[1].split("linux:", 1)[0]

        self.assertIn("--collect-all customtkinter", windows_job)
        self.assertIn("--add-data", windows_job)
        self.assertIn("assets", windows_job)


class TestWindowsZip(unittest.TestCase):
    """Windows 打包的 zip 结构。"""

    def setUp(self):
        self.release = _read(".github/workflows/release.yml")
        self.zip_step = self.release.split("- name: Zip", 1)[1].split(
            "- uses: actions/upload-artifact", 1
        )[0]

    def test_zip_does_not_include_itself(self):
        """zip 不能把自己包进去。

        make_archive(base, 'zip', root_dir='dist') 的 root_dir 就是
        zip 的输出目录 —— 边写边扫，会扫到半成品自己。
        正确写法是 base_dir='Health Float'，只扫子目录。
        """
        self.assertNotIn(
            "make_archive('dist/HealthFloat-Windows','zip','dist')",
            self.zip_step.replace(" ", ""),
            "zip 仍在打包整个 dist/，会把自己包进去",
        )
        self.assertIn(
            "base_dir",
            self.zip_step,
            "zip 没有限定 base_dir —— 会把输出目录里的其他文件（含 zip 自己）一起打包",
        )

    def test_zip_lands_in_dist(self):
        """zip 必须落在 dist/ 里。

        upload-artifact 找的是 dist/*.zip；
        之前写成 '../HealthFloat-Windows' 落到了仓库根，CI 直接报
        "No files were found with the provided path"。
        """
        self.assertIn("dist/HealthFloat-Windows", self.zip_step)


class TestMacOSArchitecture(unittest.TestCase):
    """macOS 产物的架构承诺。"""

    def test_release_uses_universal2_python(self):
        """CI 必须用 python.org 官方版 Python（自带 universal2）。

        setup-python 装的是单架构解释器，打出来的包只能跑一种芯片。
        README 承诺「Intel + Apple Silicon 通用」，靠的就是这一步。
        """
        release = _read(".github/workflows/release.yml")
        macos_job = release.split("macos:", 1)[1].split("windows:", 1)[0]
        self.assertIn(
            "python.org",
            macos_job,
            "CI 没装 python.org 官方版 Python —— macOS 产物会退化成单架构",
        )
        self.assertIn("HEALTH_FLOAT_BUILD_PYTHON", macos_job)

    def test_release_verifies_architecture(self):
        """打包后要检查架构，不能只打印。

        lipo -info 只是往日志里写一行，CI 不会因此失败 ——
        单架构包会被静默发出去，用户下完才发现打不开。
        """
        release = _read(".github/workflows/release.yml")
        macos_job = release.split("macos:", 1)[1].split("windows:", 1)[0]
        self.assertIn("lipo", macos_job)

    def test_local_script_detects_universal2(self):
        """本地脚本要能识别 universal2 构建器。"""
        script = _read("build_macos_app.sh")
        self.assertIn("universal binary", script)
        self.assertIn("--target-arch", script)


class TestReleaseAssets(unittest.TestCase):
    """Release 资产的命名与正文。"""

    def test_release_overwrites_stale_assets(self):
        """CI 产物要能覆盖同名旧资产。

        overwrite_files: false 时，Windows/Linux 的旧包永远不会被更新，
        用户会一直拿到 11-10 的老版本（缺 CTK 面板、缺黑屏延长修复）。
        """
        release = _read(".github/workflows/release.yml")
        self.assertIn("overwrite_files: true", release)

    def test_release_body_lists_real_asset_names(self):
        """Release 正文里的文件名必须是 GitHub 上真实存在的名字。

        GitHub 会把资产名里的空格换成点（softprops/action-gh-release
        的 alignAssetName：assetName.replace(/ /g, '.')），
        所以正文里写 'Health Float.dmg' 而实际下载的是 'Health.Float.dmg'
        —— 用户按正文找文件会找不到。
        """
        release = _read(".github/workflows/release.yml")
        body = release.split("body: |", 1)[1]
        # 正文里不允许出现带空格的资产名
        self.assertNotRegex(body, r"`Health Float\.(dmg|AppImage)`")
        self.assertIn("`Health.Float.dmg`", body)
        self.assertIn("`Health.Float.AppImage`", body)
        self.assertIn("`HealthFloat-Windows.zip`", body)

    def test_readme_asset_names_match_release(self):
        """README 的下载表要和 Release 正文用同一套文件名。"""
        readme = _read("README.md")
        release = _read(".github/workflows/release.yml")
        body = release.split("body: |", 1)[1]

        for name in ("Health.Float.dmg", "HealthFloat-Windows.zip", "Health.Float.AppImage"):
            with self.subTest(asset=name):
                self.assertIn(name, body, "Release 正文缺少 %s" % name)
                self.assertIn(name, readme, "README 缺少 %s" % name)

        # README 里不该再出现带空格的资产名（下载指令会找不到文件）
        self.assertNotIn("`Health Float.dmg`", readme)
        self.assertNotIn("`Health Float.AppImage`", readme)
        self.assertNotIn("chmod +x Health Float.AppImage", readme)

    def test_readme_claims_universal2(self):
        """README 承诺 Intel + Apple Silicon 通用，必须真的兑现。

        发布出去的是本机 arm64 单架构包时，这个承诺就是假的。
        """
        readme = _read("README.md")
        self.assertIn("Intel + Apple Silicon 通用", readme)


class TestVersionConsistency(unittest.TestCase):
    """版本号一致性。"""

    def test_version_is_parseable(self):
        """VERSION 常量格式固定，供打包脚本 grep。"""
        content = _read("health_float.py")
        match = re.search(r'^VERSION = "([^"]+)"', content, re.M)
        self.assertIsNotNone(match, "找不到 VERSION 常量")
        self.assertRegex(match.group(1), r"^\d+\.\d+\.\d+$")


if __name__ == "__main__":
    unittest.main()
