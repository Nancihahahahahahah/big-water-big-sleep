#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
开发用：从 assets/base.png 生成固定尺寸素材（assets/sz_*.png）
运行一次即可，普通用户无需运行（仓库已带生成好的素材）。
需要： pip install pillow
"""

import os
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(HERE, "base.png")

# 固定尺寸（应用不缩放，只用这两档）
SIZES = [
    (140, 193),   # 常驻泡泡
    (132, 182),   # 提醒卡左侧舷窗
]


def main():
    im = Image.open(BASE).convert("RGBA")
    for (w, h) in SIZES:
        im.resize((w, h), Image.LANCZOS).save(
            os.path.join(HERE, f"sz_{w}x{h}.png"))
        print(f"sz_{w}x{h}.png")
    print(f"✅ 共 {len(SIZES)} 个尺寸")


if __name__ == "__main__":
    main()
