#!/usr/bin/env bash
# Install the ITP Telegram capture + MCP service as a macOS launchd agent.
#
# Generates a plist at ~/Library/LaunchAgents/com.itp.telegram.plist that
# runs `baft itp-telegram serve` under the user's login session. The service
# auto-starts at login (RunAtLoad), restarts on crash, and stops cleanly on
# `baft itp-telegram stop` (KeepAlive treats exit code 0 as a deliberate stop).
#
# Prerequisites:
#   - ~/.heddle/.env populated with TELEGRAM_API_*, LM_STUDIO_URL (mode 600).
#   - ~/.heddle/telegram.session present (run `baft itp-telegram auth` first).
#   - LM Studio running at the URL in .env (default http://localhost:1234/v1).
#   - The `baft` binary on PATH (typically ~/.local/bin/baft from the
#     symlink to baft/.venv/bin/baft).
#
# Usage:
#   bash deploy/macos/install.sh
#   bash deploy/macos/install.sh --baft /full/path/to/baft   # override binary
#
# Logs:    ~/.heddle/itp_telegram.log
# Status:  baft itp-telegram daemon status
# Stop:    baft itp-telegram daemon uninstall  (or `baft itp-telegram stop`)
set -euo pipefail

LABEL="com.itp.telegram"
PLIST_DIR="$HOME/Library/LaunchAgents"
PLIST_PATH="$PLIST_DIR/${LABEL}.plist"
LOG_PATH="$HOME/.heddle/itp_telegram.log"
PID_PATH="$HOME/.heddle/itp_telegram.pid"
ENV_PATH="$HOME/.heddle/.env"

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

BAFT_BIN=""
WORKING_DIR=""
while [ $# -gt 0 ]; do
    case "$1" in
        --baft) BAFT_BIN="$2"; shift 2 ;;
        --working-dir) WORKING_DIR="$2"; shift 2 ;;
        -h|--help)
            sed -n '2,30p' "$0" | sed 's/^# \?//'
            exit 0
            ;;
        *) echo "Unknown arg: $1" >&2; exit 2 ;;
    esac
done

# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------

echo "=== ITP Telegram launchd installer ==="

if [ -z "$BAFT_BIN" ]; then
    BAFT_BIN=$(command -v baft 2>/dev/null || echo "$HOME/.local/bin/baft")
fi
if [ ! -x "$BAFT_BIN" ]; then
    echo "ERROR: baft binary not found at '$BAFT_BIN'." >&2
    echo "  Either symlink baft/.venv/bin/baft into ~/.local/bin or pass --baft <path>." >&2
    exit 1
fi
echo "  baft binary: $BAFT_BIN"

# ---------------------------------------------------------------------------
# TCC pre-check: macOS Sequoia restricts launchd-spawned processes from
# reading external volumes (anything under /Volumes/) without an explicit
# Full Disk Access grant on the binary that gets exec'd. We probe the real
# situation by spawning a one-shot launchd job that runs the venv's actual
# python interpreter and tries to read pyvenv.cfg — exactly what the agent
# would do at startup. If the probe fails, refuse with actionable workarounds.
# Skip the probe entirely with --skip-tcc-check (use at your own risk).
# ---------------------------------------------------------------------------

REAL_BAFT=$(python3 -c "import os; print(os.path.realpath('$BAFT_BIN'))" 2>/dev/null || echo "$BAFT_BIN")
VENV_PYTHON_LINK=$(dirname "$REAL_BAFT")/python3
REAL_VENV_PYTHON=$(python3 -c "import os; print(os.path.realpath('$VENV_PYTHON_LINK'))" 2>/dev/null || echo "$VENV_PYTHON_LINK")
PYVENV_CFG="$(dirname "$(dirname "$REAL_BAFT")")/pyvenv.cfg"

if [ "${SKIP_TCC_CHECK:-0}" != "1" ]; then
    PROBE_LABEL="com.itp.tcc-probe.$$"
    PROBE_PLIST="/tmp/${PROBE_LABEL}.plist"
    PROBE_LOG="/tmp/${PROBE_LABEL}.log"
    rm -f "$PROBE_LOG"
    cat > "$PROBE_PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PROBE_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${REAL_VENV_PYTHON}</string>
        <string>-c</string>
        <string>open('${PYVENV_CFG}').read(); print('TCC_OK')</string>
    </array>
    <key>StandardOutPath</key>
    <string>${PROBE_LOG}</string>
    <key>StandardErrorPath</key>
    <string>${PROBE_LOG}</string>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
EOF
    launchctl load "$PROBE_PLIST" 2>/dev/null
    # Wait up to 5s for the probe to finish writing
    for _ in 1 2 3 4 5; do
        sleep 1
        grep -q "TCC_OK\|Permission" "$PROBE_LOG" 2>/dev/null && break
    done
    launchctl unload "$PROBE_PLIST" 2>/dev/null
    PROBE_OK=0
    grep -q "TCC_OK" "$PROBE_LOG" 2>/dev/null && PROBE_OK=1
    rm -f "$PROBE_PLIST" "$PROBE_LOG"

    if [ "$PROBE_OK" = "1" ]; then
        echo "  TCC probe:   passed (launchd can read venv via $REAL_VENV_PYTHON)"
    else
        echo "" >&2
        echo "ERROR: TCC probe failed — launchd-spawned python can't read:" >&2
        echo "  $PYVENV_CFG" >&2
        echo "" >&2
        echo "macOS Sequoia restricts launchd-spawned processes from reading" >&2
        echo "external volumes (anything under /Volumes/) without an explicit" >&2
        echo "Full Disk Access grant on the exec'd binary. The agent would" >&2
        echo "crash on startup. Three options:" >&2
        echo "" >&2
        echo "  (A) Use the nohup-based detached daemon instead:" >&2
        echo "      baft itp-telegram daemon start" >&2
        echo "      (works today; needs manual restart after reboot/logout)" >&2
        echo "" >&2
        echo "  (B) Grant Full Disk Access to the venv's python interpreter:" >&2
        echo "      $REAL_VENV_PYTHON" >&2
        echo "      via System Settings > Privacy & Security > Full Disk Access" >&2
        echo "      (Cmd+Shift+G in the picker, then paste the path)." >&2
        echo "      Then re-run this installer." >&2
        echo "" >&2
        echo "  (C) Move the project to an internal-disk path (e.g. ~/Developer/)" >&2
        echo "      and re-run install." >&2
        echo "" >&2
        echo "  Override (advanced): SKIP_TCC_CHECK=1 bash deploy/macos/install.sh" >&2
        echo "" >&2
        exit 1
    fi
fi

if [ ! -f "$ENV_PATH" ]; then
    echo "ERROR: $ENV_PATH not found. Create it (chmod 600) before installing." >&2
    exit 1
fi
echo "  env file:    $ENV_PATH"

# Working directory — defaults to baft repo root (sibling of script's dir).
if [ -z "$WORKING_DIR" ]; then
    SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
    WORKING_DIR=$(cd "$SCRIPT_DIR/../.." && pwd)
fi
echo "  working dir: $WORKING_DIR"

mkdir -p "$PLIST_DIR"
mkdir -p "$(dirname "$LOG_PATH")"

# ---------------------------------------------------------------------------
# Stop and unload any existing instance (idempotent)
# ---------------------------------------------------------------------------

if launchctl list 2>/dev/null | grep -q "$LABEL"; then
    echo "  unloading existing $LABEL agent..."
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
fi

# Clean stale PID file (from a manually-launched daemon that died)
if [ -f "$PID_PATH" ]; then
    OLD_PID=$(cat "$PID_PATH" 2>/dev/null || echo "")
    if [ -n "$OLD_PID" ] && ! kill -0 "$OLD_PID" 2>/dev/null; then
        echo "  removing stale PID file (pid $OLD_PID is dead)"
        rm -f "$PID_PATH"
    fi
fi

# ---------------------------------------------------------------------------
# Generate plist
# ---------------------------------------------------------------------------

cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${LABEL}</string>

    <key>ProgramArguments</key>
    <array>
        <string>${BAFT_BIN}</string>
        <string>itp-telegram</string>
        <string>serve</string>
        <string>--flush-interval</string>
        <string>300</string>
    </array>

    <key>WorkingDirectory</key>
    <string>${WORKING_DIR}</string>

    <key>RunAtLoad</key>
    <true/>

    <!-- Restart on crash, but NOT on a clean exit (so `baft itp-telegram stop`
         actually stops the daemon instead of triggering an instant restart). -->
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>

    <key>ThrottleInterval</key>
    <integer>30</integer>

    <key>StandardOutPath</key>
    <string>${LOG_PATH}</string>
    <key>StandardErrorPath</key>
    <string>${LOG_PATH}</string>

    <!-- PYTHONUNBUFFERED=1 keeps line-buffered logs even when stdout isn't a tty. -->
    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONUNBUFFERED</key>
        <string>1</string>
    </dict>

    <!-- Don't lower priority — capture is latency-sensitive (live MTProto stream). -->
    <key>ProcessType</key>
    <string>Interactive</string>
</dict>
</plist>
EOF

chmod 600 "$PLIST_PATH"
echo "  wrote plist: $PLIST_PATH"

# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

launchctl load -w "$PLIST_PATH"
echo "  loaded $LABEL"

# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

echo ""
echo "Waiting for service to come up..."
for i in $(seq 1 24); do
    sleep 5
    PID=$(cat "$PID_PATH" 2>/dev/null || echo "")
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        # Confirm MCP responds (any HTTP code that isn't 000 means listening)
        CODE=$(curl -s -o /dev/null -w "%{http_code}" -m 3 \
            -X POST -H 'Content-Type: application/json' -d '{}' \
            http://127.0.0.1:8765/mcp/ 2>/dev/null || echo "000")
        if [ "$CODE" != "000" ]; then
            echo "  ready: pid $PID, MCP HTTP $CODE on http://127.0.0.1:8765/mcp/"
            break
        fi
    fi
    if [ "$i" -eq 24 ]; then
        echo "  WARNING: service not ready after 120s. Check $LOG_PATH"
    fi
done

echo ""
echo "Installed. Useful commands:"
echo "  baft itp-telegram daemon status   # launchctl + PID + MCP health"
echo "  baft itp-telegram daemon log      # tail the log"
echo "  baft itp-telegram daemon restart  # kickstart"
echo "  baft itp-telegram daemon uninstall"
echo "  baft itp-telegram stats           # vector store contents"
