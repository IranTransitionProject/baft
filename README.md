# Baft — ITP Analytical Engine

**Persian:** بافت — *woven fabric, texture, tissue*

Baft is the Iran Transition Project's analytical engine. It is an application built on the [Loom](https://github.com/IranTransitionProject/loom) actor mesh framework and the [framework](https://github.com/IranTransitionProject/framework) YAML database.

Loom provides the infrastructure: worker actors, NATS message bus, MCP gateway, RAG pipeline, scheduler, DuckDB query backend.

Baft provides the ITP-specific configuration: node system prompts, knowledge silos, inter-node schemas, terminology registry, tier rules, watch list, source channel registry, and pipeline orchestration configs.

The primary interface is a Claude chat session connected to the Baft MCP gateway. The chat session operates as the HI-A (Human Interface — Analyst) node. All structured operations (source processing, intelligence analysis, database updates, audit cycles) are invoked as MCP tools.

## Repository structure

```
configs/
  mcp/
    itp.yaml                    # MCP gateway — exposes Baft workers as tools
  workers/                      # One YAML per pipeline node
    sp_source_processor.yaml
    ia_intelligence_analyst.yaml
    tn_terminology_neutralizer.yaml
    la_logic_auditor.yaml
    pa_perspective_auditor.yaml
    rt_red_teamer.yaml
    as_audit_synthesizer.yaml
    de_database_engineer.yaml
    xv_cross_validator.yaml
    sa_session_advisor.yaml
    wt_watch_tower.yaml
    in_input_node.yaml
    ni_narrative_intelligence.yaml
  orchestrators/
    itp_standard.yaml           # SP → IA → DE (Tier 2)
    itp_audit.yaml              # SP → TN → LA+PA+RT → AS (Tier 3)
    itp_quick.yaml              # Direct DE dispatch (Tier 1)
  schedulers/
    itp.yaml                    # WT daily, AP pre-session, GA weekly, SA interval
  knowledge/
    itp_silos.yaml              # Silo path map referenced by worker configs

pipeline/
  config/
    itp_terminology_registry.yaml   # TN node vocabulary
    itp_tier_rules.yaml             # Tier selection rules
    itp_watch_list.yaml             # WT watch items with channel routing
  scripts/
    telegram_to_source_bundle.py    # Telegram JSON → SP source_bundle
    telegram_corpus_interleave.py   # Multi-channel timeline merge
    itp_import_to_duckdb.py         # framework YAML → DuckDB
  ni_findings/
    ni_findings_log.yaml            # Running narrative intelligence log

scripts/
  run_mcp_server.sh               # Start Baft MCP gateway (stdio or HTTP)
  run_workers.sh                  # Start all worker processes
  run_scheduler.sh                # Start scheduled actors

docs/
  architecture/
    ITP_MULTI_AGENT_ARCHITECTURE_v0_5.md
```

## Prerequisites

- Python 3.11+
- [Loom](https://github.com/IranTransitionProject/loom) installed (`pip install -e path/to/loom`)
- NATS server (`brew install nats-server` or Docker)
- Redis (`brew install redis` or Docker)
- Anthropic API key (`export ANTHROPIC_API_KEY=sk-ant-...`)
- ITP framework repo at `~/Developer/Repositories/framework/`

## Quick start

```bash
# 1. Install
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 2. Infrastructure
nats-server &
redis-server &

# 3. Import ITP data to DuckDB (first run)
python pipeline/scripts/itp_import_to_duckdb.py

# 4. Start workers
bash scripts/run_workers.sh

# 5. Start MCP gateway (stdio for Claude Code)
loom mcp --config configs/mcp/itp.yaml

# 6. Start MCP gateway (HTTP for claude.ai)
loom mcp --config configs/mcp/itp.yaml --transport streamable-http --port 8765
```

## Relationship to other ITP repos

| Repo | Role |
|------|------|
| [framework](https://github.com/IranTransitionProject/framework) | Analytical database (YAML source of truth) |
| [loom](https://github.com/IranTransitionProject/loom) | Actor mesh framework (infrastructure) |
| **baft** (this repo) | ITP application layer (config + scripts) |

## Architecture

See `docs/architecture/ITP_MULTI_AGENT_ARCHITECTURE_v0_5.md` for the full 16-node pipeline design, task-tier system, knowledge silo specifications, and implementation roadmap.
