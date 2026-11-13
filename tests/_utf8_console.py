#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试共用的环境修正。

**为什么需要它**

Windows 控制台默认编码是 cp1252（GBK 之外的西欧代码页），
打印中文字符会抛：

    UnicodeEncodeError: 'charmap' codec can't encode characters ...

unittest 在**测试失败**时会把断言消息写到 stderr —— 而我们的断言
消息全是中文（「齿轮没画出来」「副标题贴着标题了」……）。
于是出现一个非常糟糕的情况：

    测试失败  →  打印失败详情时崩溃  →  变成 ERROR  →  真正的失败原因被淹没

本地 macOS / Linux 是 UTF-8，永远看不到这个问题；只有 Windows CI 会炸。

**解法**：在测试模块被导入时，把 stdout/stderr 重配成 UTF-8，
并对无法编码的字符降级处理（errors="replace"）而不是抛异常。

用法：每个测试文件顶部加一行

    import _utf8_console  # noqa: F401
"""
import io
import os
import sys


def _reconfigure(stream, name):
    """把一个文本流重配成 UTF-8，且不因编码失败而抛异常。"""
    if stream is None:
        return
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
        return
    except (AttributeError, ValueError, io.UnsupportedOperation):
        pass
    # 老版本 Python 没有 reconfigure，退回包一层
    try:
        buf = stream.buffer
    except AttributeError:
        return
    wrapper = io.TextIOWrapper(buf, encoding="utf-8", errors="replace",
                               line_buffering=True)
    setattr(sys, name, wrapper)


# Windows 上 GitHub Actions 的控制台本身可能是 cp1252，
# 还要把 Python 的 I/O 编码切到 UTF-8，避免读写文件时也出问题。
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

_reconfigure(sys.stdout, "stdout")
_reconfigure(sys.stderr, "stderr")
