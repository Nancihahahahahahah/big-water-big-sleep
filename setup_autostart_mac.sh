#!/bin/zsh
# 一键把 Health Float 设为 macOS 开机自启 + 崩溃自动拉活（launchd 托管）
# 用法： ./setup_autostart_mac.sh    取消自启： launchctl bootout gui/$UID/com.nancy.health-float

set -e
cd "$(dirname "$0")"

PY="${HEALTH_FLOAT_PYTHON:-$(command -v python3)}"
APP="$(pwd)/health_float.py"
PLIST_DIR="$HOME/Library/LaunchAgents"
PLIST="$PLIST_DIR/com.nancy.health-float.plist"
LOG="$(pwd)/float.log"

mkdir -p "$PLIST_DIR"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.nancy.health-float</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PY</string>
        <string>$APP</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$LOG</string>
    <key>StandardErrorPath</key>
    <string>$LOG</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)/com.nancy.health-float" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"

echo "✅ 已安装并启动：开机自启 + 崩溃自动拉活"
echo "   日志: $LOG"
echo "   取消自启: launchctl bootout gui/\$(id -u)/com.nancy.health-float && rm $PLIST"
