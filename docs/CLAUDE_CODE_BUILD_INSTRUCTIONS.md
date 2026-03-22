# Claude Code Instructions — Baft Repository Build

**Date:** 2026-03-13  
**Repo:** `$ITP_ROOT/baft/`  
**For:** Claude Code (EXECUTOR role)

---

## Your mission

Build the Baft repository from the skeleton provided. Baft is the ITP-specific configuration layer on top of Loom. All architectural decisions are already made — this is implementation work.

**Read before starting:**

1. `CLAUDE.md` — operating rules for this repo
2. `docs/architecture/ITP_MULTI_AGENT_ARCHITECTURE_v0_5.md` — the canonical node spec
3. `$ITP_ROOT/loom/configs/workers/_template.yaml` — Loom worker config format
4. `$ITP_ROOT/loom/configs/workers/summarizer.yaml` — real example worker config

---

## Session 1: Worker configs + MCP gateway (Sprint 1, Batch A)

### Step 1.1 — Read the Loom worker template format

```bash
cat $ITP_ROOT/loom/configs/workers/_template.yaml
cat $ITP_ROOT/loom/configs/workers/summarizer.yaml
```

Understand the schema before writing any worker config. Every worker config needs:

- `name` — matches the tool name exposed via MCP
- `description` — shown to MCP clients
- `system_prompt` — full prompt text (multi-line YAML string)
- `input_schema` — JSON Schema for the input payload
- `output_schema` — JSON Schema for the output
- `knowledge_sources` — list of files to inject into context
- `default_model_tier` — `local` | `standard` | `frontier`

### Step 1.2 — Write worker configs (Batch A: core operational)

Read architecture doc Section "Node Definitions" for each node. Extract:

- "System prompt core" → `system_prompt` field
- "Input spec" YAML block → `input_schema`
- "Output spec" YAML block → `output_schema`
- "Knowledge silo" list → `knowledge_sources`

Write in this order:

**File: `configs/workers/de_database_engineer.yaml`**

- Node: DE (Database Engineer), architecture doc Node 2
- Tier: local
- This is a `processor` (non-LLM) type if Loom supports it, otherwise LLM with strict output format
- Knowledge: all JSON schemas from framework repo, current data files for ID lookup
- Input schema: `integration_request` (operations list)
- Output schema: `integration_result` with `operations_attempted`, `operations_succeeded`, `validation_result`, `ga_notification`
- System prompt: include the mid-session GA trigger behavior

**File: `configs/workers/sp_source_processor.yaml`**

- Node: SP (Source Processor), architecture doc Node 1
- Tier: local (Haiku)
- Knowledge: source hierarchy (`itp_source_hierarchy.yaml`), epistemic rules, entity name registry
- Input schema: `source_bundle`
- Output schema: `extracted_claims`
- CRITICAL: knowledge_sources must NOT include framework module content or analytical data

**File: `configs/workers/ia_intelligence_analyst.yaml`**

- Node: IA (Intelligence Analyst), architecture doc Node 3
- Tier: frontier (Opus)
- Knowledge: full framework content (ITB + ISA outputs), full DB snapshot (variables, observations, scenarios, traps, gaps), epistemic rules, standing analytical rules
- Input schema: `analytical_input`
- Output schema: `analytical_output` including `integration_spec` for DE
- This is the longest system prompt — include all standing rules, sophisticated actor default, factional neutrality, anti-Islamophobic framing discipline

**File: `configs/workers/xv_cross_validator.yaml`**

- Node: XV (Cross-Validator)
- Tier: local (Haiku)
- Knowledge: entity ID registry only (list of valid IDs and module codes — generate from DB)
- Input: list of entity references to validate
- Output: validation result with any broken refs flagged

**File: `configs/workers/in_input_node.yaml`**

- Node: IN (Input Node)
- Tier: local (Haiku)
- Knowledge: minimal — just the inbox queue format
- Input: natural language note from human (time-sensitive finding)
- Output: structured `inbox_item` YAML appended to `itp-workspace/inbox_queue.yaml`

### Step 1.3 — Write worker configs (Batch B: audit nodes)

**CRITICAL SILO ISOLATION RULE:**  
LA, PA, RT must NOT have any knowledge_sources pointing to:

- `framework/` data directory (any YAML entities)
- Framework module content (ITB/ISA)
- ITP-specific documents

These nodes are blind. They receive only the neutralized analytical text and their evaluation rubric.

**File: `configs/workers/tn_terminology_neutralizer.yaml`**

- Node: TN, architecture doc Node 3.1
- Tier: local (Haiku)
- Knowledge: `pipeline/config/itp_terminology_registry.yaml` ONLY
- Input: IA analytical output YAML
- Output: neutralized output with replacements_applied table + reverse_map
- System prompt: extremely short — it's a mechanical text transformation

**File: `configs/workers/la_logic_auditor.yaml`**

- Node: LA (Logic Auditor), architecture doc Node 4
- Tier: standard (Sonnet)
- Knowledge: ROBOTIC-LLM rubric (from repo: `docs/references/ROBOTIC-LLM.md`) — no ITP content
- Input: neutralized analytical text (post-TN)
- Output: Markdown table with [Dimension, Score, Justification] per ROBOTIC-LLM format
- System prompt: Use ROBOTIC-LLM Master Geopolitical Prompt verbatim as base, extend with:
  - Dimension 1: Factual & Historical Accuracy (same)
  - Dimension 2: Causal Logic & Second-Order Effects (same)
  - Dimension 3: ITP-specific — "Evidence Chain Integrity: Does each conclusion trace explicitly to cited evidence, or does the text rely on asserted authority?"
  - Dimension 4: ITP-specific — "Counterfactual Robustness: Does the analysis consider and explicitly rule out alternative explanations for the observed phenomena?"

**File: `configs/workers/pa_perspective_auditor.yaml`**

- Node: PA (Perspective Auditor), architecture doc Node 5
- Tier: standard (Sonnet)
- Knowledge: ROBOTIC-LLM rubric only — no ITP content
- Input: neutralized analytical text
- Output: Markdown table with [Dimension, Score, Justification]
- System prompt: ROBOTIC-LLM base, focused on Dimension 3 (Perspective Bias) extended:
  - Dimension 1: Single-actor centrism (does analysis over-weight one faction's perspective?)
  - Dimension 2: Temporal bias (does analysis treat current wartime context as permanent state?)
  - Dimension 3: Western analytical frame contamination (are conclusions shaped by Western policy preferences?)
  - Dimension 4: Diaspora vs. internal perspective balance

**File: `configs/workers/rt_red_teamer.yaml`**

- Node: RT (Red Teamer), architecture doc Node 6
- Tier: frontier (Opus) — or a different provider for Tier 4 (flag this in comments)
- Knowledge: no ITP framework — adversarial from position of ignorance
- Input: neutralized analytical text
- Output: structured challenge list with `challenge_id`, `claim_challenged`, `counter_argument`, `strength` (1–10), `evidence_basis`
- System prompt: "You are an adversarial reviewer. Your role is to find the strongest possible objections to the provided analysis. Do not soften challenges. For each challenge, rate strength 1–10 where 10 = the analysis is fundamentally wrong on this point. Output YAML only."

**File: `configs/workers/as_audit_synthesizer.yaml`**

- Node: AS (Audit Synthesizer), architecture doc Node 7
- Tier: standard (Sonnet)
- Knowledge: `itp-workspace/human_decision_log.yaml` (for blind-spot detection) — NO ITP framework
- Input: outputs from LA + PA + RT (all three)
- Output: `audit_report` with: `conflicts` list, `consensus_findings`, `recommended_human_decisions`, `blind_spot_alerts`

### Step 1.4 — Write worker configs (Batch C: scheduled/background)

**File: `configs/workers/sa_session_advisor.yaml`**

- Node: SA (Session Advisor), architecture doc Node 0.1
- Tier: local (Haiku)
- Knowledge: `pipeline/config/itp_cognitive_profile.yaml`, tier rules, session transcript (injected at runtime)
- Output: `sa_advisory` YAML with flags array
- System prompt: "You are a session quality monitor. Observe the interaction transcript. Flag: fatigue indicators, priority drift, confirmation bias, tunnel vision, emotional escalation, quality gate bypass, tier mismatch. Output YAML flags only. Do not analyze geopolitical content. Do not speak to the human."
- Note: receives session transcript via `payload.transcript` field

**File: `configs/workers/wt_watch_tower.yaml`**

- Node: WT (Watch Tower)
- Tier: standard (Sonnet)
- Knowledge: `pipeline/config/itp_watch_list.yaml`, channel registry
- Tool access: web_search enabled in Loom backend config
- Input: `watch_list_path` + optional `mode` (scan | agenda_assembly)
- Output: `watch_results` with per-item findings + agenda_items for AP

**File: `configs/workers/ni_narrative_intelligence.yaml`**

- Node: NI (Narrative Intelligence)
- Tier: standard (Sonnet)
- Knowledge: channel registry (faction tags, source tiers), prior analysis statistics
- Input: bulk Telegram corpus (post-interleave) + time_range + analysis_modes
- Output: `ni_findings` array (coordination, silence, divergence, velocity, tone findings)
- System prompt: focused on pattern detection in media behavior, NOT geopolitical interpretation

### Step 1.5 — Write orchestrator pipeline configs

Read `$ITP_ROOT/loom/configs/orchestrators/rag_pipeline.yaml` for format.

**File: `configs/orchestrators/itp_quick.yaml`** — single-stage, just DE
**File: `configs/orchestrators/itp_standard.yaml`** — SP → IA → DE (sequential, pass output forward)
**File: `configs/orchestrators/itp_audit.yaml`** — TN → [LA, PA, RT] (parallel) → AS

For the audit pipeline, LA/PA/RT must run in parallel (Loom orchestrator supports parallel decomposition).

### Step 1.6 — Update `configs/mcp/itp.yaml`

The skeleton `itp.yaml` is already in the repo. Verify all worker names match the `name` fields in the worker configs. Add any missing tools.

### Step 1.7 — Validate

```bash
# YAML syntax check all worker configs
for f in configs/workers/*.yaml; do
    python3 -c "import yaml; yaml.safe_load(open('$f'))" && echo "OK: $f" || echo "FAIL: $f"
done

# YAML syntax check orchestrators
for f in configs/orchestrators/*.yaml; do
    python3 -c "import yaml; yaml.safe_load(open('$f'))" && echo "OK: $f" || echo "FAIL: $f"
done

# Try starting MCP server dry run
loom mcp --config configs/mcp/itp.yaml --dry-run 2>/dev/null || echo "Note: --dry-run may not be supported; check loom mcp --help"
```

---

## Session 2: Data layer (Sprint 1, Batch B)

### Step 2.1 — Run DuckDB import

```bash
cd $ITP_ROOT/baft
python pipeline/scripts/itp_import_to_duckdb.py
python pipeline/scripts/itp_import_to_duckdb.py --stats
```

Fix any import errors. Common issues:

- YAML keys don't match expected entity type names → update `ENTITY_YAML_FILES` dict in script
- Missing `id` field on some entities → add fallback ID generation (use list index)
- Encoding issues → ensure `encoding="utf-8"` everywhere

### Step 2.2 — Build supporting pipeline config files

These are short files needed by workers:

**`pipeline/config/itp_source_hierarchy.yaml`** — 5-tier source taxonomy:

- Tier 1: Official regime primary sources (KHAMENEI.IR, state broadcaster, official agencies)
- Tier 2: Semi-official / regime-affiliated media with editorial function (Fars, Tasnim, ISNA, IRNA)
- Tier 3: Independent media, diaspora outlets with transparent sourcing (Iran International, IranWire)
- Tier 4: Single-source, unverified, or agenda-driven
- Tier 5: Social media noise — requires heavy verification
Include: calibration rules per tier, how epistemic_tag maps to tier

**`pipeline/config/itp_epistemic_rules.yaml`** — tagging definitions:

- Fact: Directly stated in Tier 1–2 source, independently corroborated
- Inference: Logically follows from Facts with stated reasoning chain
- Uncertain: Plausible but competing explanations exist; single source or Tier 3–4
- Speculation: Insufficient evidence; analytical hypothesis only
Include: confidence band definitions (High/Medium/Low/Marginal) and combination rules

**`pipeline/config/itp_cognitive_profile.yaml`** — SA node input:

- Session duration thresholds: flag at 90min, alert at 150min, critical at 240min
- Hyperfocus indicators: 3+ consecutive exchanges on same sub-topic
- Fatigue markers: increasing terseness, typo frequency, "good enough" language
- Quality degradation: shortening response length, fewer epistemic tags
- Priority drift definition: session objective stated → time spent on lower-priority work
- Bias patterns: known tendency to dismiss RT challenges without new evidence

**`pipeline/config/itp_entity_name_registry.yaml`** — generate from framework data:

```bash
python3 -c "
import yaml
from pathlib import Path
data = yaml.safe_load(open('$ITP_ROOT/framework/data/variables.yaml'))
# Extract entity names and aliases
# Write to pipeline/config/itp_entity_name_registry.yaml
"
```

At minimum: all entity IDs, module codes (ITB-A1 through ITB-A13, ISA sections), observation IDs, scenario IDs.

### Step 2.3 — Create workspace directories

```bash
mkdir -p itp-workspace/rag
mkdir -p itp-workspace/exports
echo "itp-workspace/" >> .gitignore  # already in .gitignore, verify
```

### Step 2.4 — Copy reference docs into repo

```bash
mkdir -p docs/architecture docs/references
cp ~/path/to/ITP_MULTI_AGENT_ARCHITECTURE_v0_5.md docs/architecture/
cp ~/path/to/ROBOTIC-LLM.md docs/references/
```

Note: ROBOTIC-LLM.md path is wherever Hooman has it. Ask if unclear.

---

## Session 3: Loom gap fix + end-to-end validation (Sprint 1, Batch C)

### Step 3.1 — Fix Loom streamable HTTP transport (Gap 1)

**File:** `$ITP_ROOT/loom/src/loom/mcp/server.py`
**Function:** `run_streamable_http()`

Read the current implementation first:

```bash
cat $ITP_ROOT/loom/src/loom/mcp/server.py | grep -A 40 "def run_streamable_http"
```

Replace the stub with a working implementation. The FastMCP library should provide an ASGI app wrapper. Check what's available:

```bash
cd $ITP_ROOT/loom
python3 -c "import mcp.server.fastmcp; help(mcp.server.fastmcp)" 2>/dev/null | head -50
```

If `FastMCP.from_server()` or similar exists, use it. Otherwise use the `mcp.server.streamable_http` module directly. Research the correct pattern from mcp-python documentation.

After fixing, validate:

```bash
cd $ITP_ROOT/baft
loom mcp --config configs/mcp/itp.yaml --transport streamable-http --port 8765 &
sleep 2
curl http://localhost:8765/health
kill %1
```

Commit the fix to the Loom repo separately:

```bash
cd $ITP_ROOT/loom
git add src/loom/mcp/server.py
git commit -m "Fix streamable HTTP MCP transport (was stub, now functional)"
```

### Step 3.2 — End-to-end Tier 1 validation

```bash
cd $ITP_ROOT/baft

# Start infrastructure
nats-server &
valkey-server &
sleep 1

# Start DE worker only (Tier 1 test)
loom worker --config configs/workers/de_database_engineer.yaml --tier local --nats-url nats://localhost:4222 &

# Start MCP gateway (stdio)
# In another terminal, start Claude Code and connect to MCP

# Test via loom CLI submit:
loom submit '{"type": "integration_request", "operations": [{"action": "validate_only", "target": "data/variables.yaml"}]}' \
    --worker-type de_database_engineer \
    --nats-url nats://localhost:4222
```

Expected result: DE returns `integration_result` with `validation_result: PASS`.

### Step 3.3 — End-to-end Tier 2 validation

Start SP + IA + DE workers. Run a test source bundle through the itp_standard pipeline:

```bash
# Create a minimal test source bundle
cat > /tmp/test_source_bundle.yaml << 'EOF'
type: source_bundle
items:
  - url: "https://example.com/test"
    language: en
    source_tier: 3
    retrieval_date: "2026-03-13"
    raw_text: |
      Iranian state media reported that IRGC commanders met with Larijani
      to discuss succession arrangements following the February strikes.
EOF

loom submit "$(cat /tmp/test_source_bundle.yaml)" \
    --worker-type sp_source_processor \
    --nats-url nats://localhost:4222
```

Validate that SP returns `extracted_claims` with properly tagged claims.

### Step 3.4 — Commit initial state

```bash
cd $ITP_ROOT/baft
git init
git add .
git commit -m "Session 1: Initial Baft repository — worker configs, MCP gateway, data layer"
```

---

## Ongoing maintenance rules

- Before every commit: `for f in configs/**/*.yaml; do python3 -c "import yaml; yaml.safe_load(open('$f'))"; done`
- After any worker config change: restart the affected worker process
- After any MCP config change: restart the MCP gateway
- After framework data changes: re-run `python pipeline/scripts/itp_import_to_duckdb.py`
- Terminology registry additions: EP flags in session, Code adds entry with `first_session` and `published` fields
- Watch list additions: Code adds from framework variables + human adds channel_routing manually

## When to stop and ask

- If a Loom API or schema has changed since the architecture was written → check Loom CLAUDE.md
- If a worker config field is undocumented → read `_template.yaml` and `building-workflows.md` in Loom docs
- If an import or dependency conflicts → ask before trying to fix the dependency
- If the streamable HTTP fix requires more than ~100 lines → something is wrong; ask before continuing
