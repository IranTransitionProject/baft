#!/usr/bin/env bash
# Uninstall the ITP Telegram launchd agent.
#
# Unloads com.itp.telegram from launchd and removes the plist. Does NOT
# touch the DuckDB store, the Telethon session file, or ~/.heddle/.env.
#
# Usage:
#   bash deploy/macos/uninstall.sh
set -euo pipefail

LABEL="com.itp.telegram"
PLIST_PATH="$HOME/Library/LaunchAgents/${LABEL}.plist"
PID_PATH="$HOME/.heddle/itp_telegram.pid"

echo "=== ITP Telegram launchd uninstaller ==="

if launchctl list 2>/dev/null | grep -q "$LABEL"; then
    echo "  unloading $LABEL..."
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
fi

if [ -f "$PLIST_PATH" ]; then
    rm -f "$PLIST_PATH"
    echo "  removed plist: $PLIST_PATH"
fi

# Clean PID file if the unload killed the process
sleep 2
if [ -f "$PID_PATH" ]; then
    PID=$(cat "$PID_PATH" 2>/dev/null || echo "")
    if [ -z "$PID" ] || ! kill -0 "$PID" 2>/dev/null; then
        rm -f "$PID_PATH"
        echo "  removed stale PID file"
    fi
fi

echo ""
echo "Uninstalled. Preserved: ~/.heddle/.env, ~/.heddle/telegram.session,"
echo "~/.heddle/itp_rag.duckdb, ~/.heddle/itp_telegram.log"
