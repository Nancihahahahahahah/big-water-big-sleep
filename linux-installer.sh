#!/bin/bash
# ============================================================
# 打包 Linux AppImage —— 用户不需要装 Python
#   依赖：pip install pyinstaller
#   可选：sudo apt install desktop-file-utils fuse libfuse2
#
# 产物：dist/Health Float.AppImage
# ============================================================
set -e
cd "$(dirname "$0")"

BUILD_PY="${HEALTH_FLOAT_BUILD_PYTHON:-python3}"
APP_NAME="Health Float"

echo "==> 检查环境"
if ! "$BUILD_PY" -c "import PyInstaller, tkinter" >/dev/null 2>&1; then
    echo "[X] 需要 PyInstaller 和 tkinter。执行：$BUILD_PY -m pip install pyinstaller python3-tk"
    exit 1
fi

ABS_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "==> 打包 onedir"
rm -rf build dist/HealthFloat.AppDir
"$BUILD_PY" -m PyInstaller \
    --noconfirm --clean \
    --name HealthFloat \
    --distpath dist \
    --workpath build \
    --specpath build \
    --add-data "$ABS_DIR/assets:assets" \
    "$ABS_DIR/health_float.py"

APPDIR="dist/HealthFloat.AppDir"

# desktop 文件
cat > "$APPDIR/healthfloat.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Health Float
Name[zh_CN]=大水大睡大健康
Comment=永远置顶的桌面健康小浮窗
Exec=HealthFloat
Icon=healthfloat
Terminal=false
Categories=Utility;
EOF

# 图标
if [ -f build_assets/icon.png ]; then
    cp build_assets/icon.png "$APPDIR/healthfloat.png"
fi

# AppDir 内的启动脚本
cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
export LD_LIBRARY_PATH="$HERE:${LD_LIBRARY_PATH}"
exec "$HERE/HealthFloat" "$@"
EOF
chmod +x "$APPDIR/AppRun"

echo "==> 生成 AppImage"
if ! command -v appimagetool >/dev/null 2>&1; then
    echo "    下载 appimagetool ..."
    curl -sSL -o /tmp/appimagetool \
        "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage" \
        || { echo "[X] appimagetool 下载失败"; exit 1; }
    chmod +x /tmp/appimagetool
fi
/tmp/appimagetool "$APPDIR" "dist/Health Float.AppImage" 2>&1 | tail -3 || \
    cp /tmp/appimagetool "dist/Health Float.AppImage"

chmod +x "dist/Health Float.AppImage"
echo ""
echo "打包完成：dist/Health Float.AppImage"
echo "用户 chmod +x 后双击即可运行，不需要装 Python。"
