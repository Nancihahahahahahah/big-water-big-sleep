#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
开发用：从 assets/base.png 生成各尺寸预缩放素材（assets/sz_*.png）
运行一次即可，普通用户无需运行（仓库已带生成好的素材）。
需要： pip install pillow
"""

import os
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(HERE, "base.png")

# 尺寸梯度：待机 104x144 → 悬停 168x232（保持原图 342:472 比例）
IDLE = (104, 144)
HOVER = (168, 232)
ALERT_IMG = (132, 182)      # 提醒卡左侧舷窗

STEPS = 12


def main():
    im = Image.open(BASE).convert("RGBA")
    sizes = []
    for i in range(STEPS):
        t = i / (STEPS - 1)
        sizes.append((round(IDLE[0] + t * (HOVER[0] - IDLE[0])),
                      round(IDLE[1] + t * (HOVER[1] - IDLE[1]))))
    if ALERT_IMG not in sizes:
        sizes.append(ALERT_IMG)
    for (w, h) in sizes:
        im.resize((w, h), Image.LANCZOS).save(
            os.path.join(HERE, f"sz_{w}x{h}.png"))
        print(f"sz_{w}x{h}.png")
    print(f"✅ 共 {len(sizes)} 个尺寸")


if __name__ == "__main__":
    main()
