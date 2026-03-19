#!/usr/bin/env bash
# baft.sh — Unified Baft start/stop for MCP usage
#
# Usage:
#   bash scripts/baft.sh start              # Start NATS + workers + MCP (stdio)
#   bash scripts/baft.sh start --http       # Start NATS + workers + MCP (HTTP on port 8765)
#   bash scripts/baft.sh start --http --port 9000
#   bash scripts/baft.sh stop               # Stop all
#   bash scripts/baft.sh status             # Show running processes
#   bash scripts/baft.sh logs [worker]      # Tail worker logs (all or specific)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BAFT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ITP_ROOT="${ITP_ROOT:-$(cd "$BAFT_DIR/.." && pwd)}"
export ITP_ROOT

LOOM_DIR="$ITP_ROOT/loom"
LOG_DIR="$BAFT_DIR/.worker-logs"
PID_FILE="$BAFT_DIR/.worker-pids"
RESOLVER="$SCRIPT_DIR/resolve_config.py"
RESOLVED_DIR="$BAFT_DIR/.resolved-configs"

# Defaults
export NATS_URL="${NATS_URL:-nats://localhost:4222}"
export OLLAMA_URL="${OLLAMA_URL:-http://localhost:11434}"
export OLLAMA_MODEL="${OLLAMA_MODEL:-llama3.2:3b}"
export ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-}"

# Colors
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()  { echo -e "${GREEN}[baft]${NC} $*"; }
warn()  { echo -e "${YELLOW}[baft]${NC} $*"; }
error() { echo -e "${RED}[baft]${NC} $*" >&2; }
header(){ echo -e "\n${BLUE}━━━ $* ━━━${NC}"; }

# ────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────

check_nats() {
    if (echo > /dev/tcp/localhost/4222) 2>/dev/null; then
        return 0
    fi
    return 1
}

start_nats() {
    if check_nats; then
        info "NATS already running on :4222"
        return 0
    fi

    if command -v nats-server &>/dev/null; then
        info "Starting nats-server..."
        nohup nats-server -p 4222 --http_port 8222 > "$LOG_DIR/nats.log" 2>&1 &
        echo "$! nats-server" >> "$PID_FILE"
    elif command -v docker &>/dev/null; then
        info "Starting NATS via Docker..."
        docker run -d --name nats-baft -p 4222:4222 -p 8222:8222 nats:latest --http_port 8222 >/dev/null 2>&1 || true
    else
        error "Neither nats-server nor docker found. Install one:"
        echo "  brew install nats-server"
        echo "  # or"
        echo "  brew install --cask docker"
        exit 1
    fi

    # Wait for NATS
    for i in $(seq 1 10); do
        check_nats && break
        sleep 0.5
    done
    check_nats || { error "NATS failed to start"; exit 1; }
    info "NATS ready on :4222"
}

resolve_config() {
    local name="$1"
    local src="$BAFT_DIR/configs/workers/${name}.yaml"
    local dst="$RESOLVED_DIR/${name}.yaml"
    (cd "$BAFT_DIR" && uv run python "$RESOLVER" "$src" -o "$dst" 2>/dev/null)
    echo "$dst"
}

start_worker() {
    local name="$1"
    local tier="$2"
    local config
    config=$(resolve_config "$name")
    local log="$LOG_DIR/${name}.log"

    nohup uv run --project "$BAFT_DIR" loom worker --config "$config" --tier "$tier" --nats-url "$NATS_URL" \
        > "$log" 2>&1 &
    local pid=$!
    echo "$pid $name" >> "$PID_FILE"
    info "  $name (tier=$tier, PID=$pid)"
}

stop_all() {
    if [[ -f "$PID_FILE" ]]; then
        info "Stopping processes..."
        while read -r pid name; do
            if kill -0 "$pid" 2>/dev/null; then
                kill "$pid" 2>/dev/null && info "  Stopped $name (PID $pid)" || true
            fi
        done < "$PID_FILE"
        rm -f "$PID_FILE"
    fi

    # Also kill any stray loom/nats processes we started
    pkill -f "loom router" 2>/dev/null || true
    pkill -f "loom worker.*resolved-configs" 2>/dev/null || true
    pkill -f "loom mcp.*itp.yaml" 2>/dev/null || true

    # Stop Docker NATS if we started it
    docker rm -f nats-baft 2>/dev/null || true

    info "All stopped."
}

show_status() {
    if [[ ! -f "$PID_FILE" ]]; then
        warn "No PID file — nothing running (or started externally)."
        return
    fi
    header "Baft process status"
    while read -r pid name; do
        if kill -0 "$pid" 2>/dev/null; then
            echo -e "  ${GREEN}✓${NC} $name (PID $pid)"
        else
            echo -e "  ${RED}✗${NC} $name (PID $pid) — not running"
        fi
    done < "$PID_FILE"
    echo ""
}

show_logs() {
    local worker="${1:-}"
    if [[ -n "$worker" ]]; then
        tail -f "$LOG_DIR/${worker}.log"
    else
        tail -f "$LOG_DIR"/*.log
    fi
}

# ────────────────────────────────────────────────
# Start
# ────────────────────────────────────────────────

do_start() {
    local transport="stdio"
    local port="8765"
    local mcp_only=false

    while [[ $# -gt 0 ]]; do
        case $1 in
            --http)       transport="streamable-http"; shift ;;
            --port)       port="$2"; shift 2 ;;
            --mcp-only)   mcp_only=true; shift ;;
            *) error "Unknown flag: $1"; exit 1 ;;
        esac
    done

    mkdir -p "$RESOLVED_DIR" "$LOG_DIR"

    # Preflight
    if [[ -z "$ANTHROPIC_API_KEY" ]]; then
        warn "ANTHROPIC_API_KEY not set — frontier-tier workers (IA) will fail."
        warn "Set it: export ANTHROPIC_API_KEY=sk-ant-..."
    fi

    if ! command -v uv &>/dev/null; then
        error "uv not found. Install: https://docs.astral.sh/uv/"
        exit 1
    fi

    # Sync if needed
    if [[ ! -d "$BAFT_DIR/.venv" ]]; then
        info "Running uv sync..."
        (cd "$BAFT_DIR" && uv sync --extra dev)
    fi

    # Stop previous run
    [[ -f "$PID_FILE" ]] && stop_all
    rm -f "$PID_FILE"

    if [[ "$mcp_only" == false ]]; then
        header "Infrastructure"
        start_nats

        header "Router"
        nohup uv run --project "$BAFT_DIR" loom router \
            --config "$LOOM_DIR/configs/router_rules.yaml" \
            --nats-url "$NATS_URL" \
            > "$LOG_DIR/router.log" 2>&1 &
        echo "$! router" >> "$PID_FILE"
        info "  Router (PID=$!)"

        sleep 1

        header "Workers"
        start_worker "de_database_engineer" "local"
        start_worker "xv_cross_validator" "local"
        start_worker "in_input_node" "local"
        start_worker "sp_source_processor" "local"
        start_worker "tn_terminology_neutralizer" "local"
        start_worker "ia_intelligence_analyst" "standard"

        sleep 2
    fi

    header "MCP Gateway"
    if [[ "$transport" == "stdio" ]]; then
        info "Transport: stdio (for Claude Desktop / Claude Code)"
        info "The MCP server will run in foreground. Press Ctrl-C to stop."
        echo ""
        exec uv run --project "$BAFT_DIR" loom mcp --config "$BAFT_DIR/configs/mcp/itp.yaml"
    else
        info "Transport: streamable-http on port $port"
        nohup uv run --project "$BAFT_DIR" loom mcp \
            --config "$BAFT_DIR/configs/mcp/itp.yaml" \
            --transport streamable-http --port "$port" \
            > "$LOG_DIR/mcp-server.log" 2>&1 &
        echo "$! mcp-server" >> "$PID_FILE"
        info "  MCP server (PID=$!, port=$port)"
        info ""
        info "MCP endpoint: http://127.0.0.1:$port/mcp"
        info "Health check: http://127.0.0.1:$port/health"
    fi

    echo ""
    show_status
    info "Logs: $LOG_DIR/"
    info "Stop: bash $0 stop"
}

# ────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────

ACTION="${1:-help}"
shift || true

case "$ACTION" in
    start)  do_start "$@" ;;
    stop)   stop_all ;;
    status) show_status ;;
    logs)   show_logs "$@" ;;
    help|*)
        echo "Usage: bash scripts/baft.sh <command> [options]"
        echo ""
        echo "Commands:"
        echo "  start              Start NATS + workers + MCP gateway (stdio)"
        echo "  start --http       Start everything with HTTP MCP transport"
        echo "  start --mcp-only   Start only the MCP gateway (workers already running)"
        echo "  stop               Stop all baft processes"
        echo "  status             Show running processes"
        echo "  logs [worker]      Tail logs (all or specific worker)"
        echo ""
        echo "Options for 'start':"
        echo "  --http             Use streamable-http transport (default: stdio)"
        echo "  --port PORT        HTTP port (default: 8765)"
        echo "  --mcp-only         Skip NATS/router/workers, start MCP server only"
        echo ""
        echo "Environment:"
        echo "  ANTHROPIC_API_KEY  Required for frontier-tier workers"
        echo "  ITP_ROOT           Project root (auto-detected from ../)"
        echo "  NATS_URL           NATS server URL (default: nats://localhost:4222)"
        echo "  OLLAMA_URL         Ollama URL (default: http://localhost:11434)"
        echo "  OLLAMA_MODEL       Default local model (default: llama3.2:3b)"
        ;;
esac
