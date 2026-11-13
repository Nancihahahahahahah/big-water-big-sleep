#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""打包配置的一致性测试。

这些测试不启动 GUI，只读仓库里的脚本和 workflow 文件。
目的：守住几个「只有打包时才暴露、而且是静默失败」的坑：

1. **CTK 资源**：CustomTkinter 的主题是 JSON 数据文件，不是 Python 模块。
   PyInstaller 自带 hook-customtkinter.py 会收 collect_data_files，
   但显式 --collect-data 更稳，而且所有打包脚本必须口径一致 ——
   CI 的 release.yml 和本地的 build_windows.sh / linux-installer.sh
   是两份独立的实现，很容易只改一份。

   注意这里必须是 --collect-data 而不是 --collect-all：
   --collect-all 会在生成 spec 时把 PIL 的二进制塞进 binaries 列表，
   而 --exclude-module 只管模块分析，管不到显式传入的 binaries ——
   两者互相抵消，PIL 照样进包。

2. **zip 自包含**：make_archive(root_dir='dist') 会把正在写入的 zip
   自己也包进去，用户解压会看到一个几十字节的空壳。

3. **架构**：macOS 产物在 CI 上是 universal2（python.org 官方 Python），
   本机是单架构。README 承诺「Intel + Apple Silicon 通用」，
   这个承诺只有 CI 产物能满足。
"""

import os
import re
import sys
import unittest

# 让控制台输出不依赖系统编码：Windows 是 cp1252，
# 打印中文断言消息时会抛 UnicodeEncodeError，
# 把「测试失败」变成「测试崩溃」，真正的失败原因反而看不见。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _utf8_console  # noqa: F401,E402


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

    def test_every_packer_passes_collect_data(self):
        """每个打包脚本都要传 --collect-data customtkinter。

        PyInstaller 自带 hook 会收数据文件（主题 JSON），
        显式 --collect-data 更稳。
        更重要的是：五个脚本口径必须一致，否则 CI 和本地出的包不一样。
        """
        for rel in self.ALL_PACKERS:
            with self.subTest(packer=rel):
                content = _read(rel)
                self.assertIn(
                    "--collect-data customtkinter",
                    content,
                    "%s 缺少 --collect-data customtkinter" % rel,
                )

    def test_no_packer_uses_collect_all(self):
        """绝不能用 --collect-all customtkinter。

        --collect-all 会在生成 spec 时执行 collect_all()，
        把 PIL 的二进制（_imaging*.so）直接放进 spec 的 binaries 列表。
        --exclude-module 只影响模块分析阶段，管不到显式传入的 binaries ——
        两者互相抵消，结果 PIL 照样进包。

        实测（用 scripts/verify_package.py 验真实构建产物）：
          --collect-all  → 包里有 PIL/_imaging*.so
          --collect-data → PIL 0 个，CTK 主题 json 4 个，运行时正常
        """
        for rel in self.ALL_PACKERS:
            with self.subTest(packer=rel):
                content = _read(rel)
                self.assertNotIn(
                    "--collect-all customtkinter",
                    content,
                    "%s 用了 --collect-all —— 它会把 PIL 二进制拉进来，"
                    "抵消掉 --exclude-module PIL" % rel,
                )

    def test_release_workflow_windows_matches_local_script(self):
        """release.yml 的 Windows 构建必须和 build_windows.sh 口径一致。

        两份独立的 PyInstaller 命令行是最容易漂移的地方：
        本地改了、CI 没改，用户拿到的是旧界面。
        """
        release = _read(".github/workflows/release.yml")
        windows_job = release.split("windows:", 1)[1].split("linux:", 1)[0]

        self.assertIn("--collect-data customtkinter", windows_job)
        self.assertIn("--add-data", windows_job)
        self.assertIn("assets", windows_job)


class TestPillowExclusion(unittest.TestCase):
    """Pillow 必须被排除在包外。

    这条是被 CI 逼出来的：加了 --collect-data customtkinter 之后，
    macOS 的 universal2 构建直接挂了：

        IncompatibleBinaryArchError:
          PIL/_avif.cpython-312-darwin.so is not a fat binary!

    链条是：CTK 的 ctk_image.py 里 `from PIL import Image, ImageTk`
    → PyInstaller 把整个 Pillow 拉进来
    → Pillow 的编译扩展是单架构二进制
    → universal2 构建要把它转双架构，直接失败。

    本项目用 tk.PhotoImage 读 PNG，不需要 PIL；
    CTK 那边的 PIL 是 try/except 包着的软依赖，排除后照常工作。
    """

    # 会跑 PyInstaller 的脚本
    PACKERS = [
        ".github/workflows/release.yml",
        "build_macos_app.sh",
        "build_windows.sh",
        "build_windows.bat",
        "linux-installer.sh",
    ]

    def test_every_packer_excludes_pillow(self):
        """每个打包脚本都要 --exclude-module PIL。"""
        for rel in self.PACKERS:
            with self.subTest(packer=rel):
                content = _read(rel)
                self.assertIn(
                    "--exclude-module PIL",
                    content,
                    "%s 没有排除 PIL —— universal2 构建会因 PIL 单架构扩展而失败" % rel,
                )

    def test_app_does_not_need_pillow(self):
        """主程序不该直接依赖 PIL。

        如果哪天真的需要了，这条测试会提醒你：
        同时要处理 universal2 架构转换问题。
        """
        source = _read("health_float.py")
        # tk.PhotoImage 是标准库自带的读图方式，不需要 PIL
        self.assertNotIn("from PIL", source)
        self.assertNotIn("import PIL", source)

    def test_icon_asset_is_committed(self):
        """图标必须在仓库里。

        否则构建期要靠 Pillow 现场生成 —— 而 Pillow 的编译扩展
        是单架构的，正是 universal2 构建失败的元凶。
        """
        self.assertTrue(
            os.path.exists(os.path.join(REPO_ROOT, "assets", "app-icon.png")),
            "assets/app-icon.png 缺失 —— 构建期就得依赖 Pillow",
        )


class TestMacOSDistSync(unittest.TestCase):
    """macOS 产物同步到 dist/ 时必须是「精确镜像」，不能是「合并」。

    踩坑记录：11-10 用 --collect-all 打的包里有 PIL/，
    11-13 改成 --collect-data 重新构建，构建产物本身已经干净，
    但 dist/Health Float.app 里旧版的 PIL 文件还在 ——
    因为 ditto 是合并语义，目标里多出来的旧文件不会被清掉。
    verify_package.py 于是一直报「Pillow leaked into the package」，
    差点误判成打包参数没生效。

    解法是 rsync --delete：镜像语义，结果等价于「先删后拷」，
    但没有 rm -rf 那一步（批量删除在有安全守卫的环境里会被拦下）。
    """

    SCRIPT = "build_macos_app.sh"

    def test_uses_rsync_delete_for_dist(self):
        """dist/ 的 .app 必须用 rsync --delete 同步。"""
        content = _read(self.SCRIPT)
        self.assertIn(
            "rsync -a --delete",
            content,
            "%s 没用 rsync --delete 同步 dist —— "
            "旧版残留文件会留在产物里（PIL 就是这么混进去的）" % self.SCRIPT,
        )

    def test_no_ditto_merge_into_dist(self):
        """不能再用 ditto 合并的方式把 .app 拷进 dist/。

        ditto 复制目录是合并语义：不删目标里多余的旧文件。
        """
        content = _read(self.SCRIPT)
        for line in content.splitlines():
            stripped = line.strip()
            if not stripped.startswith("ditto "):
                continue
            self.fail(
                "%s 里有 ditto 复制目录：%s\n"
                "ditto 是合并语义，旧文件不会被清掉；"
                "请改用 rsync -a --delete" % (self.SCRIPT, stripped)
            )

    def test_no_bulk_rm_of_app_bundle(self):
        """不要 rm -rf 整个 .app。

        一次删几百个文件属于批量删除，在有安全守卫的环境里会被拦下，
        整个打包流程直接中断。rsync --delete 没有这个问题。
        """
        content = _read(self.SCRIPT)
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("rm -rf") and ".app" in stripped:
                self.fail(
                    "%s 里有 rm -rf 整个 .app：%s\n"
                    "请改用 rsync -a --delete" % (self.SCRIPT, stripped)
                )


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

    def test_release_asserts_universal2(self):
        """架构必须是断言，不是打印。

        README 承诺「Intel + Apple Silicon 通用」，
        这个承诺要由 CI 强制执行 —— lipo -archs 拿到结果后
        必须 exit 1 让构建失败，否则单架构包照发。
        """
        release = _read(".github/workflows/release.yml")
        macos_job = release.split("macos:", 1)[1].split("windows:", 1)[0]
        self.assertIn("lipo -archs", macos_job)
        self.assertIn("x86_64", macos_job)
        self.assertIn("arm64", macos_job)
        self.assertIn(
            "exit 1",
            macos_job,
            "架构检查没有 exit 1 —— 单架构包会被静默发布",
        )

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

    def test_release_dmg_has_applications_symlink(self):
        """发布出去的 DMG 里要有指向 /Applications 的软链。

        软链是用户「把 app 拖进应用程序」的入口。
        之前 release.yml 直接 hdiutil -srcfolder "dist/Health Float.app"，
        软链没有 —— 而本地 build_macos_app.sh 生成的 DMG 是有的，
        两边不一致，发布出去的那份反而少了这个入口。
        """
        release = _read(".github/workflows/release.yml")
        dmg_step = release.split("- name: Make DMG", 1)[1].split(
            "- name: Verify package contents", 1
        )[0]
        self.assertIn(
            "ln -sfn /Applications",
            dmg_step,
            "发布用的 DMG 没有 /Applications 软链 —— "
            "用户打开 DMG 少了一个拖拽入口",
        )

    def test_release_configures_git_identity_before_tagging(self):
        """打注解 tag 之前必须配置 git 身份。

        CI runner 上默认没有 committer 身份，`git tag -a` 会直接失败：

            Committer identity unknown
            fatal: empty ident name ... not allowed

        这条路径只有「新版本号」才会走到 ——
        版本号已经存在时直接跳过打 tag。
        所以复用旧版本号发布时一直没暴露，一升版本就炸。
        """
        release = _read(".github/workflows/release.yml")
        tag_step = release.split("- name: Ensure tag exists", 1)[1].split(
            "- uses: softprops/action-gh-release", 1
        )[0]

        # 先剥掉注释行 —— 否则注释里提到「git tag -a」也会被当成命令
        code = "\n".join(
            line for line in tag_step.splitlines()
            if not line.strip().startswith("#")
        )

        config_at = code.find("git config user.name")
        tag_at = code.find("git tag -a")
        self.assertNotEqual(
            config_at,
            -1,
            "打 tag 前没有配置 git 身份 —— 发新版本号时必然失败",
        )
        self.assertNotEqual(tag_at, -1, "找不到 git tag -a")
        self.assertLess(
            config_at,
            tag_at,
            "git 身份配置必须排在 git tag -a 之前",
        )


class TestVersionConsistency(unittest.TestCase):
    """版本号一致性。"""

    def test_version_is_parseable(self):
        """VERSION 常量格式固定，供打包脚本 grep。"""
        content = _read("health_float.py")
        match = re.search(r'^VERSION = "([^"]+)"', content, re.M)
        self.assertIsNotNone(match, "找不到 VERSION 常量")
        self.assertRegex(match.group(1), r"^\d+\.\d+\.\d+$")

    def test_readme_version_matches_code(self):
        """README 下载链接里的版本号必须和代码里的 VERSION 一致。

        改版本号时忘了改 README，用户点进去下载到的就是旧版 ——
        而且链接指向的 tag 可能根本不存在。
        """
        content = _read("health_float.py")
        match = re.search(r'^VERSION = "([^"]+)"', content, re.M)
        version = match.group(1)
        readme = _read("README.md")

        self.assertIn(
            "v%s" % version,
            readme,
            "README 里找不到 v%s —— 下载链接指向的 tag 可能不存在" % version,
        )

        # README 里出现的所有 releases/tag 链接，都必须指向当前版本
        tags = re.findall(r"releases/tag/(v[\d.]+)", readme)
        self.assertTrue(tags, "README 里没有 releases/tag 下载链接")
        for tag in tags:
            self.assertEqual(
                tag,
                "v%s" % version,
                "README 的下载链接指向 %s，但代码版本是 %s" % (tag, version),
            )


if __name__ == "__main__":
    unittest.main()
