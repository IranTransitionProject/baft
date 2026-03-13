#!/usr/bin/env bash
# run_workers.sh — Start all Baft worker processes
# Usage: bash scripts/run_workers.sh [--tier local|standard|frontier]

set -euo pipefail

TIER="${1:-local}"
NATS_URL="${NATS_URL:-nats://localhost:4222}"

echo "Starting Baft workers (tier: $TIER, NATS: $NATS_URL)"

# Core operational workers (always start)
loom worker --config configs/workers/sp_source_processor.yaml     --tier local     --nats-url "$NATS_URL" &
loom worker --config configs/workers/ia_intelligence_analyst.yaml --tier frontier   --nats-url "$NATS_URL" &
loom worker --config configs/workers/de_database_engineer.yaml    --tier local     --nats-url "$NATS_URL" &
loom worker --config configs/workers/xv_cross_validator.yaml      --tier local     --nats-url "$NATS_URL" &
loom worker --config configs/workers/in_input_node.yaml           --tier local     --nats-url "$NATS_URL" &

# Audit workers (start if AUDIT_TIER is set)
if [[ "${START_AUDIT_WORKERS:-false}" == "true" ]]; then
    loom worker --config configs/workers/tn_terminology_neutralizer.yaml --tier local    --nats-url "$NATS_URL" &
    loom worker --config configs/workers/la_logic_auditor.yaml           --tier standard --nats-url "$NATS_URL" &
    loom worker --config configs/workers/pa_perspective_auditor.yaml     --tier standard --nats-url "$NATS_URL" &
    loom worker --config configs/workers/rt_red_teamer.yaml              --tier frontier --nats-url "$NATS_URL" &
    loom worker --config configs/workers/as_audit_synthesizer.yaml       --tier standard --nats-url "$NATS_URL" &
    echo "Audit workers started"
fi

# Background/monitoring workers
loom worker --config configs/workers/wt_watch_tower.yaml          --tier standard  --nats-url "$NATS_URL" &
loom worker --config configs/workers/sa_session_advisor.yaml      --tier local     --nats-url "$NATS_URL" &
loom worker --config configs/workers/ni_narrative_intelligence.yaml --tier standard --nats-url "$NATS_URL" &

echo "All workers started. PIDs stored in /tmp/baft_workers.pids"
jobs -p > /tmp/baft_workers.pids

echo "To stop all workers: kill \$(cat /tmp/baft_workers.pids)"
wait
