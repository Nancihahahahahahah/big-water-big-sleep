#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
开发用：把素材的灰底换成卡片色，生成提醒卡专用素材（assets/card_*.png）

为什么需要这一步
----------------
舷窗这张画是画在一片**渐变**灰底上的（顶部 #b8bdc4，底部偏暗），
所以它放在画布上时能完全融进去，看不出是一张图。

但提醒卡要的是「一个整体的框」：整张卡片一个颜色，图和字都在框里。
如果卡片换成别的颜色，这张画就会带着原来那片灰底，
在卡片上显出一个生硬的矩形 —— 又是「两个框」。

抠透明行不通：画的外圈有一大片柔和的光晕和投影，
按颜色抠会把它们一起抠掉、留下一圈毛边（实测过，很难看）。

所以用「按与背景的差值做平滑混合」的方式换色：
  越接近背景的像素（背景本身、渐变、投影）→ 越彻底地换成新底色
  离背景越远的像素（金属圈、云、叶片、光晕）→ 保持原样
中间用 smoothstep 过渡，所以看不到硬边。

关键点：背景是渐变的，不能拿单一颜色当基准。
所以先用四条边拟合一个双线性背景模型，逐像素跟「该位置的背景」
比较 —— 否则底部的暗区换不掉，会留下一条灰带。

跑一次即可，普通用户无需运行（仓库已带生成好的素材）。
需要： pip install pillow
"""

import os
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(HERE, "base.png")

# 过渡宽度：像素与「该位置背景」的 L1 距离小于该值时开始被替换。
# 太大 → 金属圈被拽向背景、轮廓发虚；太小 → 渐变和投影残留成灰边。
# 32 是实测下来两头都还行的值（图片四角与卡片色完全贴合）。
T_MAX = 32

# 色调方案：名称 → 卡片底色
TONES = {
    # 暖色做旧纸：和冷灰蓝的舷窗形成冷暖对比，复古水彩的调子
    "warm": (233, 229, 220),
    # 冷调柔灰：和原素材同色系，只是更浅更柔
    "cool": (221, 226, 231),
}

# 提醒卡左侧舷窗的尺寸（比常驻泡泡略小，给文字腾地方）
SIZES = [
    (106, 146),
]


def _avg(pixels):
    n = len(pixels)
    return tuple(sum(p[i] for p in pixels) / float(n) for i in range(3))


def fit_background(px, w, h):
    """用四条边拟合背景的双线性模型，返回四个角的颜色。

    背景是渐变的（上亮下暗、左右也有微差），
    用单一颜色当基准会把暗区漏掉。
    """
    def corner(pts):
        return _avg(pts)

    tl = corner([px[0, 0], px[1, 0], px[0, 1]])
    tr = corner([px[w - 1, 0], px[w - 1, 1], px[w - 2, 0]])
    bl = corner([px[0, h - 1], px[1, h - 1], px[0, h - 2]])
    br = corner([px[w - 1, h - 1], px[w - 2, h - 1], px[w - 1, h - 2]])
    return tl, tr, bl, br


def _bg_at(corners, x, y, w, h):
    tl, tr, bl, br = corners
    u = x / float(w - 1)
    v = y / float(h - 1)
    top = [tl[i] * (1 - u) + tr[i] * u for i in range(3)]
    bot = [bl[i] * (1 - u) + br[i] * u for i in range(3)]
    return [top[i] * (1 - v) + bot[i] * v for i in range(3)]


def recolor(im, bg_new):
    """把 im 的背景换成 bg_new，返回新的 RGB 图。"""
    im = im.convert("RGB")
    w, h = im.size
    px = im.load()
    corners = fit_background(px, w, h)
    out = Image.new("RGB", (w, h))
    op = out.load()
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            bgr, bgg, bgb = _bg_at(corners, x, y, w, h)
            d = abs(r - bgr) + abs(g - bgg) + abs(b - bgb)
            t = d / float(T_MAX)
            if t > 1.0:
                t = 1.0
            s = t * t * (3 - 2 * t)          # 0=纯背景 1=物体
            op[x, y] = (
                int(r + (bg_new[0] - bgr) * (1 - s)),
                int(g + (bg_new[1] - bgg) * (1 - s)),
                int(b + (bg_new[2] - bgb) * (1 - s)),
            )
    return out


def main():
    base = Image.open(BASE)
    for tone, color in TONES.items():
        for (w, h) in SIZES:
            img = recolor(base, color).resize((w, h), Image.LANCZOS)
            path = os.path.join(HERE, "card_%s_%dx%d.png" % (tone, w, h))
            img.save(path)
            print("card_%s_%dx%d.png  %s" % (tone, w, h, color))
    print("✅ 共 %d 个素材" % (len(TONES) * len(SIZES)))


if __name__ == "__main__":
    main()
