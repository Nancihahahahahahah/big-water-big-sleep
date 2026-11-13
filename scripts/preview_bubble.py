#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""常驻泡泡（浮窗常态）排版预览 —— 渲染真实泡泡并截图。

用法：
    python3 scripts/preview_bubble.py [输出目录]

为什么需要这个工具：
    提醒卡改版时动了齿轮尺寸和强调色 —— 这两样常驻泡泡上也有。
    只看提醒卡的截图会漏掉「常驻浮窗被改坏了」这类问题。
    提醒卡和泡泡是同一个窗口的两个状态，必须一起审。

截图实现与 preview_alert.py 完全一致（复用它的 grab_window），
踩过的坑都在那里注释着：必须抓 layer=19 的浮窗、
必须等窗口服务器追上 Tk 的实际尺寸。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import tkinter as tk  # noqa: E402

import health_float as hf  # noqa: E402
from preview_alert import grab_window  # noqa: E402


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "_preview")
    os.makedirs(out_dir, exist_ok=True)

    root = tk.Tk()
    root.withdraw()

    cfg = hf.load_config()
    app = hf.FloatApp(root, cfg)

    root.deiconify()
    try:
        root.attributes("-alpha", 1.0)
    except tk.TclError:
        pass
    # 先按泡泡的最终尺寸上屏，再切状态（和提醒卡同一个坑）
    root.geometry(f"{hf.BUBBLE[0]}x{hf.BUBBLE[1]}+300+200")
    root.update_idletasks()
    root.update()

    app.current = None
    app._resize_to(*hf.BUBBLE)
    app._layout_bubble()
    app.cv.update()
    root.update()
    root.update_idletasks()

    def capture():
        path = os.path.join(out_dir, "bubble.png")
        if grab_window(root, path, (hf.BUBBLE[0], hf.BUBBLE[1])):
            print("[OK] %s" % path)
        root.destroy()

    root.after(500, capture)
    root.mainloop()


if __name__ == "__main__":
    main()
