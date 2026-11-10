#!/bin/zsh
# 把 Health Float 打包成 macOS App：Health Float.app
# 用法： ./make_mac_app.sh
#   可用环境变量指定 Python（默认自动找一个 tkinter 可用的）：
#   HEALTH_FLOAT_PYTHON=/path/to/python3 ./make_mac_app.sh
# 打包后双击 app 即可运行；要开机自启，把它加入「系统设置 → 登录项」。
#
# 注意：用户配置不在 app 包里，而是存在
#   ~/Library/Application Support/HealthFloat/config.json
# 所以重新打包/升级不会冲掉你的设置。

set -e
cd "$(dirname "$0")"

APP="Health Float.app"

# —— 选一个 tkinter 真能用的 Python ——
PY="${HEALTH_FLOAT_PYTHON:-}"
if [ -z "$PY" ]; then
    for CAND in python3 /opt/homebrew/bin/python3 /usr/local/bin/python3 \
                /usr/bin/python3 \
                /Library/Frameworks/Python.framework/Versions/Current/bin/python3; do
        if command -v "$CAND" >/dev/null 2>&1 && \
           "$CAND" -c "import tkinter; tkinter.Tk().destroy()" >/dev/null 2>&1; then
            PY="$CAND"
            break
        fi
    done
fi
if [ -z "$PY" ]; then
    echo "❌ 未找到带 tkinter 的 Python 3。"
    echo "   brew install python-tk   或安装 https://www.python.org/downloads/"
    exit 1
fi

# 版本号从代码里读，避免两处维护不同步
VER="$(grep -m1 '^VERSION = ' health_float.py | sed 's/.*"\(.*\)".*/\1/')"

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp health_float.py "$APP/Contents/Resources/"
cp -R assets "$APP/Contents/Resources/assets"
# 注意：故意不复制 config.json —— 配置存用户目录，这里不碰

cat > "$APP/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleIdentifier</key>
    <string>com.nancy.health-float</string>
    <key>CFBundleName</key>
    <string>Health Float</string>
    <key>CFBundleExecutable</key>
    <string>HealthFloat</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>${VER}</string>
    <key>CFBundleVersion</key>
    <string>${VER}</string>
    <key>LSUIElement</key>
    <true/>
</dict>
</plist>
EOF

cat > "$APP/Contents/MacOS/HealthFloat" <<EOF
#!/bin/zsh
DIR="\$(dirname "\$0")/../Resources"
LOG="\$HOME/Library/Application Support/HealthFloat/health_float.log"
mkdir -p "\$(dirname "\$LOG")"
exec "$PY" "\$DIR/health_float.py" >> "\$LOG" 2>&1
EOF
chmod +x "$APP/Contents/MacOS/HealthFloat"

echo "✅ 已生成 $APP (v${VER})"
echo "   双击运行；开机自启：系统设置 → 通用 → 登录项 → 添加这个 app"
echo "   配置位置：~/Library/Application Support/HealthFloat/config.json"
