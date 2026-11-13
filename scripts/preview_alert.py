#!/usr/bin/env python3
"""提醒卡排版预览 —— 渲染真实提醒卡并截图，供肉眼审稿。

用法：
    python3 scripts/preview_alert.py [输出目录]

为什么要这个工具：
    提醒卡的排版问题（行距、字号层级、按钮丢字）肉眼一看就知道，
    但靠读代码改排版等于闭眼调参。有了预览，改一版截一图，对比着改。

为什么不用 canvas.postscript()：
    Ghostscript 渲染不了中文和 emoji，导出的图里字全是空的，
    排版问题反而看不出来。

截图走 macOS 的 Quartz：CGWindowListCreateImage 直抓 layer=19 的
无边框浮窗。两个必须知道的坑：

1. 必须选 layer=19 的浮窗。同进程下还有菜单栏之类的 layer=0 窗口，
   面积可能更大，按面积选会抓错对象。

2. 直抓拿到的是 window server 的合成缓存。窗口刚 resize 过
   （140x241 -> 302x236）时缓存还没刷新，截出来是旧残影 ——
   表现就是「代码里元素明明在，图上就是没有」，非常误导。
   所以先轮询 Quartz 的窗口 bounds，等它报出期望尺寸再截。

（另一条路 screencapture 全屏截图在这里不行：脚本在后台跑时，
无边框窗口不在合成层，截出来是桌面壁纸。）

依赖：pyobjc + Pillow 在 managed venv 里，tkinter 在 managed python 里，
两者用 PYTHONPATH 合并：

    PYTHONPATH=<venv>/lib/python3.13/site-packages \
      <managed python> scripts/preview_alert.py
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import tkinter as tk  # noqa: E402

import health_float as hf  # noqa: E402


def grab_window(root, out_path, expect_size):
    """抓 layer=19 的无边框浮窗并存成 PNG。"""
    try:
        import Quartz
        from AppKit import NSBitmapImageRep
        from io import BytesIO
        from PIL import Image
    except ImportError:
        print("[!] 缺少 pyobjc/Pillow，无法自动截图")
        return False

    # 等窗口服务器的缓存追上 Tk 的实际尺寸
    target = None
    for _ in range(60):
        target = None
        for w in Quartz.CGWindowListCopyWindowInfo(
                Quartz.kCGWindowListOptionAll, Quartz.kCGNullWindowID):
            if w.get("kCGWindowOwnerPID") != os.getpid():
                continue
            if w.get("kCGWindowLayer") != 19:
                continue
            b = w.get("kCGWindowBounds", {})
            if not b.get("Width"):
                continue
            if int(b["Width"]) != expect_size[0]:
                continue
            target = w.get("kCGWindowNumber")
            break
        if target:
            break
        root.update()
        time.sleep(0.05)
    if not target:
        print(f"[X] 没找到宽度 {expect_size[0]} 的浮窗")
        return False

    img = Quartz.CGWindowListCreateImage(
        Quartz.CGRectNull,
        Quartz.kCGWindowListOptionIncludingWindow,
        target,
        Quartz.kCGWindowImageBoundsIgnoreFraming)
    if img is None:
        print("[X] Quartz 拿不到窗口图像")
        return False

    rep = NSBitmapImageRep.alloc().initWithCGImage_(img)
    data = rep.representationUsingType_properties_(4, {})
    Image.open(BytesIO(data)).convert("RGB").save(out_path)
    print(f"[OK] {out_path}")
    return True


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "_preview")
    os.makedirs(out_dir, exist_ok=True)

    root = tk.Tk()
    root.withdraw()

    # 建一个真实的 FloatApp（复用产品代码 ——
    # 复制一份布局就会出现「预览好看、实际很丑」）
    cfg = hf.load_config()
    app = hf.FloatApp(root, cfg)

    root.deiconify()
    try:
        root.attributes("-alpha", 1.0)
    except tk.TclError:
        pass
    # 关键：先按提醒卡的最终尺寸上屏，再切状态。
    # 反过来的话（先以 140x241 的泡泡尺寸上屏，再 resize 到 302x236），
    # 窗口服务器会保留旧尺寸那帧的合成缓存，截图左上角会出现
    # 一块「旧内容残影」—— 看起来像画布没清干净。
    root.geometry(f"{hf.ALERT[0]}x{hf.ALERT[1]}+300+200")
    root.update_idletasks()
    root.update()

    keys = list(hf.ALERT_META.keys())
    results = {}

    def shoot(i):
        if i >= len(keys):
            root.destroy()
            print("\n=== 完成 ===")
            for k, p in results.items():
                print(f"  {k}: {p}")
            return
        key = keys[i]
        # 直接切到该提醒的显示态
        app.current = key
        app.auto_left = hf.ALERT_META[key][3]
        app._resize_to(*hf.ALERT)
        app._layout_alert()
        # 底部提示文字由 _update_auto_hint 填写，不调用的话截图里是空的
        app._update_auto_hint()
        app.cv.update()
        root.update()
        root.update_idletasks()

        def capture():
            path = os.path.join(out_dir, f"alert_{key}.png")
            if grab_window(root, path, (hf.ALERT[0], hf.ALERT[1])):
                results[key] = path
            root.after(150, shoot, i + 1)

        # 延迟一帧再截，给窗口服务器提交重绘的时间
        root.after(400, capture)

    root.after(500, shoot, 0)
    root.mainloop()


if __name__ == "__main__":
    main()
