#!/bin/zsh
# macOS 双击启动
cd "$(dirname "$0")"

# 优先用 python.org 官方 Python（避开系统 tkinter 的兼容 bug）
for PY in python3 /usr/local/bin/python3 /opt/homebrew/bin/python3; do
    if command -v $PY >/dev/null 2>&1; then
        nohup $PY health_float.py >/dev/null 2>&1 &
        disown
        exit 0
    fi
done
echo "未找到 Python 3，请先安装：https://www.python.org/downloads/"
