#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""产物内容自检 —— 发布前确认包里该有的有、不该有的没有。

用法：
    python3 scripts/verify_package.py <zip|dir> [--name macos|windows|linux]

为什么需要它
------------
这一轮挖出的三个缺陷，本地全绿、CI 全绿、代码读起来完全正常，
只有把「实际产物」打开看才会暴露：

- CTK 主题 JSON 缺失 → 设置面板悄悄退化成原生 tk 界面
- PIL 混进包里      → 单架构扩展，universal2 打包直接失败
- zip 把自己包进去  → 用户解压看到几十字节的空壳

这些都不是「跑不起来」的错，而是「跑起来了但结果不对」的错。
构建脚本跑完不代表产物对 —— 必须在发布前把产物打开验一遍。

检查项
------
1. CustomTkinter 主题 JSON 必须存在（4 个内置主题）
2. PIL 不得出现（它的编译扩展是单架构的，会破坏 universal2 打包）
3. zip 不得把自己包进去（排除 PyInstaller 自带的 base_library.zip）
"""

import os
import sys
import zipfile


def _check_windows(zip_path):
    """检查 Windows zip。"""
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()

    themes = [n for n in names if "themes" in n and n.endswith(".json")]
    print("  CTK theme files: %d" % len(themes))
    if not themes:
        return ("[X] missing CustomTkinter themes - "
                "settings panel would degrade to plain tkinter")

    # PIL 不得进包：它的编译扩展是单架构的，会破坏 universal2 打包。
    pil_hits = [
        n for n in names
        if os.path.basename(n).startswith("PIL")
        or "_avif" in n
        or "_imaging" in n
    ]
    if pil_hits:
        return "[X] Pillow leaked into the package: %s" % pil_hits[:3]

    # base_library.zip 是 PyInstaller 自带的 Python 运行时，不是自包含
    self_included = [n for n in names if n.endswith(".zip") and "base_library" not in n]
    if self_included:
        return "[X] zip contains itself: %s" % self_included[:3]

    return None


def _check_dir(root):
    """检查 onedir 产物目录（macOS 的 .app / Linux 的 AppDir）。"""
    themes = []
    pil_hits = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            if fn.endswith(".json") and "themes" in full and "customtkinter" in full:
                themes.append(full)
            if fn.startswith("PIL") or "_avif" in fn or "_imaging" in fn:
                pil_hits.append(full)

    print("  CTK theme files: %d" % len(themes))
    if not themes:
        return ("[X] missing CustomTkinter themes - "
                "settings panel would degrade to plain tkinter")

    if pil_hits:
        return "[X] Pillow leaked into the package: %s" % pil_hits[:3]

    return None


def main(argv):
    if len(argv) < 2:
        # 注意：不要 print(__doc__) —— docstring 是中文，
        # Windows 控制台是 cp1252，打印中文会抛 UnicodeEncodeError。
        print("usage: verify_package.py <zip|dir>")
        return 2

    target = argv[1]
    if os.path.isdir(target):
        error = _check_dir(target)
    elif zipfile.is_zipfile(target):
        error = _check_windows(target)
    else:
        print("[X] artifact not found: %s" % target)
        return 1

    if error:
        print(error)
        return 1

    print("[OK] package contents verified")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
