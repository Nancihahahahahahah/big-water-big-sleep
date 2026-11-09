@echo off
rem Windows 双击启动（pythonw 不弹黑框）
cd /d "%~dp0"
where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw health_float.py
) else (
    echo 未找到 Python，请先安装：https://www.python.org/downloads/
    pause
)
