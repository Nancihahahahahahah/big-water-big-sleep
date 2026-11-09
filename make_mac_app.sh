#!/bin/zsh
# 把 Health Float 打包成 macOS App：Health Float.app
# 用法： ./make_mac_app.sh
#   可用环境变量指定 Python（默认取当前 python3）：
#   HEALTH_FLOAT_PYTHON=/path/to/python3 ./make_mac_app.sh
# 打包后双击 app 即可运行；要开机自启，把它加入「系统设置 → 登录项」。

set -e
cd "$(dirname "$0")"

PY="${HEALTH_FLOAT_PYTHON:-$(command -v python3)}"
APP="Health Float.app"

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp health_float.py config.json "$APP/Contents/Resources/"
cp -R assets "$APP/Contents/Resources/assets"

cat > "$APP/Contents/Info.plist" <<'EOF'
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
    <string>1.1</string>
    <key>LSUIElement</key>
    <true/>
</dict>
</plist>
EOF

cat > "$APP/Contents/MacOS/HealthFloat" <<EOF
#!/bin/zsh
DIR="\$(dirname "\$0")/../Resources"
exec "$PY" "\$DIR/health_float.py" >> "\$DIR/float.log" 2>&1
EOF
chmod +x "$APP/Contents/MacOS/HealthFloat"

echo "✅ 已生成 $APP"
echo "   双击运行；开机自启：系统设置 → 通用 → 登录项 → 添加这个 app"
