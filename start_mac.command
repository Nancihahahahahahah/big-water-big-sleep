#!/bin/zsh
# macOS 双击启动
cd "$(dirname "$0")"

# 找一个「真的能用 tkinter」的 Python。
# 注意：不能只看 `command -v python3` —— macOS 自带的和 Homebrew 装的
# 都可能缺 tkinter（前者版本不兼容崩溃，后者需要单独 brew install python-tk）。
# 所以必须实际建一次窗口来验证。
for PY in python3 /opt/homebrew/bin/python3 /usr/local/bin/python3 \
          /usr/bin/python3 /Library/Frameworks/Python.framework/Versions/Current/bin/python3; do
    if command -v "$PY" >/dev/null 2>&1; then
        if "$PY" -c "import tkinter; tkinter.Tk().destroy()" >/dev/null 2>&1; then
            nohup "$PY" health_float.py >/dev/null 2>&1 &
            disown
            exit 0
        fi
    fi
done

echo "未找到可用的 Python 3（缺少 tkinter）。"
echo "请安装其中一种："
echo "  · brew install python-tk       # Homebrew Python"
echo "  · https://www.python.org/downloads/  # python.org 官方版（自带 tkinter）"
echo ""
read "?按回车键关闭…"
