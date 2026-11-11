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

CTK_ARGS=()
if [ "$HAVE_CTK" = "1" ]; then
    CTK_ARGS=(--collect-all customtkinter)
fi

echo "==> 打包 onedir"
rm -rf build dist/HealthFloat
"$BUILD_PY" -m PyInstaller \
    --noconfirm --clean \
    --name HealthFloat \
    --distpath dist \
    --workpath build \
    --specpath build \
    --add-data "$ABS_DIR/assets:assets" \
    "${CTK_ARGS[@]}" \
    "$ABS_DIR/health_float.py"

# PyInstaller onedir 产物目录 = dist/<name>，即 dist/HealthFloat
APPDIR="dist/HealthFloat"
if [ ! -d "$APPDIR" ]; then
    echo "[X] PyInstaller 产物目录不存在：$APPDIR"
    echo "    实际生成的内容："; ls -la dist/ 2>/dev/null || true
    exit 1
fi

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

# 图标（appimagetool 强制要求 Icon= 指向的文件真实存在）
ICON_SRC="assets/app-icon.png"
if [ -f "$ICON_SRC" ]; then
    cp "$ICON_SRC" "$APPDIR/healthfloat.png"
else
    echo "[!] 找不到图标 $ICON_SRC，AppImage 会生成失败"
    exit 1
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
# appimagetool 本身是个 AppImage，CI 里常因没有 FUSE 而跑不起来。
# 用 --appimage-extract-and-run 让它解压后直接运行，绕过 FUSE。
APPIMAGE_TOOL="/tmp/appimagetool"
if [ ! -x "$APPIMAGE_TOOL" ]; then
    echo "    下载 appimagetool ..."
    curl -sSL -o "$APPIMAGE_TOOL" \
        "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage" \
        || { echo "[X] appimagetool 下载失败"; exit 1; }
    chmod +x "$APPIMAGE_TOOL"
fi
# 桌面文件必须是 AppDir 根目录下的 .desktop（appimagetool 的硬性要求）
if ! command -v appimagetool >/dev/null 2>&1; then
    echo "    用 --appimage-extract-and-run 绕过 FUSE"
fi
export APPIMAGE_EXTRACT_AND_RUN=1
"$APPIMAGE_TOOL" --appimage-extract-and-run "$APPDIR" "dist/Health Float.AppImage" 2>&1 | tail -5

if [ ! -f "dist/Health Float.AppImage" ]; then
    echo "[X] AppImage 生成失败"
    exit 1
fi
chmod +x "dist/Health Float.AppImage"
echo ""
echo "打包完成：dist/Health Float.AppImage"
echo "用户 chmod +x 后双击即可运行，不需要装 Python。"
