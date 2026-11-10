@echo off
rem Windows 双击启动（pythonw 不弹黑框）
cd /d "%~dp0"

rem 找一个真的能 import tkinter 的 Python（存在 ≠ 能用）
set "PY="
for %%P in (pythonw.exe) do (
    where %%P >nul 2>nul && (
        %%P -c "import tkinter" >nul 2>nul && set "PY=%%P"
    )
)
if not defined PY (
    for %%P in (python.exe) do (
        where %%P >nul 2>nul && (
            %%P -c "import tkinter" >nul 2>nul && set "PY=%%P"
        )
    )
)

if defined PY (
    start "" %PY% health_float.py
) else (
    echo.
    echo 未找到可用的 Python（缺少 tkinter）。
    echo 请安装官方版本：https://www.python.org/downloads/
    echo 安装时请勾选 "tcl/tk and IDLE" 选项。
    echo.
    pause
)
