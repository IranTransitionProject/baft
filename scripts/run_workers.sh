#!/usr/bin/env bash
# run_workers.sh — Start Heddle router + ITP workers for local development
#
# Usage:
#   bash scripts/run_workers.sh              # Start router + all Tier 1-2 workers
#   bash scripts/run_workers.sh --tier1      # Router + DE only
#   bash scripts/run_workers.sh --stop       # Kill all heddle processes
#
# Requires:
#   - NATS running at localhost:4222
#   - Ollama running (for local-tier workers)
#   - ITP_ROOT set or auto-detected
#   - uv installed and deps synced (uv sync --extra dev)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BAFT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ITP_ROOT="${ITP_ROOT:-$(cd "$BAFT_DIR/.." && pwd)}"
export ITP_ROOT
export OLLAMA_URL="${OLLAMA_URL:-http://localhost:11434}"
export OLLAMA_MODEL="${OLLAMA_MODEL:-llama3.2:3b}"
# ANTHROPIC_API_KEY must already be set in environment for standard/frontier tier workers
export ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-}"
HEDDLE_DIR="$ITP_ROOT/heddle"
RESOLVER="$SCRIPT_DIR/resolve_config.py"
RESOLVED_DIR="$BAFT_DIR/.resolved-configs"
LOG_DIR="$BAFT_DIR/.worker-logs"
PID_FILE="$BAFT_DIR/.worker-pids"

# Colors
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

stop_workers() {
    if [[ -f "$PID_FILE" ]]; then
        info "Stopping workers..."
        while read -r pid name; do
            if kill -0 "$pid" 2>/dev/null; then
                kill "$pid" 2>/dev/null && info "  Stopped $name (PID $pid)" || true
            fi
        done < "$PID_FILE"
        rm -f "$PID_FILE"
    else
        warn "No PID file found. Killing any heddle processes..."
        pkill -f "heddle router" 2>/dev/null || true
        pkill -f "heddle worker" 2>/dev/null || true
    fi
    info "All workers stopped."
}

if [[ "${1:-}" == "--stop" ]]; then
    stop_workers
    exit 0
fi

# --- Preflight checks ---
if ! curl -sf http://localhost:4222 >/dev/null 2>&1 && ! curl -sf http://localhost:8222/varz >/dev/null 2>&1; then
    # Try raw TCP check
    if ! (echo > /dev/tcp/localhost/4222) 2>/dev/null; then
        error "NATS not reachable at localhost:4222. Start it first:"
        echo "  docker run -d --name nats-itp -p 4222:4222 -p 8222:8222 nats:latest --http_port 8222"
        exit 1
    fi
fi

if ! command -v uv &>/dev/null; then
    error "uv not found. Install from: https://docs.astral.sh/uv/"
    exit 1
fi

# Ensure deps are synced (creates .venv if needed)
if [[ ! -d "$BAFT_DIR/.venv" ]]; then
    info "Running uv sync..."
    (cd "$BAFT_DIR" && uv sync --extra dev)
fi

# --- Resolve configs ---
mkdir -p "$RESOLVED_DIR" "$LOG_DIR"

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

    nohup uv run --project "$BAFT_DIR" heddle worker --config "$config" --tier "$tier" --nats-url nats://localhost:4222 \
        > "$log" 2>&1 &
    local pid=$!
    echo "$pid $name" >> "$PID_FILE"
    info "  Started $name (tier=$tier, PID=$pid, log=$log)"
}

# --- Stop any existing workers ---
[[ -f "$PID_FILE" ]] && stop_workers

rm -f "$PID_FILE"

# --- Start router ---
info "Starting Loom router..."
nohup uv run --project "$BAFT_DIR" heddle router --config "$HEDDLE_DIR/configs/router_rules.yaml" --nats-url nats://localhost:4222 \
    > "$LOG_DIR/router.log" 2>&1 &
ROUTER_PID=$!
echo "$ROUTER_PID router" >> "$PID_FILE"
info "  Router started (PID=$ROUTER_PID)"

sleep 1

# --- Start workers ---
TIER1_ONLY=false
[[ "${1:-}" == "--tier1" ]] && TIER1_ONLY=true

info "Starting Tier 1 workers..."
start_worker "de_database_engineer" "local"
start_worker "xv_cross_validator" "local"
start_worker "in_input_node" "local"

if [[ "$TIER1_ONLY" == false ]]; then
    info "Starting Tier 2 workers..."
    start_worker "sp_source_processor" "local"
    start_worker "ia_intelligence_analyst" "standard"
fi

sleep 2

# --- Verify ---
info ""
info "=== Running workers ==="
while read -r pid name; do
    if kill -0 "$pid" 2>/dev/null; then
        echo -e "  ${GREEN}✓${NC} $name (PID $pid)"
    else
        echo -e "  ${RED}✗${NC} $name (PID $pid) — CRASHED, check $LOG_DIR/${name}.log"
    fi
done < "$PID_FILE"

info ""
info "Logs: $LOG_DIR/"
info "Stop: bash $0 --stop"
info ""
info "Ready for e2e tests:"
info "  cd $BAFT_DIR && uv run pytest tests/test_e2e_smoke.py -v"
