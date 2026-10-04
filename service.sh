#!/usr/bin/env bash
# ==============================================================================
# TG-Voicer Service Manager (macOS / Linux)
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON_BIN="python3"
if ! command -v python3 &>/dev/null; then
    echo "❌ Error: python3 not found in PATH!"
    exit 1
fi

PLIST_NAME="com.iwsen.tg-voicer.plist"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_NAME"

case "$1" in
    start)
        echo "🚀 Starting TG-Voicer daemon in background..."
        $PYTHON_BIN main.py --daemon "${@:2}"
        ;;
    stop)
        echo "🛑 Stopping TG-Voicer daemon..."
        $PYTHON_BIN main.py --stop
        ;;
    restart)
        echo "🔄 Restarting TG-Voicer daemon..."
        $PYTHON_BIN main.py --restart "${@:2}"
        ;;
    status)
        $PYTHON_BIN main.py --status
        ;;
    logs)
        $PYTHON_BIN main.py --logs -f
        ;;
    install-macos)
        echo "🍏 Installing TG-Voicer LaunchAgent for macOS (autostart on login)..."
        mkdir -p "$HOME/Library/LaunchAgents"
        PYTHON_PATH=$(which python3)
        cat <<EOF > "$PLIST_PATH"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.iwsen.tg-voicer</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON_PATH</string>
        <string>$SCRIPT_DIR/main.py</string>
        <string>--daemon-worker</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$SCRIPT_DIR</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$SCRIPT_DIR/data/voicer.log</string>
    <key>StandardErrorPath</key>
    <string>$SCRIPT_DIR/data/voicer.log</string>
</dict>
</plist>
EOF
        launchctl unload "$PLIST_PATH" 2>/dev/null || true
        launchctl load "$PLIST_PATH"
        echo "✅ LaunchAgent installed and loaded: $PLIST_PATH"
        echo "Check status: launchctl list | grep tg-voicer"
        echo "Stream logs:  tail -f data/voicer.log"
        ;;
    uninstall-macos)
        echo "🍏 Removing LaunchAgent for macOS..."
        if [ -f "$PLIST_PATH" ]; then
            launchctl unload "$PLIST_PATH" 2>/dev/null || true
            rm -f "$PLIST_PATH"
            echo "✅ LaunchAgent uninstalled."
        else
            echo "ℹ️ LaunchAgent not found."
        fi
        ;;
    *)
        echo "Usage: ./service.sh {start|stop|restart|status|logs|install-macos|uninstall-macos}"
        echo ""
        echo "Commands:"
        echo "  start           — Start in background (daemon mode)"
        echo "  stop            — Stop running background daemon"
        echo "  restart         — Restart background daemon"
        echo "  status          — Check status and metrics"
        echo "  logs            — Follow logs in real time (tail -f)"
        echo "  install-macos   — Setup autostart on macOS login (LaunchAgent)"
        echo "  uninstall-macos — Remove macOS autostart"
        exit 1
        ;;
esac
