#!/bin/zsh
# ============================================================
# 打包成「双击即用」的 Windows 程序 —— 用户不需要装 Python
#   注意：必须在 Windows 上执行（PyInstaller 不能跨平台打包）
#
#   在 Windows 上：
#     git clone ...
#     cd big-water-big-sleep
#     pip install pyinstaller
#     build_windows.bat
#
# 产物：dist\Health Float.exe（单文件，双击即用）
# ============================================================
set -e
cd "$(dirname "$0")"

BUILD_PY="${HEALTH_FLOAT_BUILD_PYTHON:-python}"
VER="$(grep -m1 '^VERSION = ' health_float.py | sed 's/.*"\(.*\)".*/\1/')"

echo "==> 检查构建环境"
if ! "$BUILD_PY" -c "import PyInstaller, tkinter" >/dev/null 2>&1; then
    echo "[X] 需要 PyInstaller 和 tkinter。执行："
    echo "    $BUILD_PY -m pip install pyinstaller"
    exit 1
fi

ABS_DIR="$(cd "$(dirname "$0")" && pwd)"

# CustomTkinter 是可选依赖：装了就打包现代圆角面板，
# 没装也能出包（程序运行时会自动降级到原生 tk 面板）。
HAVE_CTK=0
if "$BUILD_PY" -c "import customtkinter" >/dev/null 2>&1; then
    HAVE_CTK=1
    echo "    [OK] CustomTkinter 已安装 -> 打包现代界面版"
else
    echo "    [!] 未装 CustomTkinter，尝试安装..."
    if "$BUILD_PY" -m pip install --quiet customtkinter >/dev/null 2>&1 \
       && "$BUILD_PY" -c "import customtkinter" >/dev/null 2>&1; then
        HAVE_CTK=1
        echo "    [OK] 安装成功 -> 打包现代界面版"
    else
        echo "    [!] 安装失败 -> 打包降级版（原生 tk 设置面板）"
    fi
fi

CTK_ARGS=(--exclude-module PIL)
if [ "$HAVE_CTK" = "1" ]; then
    CTK_ARGS+=(--collect-data customtkinter)
fi

echo "==> 打包 v${VER}"
# PyInstaller 每次用全新构建目录，避免清理旧目录时出问题
STAMP="$(date +%H%M%S)"
BUILD_DIR="$ABS_DIR/.build/v${VER}-$STAMP"
mkdir -p "$BUILD_DIR"

# --add-data 在 Windows 上用分号分隔：源路径;目标目录
# 用 --onedir 而非 --onefile：启动更快，且杀毒软件误报率低得多
"$BUILD_PY" -m PyInstaller \
    --noconfirm --windowed \
    --name "Health Float" \
    --distpath "$BUILD_DIR/dist" \
    --workpath "$BUILD_DIR/work" \
    --specpath "$BUILD_DIR" \
    --add-data "$ABS_DIR/assets;assets" \
    "${CTK_ARGS[@]}" \
    "$ABS_DIR/health_float.py"

# 复制到 dist/
mkdir -p "$ABS_DIR/dist"
cp -Rf "$BUILD_DIR/dist/Health Float" "$ABS_DIR/dist/"

echo ""
echo "打包完成：dist/Health Float/Health Float.exe"
echo "用户双击即可运行，不需要装 Python。"
echo "分发时请把整个 Health Float 文件夹一起打包成 zip。"
