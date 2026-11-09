#!/bin/bash
# Linux 启动
cd "$(dirname "$0")"
nohup python3 health_float.py >/dev/null 2>&1 &
disown
