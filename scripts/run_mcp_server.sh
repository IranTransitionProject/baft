#!/usr/bin/env bash
# run_mcp_server.sh — Start Baft MCP gateway
# Usage:
#   bash scripts/run_mcp_server.sh           # stdio (for Claude Code)
#   bash scripts/run_mcp_server.sh --http    # streamable HTTP (for claude.ai)
#   bash scripts/run_mcp_server.sh --port 8765 --http

set -euo pipefail

CONFIG="configs/mcp/itp.yaml"
PORT="${PORT:-8765}"
TRANSPORT="stdio"

while [[ $# -gt 0 ]]; do
    case $1 in
        --http)       TRANSPORT="streamable-http"; shift ;;
        --port)       PORT="$2"; shift 2 ;;
        --config)     CONFIG="$2"; shift 2 ;;
        *) echo "Unknown arg: $1"; exit 1 ;;
    esac
done

echo "Starting Baft MCP gateway"
echo "  Config:    $CONFIG"
echo "  Transport: $TRANSPORT"
[[ "$TRANSPORT" == "streamable-http" ]] && echo "  Port:      $PORT"

if [[ "$TRANSPORT" == "streamable-http" ]]; then
    uv run loom mcp --config "$CONFIG" --transport streamable-http --port "$PORT"
else
    uv run loom mcp --config "$CONFIG"
fi
