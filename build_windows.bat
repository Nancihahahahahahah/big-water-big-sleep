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

echo == 检查 CustomTkinter（可选，装了才有现代界面）==
python -c "import customtkinter" >nul 2>nul
if errorlevel 1 (
    echo 未安装 CustomTkinter，正在安装...
    python -m pip install --quiet customtkinter >nul 2>nul
    python -c "import customtkinter" >nul 2>nul
    if errorlevel 1 (
        echo [!] 安装失败，将打包降级版（原生 tk 设置面板，功能一致）
        set "CTKARG="
    ) else (
        echo [OK] 安装成功，将打包现代界面版
        set "CTKARG=--collect-all customtkinter"
    )
) else (
    echo [OK] CustomTkinter 已安装，将打包现代界面版
    set "CTKARG=--collect-all customtkinter"
)

echo == 打包中（首次约 1-2 分钟）==
set "STAMP=%RANDOM%%RANDOM%"
set "BUILDDIR=%CD%\.build\v%STAMP%"
mkdir "%BUILDDIR%" 2>nul

rem --exclude-module PIL：CTK 的 ctk_image.py 会 from PIL import Image，
rem 把整个 Pillow 拖进来；Pillow 的编译扩展是单架构二进制，
rem 打包时会失败。本项目用 tk.PhotoImage 读 PNG，不需要 PIL。
python -m PyInstaller --noconfirm --windowed ^
    --name "Health Float" ^
    --distpath "%BUILDDIR%\dist" ^
    --workpath "%BUILDDIR%\work" ^
    --specpath "%BUILDDIR%" ^
    --add-data "%CD%\assets;assets" ^
    %CTKARG% ^
    --exclude-module PIL ^
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
