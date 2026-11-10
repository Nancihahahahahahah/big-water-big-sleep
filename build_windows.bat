@echo off
rem Windows 双击打包 —— 生成 dist\Health Float\Health Float.exe
rem 用户拿到后双击即可运行，不需要装 Python
cd /d "%~dp0"

echo == 检查构建环境 ==
python -c "import PyInstaller, tkinter" >nul 2>nul
if errorlevel 1 (
    echo 需要 PyInstaller。正在安装...
    python -m pip install pyinstaller
    python -c "import PyInstaller, tkinter" >nul 2>nul
    if errorlevel 1 (
        echo [X] 仍然缺少 PyInstaller 或 tkinter
        echo     请安装官方 Python: https://www.python.org/downloads/
        echo     安装时务必勾选 "tcl/tk and IDLE"
        pause
        exit /b 1
    )
)

echo == 打包中（首次约 1-2 分钟）==
set "STAMP=%RANDOM%%RANDOM%"
set "BUILDDIR=%CD%\.build\v%STAMP%"
mkdir "%BUILDDIR%" 2>nul

python -m PyInstaller --noconfirm --windowed ^
    --name "Health Float" ^
    --distpath "%BUILDDIR%\dist" ^
    --workpath "%BUILDDIR%\work" ^
    --specpath "%BUILDDIR%" ^
    --add-data "%CD%\assets;assets" ^
    "%CD%\health_float.py"

if errorlevel 1 (
    echo [X] 打包失败
    pause
    exit /b 1
)

echo == 复制产物 ==
if not exist dist mkdir dist
xcopy /E /I /Y "%BUILDDIR%\dist\Health Float" "dist\Health Float" >nul

echo.
echo 打包完成：dist\Health Float\Health Float.exe
echo 把整个 dist\Health Float 文件夹压缩成 zip 就能发给别人了。
echo.
pause
