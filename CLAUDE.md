# CLAUDE.md — Baft project context

## What this project is

Baft is the ITP (Iran Transition Project) analytical engine — the application layer built on the Loom framework. It provides ITP-specific worker configurations, pipeline definitions, knowledge silo mappings, and utility scripts for the multi-agent intelligence analysis system.

This repo does NOT contain analytical work or the Loom framework itself. It translates the ITP pipeline architecture (defined in `docs/architecture/`) into working Loom YAML configurations.

## Three-repo architecture

- **framework/** — ITP analytical database (YAML source of truth, schemas, briefs)
- **loom/** — Loom framework (worker runtime, MCP server, NATS bus, scheduler)
- **baft/** (this repo) — ITP application layer (all ITP-specific config)

Source of truth for node definitions: `docs/architecture/ITP_MULTI_AGENT_ARCHITECTURE_v0_5.md`

## Project structure

```text
configs/
  workers/              # 13 worker YAML configs (system prompts, I/O schemas, tiers)
    sp_source_processor.yaml      # SP — source processing (local tier)
    ia_intelligence_analyst.yaml  # IA — analytical decisions (frontier tier)
    de_database_engineer.yaml     # DE — database integration (local tier, processor)
    xv_cross_validator.yaml       # XV — cross-reference validation (local tier)
    in_input_node.yaml            # IN — low-friction note capture (local tier)
    tn_terminology_neutralizer.yaml  # TN — audit neutralizer (local tier)
    la_logic_auditor.yaml         # LA — logic audit (standard tier, blind)
    pa_perspective_auditor.yaml   # PA — perspective audit (standard tier, blind)
    rt_red_teamer.yaml            # RT — red team challenge (frontier tier, blind)
    as_audit_synthesizer.yaml     # AS — audit synthesis (standard tier)
    sa_session_advisor.yaml       # SA — session quality monitor (local tier)
    wt_watch_tower.yaml           # WT — watch list scanning (standard tier)
    ni_narrative_intelligence.yaml # NI — narrative corpus analysis (standard tier)
  orchestrators/        # Pipeline configs
    itp_quick.yaml      # Tier 1: direct single-worker dispatch
    itp_standard.yaml   # Tier 2: SP → IA → XV → DE sequential pipeline
    itp_audit.yaml      # Tier 3: TN → [LA + PA + RT parallel] → AS
  schedulers/
    itp.yaml            # Scheduled actors (WT daily, NI daily, AP pre-session, SA every 15min, GA weekly)
  mcp/
    itp.yaml            # MCP gateway exposing workers + DuckDB queries as tools
  knowledge/
    itp_silos.yaml      # Knowledge silo index (silo name → file paths)

pipeline/
  config/               # Pipeline configuration data files
    itp_source_hierarchy.yaml       # 5-tier source taxonomy
    itp_epistemic_rules.yaml        # Fact/Inference/Uncertain/Speculation rules
    itp_tier_rules.yaml             # Task complexity → tier mapping
    itp_watch_list.yaml             # Priority watch items with channel routing
    itp_cognitive_profile.yaml      # Analyst profile for SA monitoring
    itp_entity_name_registry.yaml   # Entity transliteration standards
    itp_terminology_registry.yaml   # ITP-specific terminology for audit neutralization
    itp_telegram_channels.yaml      # Telegram channel registry
    human_decision_log_template.yaml
  scripts/              # Data pipeline utilities
    itp_import_to_duckdb.py         # YAML → DuckDB import (full + incremental)
    telegram_to_source_bundle.py    # Telegram JSON → SP source_bundle format
    telegram_corpus_interleave.py   # Multi-channel corpus interleaving
    generate_entity_registry.py     # Extract entity names from framework data

src/baft/               # Python package (v0.3.0)
  __init__.py           # Package marker
  sessions.py           # Session tracking for scheduler expansion (get_active_sessions)
  tracing.py            # OTel tracing integration (wraps loom.tracing with ITP defaults)
  contracts/            # Pydantic I/O models — source of truth for worker schemas
    __init__.py         # Re-exports all contract models
    core.py             # SP, IA, DE, XV, IN contracts (Tier 1–2 pipeline)
    audit.py            # TN, LA, PA, RT, AS contracts (Tier 3 audit pipeline)
    monitor.py          # SA, WT, NI contracts (background/scheduled workers)

scripts/                # Development utilities
  resolve_config.py     # Resolve silo references and ${ITP_ROOT} in worker configs
  build-app.sh          # Build deployment ZIP for Loom Workshop
  audition_models.py    # Test different LLM models against worker prompts
  test_e2e_quick.py     # Quick end-to-end smoke test

manifest.yaml           # App manifest for Loom Workshop deployment

tests/                  # 356 unit tests (7 test files)
  test_baft_workers.py      # Worker config validation (schema, silo resolution)
  test_contracts.py         # Pydantic contract models (validation, schema generation)
  test_baft_pipelines.py    # Pipeline orchestration (InMemoryBus, mock backends)
  test_duckdb_import.py     # DuckDB import script validation
  test_e2e_smoke.py         # End-to-end smoke tests (@pytest.mark.e2e)
  test_resolve_config.py    # Config resolution and silo expansion
  test_new_loom_features.py # OTel tracing, retries, Workshop MCP, eval baselines, TUI, dead-letter

docs/
  ANALYST_GUIDE.md      # Non-technical analyst guide (tools, workflows, Workshop, TUI)
  OPERATIONS_GUIDE.md   # Technical ops guide (tracing, retries, dead-letter, troubleshooting)
  SETUP.md              # Local environment setup (step-by-step)
  CLAUDE_DESKTOP_GUIDE.md  # Claude Desktop/Code connection guide
  LOOM_BUILDERS_GUIDE.md   # Design philosophy and lessons learned
  DESIGN_INVARIANTS.md  # Baft-specific design constraints (silo isolation, audit independence)
  architecture/         # ITP multi-agent architecture specification
```

## Relationship to Loom

Baft depends on `loom[mcp,duckdb,rag,workshop,tui,otel]` as a package (v0.8.0+). It uses:

- Worker YAML configs loaded by `loom worker` and `loom processor` CLI commands
- `PipelineOrchestrator` via `loom pipeline` CLI for Tier 2 and Tier 3 pipelines
- `SchedulerActor` via `loom scheduler` CLI for automated tasks
- MCP gateway via `loom mcp` CLI to expose workers as MCP tools
- `loom.contrib.duckdb.DuckDBQueryBackend` for structured queries against ITP data
- `loom.core.config.resolve_schema_refs()` to resolve `input_schema_ref`/`output_schema_ref` in worker configs to JSON Schema from Pydantic models in `baft.contracts`
- **OpenTelemetry tracing** — `baft.tracing` wraps `loom.tracing` for end-to-end pipeline visibility; W3C traceparent propagation through NATS messages
- **Per-stage retry** — all pipeline stages have `max_retries` configured (2 for local tier, 1 for standard/frontier)
- **ResultStream** — `loom.orchestrator.stream.ResultStream` for incremental result collection during audit pipeline parallel groups
- **Workshop MCP tools** — `workshop.*` namespace tools for worker CRUD, test bench, eval, impact analysis, dead-letter inspection
- **Config impact analysis** — `loom.workshop.config_impact.get_impact()` maps worker changes to affected pipelines/downstream stages
- **Eval baselines** — `WorkshopDB.promote_baseline()` / `compare_against_baseline()` for golden dataset regression detection
- **Dead-letter audit trail** — `ReplayRecord` on `DeadLetterConsumer` tracks replay history for governance
- **TUI dashboard** — `loom ui` for real-time NATS observation of goals, tasks, pipeline stages

The CLI loads backends by fully qualified class path from worker configs.

## Pipeline tiers

### Tier 1 — Quick (itp_quick.yaml)

Direct single-worker dispatch, no orchestration. Used for:

- DE database updates (validate_only, add observations)
- XV cross-reference checks
- IN inbox note capture

### Tier 2 — Standard (itp_standard.yaml)

Sequential pipeline: SP → IA → XV → DE

- **SP** extracts claims from source material
- **IA** analyzes claims against analytical framework, produces integration spec
- **XV** validates cross-references and epistemic tags
- **DE** persists validated results to database

Session context flows via `session_id` through `input_mapping`.

### Tier 3 — Audit (itp_audit.yaml)

Full audit cycle: TN → [LA + PA + RT parallel] → AS

- **TN** neutralizes ITP-specific terminology for blind review
- **LA**, **PA**, **RT** run in parallel (Loom auto-detects independence from input_mapping)
- **AS** synthesizes all three audit outputs with human decision log

Audit nodes use `audit_id` (not `session_id`) and are blind to analytical framework.

## Critical silo isolation rules

These are enforced by config — audit independence depends on them:

- **LA, PA, RT**: MUST NOT have any framework data in `knowledge_sources`
- **AS**: MUST NOT have ITP framework — only audit node outputs + human_decision_log
- **TN**: MUST ONLY have terminology_registry — nothing else
- **SA**: MUST NOT have analytical framework — only cognitive_profile, tier_rules, constitution

## Session management

- `session_id` is externally provided (by analyst via MCP tool calls)
- Flows through Tier 2 pipeline: SP (no session) → IA (receives session_id) → XV → DE (tracks session_id)
- SA monitors session quality with `session_id` in its input schema
- DE tracks `session_operation_count` per session for governance audit triggers

## Build and test commands

```bash
# Install all dependencies (requires Python 3.11+, uses uv)
# Loom is resolved from ../loom via [tool.uv.sources] in pyproject.toml
uv sync --extra dev

# Run unit tests (no infrastructure needed)
uv run pytest tests/ -v -m "not e2e"

# Run with infrastructure (needs NATS + Loom installed)
# Terminal 1: docker run -p 4222:4222 nats:latest
# Terminal 2: uv run loom router --nats-url nats://localhost:4222
# Terminal 3: uv run loom processor --config configs/workers/de_database_engineer.yaml --nats-url nats://localhost:4222
# Terminal 4: OLLAMA_URL=http://localhost:11434 uv run loom worker --config configs/workers/sp_source_processor.yaml --tier local --nats-url nats://localhost:4222
# Terminal 5: ANTHROPIC_API_KEY=sk-... uv run loom worker --config configs/workers/ia_intelligence_analyst.yaml --tier frontier --nats-url nats://localhost:4222
# Terminal 6: uv run loom pipeline --config configs/orchestrators/itp_standard.yaml --nats-url nats://localhost:4222

# MCP server (includes Workshop tools: worker CRUD, test bench, eval, impact, dead-letter)
uv run loom mcp --config configs/mcp/itp.yaml
uv run loom mcp --config configs/mcp/itp.yaml --transport streamable-http --port 8765

# Workshop web UI (worker testing, eval baselines, config impact analysis)
uv run loom workshop --port 8080
uv run loom workshop --port 8080 --nats-url nats://localhost:4222  # with live metrics

# TUI dashboard (real-time NATS observation — goals, tasks, pipeline stages)
uv run loom ui --nats-url nats://localhost:4222

# Import framework data to DuckDB
python pipeline/scripts/itp_import_to_duckdb.py
python pipeline/scripts/itp_import_to_duckdb.py --incremental

# Lint
uv run ruff check scripts/ pipeline/scripts/
```

## Current state

All configuration and infrastructure is implemented and working:

- 13 worker configs (Batch A core + Batch B audit + Batch C background/scheduled)
- 3 orchestrator pipeline configs (quick, standard, audit) — all with per-stage `max_retries`
- Scheduler config with 5 scheduled actors
- MCP gateway config exposing workers + DuckDB queries + Workshop tools (worker/test/eval/impact/deadletter)
- Knowledge silo index mapping silo names to file paths
- 9 pipeline config data files (source hierarchy, epistemic rules, watch list, etc.)
- DuckDB import script with full and incremental modes
- Telegram-to-source-bundle converter
- Config resolution script (silo expansion, ${ITP_ROOT} substitution)
- OpenTelemetry tracing integration (`baft.tracing` module)
- Unit tests: 356 tests pass (workers, contracts, pipelines, DuckDB import, config resolution, new loom features)

## What to implement next

1. **End-to-end Tier 2 validation** — Run full SP → IA → XV → DE pipeline against a real document with NATS + workers running
2. **Parallel pipeline variant** — Design a variant where classify and summarize run concurrently if summarizer doesn't need document_type

## Worker config format

All 13 worker configs follow the Loom v0.8.0 worker config schema:

- **`name`** (str, required) — unique worker identifier, matches filename
- **`description`** (str, required) — one-sentence purpose, shown in Workshop/MCP
- **`system_prompt`** (str, required) — complete LLM instructions
- **`default_model_tier`** (str, required) — `local` | `standard` | `frontier`
- **`reset_after_task`** (bool, required) — must be `true` (workers are stateless)
- **`timeout_seconds`** (int, required) — per-task timeout
- **`input_schema_ref`** / **`output_schema_ref`** (str) — Pydantic model dotted path in `baft.contracts`, resolved to JSON Schema at load time by `loom.core.config.resolve_schema_refs()`
- **`knowledge_sources`** (list) — silo references (`silo: <name>`) resolved via `itp_silos.yaml`
- **`output_constraints`** (dict) — `{format: json_only, max_tokens: N}` for output enforcement

## Concurrent multi-analyst sessions (v0.3.0)

Baft supports multiple analysts working simultaneously:

- **Pipelines** set `max_concurrent_goals: 4` (itp_standard, itp_audit) for parallel goal processing
- **SA scheduler** uses `expand_from: baft.sessions.get_active_sessions` to dispatch one SA task per active session
- **Session tracking** via `baft.sessions.register_session()` / `unregister_session()` — file-based markers in `~/.loom/sessions/`
- **DuckDB writes** serialized via single DE processor instance (default `max_concurrent=1`)
- **App bundle** built via `scripts/build-app.sh` → deploy via Loom Workshop

## Environment variables

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export ITP_ROOT="/path/to/IranTransitionProject"  # parent of framework/, loom/, baft/
export BAFT_WORKSPACE="$ITP_ROOT/baft/itp-workspace"
export NATS_URL="nats://localhost:4222"
export REDIS_URL="redis://localhost:6379"
export OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4317"  # Optional: OTel collector for tracing
export LOOM_TRACE=1  # Optional: full I/O debug logging for pipeline stages
```

## Observability and resilience

### OpenTelemetry tracing

- `baft.tracing.init_baft_tracing()` initializes OTel with service name `baft-itp`
- `baft.tracing.get_baft_tracer(scope)` returns a scoped tracer (real or no-op)
- W3C traceparent propagates through NATS messages via `_trace_context` key
- Spans on: actor message processing, router dispatch, pipeline stages, LLM calls
- LLM call spans include `gen_ai.*` attributes per OTel GenAI semantic conventions (`gen_ai.system`, `gen_ai.request.model`, `gen_ai.response.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`)
- `LOOM_TRACE_CONTENT=1` records prompt/completion text as OTel span events
- Requires `OTEL_EXPORTER_OTLP_ENDPOINT` env var (e.g. Jaeger at `http://localhost:4317`)
- Safe to call without OTel installed — degrades to no-ops

### Code coverage

- CI uploads coverage to Codecov; badge displayed on README
- Run locally: `uv run pytest --cov=baft --cov-report=term-missing`

### Per-stage retry

All pipeline stages have `max_retries` configured:

- **Local tier** workers (SP, XV, TN, DE): `max_retries: 2` (cheap to retry)
- **Standard tier** workers (LA, PA, AS): `max_retries: 1`
- **Frontier tier** workers (IA, RT): `max_retries: 1` (expensive — conservative)
- Retries only on transient errors (timeouts, worker failures), not validation errors

### Workshop MCP tools

The MCP gateway exposes Workshop tools under `workshop.*` namespace:

- `workshop.worker.{list,get,update}` — worker config CRUD
- `workshop.worker.test` — run worker against test payload
- `workshop.eval.{run,compare}` — eval suite execution + baseline comparison
- `workshop.impact.analyze` — config change impact analysis
- `workshop.deadletter.{list,replay}` — dead-letter inspection + replay (audit trail)

### TUI dashboard

`loom ui --nats-url nats://localhost:4222` shows live pipeline state:

- Goals panel (status, subtask count, elapsed)
- Tasks panel (worker type, tier, model, elapsed)
- Pipeline panel (stage execution with wall time)
- Events panel (scrolling log of all `loom.>` messages)

## Environment

- Apple Silicon Mac
- Python >=3.11 (pyproject.toml)
- Loom framework (resolved from ../loom)
- NATS for message bus
- DuckDB for embedded analytics database
- Ollama for local LLM tier
