# CLAUDE.md — Baft

## What this is

Baft is the ITP (Iran Transition Project) analytical application layer built on the Heddle framework. It provides worker configs, pipeline definitions, knowledge silo mappings, and session tooling for the multi-agent intelligence analysis system.

This repo does NOT contain analytical data. It translates the ITP pipeline architecture into Heddle YAML configs. Data lives in `baseline/`. The Heddle framework lives in `../heddle`.

## Three-repo layout

- **baseline/** — ITP analytical database (YAML source of truth, schemas, briefs)
- **heddle/** — Heddle framework (worker runtime, MCP server, NATS bus, scheduler)
- **baft/** (this repo) — ITP application layer (worker/pipeline/silo/session configs)

Node definitions source of truth: `docs/architecture/ITP_MULTI_AGENT_ARCHITECTURE_v0_5.md`

## Pipeline tiers

| Tier | Config | Flow |
| ------ | -------- | ------ |
| 1 — Quick | `itp_quick.yaml` | Direct single-worker dispatch (DE, XV, IN) |
| 2 — Standard | `itp_standard.yaml` | SP → IA → XV → DE |
| 3 — Audit | `itp_audit.yaml` | TN → [LA + PA + RT in parallel] → AS |

`session_id` flows through Tier 2: SP (no session) → IA → XV → DE. DE tracks `session_operation_count` for governance audit triggers.

## Critical silo isolation rules

**Audit independence breaks if these are violated. Enforced by config, not code.**

- `LA`, `PA`, `RT` — MUST NOT have any ITP framework data in `knowledge_sources`
- `AS` — MUST NOT have ITP framework; only audit node outputs + `human_decision_log`
- `TN` — MUST have ONLY `terminology_registry`; nothing else
- `SA` — MUST NOT have analytical framework; only `cognitive_profile`, `tier_rules`, `constitution`

Silo names resolve via `configs/knowledge/itp_silos.yaml`.

## Concurrent multi-analyst sessions

Pipelines set `max_concurrent_goals: 4`. SA scheduler uses `expand_from: baft.sessions.get_active_sessions` to dispatch one SA task per active session. Session markers: `~/.heddle/sessions/`. DuckDB writes are serialized via a single DE processor instance.

## Build and test

```bash
uv sync --extra dev              # Python 3.11+; Heddle resolved from ../heddle
uv run pytest tests/ -v -m "not e2e and not deepeval"   # unit tests, no infra
uv run pytest tests/ -m deepeval -v                     # needs Ollama + command-r7b
uv run ruff check scripts/ pipeline/scripts/            # lint
uv run heddle validate configs/workers/*.yaml           # validate all worker configs
uv run baft preflight                                   # environment check (10 validations)
```

## Session CLI

```bash
uv run baft session start                      # pull baseline, start session
uv run baft session status                     # active sessions + service health
uv run baft session sync                       # pull + incremental DuckDB import
uv run baft session end -m "message"           # commit + push baseline changes
```

Session `end` commits only the `data/` directory — never infrastructure files. See `docs/ANALYST_GUIDE.md` for the full analyst workflow.

## MCP and Workshop

```bash
uv run heddle mcp --config configs/mcp/itp.yaml                           # stdio
uv run heddle mcp --config configs/mcp/itp.yaml --transport streamable-http --port 8765
uv run heddle workshop --port 8080 --nats-url nats://localhost:4222
uv run heddle ui --nats-url nats://localhost:4222                          # TUI dashboard
```

## ITP Telegram subsystem

Separate from the main pipeline (no shared NATS, Workshop, or DB). See `docs/TELEGRAM_CAPTURE.md`. Lives in `src/baft/itp_telegram/`; driven by `baft itp-telegram` CLI. Daemon must be started via `baft itp-telegram daemon start` (not launchd) on this machine — the project is on `/Volumes/Data/` and launchd-spawned processes lack TCC access to external volumes.

## Environment variables

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export ITP_ROOT="/path/to/IranTransitionProject"   # parent of baseline/, heddle/, baft/
export BAFT_WORKSPACE="$ITP_ROOT/baft/itp-workspace"
export NATS_URL="nats://localhost:4222"
```

Optional: `REDIS_URL`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `LOOM_TRACE=1`.

See `docs/OPERATIONS_GUIDE.md` for tracing, retries, dead-letter queue, and troubleshooting.
