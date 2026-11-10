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
WIN_DIR="$(cygpath -w "$ABS_DIR" 2>/dev/null || echo "$ABS_DIR")"

echo "==> 打包 v${VER}"
rm -rf build dist
"$BUILD_PY" -m PyInstaller \
    --noconfirm --clean --onefile --windowed \
    --name "Health Float" \
    --distpath dist \
    --workpath build \
    --specpath build \
    --add-data "$ABS_DIR/assets;assets" \
    "$ABS_DIR/health_float.py"

echo ""
echo "打包完成：dist/Health Float.exe"
echo "用户双击即可运行，不需要装 Python。"
