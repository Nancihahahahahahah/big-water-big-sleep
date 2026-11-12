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
# 选解释器的规则（按优先级）：
#   1. HEALTH_FLOAT_BUILD_PYTHON（显式指定，最高优先）
#   2. PATH 里的 python3 —— CI 上 setup-python 装的就是它，依赖已就位
#   3. universal2 的候选（Intel + Apple Silicon 通用）
# 硬性要求：必须同时能 import tkinter 和 PyInstaller。
# （只检查 tkinter 会挑到系统 Python —— 它有 tkinter 但没 PyInstaller）
if [ -n "$HEALTH_FLOAT_BUILD_PYTHON" ]; then
    BUILD_PY="$HEALTH_FLOAT_BUILD_PYTHON"
else
    BUILD_PY=""
    for CAND in python3 \
                /usr/local/bin/python3 \
                /Library/Frameworks/Python.framework/Versions/Current/bin/python3 \
                /opt/homebrew/bin/python3; do
        command -v "$CAND" >/dev/null 2>&1 || continue
        "$CAND" -c "import tkinter, PyInstaller; tkinter.Tk().destroy()" \
            >/dev/null 2>&1 || continue
        BUILD_PY="$CAND"
        # universal2 优先：能出 Intel + Apple Silicon 通用的包
        if file "$CAND" 2>/dev/null | grep -q "universal binary"; then
            break
        fi
    done
fi

if [ -z "$BUILD_PY" ]; then
    echo "❌ 未找到同时具备 tkinter 和 PyInstaller 的 Python。"
    echo "   pip install pyinstaller customtkinter"
    echo "   （或用 HEALTH_FLOAT_BUILD_PYTHON=/path/to/python3 指定）"
    exit 1
fi
if ! "$BUILD_PY" -c "import PyInstaller" >/dev/null 2>&1; then
    echo "❌ 缺少 PyInstaller。执行： $BUILD_PY -m pip install pyinstaller customtkinter"
    exit 1
fi
ARCH=$(file "$BUILD_PY" 2>/dev/null | grep -o "universal binary" || echo "单架构")
echo "    构建器 $BUILD_PY  ($ARCH)"

# CustomTkinter 是可选依赖：装了就打包现代圆角面板，
# 没装也能出包（程序运行时会自动降级到原生 tk 面板）。
# 这里主动尝试装一次 —— 装不上不阻断构建。
HAVE_CTK=0
if "$BUILD_PY" -c "import customtkinter" >/dev/null 2>&1; then
    HAVE_CTK=1
    echo "    ✓ CustomTkinter 已安装 → 打包现代界面版"
else
    echo "    ⚠ 未装 CustomTkinter，尝试安装..."
    if "$BUILD_PY" -m pip install --quiet customtkinter >/dev/null 2>&1 \
       && "$BUILD_PY" -c "import customtkinter" >/dev/null 2>&1; then
        HAVE_CTK=1
        echo "    ✓ 安装成功 → 打包现代界面版"
    else
        echo "    ⚠ 安装失败 → 打包降级版（设置面板为原生 tk 界面）"
    fi
fi

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
# 优先用仓库里已提交的图标（assets/app-icon.png，跟 Linux 打包共用同一份）；
# 没有才用 Pillow 现场生成一个。
if [ -f "assets/app-icon.png" ]; then
    cp "assets/app-icon.png" "$ICON_DIR/icon.png"
    echo "    使用仓库内图标 assets/app-icon.png"
else
    # 兜底：仓库里没有图标时才现场生成。
    # 注意 Pillow 的编译扩展是单架构的，universal2 打包时不能进包
    # （见下面 CTK_ARGS 的注释）—— 所以这里只在**构建期**用一下，
    # 生成完的 PNG 是纯数据，进包没问题。
    "$BUILD_PY" - <<'PYEOF'
import os
try:
    from PIL import Image, ImageDraw
except ImportError:
    print("    [!] 无 Pillow 且仓库内也没有 assets/app-icon.png —— 无法生成图标")
    print("        pip install pillow，或把一张 1024x1024 PNG 放到 assets/app-icon.png")
    raise SystemExit(1)

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
fi

echo "==> PyInstaller 打包（--windowed 无终端窗口）"
ABS_DIR="$(cd "$(dirname "$0")" && pwd)"
# 每次用全新构建目录，避免 PyInstaller 清理旧目录时被拦截
STAMP="$(date +%H%M%S)"
BUILD_DIR="$ABS_DIR/.build/v${VER}-$STAMP"
mkdir -p "$BUILD_DIR"
# --add-data 的源路径必须是绝对路径（specpath 会改变相对路径的解析基准）
# CTK 参数只在装了 customtkinter 时才加 —— 没装的话 PyInstaller
# 会因为找不到模块直接报错。
#
# --exclude-module PIL 是必须的，不是可选优化：
# CustomTkinter 的 ctk_image.py 会 `from PIL import Image, ImageTk`，
# 于是 PyInstaller 把整个 Pillow 拉进来。而 Pillow 的编译扩展
# （_avif.so 等）是**单架构**二进制，universal2 构建时 PyInstaller
# 要把它转成双架构，直接报错：
#   IncompatibleBinaryArchError: PIL/_avif.cpython-312-darwin.so
#   is not a fat binary!
#
# 本项目根本不需要 PIL：图片一律用 tk.PhotoImage 读 PNG。
# CTK 那边 PIL 是 try/except 包着的软依赖，排除后照常工作
# （已验证：排除 PIL 后 CTK 面板正常渲染，主题正常加载）。
CTK_ARGS=(--exclude-module PIL)
if [ "$HAVE_CTK" = "1" ]; then
    CTK_ARGS+=(--collect-all customtkinter)
fi
if [ -n "$TARGET_ARCH" ]; then
    "$BUILD_PY" -m PyInstaller \
        --noconfirm --windowed \
        --name "$APP_NAME" \
        --distpath "$BUILD_DIR/dist" \
        --workpath "$BUILD_DIR/work" \
        --specpath "$BUILD_DIR" \
        --add-data "$ABS_DIR/assets:assets" \
        "${CTK_ARGS[@]}" \
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
        "${CTK_ARGS[@]}" \
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
