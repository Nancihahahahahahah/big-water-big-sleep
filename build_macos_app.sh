#!/bin/zsh
# ============================================================
# 打包成「双击即用」的 macOS 应用 —— 用户不需要装 Python
#
#   ./build_macos_app.sh
#
# 产物：dist/Health Float.app
#   - 自带 Python 运行时（用户机器不用装任何东西）
#   - 自带素材、图标
#   - 双击即可运行；拖进「登录项」即可开机自启
#
# 依赖：pip install pyinstaller（构建机需要；使用者不需要）
#
# 架构说明：优先用 universal2 的 Python（Intel + Apple Silicon 通用）。
# 用单架构 Python 打出来的 app 只能在一种芯片上运行。
# ============================================================
set -e
cd "$(dirname "$0")"

BUILD_PY="${HEALTH_FLOAT_BUILD_PYTHON:-python3}"
OUT="dist"
APP_NAME="Health Float"

echo "==> 检查构建环境"
# 优先用 universal2（Intel + Apple Silicon 通用）的 Python，
# 否则打出来的 app 只能在一种架构上跑。
if [ -z "$HEALTH_FLOAT_BUILD_PYTHON" ]; then
    for CAND in /usr/local/bin/python3 \
                /Library/Frameworks/Python.framework/Versions/Current/bin/python3 \
                python3 /opt/homebrew/bin/python3; do
        if command -v "$CAND" >/dev/null 2>&1 && \
           "$CAND" -c "import tkinter; tkinter.Tk().destroy()" >/dev/null 2>&1; then
            if file "$CAND" 2>/dev/null | grep -q "universal binary"; then
                BUILD_PY="$CAND"
                break
            fi
            # 非 universal 也接受，但要记住这一点
            [ -z "$BUILD_PY" ] && BUILD_PY="$CAND"
        fi
    done
else
    BUILD_PY="$HEALTH_FLOAT_BUILD_PYTHON"
fi

if [ -z "$BUILD_PY" ]; then
    echo "❌ 未找到可用的 Python 3（带 tkinter）。"
    echo "   brew install python-tk   或安装 https://www.python.org/downloads/"
    exit 1
fi
if ! "$BUILD_PY" -c "import PyInstaller" >/dev/null 2>&1; then
    echo "❌ 缺少 PyInstaller。执行： $BUILD_PY -m pip install pyinstaller pillow"
    exit 1
fi
ARCH=$(file "$BUILD_PY" 2>/dev/null | grep -o "universal binary" || echo "单架构")
echo "    构建器 $BUILD_PY  ($ARCH)"

# 目标架构：默认 universal2（Intel Mac + Apple Silicon 通用）。
# 只有构建器本身是 universal2 时才敢这么做，否则会失败。
TARGET_ARCH=""
if [ "$ARCH" = "universal binary" ]; then
    TARGET_ARCH="universal2"
    echo "    目标架构 universal2（Intel + Apple Silicon 通用）"
else
    echo "    ⚠ 构建器不是 universal2，只能出单架构包"
    echo "      想要通用包：装 python.org 官方版 Python（自带 universal2）"
fi

# zsh 的 ${var:+word} 不会按 word 拆词，用数组传参更可靠
ARCH_ARGS=()
if [ -n "$TARGET_ARCH" ]; then
    ARCH_ARGS=(--target-arch "$TARGET_ARCH")
fi

VER="$(grep -m1 '^VERSION = ' health_float.py | sed 's/.*"\(.*\)".*/\1/')"
echo "    版本 v${VER}  构建器 $BUILD_PY"

echo "==> 准备图标"
ICON_DIR="build_assets"
mkdir -p "$ICON_DIR"
# 用 Python 生成一个简洁图标（舷窗：圆角方 + 蓝天 + 白云）
"$BUILD_PY" - <<'PYEOF'
import os
try:
    from PIL import Image, ImageDraw
except ImportError:
    print("    (无 Pillow，跳过图标生成)")
    raise SystemExit(0)

S = 1024
im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(im)
# 机舱外壳（圆角深灰）
d.rounded_rectangle([40, 40, S-40, S-40], radius=190, fill=(178, 189, 196, 255))
# 内圈白框
d.rounded_rectangle([120, 120, S-120, S-120], radius=150, fill=(248, 250, 252, 255))
# 天空
d.rounded_rectangle([180, 180, S-180, S-180], radius=118, fill=(168, 214, 245, 255))
# 渐变感：下方更蓝
for y in range(180, S-180):
    t = (y - 180) / (S - 360)
    r = int(196 - 46 * t); g = int(230 - 26 * t); b = int(250 - 5 * t)
    d.line([(180, y), (S-180, y)], fill=(r, g, b, 255))
# 云
d.ellipse([300, 430, 520, 560], fill=(255, 255, 255, 235))
d.ellipse([420, 390, 640, 540], fill=(255, 255, 255, 235))
d.ellipse([540, 450, 740, 560], fill=(255, 255, 255, 235))
# 底部文字条
d.rounded_rectangle([120, S-260, S-120, S-120], radius=60, fill=(178, 189, 196, 255))
im.save("build_assets/icon.png")
print("    图标已生成")
PYEOF

echo "==> PyInstaller 打包（--windowed 无终端窗口）"
ABS_DIR="$(cd "$(dirname "$0")" && pwd)"
# 每次用全新构建目录，避免 PyInstaller 清理旧目录时被拦截
STAMP="$(date +%H%M%S)"
BUILD_DIR="$ABS_DIR/.build/v${VER}-$STAMP"
mkdir -p "$BUILD_DIR"
# --add-data 的源路径必须是绝对路径（specpath 会改变相对路径的解析基准）
if [ -n "$TARGET_ARCH" ]; then
    "$BUILD_PY" -m PyInstaller \
        --noconfirm --windowed \
        --name "$APP_NAME" \
        --distpath "$BUILD_DIR/dist" \
        --workpath "$BUILD_DIR/work" \
        --specpath "$BUILD_DIR" \
        --add-data "$ABS_DIR/assets:assets" \
        --osx-bundle-identifier com.nancy.healthfloat \
        --target-arch "$TARGET_ARCH" \
        "$ABS_DIR/health_float.py"
else
    "$BUILD_PY" -m PyInstaller \
        --noconfirm --windowed \
        --name "$APP_NAME" \
        --distpath "$BUILD_DIR/dist" \
        --workpath "$BUILD_DIR/work" \
        --specpath "$BUILD_DIR" \
        --add-data "$ABS_DIR/assets:assets" \
        --osx-bundle-identifier com.nancy.healthfloat \
        "$ABS_DIR/health_float.py"
fi

# 把产物复制到 dist/（用 ditto 覆盖，不做批量删除）
mkdir -p "$ABS_DIR/dist"
ditto "$BUILD_DIR/dist/$APP_NAME.app" "$ABS_DIR/dist/$APP_NAME.app"

# 打包后把图标塞进 .app
APP="$ABS_DIR/dist/$APP_NAME.app"
if [ -f "$ICON_DIR/icon.png" ]; then
    # 生成 .icns（macOS 图标格式）
    ICONSET="$ICON_DIR/icon.iconset"
    mkdir -p "$ICONSET"
    for S in 16 32 64 128 256 512; do
        sips -z $S $S "$ICON_DIR/icon.png" --out "$ICONSET/icon_${S}x${S}.png" >/dev/null 2>&1
        D=$((S*2))
        sips -z $D $D "$ICON_DIR/icon.png" --out "$ICONSET/icon_${S}x${S}@2x.png" >/dev/null 2>&1
    done
    iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/icon.icns" 2>/dev/null || true
    /usr/libexec/PlistBuddy -c "Set :CFBundleIconFile icon.icns" "$APP/Contents/Info.plist" 2>/dev/null || true
    echo "    图标已嵌入"
fi

# 在 Info.plist 里写入版本号
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $VER" "$APP/Contents/Info.plist" 2>/dev/null || \
    /usr/libexec/PlistBuddy -c "Add :CFBundleShortVersionString string $VER" "$APP/Contents/Info.plist"

# 去掉 quarantine 标记（本地构建产物，避免自己被拦）
xattr -cr "$APP" 2>/dev/null || true

# 签名（ad-hoc）：让 macOS 允许运行，且第一次打开不用额外操作
codesign --force --deep --sign - "$APP" 2>&1 | tail -1 || echo "    (签名跳过，不影响本机使用)"

SIZE=$(du -sh "$APP" | cut -f1)

# —— 打 DMG（用户下载双击的形式）——
DMG="$ABS_DIR/dist/Health Float.dmg"
DMG_ROOT="$ABS_DIR/.build/dmg-root"
mkdir -p "$DMG_ROOT"
ditto "$APP" "$DMG_ROOT/$APP_NAME.app"
ln -sfn /Applications "$DMG_ROOT/Applications"
hdiutil create -volname "$APP_NAME" -srcfolder "$DMG_ROOT" -ov -format UDZO "$DMG" 2>&1 | tail -1
DMG_SIZE=$(du -sh "$DMG" | cut -f1)

echo ""
echo "✅ 打包完成："
echo "   $APP  (${SIZE})"
echo "   $DMG  (${DMG_SIZE})  ← 发给用户这个"
echo ""
echo "   用户怎么用："
echo "   1. 把这个 Health Float.app 拖到「应用程序」文件夹"
echo "   2. 双击打开（首次运行会弹出设置窗口，选好洗澡/睡觉时间）"
echo "   3. 想开机自动启动：系统设置 → 通用 → 登录项 → 添加这个 app"
