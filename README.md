# Baft — ITP Analytical Engine

[![CI](https://github.com/IranTransitionProject/baft/actions/workflows/ci.yml/badge.svg)](https://github.com/IranTransitionProject/baft/actions/workflows/ci.yml)
[![Docs](https://github.com/IranTransitionProject/baft/actions/workflows/docs.yml/badge.svg)](https://irantransitionproject.github.io/baft/)
[![codecov](https://codecov.io/github/IranTransitionProject/baft/graph/badge.svg)](https://codecov.io/github/IranTransitionProject/baft)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![License: MPL 2.0](https://img.shields.io/badge/License-MPL_2.0-brightgreen.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
<!-- Keep in sync with loom pyproject.toml version -->
[![Built on Loom](https://img.shields.io/badge/built_on-Loom_v0.8.0-blueviolet.svg)](https://github.com/IranTransitionProject/loom)
[![Status: Active Development](https://img.shields.io/badge/status-active_development-brightgreen.svg)]()

**Persian:** بافت — *woven fabric, texture, tissue*

Baft is the Iran Transition Project's analytical engine. It is an application built on the [Loom](https://github.com/IranTransitionProject/loom) actor mesh framework and the [framework](https://github.com/IranTransitionProject/framework) YAML database.

Loom provides the infrastructure: worker actors, NATS message bus, MCP gateway, RAG pipeline, scheduler, DuckDB query backend, Workshop web UI, TUI dashboard, distributed tracing.

Baft provides the ITP-specific configuration: node system prompts, knowledge silos, inter-node schemas, terminology registry, tier rules, watch list, source channel registry, and pipeline orchestration configs.

The primary interface is a Claude chat session connected to the Baft MCP gateway. The chat session operates as the HI-A (Human Interface — Analyst) node. All structured operations (source processing, intelligence analysis, database updates, audit cycles) are invoked as MCP tools. Workshop tools for worker testing, evaluation, impact analysis, and dead-letter management are also available as MCP tools.

## Repository structure

```text
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
    itp_standard.yaml           # SP → IA → XV → DE (Tier 2)
    itp_audit.yaml              # TN → [LA+PA+RT] → AS (Tier 3)
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
  baft.sh                         # Unified start/stop (NATS + workers + MCP)
  run_mcp_server.sh               # Start Baft MCP gateway (stdio or HTTP)
  run_workers.sh                  # Start all worker processes
  run_scheduler.sh                # Start scheduled actors

docs/
  architecture/
    ITP_MULTI_AGENT_ARCHITECTURE_v0_5.md
```

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- [Loom](https://github.com/IranTransitionProject/loom) cloned as sibling directory (`../loom`)
- [Ollama](https://ollama.com/) for local-tier workers
- NATS server (`brew install nats-server` or Docker)
- Valkey (`brew install valkey` or Docker) — optional, for checkpoints
- Anthropic API key (`export ANTHROPIC_API_KEY=sk-ant-...`) — for standard/frontier tier
- `ITP_ROOT` env var set to the project root (parent of `framework/`, `loom/`, `baft/`)

## Quick start

```bash
# 1. Install (resolves loom from ../loom automatically)
uv sync --extra dev

# 2. Infrastructure
nats-server &
valkey-server &

# 3. Import ITP data to DuckDB (first run)
uv run python pipeline/scripts/itp_import_to_duckdb.py

# 4. Start workers
bash scripts/run_workers.sh

# 5. Start MCP gateway (stdio for Claude Code)
uv run loom mcp --config configs/mcp/itp.yaml

# 6. Start MCP gateway (HTTP for claude.ai)
uv run loom mcp --config configs/mcp/itp.yaml --transport streamable-http --port 8765
```

## Relationship to other ITP repos

| Repo | Role |
|------|------|
| [framework](https://github.com/IranTransitionProject/framework) | Analytical database (YAML source of truth) |
| [loom](https://github.com/IranTransitionProject/loom) | Actor mesh framework (infrastructure) |
| **baft** (this repo) | ITP application layer (config + scripts) |

## Documentation

| Guide | Audience | What it covers |
|-------|----------|---------------|
| [Analyst Guide](docs/ANALYST_GUIDE.md) | Analysts | Day-to-day usage, tools, workflows, Workshop, TUI |
| [Operations Guide](docs/OPERATIONS_GUIDE.md) | Tech support | Tracing, retries, dead-letter, troubleshooting, tuning |
| [Claude Desktop Guide](docs/CLAUDE_DESKTOP_GUIDE.md) | All users | Connecting Baft to Claude Desktop or Claude Code |
| [Setup Guide](docs/SETUP.md) | New users | Full local environment setup |
| [Architecture v0.5](docs/architecture/ITP_MULTI_AGENT_ARCHITECTURE_v0_5.md) | Architects | Pipeline design, gap analysis, implementation roadmap |
| [Design Invariants](docs/DESIGN_INVARIANTS.md) | All | Silo isolation rules, audit independence constraints |
| [Loom Builders Guide](docs/LOOM_BUILDERS_GUIDE.md) | Engineers | Design philosophy, lessons learned, extending Loom |
