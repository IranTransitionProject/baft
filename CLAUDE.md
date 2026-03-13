# Baft — Claude Code Operating Instructions

This is the ITP analytical engine repository. You are the **EXECUTOR** — responsible for building and maintaining the ITP-specific configuration layer on top of the Loom framework.

## Your role

You do NOT do analytical work here. You translate the ITP pipeline architecture (defined in `docs/architecture/`) into working Loom YAML configuration files, write utility scripts, and maintain the data import pipeline. Analytical judgments belong to the Chat session (HI-A role).

## Essential context

**Three-repo architecture:**
- `~/Developer/Repositories/framework/` — ITP analytical database (YAML source of truth, schemas, briefs)
- `~/Developer/Repositories/loom/` — Loom framework (worker runtime, MCP server, NATS bus, scheduler)
- This repo (`baft/`) — ITP application layer (all ITP-specific config lives here)

**Source of truth for node definitions:** `docs/architecture/ITP_MULTI_AGENT_ARCHITECTURE_v0_5.md`
Every worker config system prompt, knowledge silo, and I/O schema is specified there. Read that document before writing worker configs.

**Loom worker config format** (from `~/Developer/Repositories/loom/configs/workers/_template.yaml`):
```yaml
name: worker_name
description: "One-line description"
system_prompt: |
  [Full system prompt text]
input_schema:
  type: object
  properties:
    field_name:
      type: string
      description: "..."
  required: [field_name]
output_schema:
  type: object
  properties:
    result_field:
      type: string
  required: [result_field]
knowledge_sources:
  - type: file
    path: "path/to/knowledge/file"
    inject_as: "context_variable_name"
default_tier: local   # local | standard | frontier
output_constraints:
  max_tokens: 2000
  format: yaml_only
```

## Gap remediation priority order

Work through gaps in this order. Each gap has a validation step — do not move to the next gap until validation passes.

---

### Gap 1 [BLOCKING] — Streamable HTTP MCP transport

**File:** `~/Developer/Repositories/loom/src/loom/mcp/server.py`
**Function:** `run_streamable_http()`

The current implementation serves only a `/health` route via bare Starlette. It does not handle MCP protocol messages over HTTP.

**Fix:** Replace the stub with a working FastMCP streamable HTTP transport. The correct pattern uses `mcp.server.fastmcp.FastMCP` to wrap the low-level server in an ASGI app that handles MCP's streamable HTTP protocol.

Reference implementation pattern:
```python
async def _run():
    import uvicorn
    from mcp.server.fastmcp import FastMCP
    
    await gateway.bridge.connect()
    
    # Wrap low-level server in FastMCP ASGI app
    mcp_app = FastMCP.from_server(server)
    starlette_app = mcp_app.streamable_http_app()
    
    config = uvicorn.Config(starlette_app, host=host, port=port, log_level="info")
    uv_server = uvicorn.Server(config)
    try:
        await uv_server.serve()
    finally:
        await gateway.bridge.close()
```

**Validation:** `loom mcp --config configs/mcp/itp.yaml --transport streamable-http --port 8765` starts without error and responds to an HTTP GET `/health` with `{"status": "ok"}`.

**Note:** This modifies the Loom repo, not baft. Commit to Loom separately.

---

### Gap 2 [BLOCKING] — ITP MCP gateway config

**File:** `configs/mcp/itp.yaml`

Expose the core Tier 1–2 workers and the ITP DuckDB database as MCP tools. Audit nodes (LA, PA, RT, AS, TN) go into a separate `itp_audit.yaml` later.

```yaml
name: "baft"
description: "ITP analytical engine — source processing, intelligence analysis, database operations"
nats_url: "nats://localhost:4222"

tools:
  workers:
    - config: "configs/workers/sp_source_processor.yaml"
    - config: "configs/workers/ia_intelligence_analyst.yaml"
    - config: "configs/workers/de_database_engineer.yaml"
    - config: "configs/workers/xv_cross_validator.yaml"
    - config: "configs/workers/in_input_node.yaml"

  queries:
    - backend: "loom.contrib.duckdb.query_backend.DuckDBQueryBackend"
      actions: ["search", "filter", "stats", "get"]
      name_prefix: "itp"
      backend_config:
        db_path: "${HOME}/Developer/Repositories/baft/itp-workspace/itp.duckdb"
        table_name: "entities"
        result_columns: ["id", "type", "title", "status", "epistemic_tag", "confidence"]
        id_column: "id"
        full_text_column: "content"
        fts_fields: "title,content,tags"
        filter_fields:
          entity_type: "type = ?"
          status: "status = ?"
        stats_groups: ["type", "status"]
        stats_aggregates: ["COUNT(*) AS count"]

resources:
  workspace_dir: "${HOME}/Developer/Repositories/framework/data"
  patterns: ["*.yaml"]
```

**Validation:** `loom mcp --config configs/mcp/itp.yaml` starts without error and `loom mcp list-tools --config configs/mcp/itp.yaml` lists at minimum: `process_sources`, `analyze_intelligence`, `update_database`, `validate_cross_refs`, `submit_input`, `itp_search`, `itp_get`.

---

### Gap 3 [BLOCKING] — Worker configs (13 files)

**Directory:** `configs/workers/`

Read `docs/architecture/ITP_MULTI_AGENT_ARCHITECTURE_v0_5.md` Section "Node Definitions" before writing these. Each node definition contains: Function, Input spec, Output spec, Knowledge silo, System prompt core.

Write configs in this priority order (most-needed first):

**Batch A — Core operational nodes (build first, test after each):**
1. `de_database_engineer.yaml` — tier: local, no LLM (processor), reads framework schemas
2. `sp_source_processor.yaml` — tier: local (Haiku), reads source hierarchy + entity name registry
3. `ia_intelligence_analyst.yaml` — tier: frontier (Opus), reads full framework + DB snapshot
4. `xv_cross_validator.yaml` — tier: local (Haiku), reads entity ID registry only
5. `in_input_node.yaml` — tier: local (Haiku), minimal — just parses and routes inbox notes

**Batch B — Audit nodes:**
6. `tn_terminology_neutralizer.yaml` — tier: local (Haiku), reads terminology registry ONLY
7. `la_logic_auditor.yaml` — tier: standard (Sonnet), NO ITP framework in silo (blind)
8. `pa_perspective_auditor.yaml` — tier: standard (Sonnet), NO ITP framework in silo (blind)
9. `rt_red_teamer.yaml` — tier: frontier (Opus or different provider), NO ITP framework (blind)
10. `as_audit_synthesizer.yaml` — tier: standard (Sonnet), reads only audit outputs + human decision log

**Batch C — Background/scheduled nodes:**
11. `sa_session_advisor.yaml` — tier: local (Haiku), reads cognitive profile + session transcript
12. `wt_watch_tower.yaml` — tier: standard (Sonnet), reads watch list + web search tool enabled
13. `ni_narrative_intelligence.yaml` — tier: standard (Sonnet), reads channel registry + baseline stats

**Critical silo isolation rules (ENFORCE THESE — audit independence depends on them):**
- LA, PA, RT: MUST NOT have any path from `framework/` data or module content in `knowledge_sources`
- AS: MUST NOT have ITP framework content — only audit node outputs and human_decision_log
- TN: MUST ONLY have `pipeline/config/itp_terminology_registry.yaml` — nothing else
- SA: MUST NOT have analytical framework — only cognitive profile, session objectives, tier definitions

For blind audit nodes (LA, PA, RT), use the ROBOTIC-LLM rubric as the base system prompt. File is at `/mnt/user-data/uploads/ROBOTIC-LLM.md` (in the current session context). Extend it with ITP-specific evaluation criteria from the v0.5 architecture doc.

**Validation for each worker:**
```bash
# Syntax check
python3 -c "import yaml; yaml.safe_load(open('configs/workers/WORKER.yaml'))"
# Schema check (once workers are running)
loom worker --config configs/workers/WORKER.yaml --tier local --dry-run
```

---

### Gap 4 [BLOCKING] — Orchestrator pipeline configs (3 files)

**Directory:** `configs/orchestrators/`

**`itp_quick.yaml`** — Tier 1: direct single-worker dispatch, no orchestration needed. Just a wrapper config.

**`itp_standard.yaml`** — Tier 2: sequential pipeline
```
SP (source_processor) → IA (intelligence_analyst) → DE (database_engineer)
```
Stage 2 (IA) receives SP output as `new_claims` in context.
Stage 3 (DE) receives IA `integration_spec` as its `integration_request`.

**`itp_audit.yaml`** — Tier 3: full audit cycle
```
TN (terminology_neutralizer) → [LA + PA + RT in parallel] → AS (audit_synthesizer)
```
LA, PA, RT run in parallel (Loom supports this via orchestrator decomposer).
AS receives all three audit outputs as `audit_inputs`.

**Reference:** `~/Developer/Repositories/loom/configs/orchestrators/rag_pipeline.yaml` for pipeline config format.

**Validation:** `loom pipeline --config configs/orchestrators/itp_standard.yaml --dry-run`

---

### Gap 5 [BLOCKING] — Scheduler config

**File:** `configs/schedulers/itp.yaml`

```yaml
name: itp_scheduler
schedules:
  - name: watch_tower_daily
    cron: "0 6 * * *"          # 06:00 UTC daily
    dispatch_type: task
    task:
      worker_type: wt_watch_tower
      payload:
        watch_list_path: "pipeline/config/itp_watch_list.yaml"
      model_tier: standard

  - name: session_advisor
    interval_seconds: 900       # Every 15 minutes
    dispatch_type: task
    task:
      worker_type: sa_session_advisor
      payload: {}               # SA reads session transcript from its knowledge silo
      model_tier: local

  - name: governance_audit_weekly
    cron: "0 8 * * 1"          # 08:00 UTC Mondays
    dispatch_type: goal
    goal:
      instruction: "Run governance audit against current database state"
      priority: normal

  - name: agenda_planner_presession
    cron: "0 7 * * *"          # 07:00 UTC daily (run before typical session start)
    dispatch_type: task
    task:
      worker_type: wt_watch_tower
      payload:
        mode: agenda_assembly
      model_tier: standard
```

---

### Gap 6 [BLOCKING] — Knowledge silo index

**File:** `configs/knowledge/itp_silos.yaml`

Map each silo name to its file paths. Worker configs reference silo names rather than hardcoded paths, so path changes update in one place.

```yaml
# Referenced by worker configs as: knowledge_sources: [{silo: "silo_name"}]
silos:
  source_hierarchy:
    - path: "pipeline/config/itp_source_hierarchy.yaml"
      inject_as: "source_tier_rules"

  entity_name_registry:
    - path: "pipeline/config/itp_entity_name_registry.yaml"
      inject_as: "entity_names"

  epistemic_rules:
    - path: "pipeline/config/itp_epistemic_rules.yaml"
      inject_as: "epistemic_tagging_rules"

  terminology_registry:
    - path: "pipeline/config/itp_terminology_registry.yaml"
      inject_as: "terminology_registry"

  framework_full:
    - path: "${FRAMEWORK_REPO}/output/itb_full.md"
      inject_as: "analytical_framework"
    - path: "${FRAMEWORK_REPO}/output/isa_full.md"
      inject_as: "stress_architecture"

  database_current:
    - path: "${FRAMEWORK_REPO}/data/variables.yaml"
      inject_as: "current_variables"
    - path: "${FRAMEWORK_REPO}/data/observations.yaml"
      inject_as: "current_observations"
    - path: "${FRAMEWORK_REPO}/data/scenarios.yaml"
      inject_as: "current_scenarios"
    - path: "${FRAMEWORK_REPO}/data/traps.yaml"
      inject_as: "current_traps"
    - path: "${FRAMEWORK_REPO}/data/gaps.yaml"
      inject_as: "open_gaps"

  tier_rules:
    - path: "pipeline/config/itp_tier_rules.yaml"
      inject_as: "task_tier_rules"

  watch_list:
    - path: "pipeline/config/itp_watch_list.yaml"
      inject_as: "watch_items"

  cognitive_profile:
    - path: "pipeline/config/itp_cognitive_profile.yaml"
      inject_as: "analyst_profile"
```

Where `${FRAMEWORK_REPO}` = `~/Developer/Repositories/framework`. Use Python's `os.path.expandvars()` in the silo loader, or hardcode the expanded path.

---

### Gap 7 [BLOCKING] — DuckDB import script

**File:** `pipeline/scripts/itp_import_to_duckdb.py`

Reads all entity YAML files from `framework/data/` and populates a DuckDB database for structured queries.

**Tables to create:**
- `variables` — from `data/variables.yaml`
- `observations` — from `data/observations.yaml`
- `scenarios` — from `data/scenarios.yaml`
- `traps` — from `data/traps.yaml`
- `gaps` — from `data/gaps.yaml`
- `briefs` — from `data/briefs/*.yaml`
- `modules` — from `data/modules.yaml`
- `sessions` — from `data/sessions.yaml`

**Universal `entities` view:** Create a unified view joining all tables with columns: `id`, `type`, `title`, `status`, `content` (serialized YAML of full entity), `tags` (concatenated searchable fields), `updated_date`.

**FTS index:** Enable DuckDB's full-text search on `entities.content` and `entities.title`.

**Run mode:** 
- Default: full reimport (drop + recreate tables)
- `--incremental`: Only update entities modified since last import (compare YAML mtime to DB timestamp)

**Output path:** `itp-workspace/itp.duckdb` (gitignored, regenerated from framework YAML)

**Validation:** After import, `SELECT COUNT(*) FROM entities` returns expected total entity count.

---

### Gap 8 [IMPORTANT] — Telegram-to-source-bundle converter

**File:** `pipeline/scripts/telegram_to_source_bundle.py`

Convert Telegram JSON exports (from `TelegramIngestor`) to SP `source_bundle` format, with WT watch list pre-filtering.

**Input:** Telegram export JSON file path + channel registry YAML
**Output:** `source_bundle.yaml` in SP input format

**Key requirements:**
- Load channel metadata from `telegram_channel_registry.yaml` (source_tier, faction_tag, language)
- Apply keyword pre-filter against WT watch list (only emit messages matching watch terms)
- Include `forwarded_from` metadata as a field on each source item
- Respect `min_text_len` = 30 characters minimum
- Emit messages in chronological order
- Include `global_id` (channel_id:message_id) for dedup downstream

**Validation:** Feed a real Telegram export; confirm output YAML validates against SP input schema.

---

### Gap 9 [IMPORTANT] — Pipeline config files (stubs to fill)

**Files to create with meaningful initial content:**

`pipeline/config/itp_tier_rules.yaml` — already partially defined in architecture doc. Formalize as YAML.

`pipeline/config/itp_watch_list.yaml` — Extract top 20 watch items from `framework/data/variables.yaml` (highest-priority variables + open gaps). Add `channel_routing` field specifying which Telegram channels + platforms to search per item.

`pipeline/config/itp_source_hierarchy.yaml` — Formalize the 5-tier source taxonomy from the architecture doc.

`pipeline/config/itp_epistemic_rules.yaml` — Fact/Inference/Uncertain/Speculation rules with confidence band definitions.

`pipeline/config/itp_cognitive_profile.yaml` — Analyst profile for SA node. Include: session duration thresholds, known hyperfocus patterns, fatigue indicators, quality degradation markers.

`pipeline/config/itp_entity_name_registry.yaml` — Entity transliteration standards from framework. Extract all entity names and aliases from `data/variables.yaml` entities_mentioned fields.

---

### Gap 10 [PHASE 2] — Orchestrator and integration tests

**Directory:** `tests/`

After the above gaps are closed and one Tier 1 and one Tier 2 operation have been validated end-to-end:

Write `tests/test_baft_workers.py` — unit tests for each worker config (input schema validation, output schema validation, knowledge silo path resolution).

Write `tests/test_baft_pipelines.py` — integration tests for itp_standard and itp_audit pipelines using in-memory bus (InMemoryBus) and mock LLM backends.

Write `tests/test_duckdb_import.py` — validates that `itp_import_to_duckdb.py` produces the expected table structure and row counts.

---

## Validation checklist before declaring Phase 1 complete

```
[ ] loom mcp --config configs/mcp/itp.yaml starts without error
[ ] All 13 worker YAML files parse without error
[ ] itp_import_to_duckdb.py imports data successfully
[ ] One Tier 1 operation (DE update) works end-to-end via MCP
[ ] One Tier 2 operation (SP → IA → DE) works end-to-end via MCP
[ ] telegram_to_source_bundle.py converts a real export successfully
[ ] itp_terminology_registry.yaml has >= 30 entries
[ ] itp_watch_list.yaml has >= 20 entries with channel_routing
```

---

## Environment variables

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export FRAMEWORK_REPO="$HOME/Developer/Repositories/framework"
export BAFT_WORKSPACE="$HOME/Developer/Repositories/baft/itp-workspace"
export NATS_URL="nats://localhost:4222"
export REDIS_URL="redis://localhost:6379"
```

Add to `~/.zshrc` or `.env` at repo root (gitignored).

---

## Commit discipline

- All commits to `baft/` follow the same format as `framework/`: `Session N: [summary]`
- Never commit `itp-workspace/` (gitignored — contains DuckDB, exports, workspace files)
- Never commit `.env`
- Always validate YAML files before committing (`python3 -c "import yaml; yaml.safe_load(open('FILE'))"`)
- Run `loom mcp --config configs/mcp/itp.yaml --dry-run` after any MCP config change

---

## Coordination with Chat (HI-A)

This repo follows the same Chat→Code coordination protocol as `framework/`:
- Chat appends `Integration Request` entries to `CLAUDE_SESSION_LOG.md` in `framework/`
- Code processes and appends `Integration Complete`
- Baft-specific integration requests follow the same format, tagged with `[BAFT]` prefix in the summary line
