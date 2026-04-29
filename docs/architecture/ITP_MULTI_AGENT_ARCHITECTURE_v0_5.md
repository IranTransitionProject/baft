# ITP Multi-Agent Architecture v0.5 — Heddle Integration and Gap Analysis

**Version:** 0.5 DRAFT  
**Date:** 2026-03-13  
**Parent document:** ITP_MULTI_AGENT_ARCHITECTURE v0.4 + Addendum A (Source Access Layer)  
**Purpose:** Map the v0.4 architecture onto Heddle's actual implementation state. Identify what is already built, what is missing, and what the MCP-connected conversational UI design requires.

---

## Executive Summary

Heddle is further along than you likely realize. The core infrastructure — actor mesh, MCP server, Telegram ingestion, RAG pipeline, scheduler, DuckDB query backend, knowledge silo injection — is implemented and tested. The gap is not architectural plumbing. The gap is **ITP-specific configuration** (worker YAML files, knowledge silo content, MCP gateway config, terminology registry) and **two code completions** (streamable HTTP MCP transport, NRM normalizer).

The conversational UI → MCP → Heddle engine design is the right call. Heddle's MCP server already exists and exposes workers as tools. A Claude chat session connected to the Heddle MCP gateway gives you the HI-A role with full tool access to the analytical engine. The remaining infrastructure work is small. The configuration work is larger but tractable.

**Revised effort estimate:**

- Code gaps to close: ~3–4 items, none large
- Configuration gaps to fill: ~18 YAML files
- Architecture doc gaps to resolve: 4 Open Questions can now be closed
- Total before Phase 1 is operational: 2–3 Claude Code sessions

---

## What Heddle Has (Mapped to ITP Architecture)

### Infrastructure layer (complete)

| Heddle Component | ITP Architecture Role | Status |
|---|---|---|
| `core/actor.py` + NATS | Message bus, actor lifecycle | ✅ Complete, tested |
| `orchestrator/runner.py` + `decomposer.py` | HI-R orchestration function | ✅ Complete |
| `orchestrator/pipeline.py` | Sequential stage pipelines | ✅ Complete |
| `orchestrator/checkpoint.py` | Context overflow management | ✅ Complete |
| `orchestrator/synthesizer.py` | Multi-result aggregation | ✅ Complete |
| `worker/runner.py` + `knowledge.py` | All analytical node execution | ✅ Complete |
| `worker/backends.py` | Anthropic + Ollama + OpenAI-compatible | ✅ Complete |
| `router/router.py` | Task routing, tier enforcement, dead-letter | ✅ Complete |
| `mcp/server.py` | MCP gateway (tools + resources) | ✅ Complete (stdio) |
| `mcp/bridge.py` | MCP → NATS dispatch | ✅ Complete |
| `mcp/discovery.py` | Worker/pipeline/query tool generation | ✅ Complete |
| `scheduler/scheduler.py` | Cron + interval dispatch | ✅ Complete |
| `contrib/rag/ingestion/telegram_ingestor.py` | SC-TG source channel | ✅ Complete |
| `contrib/rag/vectorstore/duckdb_store.py` | Vector search | ✅ Complete |
| `contrib/duckdb/query_backend.py` | ITP database queries | ✅ Complete |
| `contrib/rag/chunker/sentence_chunker.py` | Corpus chunking for NI | ✅ Complete |
| `contrib/rag/analysis/llm_analyzers.py` | LLM-driven corpus analysis | ✅ Complete |
| `bus/memory.py` | In-memory bus for testing | ✅ Complete |

**Test coverage:** 89+ unit tests. No integration tests yet (known gap, listed in README).

### Node mapping (what exists vs. what needs config)

| ITP Node | Heddle Mechanism | Code Status | Config Status |
|---|---|---|---|
| HI-R (Router) | Orchestrator runner + decomposer | ✅ | ❌ No ITP orchestrator config |
| HI-A (Analyst) | Claude chat + MCP tools | ✅ MCP server | ❌ No ITP MCP gateway config |
| SA (Session Advisor) | Scheduled worker, reads transcript | ✅ | ❌ No SA worker config |
| SP (Source Processor) | Worker runner | ✅ | ❌ No SP worker config |
| IA (Intelligence Analyst) | Worker runner | ✅ | ❌ No IA worker config |
| TN (Terminology Neutralizer) | Worker runner OR script | ✅ | ❌ No TN config or registry |
| LA (Logic Auditor) | Worker runner | ✅ | ❌ No LA worker config |
| PA (Perspective Auditor) | Worker runner | ✅ | ❌ No PA worker config |
| RT (Red Teamer) | Worker runner (diff. backend) | ✅ backends exist | ❌ No RT worker config |
| AS (Audit Synthesizer) | Worker runner | ✅ | ❌ No AS worker config |
| DE (Database Engineer) | Worker runner + Claude Code | ✅ | ❌ No DE worker config |
| XV (Cross-Validator) | Worker runner | ✅ | ❌ No XV worker config |
| GA (Governance Auditor) | Scheduled worker | ✅ | ❌ No GA config |
| AP (Agenda Planner) | Scheduled pipeline | ✅ | ❌ No AP config |
| WT (Watch Tower) | Scheduled worker + web search | ✅ | ❌ No WT config or watch list |
| IN (Input Node) | Worker runner + NATS publish | ✅ | ❌ No IN config |
| SC-TG (Telegram) | TelegramIngestor | ✅ | ⚠️ Needs wiring to SP/WT pipeline |
| NRM (Normalizer/Dedup) | **NOT BUILT** | ❌ | ❌ |
| NI (Narrative Intelligence) | llm_analyzers.py (partial) | ⚠️ Partial | ❌ No NI worker config |

---

## Gaps to Close Before Phase 1

Ordered by blocking priority.

---

### Gap 1 [BLOCKING]: Streamable HTTP MCP Transport

**Location:** `src/heddle/mcp/server.py` → `run_streamable_http()`

**Current state:** The function exists but is a stub. It creates a Starlette app with only a `/health` route. No MCP protocol messages are handled over HTTP. The stdio transport works correctly.

**Why it blocks Phase 1:** The conversational UI design — a Claude chat session connecting to Heddle via MCP — requires HTTP transport. Claude.ai's custom MCP server integration expects a streamable HTTP endpoint. Stdio only works for local Claude Code sessions.

**Fix required:** Complete the Starlette/FastMCP integration. The comment in the source already identifies the path: `FastMCP streamable_http_app()` helper. The correct implementation wraps the low-level Server in FastMCP's ASGI app, not a bare Starlette route. Estimated: ~50 lines of code change.

**Immediate workaround for Phase 1:** Use stdio transport via Claude Code locally while building out the HTTP transport. This is the right sequence anyway — validate the pipeline locally before exposing it via HTTP.

**File to modify:** `src/heddle/mcp/server.py`
**Reference:** FastMCP `streamable_http_app()` pattern in mcp-python docs

---

### Gap 2 [BLOCKING]: ITP MCP Gateway Config

**Location:** `configs/mcp/` (new file: `itp.yaml`)

**Current state:** Only `docman.yaml` exists, exposing document processing workers. No ITP-specific MCP config.

**What's needed:** A `configs/mcp/itp.yaml` that exposes:

- Workers: SP, IA, DE, XV, TN (the core operational nodes)
- Pipelines: SP→IA→DE (standard analytical pipeline), SP→TN→LA→PA→RT→AS (audit pipeline)
- Queries: ITP database search (variables, observations, gaps, briefs, scenarios)
- Resources: `data/` directory (YAML files as readable MCP resources)

This is the single config file that turns Heddle into "the ITP engine" from the chat UI's perspective.

**Template:** Copy `configs/mcp/docman.yaml`, replace workers/pipelines/queries with ITP equivalents.

---

### Gap 3 [BLOCKING]: ITP Worker Configs (18 files)

**Location:** `configs/workers/` and `configs/orchestrators/` and `configs/schedulers/`

**Required files:**

```text
configs/workers/sp_source_processor.yaml
configs/workers/ia_intelligence_analyst.yaml
configs/workers/tn_terminology_neutralizer.yaml
configs/workers/la_logic_auditor.yaml
configs/workers/pa_perspective_auditor.yaml
configs/workers/rt_red_teamer.yaml
configs/workers/as_audit_synthesizer.yaml
configs/workers/de_database_engineer.yaml
configs/workers/xv_cross_validator.yaml
configs/workers/sa_session_advisor.yaml
configs/workers/wt_watch_tower.yaml
configs/workers/in_input_node.yaml
configs/workers/ni_narrative_intelligence.yaml
configs/orchestrators/itp_standard.yaml      # SP→IA→DE pipeline
configs/orchestrators/itp_audit.yaml         # SP→TN→LA→PA→RT→AS pipeline
configs/orchestrators/itp_quick.yaml         # HI-R→DE direct (Tier 1)
configs/schedulers/itp.yaml                  # WT daily, AP pre-session, GA weekly, SA every 15min
```

Each worker config contains: `name`, `description`, `system_prompt`, `input_schema`, `output_schema`, `knowledge_sources`, `default_model_tier`, `reset_after_task`, `timeout_seconds`, `output_constraints`.

The system prompt content already exists — it's in v0.4 under each node's "System prompt core" section. The task is translating those prose definitions into Heddle YAML format.

**This is the largest single work item** but is pure configuration (no code). Claude Code can generate all 18 files from the v0.4 document in one session.

---

### Gap 4 [BLOCKING]: ITP Knowledge Silo Wiring

**Location:** `configs/workers/*.yaml` → `knowledge_sources` fields, plus a new `configs/knowledge/itp_silos.yaml`

**Current state:** Heddle's `worker/knowledge.py` loads knowledge from file paths specified in worker configs. The baseline repo contains all the content needed (YAML data files, module markdown, schemas). But no worker config points to these files yet.

**What's needed:**

```yaml
# In each worker config, knowledge_sources field:
knowledge_sources:
  - type: file
    path: "$ITP_ROOT/baseline/data/variables.yaml"
    inject_as: "current_variables_snapshot"
  - type: file  
    path: "pipeline/config/itp_terminology_registry.yaml"
    inject_as: "terminology_registry"
```

**Key silo definitions from v0.4:**

| Node | Must Include | Must Exclude |
|---|---|---|
| SP | Source hierarchy, epistemic rules, entity name registry | Framework prose, observations, scenarios |
| IA | Full framework content, full DB state | Build pipeline, schema mechanics |
| TN | Terminology registry only | Everything else |
| LA/PA/RT | ROBOTIC-LLM rubric (from uploaded doc), epistemic rules | ITP framework (blind audit) |
| DE | All JSON schemas, current data files | Framework prose, brief content |
| SA | Cognitive profile, session objectives, tier definitions | Analytical framework content |

**Silo isolation is where audit independence is enforced.** The LA/PA/RT nodes must not receive ITP framework content in their knowledge sources — this is the mechanism that makes them genuinely blind.

---

### Gap 5 [BLOCKING]: ITP Database in DuckDB

**Location:** New DuckDB file at `itp-workspace/itp.duckdb`

**Current state:** Heddle has a fully functional DuckDB query backend (`contrib/duckdb/`). The docman test uses it for document data. The ITP entity data (variables, observations, gaps, briefs, scenarios, modules) lives as YAML in the baseline repo.

**What's needed:** A one-time import script that reads the framework YAML files and populates DuckDB tables that workers can query.

```python
# scripts/itp_import_to_duckdb.py
# Read: data/variables.yaml, data/observations.yaml, data/gaps.yaml, etc.
# Write: itp.duckdb tables: variables, observations, gaps, briefs, scenarios, modules
# Index: full-text search fields for WT and SP lookups
```

After this, the DuckDB query backend in the MCP config gives the chat UI direct structured access to the full ITP entity database. This replaces the current pattern of loading YAML into context via `project_knowledge_search`.

---

### Gap 6 [BLOCKING]: Terminology Registry YAML

**Location:** `pipeline/config/itp_terminology_registry.yaml` (new file)

**Current state:** The TN node design exists but the registry it needs doesn't. The document mentions building it "in CLAUDE_CHAT_INSTRUCTIONS.md" — it hasn't been formalized.

**What's needed:**

```yaml
# itp_terminology_registry.yaml
version: "1.0"
entries:
  - itp_term: "convergent spoiler"
    neutral_equivalent: "multi-actor veto mechanism"
    context: "China as active spoiler in deal scenarios"
  - itp_term: "puppet problem"
    neutral_equivalent: "succession authority gap"
    context: "Successor selected as puppet; constitutional powers make arrangement unstable"
  - itp_term: "velocity gap"
    neutral_equivalent: "pace asymmetry between concurrent processes"
  - itp_term: "hollowness thesis"
    neutral_equivalent: "institutional fragility hypothesis"
  - itp_term: "wrong interlocutor"
    neutral_equivalent: "negotiating counterpart mismatch"
  - itp_term: "Deal Cannot Hold"
    neutral_equivalent: "Agreement Stability Assessment: Low"
  # ... ~30–50 more entries
```

HI-A sessions are the best source for new entries — EP and DE should flag terms as they appear. The TN registry is a living document. OQ #14 is resolved by this: EP flags during publication, DE adds to registry, GA checks completeness weekly.

---

### Gap 7 [IMPORTANT]: NRM (Normalizer/Dedup) — Not Built

**Location:** New file: `src/heddle/contrib/rag/ingestion/normalizer.py`

**Current state:** The NRM function is defined in Addendum A but has no implementation. It sits between Source Channels and the SP/WT nodes.

**What's needed:** A processor (not a worker — no LLM required) that:

1. Accepts `normalized_source_entry` objects from multiple SC outputs
2. Deduplicates by content hash + timestamp window
3. Assigns `source_tier` from the channel registry
4. Tags language (already done by TelegramIngestor)
5. Emits a `source_bundle` in SP input format

**Why it can wait for Phase 1.5:** Phase 1 uses manual source channel queries (Hooman queries Grok/Gemini, pastes results as IN notes). NRM only becomes critical when SC outputs are automated and can produce duplicates. For Phase 1, the `telegram_to_source_bundle.py` converter script is sufficient — it's a single-source path with no dedup needed.

---

### Gap 8 [IMPORTANT]: Telegram-to-SP Pipeline Wiring

**Location:** New script: `pipeline/scripts/telegram_to_source_bundle.py`

**Current state:** `TelegramIngestor` reads and normalizes Telegram JSON exports. But there's no script that converts its output into SP's `source_bundle` input format, and no pipeline config that routes the output to SP/WT.

**What's needed:**

- ~100-line converter script (specified in Addendum A)
- A pipeline config or scheduler entry that triggers SP processing on new Telegram bundles
- Channel registry integration so each post inherits its channel's `source_tier` and `faction_tag`

This is the highest-value near-term build item after the blocking gaps — it's the first actual source data flowing through the pipeline.

---

### Gap 9 [PHASE 2]: Orchestrator and Integration Tests

**Location:** `tests/test_orchestrator.py` and `tests/test_integration.py`

**Current state:** The README lists "Orchestrator tests" and "End-to-end integration test" explicitly as "What to build next." The orchestrator decompose/dispatch/collect/synthesize loop has no test coverage. The integration test is excluded by marker in pytest.

**Why it matters for ITP:** Before running analytical pipelines with real data and real API calls, the orchestrator loop needs validated behavior. A broken decomposer that misroutes an IA task to the DE node, or a synthesizer that drops results, is silent failure in production. The test gap is a reliability risk.

---

### Gap 10 [PHASE 2]: Human Decision Log Persistence

**Location:** New: `itp-workspace/human_decision_log.yaml` + DuckDB table

**Current state:** v0.4 specifies a `human_decision_log` that tracks: which audit findings the human accepted vs. dismissed, rationale, and triggers a blind-spot alert after 3+ unexamined dismissals of the same type. Nothing persists this currently.

**What's needed:** A simple YAML append file (like `CLAUDE_SESSION_LOG.md`) plus a DuckDB import. The AS node writes to it; GA reads it for blind-spot detection. The data model is specified in v0.4.

---

### Gap 11 [PHASE 3]: Completed Streamable HTTP for Claude.ai Direct MCP

**Note:** Partially overlaps with Gap 1. Gap 1 is about completing the function. This gap is about the broader deployment consideration — running Heddle as a persistent HTTP server accessible to claude.ai's MCP configuration.

**Requirements:**

- Persistent process (not per-request) — NATS and Valkey must stay connected
- TLS if exposed beyond localhost (claude.ai will require HTTPS for remote MCPs)
- Authentication header support (claude.ai sends bearer tokens)
- For local use (Claude Code on same machine), stdio is fine indefinitely

**Recommendation:** For Phase 1–2, run Heddle locally, use stdio from Claude Code for DE/executor tasks, and use the HTTP transport for the analytical chat session once Gap 1 is closed. Defer public TLS/auth to Phase 3.

---

## Resolved Open Questions from v0.4

### OQ #4 (Inter-node schema formalization) — Now has a path

Heddle's `core/contracts.py` provides JSON Schema validation for worker I/O. The ITP schemas are defined in the v0.4 node specs (input/output YAML structures for SP, IA, TN, AS, etc.). The action is: transcribe those schemas into Heddle's `input_schema`/`output_schema` fields in each worker config. No new code — pure config.

### OQ #8 (ROBOTIC-LLM integration) — Closed

The ROBOTIC-LLM three-dimension rubric maps directly to the LA and PA nodes:

- **Factual & Historical Accuracy** → LA (Logic Auditor)
- **Causal Logic & Second-Order Effects** → LA (Logic Auditor)  
- **Perspective Bias** → PA (Perspective Auditor)

Implementation: The ROBOTIC-LLM system prompt (Phase 2 section, Master Geopolitical Prompt) becomes the base for LA and PA system prompts, extended with ITP-specific audit criteria. The "keep the cage small" principle (exact output length constraint: "exactly two sentences") maps to Heddle's `output_constraints` field in the worker config. The "zero-shot, fresh session, strip metadata" rules map directly to Heddle's stateless worker design — workers reset after every task by design.

### OQ #9 (Session log integration) — Confirmed and clarified

Architecture: Only the HI-R (Heddle orchestrator) writes to `CLAUDE_SESSION_LOG.md`. Individual workers (SP, IA, LA, etc.) are internal pipeline — their outputs go into NATS → DuckDB, not the session log. WT alerts and IN notes have their own YAML queues. The DE node, when handling Tier 1 database operations, may write directly to the session log via the existing Chat→Code protocol.

### OQ #15 (HI-R/HI-A handoff latency) — Resolved by MCP architecture

The MCP design eliminates the handoff friction in Phase 1. The claude.ai chat session IS the HI-A. It has direct tool access to the Heddle engine via MCP — calling SP, IA, DE, XV as tools within the same conversation. The HI-R function (orchestration, tier selection, sequencing) is handled by the orchestrator running in Heddle, invoked when the HI-A submits a multi-step goal. Single session, no context switching.

---

## Refined Architecture: MCP Chat Connection Design

This is the key design addition in v0.5.

```text
┌─────────────────────────────────────────────────────────┐
│                  HUMAN INTERFACE LAYER                   │
│                                                           │
│  Claude Chat Session (claude.ai or Claude Code)          │
│  ══════════════════════════════════════════              │
│  This IS the HI-A node.                                  │
│  Has full framework knowledge (via project knowledge     │
│  and conversation context).                              │
│  Calls Heddle tools via MCP for all structured operations. │
│                                                           │
│  MCP Tools available (from configs/mcp/itp.yaml):        │
│  • process_sources(source_bundle) → extracted_claims     │
│  • analyze_intelligence(analytical_input) → findings     │
│  • run_audit(neutralized_output) → audit_report          │
│  • update_database(integration_request) → result         │
│  • validate_cross_refs(entity_ids) → validation_result   │
│  • search_database(query) → entity_results               │
│  • query_watch_items(terms) → watch_results              │
│                                                           │
└─────────────────────┬───────────────────────────────────┘
                      │ MCP (stdio or HTTP)
                      │
┌─────────────────────▼───────────────────────────────────┐
│                   LOOM MCP GATEWAY                        │
│              (configs/mcp/itp.yaml)                       │
│                                                           │
│  mcp/server.py → mcp/bridge.py → NATS bus               │
│                                                           │
└──┬──────────────────┬────────────────────┬──────────────┘
   │                  │                    │
   ▼                  ▼                    ▼
┌──────┐          ┌────────┐          ┌────────┐
│Router│          │Orchestr│          │ Query  │
│      │          │ ator   │          │Backend │
│Routes│          │        │          │        │
│tasks │          │Runs    │          │DuckDB  │
│to    │          │multi-  │          │ITP     │
│worker│          │stage   │          │entities│
│tier  │          │pipelines│         │        │
└──┬───┘          └───┬────┘          └────────┘
   │                  │
   ▼                  ▼
┌──────────────────────────────────────────────┐
│              WORKER POOL (NATS queue groups)  │
│                                               │
│  SP  │ IA  │ TN  │ LA  │ PA  │ RT  │ AS      │
│  DE  │ XV  │ SA  │ WT  │ IN  │ NI  │ GA│ AP  │
│                                               │
│  Each worker: stateless, single system        │
│  prompt, strict I/O schema, resets per task  │
└──────────────┬───────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────┐
│          KNOWLEDGE + DATA LAYER               │
│                                               │
│  baseline/data/*.yaml  → ITP entity data    │
│  itp.duckdb             → structured queries │
│  itp-workspace/rag/     → vector embeddings  │
│  Telegram exports       → SC-TG feed         │
│  pipeline/config/       → tier rules, TN reg │
└──────────────────────────────────────────────┘

                    BACKGROUND ACTORS (Scheduler)
                    ├── WT: daily cron, watch list scan
                    ├── AP: pre-session, agenda assembly
                    ├── GA: weekly, governance audit
                    └── SA: every 15min during sessions
```

### How the chat UI interaction works in practice

**Tier 1 (Quick) — database operation:**

```text
Human: "Update SV-03 trend to deteriorating"
HI-A (Claude): Calls tool update_database({action: update, entity_id: SV-03, fields: {trend: deteriorating}})
Heddle: Routes to DE worker → validates → commits → returns result
HI-A: Reports result with validation status
```

**Tier 2 (Standard) — new source integration:**

```text
Human: "I have new Khamenei.ir content — [pastes text]"
HI-A (Claude): Calls tool process_sources({source_bundle: [...]})
Heddle: SP worker extracts claims → returns extracted_claims
HI-A: Reviews claims, proposes variable updates
Human: "Agree, also triggers a new observation"
HI-A: Calls tool analyze_intelligence({new_claims: [...], session_question: "..."})
Heddle: IA worker produces analytical_output
HI-A: Reviews, confirms
HI-A: Calls tool update_database({operations: [...]})
Heddle: DE worker commits
```

**Tier 3 (Publication) — new brief, full audit:**

```text
Human: "Ready to run audit on the Mirbagheri analysis"
HI-A (Claude): Calls tool run_audit({analytical_input: [IA output]})
Heddle: Orchestrator runs TN → LA + PA + RT (parallel) → AS → returns audit_report
HI-A: Presents structured audit findings
Human: Reviews, decides on each finding
HI-A: Logs decisions, calls update_database with any amendments
```

---

## Implementation Sequence for Phase 1

### Sprint 1: Local pipeline, no HTTP needed (Claude Code sessions)

1. **Build all 18 worker/orchestrator/scheduler configs** — Claude Code, one session, template from v0.4 node definitions. Priority order: DE, SP, IA, XV, TN, then audit nodes, then scheduled nodes.

2. **Build `itp_terminology_registry.yaml`** — Claude Code + Chat collaboration. Start with ~30 terms from current published Substack content. OQ #14 resolution: EP flags new terms, GA verifies registry completeness weekly.

3. **Build `itp.yaml` MCP gateway config** — Wire SP, IA, DE, XV as the core Tier 1–2 tools. Add DuckDB query tools for entity search. Add resources for `data/` YAML files.

4. **Build `itp_import_to_duckdb.py`** — Import current framework YAML into DuckDB. One-time run plus scheduled re-import after each DE commit.

5. **Validate: run one Tier 1 operation end-to-end** — Chat → MCP (stdio) → DE worker → validate → return result. This is the minimum viable loop.

### Sprint 2: Source access layer

6. **Build `telegram_to_source_bundle.py`** — ~100 lines. Converts TelegramIngestor output to SP `source_bundle` format. Apply keyword pre-filter from WT watch list.

7. **Build `telegram_corpus_interleave.py`** — Side-by-side timeline for manual NI scanning.

8. **Subscribe to critical Telegram channels** — Using the channel registry. At minimum: Fars, Tasnim, Sepah News (regime/IRGC), MASAF (eschatological), Etemad/Iran International (reformist/diaspora), Hengaw (Kurdish HR).

9. **First real source cycle** — Export 24hr from 5 channels, run through SP, review extracted_claims. Validate pipeline produces usable intelligence.

### Sprint 3: Audit loop

10. **Complete streamable HTTP transport** — Gap 1. Closes the claude.ai direct MCP connection.

11. **Run first Tier 3 audit cycle** — "Deal Cannot Hold" brief (Brief #5). Manual TN application, then LA/PA/RT as separate worker invocations, AS synthesis. This is the acid test specified in v0.4 immediate next steps.

12. **Add SA and scheduled nodes** — SA every 15 minutes, WT daily, AP pre-session.

---

## Updated Open Questions

### Newly opened

**OQ #17 (Knowledge silo update frequency):** The IA worker loads framework YAML at task time. As the database changes (DE commits), the silo content becomes stale mid-session. Solution options: (a) DuckDB live query instead of file load, (b) worker reads current file at each invocation (default Heddle behavior — acceptable for YAML files), (c) Valkey-cached snapshot with TTL. Recommendation: (b) is fine for Phase 1. Evaluate (a) when DuckDB import is operational.

**OQ #18 (Streamable HTTP auth for claude.ai MCP):** When claude.ai connects to a custom MCP server, it sends an OAuth bearer token. Heddle's HTTP transport (when completed) needs to validate this. The mcp-python library handles token verification in its streamable HTTP transport layer — this is handled by the library, not custom code. But it needs a secret configured. Track when Gap 1 is resolved.

**OQ #19 (DE worker vs. Claude Code for database operations):** Currently Claude Code handles all YAML/git operations via the session log protocol. The DE worker would duplicate some of this. Recommendation: Keep Claude Code for git commits (it has filesystem + git access). Use DE worker for validation-only operations that the HI-A needs real-time feedback on. Two-track: DE worker → validate+return result; Claude Code → commit to repo. The DE worker result triggers the session log integration request.

**OQ #20 (NI node timing):** When should NI run? v0.4 Addendum A says "daily or every few days." Recommendation for Phase 2: Daily after WT, but only if Telegram exports for the period are available. NI without Telegram data is just WT with different framing. Schedule: WT runs at 06:00 UTC (watch list scan), NI runs at 07:00 UTC (corpus analysis on last 24hr exports). AP runs at 08:00 UTC (assembles WT + NI findings into session agenda).

### Carried forward from v0.4 (still open)

**OQ #1 (IA context window budget):** Empirical test needed. Load full ISA-CORE + all data entities and measure degradation. Can now be tested with actual IA worker.

**OQ #2 (SA calibration):** Conservative defaults, track interventions.

**OQ #6 (Cost/session economics):** Now estimable: Tier 1 = 1 DE call (Haiku). Tier 2 = SP + IA + DE (Haiku + Opus + Haiku). Tier 3 = +TN + LA + PA + RT + AS (Haiku + Sonnet×4 + Sonnet). Full Tier 3 cycle: ~$0.10–0.30 per brief depending on models. Acceptable.

**OQ #7 (Which LLMs for which nodes?):** No change from v0.4. Confirmed by Heddle's tier system (local/standard/frontier maps to Haiku/Sonnet/Opus).

---

## Pipeline Directory Target Structure

After Sprint 1–2:

```text
heddle/
  configs/
    mcp/
      itp.yaml                             ← Gap 2 [new]
    workers/
      sp_source_processor.yaml             ← Gap 3 [new]
      ia_intelligence_analyst.yaml         ← Gap 3 [new]
      tn_terminology_neutralizer.yaml      ← Gap 3 [new]
      la_logic_auditor.yaml                ← Gap 3 [new]
      pa_perspective_auditor.yaml          ← Gap 3 [new]
      rt_red_teamer.yaml                   ← Gap 3 [new]
      as_audit_synthesizer.yaml            ← Gap 3 [new]
      de_database_engineer.yaml            ← Gap 3 [new]
      xv_cross_validator.yaml              ← Gap 3 [new]
      sa_session_advisor.yaml              ← Gap 3 [new]
      wt_watch_tower.yaml                  ← Gap 3 [new]
      in_input_node.yaml                   ← Gap 3 [new]
      ni_narrative_intelligence.yaml       ← Gap 3 [new]
    orchestrators/
      itp_standard.yaml                    ← Gap 3 [new]
      itp_audit.yaml                       ← Gap 3 [new]
      itp_quick.yaml                       ← Gap 3 [new]
    schedulers/
      itp.yaml                             ← Gap 3 [new]
    knowledge/
      itp_silos.yaml                       ← Gap 4 [new, referenced by worker configs]
  pipeline/
    config/
      itp_terminology_registry.yaml        ← Gap 6 [new]
      itp_tier_rules.yaml                  ← from v0.4 immediate next steps
      itp_watch_list.yaml                  ← WT watch items
    scripts/
      telegram_to_source_bundle.py         ← Gap 8 [new]
      telegram_corpus_interleave.py        ← Addendum A [new]
      itp_import_to_duckdb.py              ← Gap 5 [new]
    ni_findings/
      ni_findings_log.yaml                 ← running NI log
  src/heddle/
    mcp/
      server.py                            ← Gap 1 [complete streamable HTTP]
    contrib/
      rag/
        ingestion/
          normalizer.py                    ← Gap 7 [new NRM]
```

---

## Decision Record: Why MCP Chat is the Right Design

The alternative would be a dedicated web UI or a custom chat application built on the Heddle orchestrator. Rejected because:

1. **Claude chat IS the HI-A.** Building a custom chat app means rebuilding Claude's reasoning, multilingual capability, Farsi/Arabic text handling, epistemic discipline, and framework engagement from scratch. Claude already has all of this — the job is giving it tools, not replacing it.

2. **MCP is the right interface contract.** Tool use via MCP gives the HI-A (Claude) structured, validated access to the engine without giving it direct filesystem or database access. The HI-A calls `analyze_intelligence()` and gets structured YAML back — it doesn't load all the YAML files into context and try to do what the IA worker does. Separation is maintained.

3. **Heddle's MCP server already works.** The bridge, discovery, and server assembly are complete. The gap (HTTP transport) is small and well-defined.

4. **No infrastructure fragility.** A custom chat UI would need its own deployment, auth, and maintenance. Claude.ai or Claude Code connected to a local Heddle server is a zero-new-infrastructure design for Phases 1–2.

The one caveat: the claude.ai direct MCP connection requires the HTTP transport (Gap 1). Until that's done, the operational pattern is: Claude Code terminal session handles executor tasks (DE, data operations), Claude Chat handles analytical work with manual tool-call results pasted in. This is acceptable for Phase 1 — it's essentially the current workflow with better structure.

---

*Document version: 0.5. Parent: v0.4 + Addendum A. Next revision triggered by: Sprint 1 completion or Gap 1 resolution.*
