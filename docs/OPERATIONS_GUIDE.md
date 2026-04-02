# Operations Guide — Baft Technical Reference

**Audience:** Technical staff supporting ITP analysts. Covers observability, troubleshooting, performance tuning, and advanced configuration.

![Worker Map](images/worker-map.svg)

![Pipeline Data Flow](images/pipeline-data-flow.svg)

![Deployment Architecture](images/deployment-architecture.svg)

---

## Architecture overview

```text
Claude Desktop / Claude Code / Workshop UI
       | MCP (stdio or HTTP)
       v
+------------------+
|  MCP Gateway     |--- DuckDB queries (itp_search, itp_filter, itp_stats, itp_get)
|  (loom mcp)      |--- Framework YAML as MCP resources
|                  |--- Workshop tools (worker CRUD, test bench, eval, impact, dead-letter)
+--------+---------+
         | NATS (localhost:4222)
         v
+------------------+    +----------------------------------+
|  Router          |--->|  Workers (13 actors)             |
|  (deterministic) |    |  SP, IA, DE, XV, IN, TN,         |
+------------------+    |  LA, PA, RT, AS, SA, WT, NI      |
         |              +----------------------------------+
         v                          |
+------------------+                v
|  Pipeline Orch   |    +----------------------------------+
|  Tier 2 / Tier 3 |    |  DuckDB        |  Framework      |
+------------------+    |  (itp.duckdb)  |  (YAML/Git)     |
                        +----------------------------------+
```

All communication between components flows through NATS. The only exceptions are:

- Workshop tools (direct component calls, no NATS needed)
- DuckDB queries (direct database access)
- MCP resources (direct file reads)

---

## Observability stack

### 1. Distributed tracing (OpenTelemetry)

Baft integrates with OpenTelemetry for end-to-end pipeline visibility.

**Setup with Jaeger (local development):**

```bash
# Start Jaeger all-in-one (Docker)
docker run -d --name jaeger \
  -p 16686:16686 \
  -p 4317:4317 \
  njaegertracing/jaeger:latest

# Set the collector endpoint
export OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4317"
```

**Initialize tracing in baft:**

```python
from baft.tracing import init_baft_tracing
init_baft_tracing()  # reads OTEL_EXPORTER_OTLP_ENDPOINT from env
```

**What gets traced:**

| Component | Span name | Attributes |
|-----------|-----------|------------|
| BaseActor | `actor.process_one` | `worker_type`, `task_id`, `model_tier` |
| TaskRouter | `router.route` | `worker_type`, `tier`, `subject` |
| PipelineOrchestrator | `pipeline.execute_stage` | `stage_id`, `worker_type`, `attempt` |
| MCPBridge | `mcp.dispatch_and_wait` | `tool_name`, `timeout` |
| OrchestratorActor | `orchestrator.decompose`, `.dispatch`, `.collect`, `.synthesize` | `goal_id` |
| LLMWorker | `worker.execute_with_tools` | `model`, `round`, `tokens`, `gen_ai.system`, `gen_ai.request.model`, `gen_ai.response.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens` |

**Trace context propagation:**

- W3C `traceparent` headers are injected into NATS messages under `_trace_context`
- Spans link across actor boundaries for full pipeline traces
- A single Tier 2 pipeline run produces ~6-8 connected spans

**Viewing traces:**
Open <http://localhost:16686> and search for service `baft-itp`. Filter by operation name (e.g., `pipeline.execute_stage`) to find specific pipeline runs.

**When OTel is not installed:**
All tracing functions degrade to no-ops. No performance impact, no errors. You can safely leave tracing calls in production code without the OTel SDK installed.

### 2. I/O debug logging (LOOM_TRACE)

For detailed input/output logging without full OTel:

```bash
export LOOM_TRACE=1
```

This logs the full payload for every message sent and received by actors. Large payloads are truncated by default. Useful for debugging schema mismatches and data flow issues.

**When to use LOOM_TRACE vs. OTel:**

- Use `LOOM_TRACE` for debugging a specific worker's input/output
- Use `LOOM_TRACE_CONTENT=1` to record prompt/completion text as OTel span events (pairs with full OTel tracing)
- Use OTel for understanding timing and flow across an entire pipeline

### 3. TUI dashboard (real-time monitoring)

```bash
uv run loom ui --nats-url nats://localhost:4222
```

**Panels:**

| Panel | Shows | Key columns |
|-------|-------|-------------|
| Goals | Active pipeline goals | status, subtask count, elapsed time |
| Tasks | Individual worker tasks | worker type, tier, model, elapsed |
| Pipeline | Stage execution within pipelines | stage name, wall time, status |
| Events | Scrolling log of all `loom.>` NATS messages | timestamp, subject, summary |

**Keyboard shortcuts:** `q` quit, `c` clear log, `r` refresh tables

The TUI subscribes to `loom.>` wildcard and never publishes. It's a pure observer — safe to run alongside production actors at any time.

**What to look for:**

- Tasks stuck in "running" for longer than `timeout_seconds` — potential LLM backend issues
- Goals with 0 subtasks — decomposition may have failed
- Pipeline stages showing repeated attempts — retries are firing (check the stage's max_retries)
- Events with `dead_letter` in the subject — tasks are being rejected by the router

### 4. NATS monitoring

NATS exposes HTTP monitoring at port 8222:

```bash
# Connection count
curl -s http://localhost:8222/varz | python3 -c "import sys,json; print(json.load(sys.stdin)['connections'])"

# Subscription count
curl -s http://localhost:8222/subsz | python3 -m json.tool

# Slow consumers
curl -s http://localhost:8222/connz?sort=msgs_to | python3 -m json.tool
```

### 5. Worker logs

```bash
# All worker logs
bash scripts/baft.sh logs

# Specific worker
bash scripts/baft.sh logs ia_intelligence_analyst

# Direct log file access
ls .worker-logs/
cat .worker-logs/sp_source_processor.log
```

---

## Retry configuration

All pipeline stages have automatic retry for transient failures.

### Current retry settings

| Pipeline | Stage | Worker | Tier | max_retries |
|----------|-------|--------|------|-------------|
| itp_standard | source_process | SP | local | 2 |
| itp_standard | analyze | IA | frontier | 1 |
| itp_standard | cross_validate | XV | local | 2 |
| itp_standard | db_write | DE | local | 1 |
| itp_audit | neutralize | TN | local | 2 |
| itp_audit | logic_audit | LA | standard | 1 |
| itp_audit | perspective_audit | PA | standard | 1 |
| itp_audit | red_team | RT | frontier | 1 |
| itp_audit | synthesize | AS | standard | 1 |
| itp_quick | xv_validate | XV | local | 2 |
| itp_quick | de_write | DE | local | 1 |

### What gets retried

Only transient errors trigger retries:

- **Timeout** — worker didn't respond within `timeout_seconds`
- **Worker error** — LLM returned malformed JSON, connection dropped
- **NATS delivery failure** — message couldn't be delivered

What does NOT get retried:

- **Validation error** — output failed schema validation (this is a config issue)
- **Pipeline mapping error** — input_mapping references a missing field
- **Condition failure** — stage condition evaluated to false

### Tuning retries

Edit the pipeline YAML config to adjust `max_retries` per stage:

```yaml
stages:
  - id: source_process
    worker: sp_source_processor
    max_retries: 3          # increase for flaky backends
```

**Guidelines:**

- Local tier (Ollama): 2-3 retries is safe — fast and free
- Standard tier (Sonnet): 1-2 retries — moderate cost
- Frontier tier (Opus): 1 retry only — expensive per call
- DE writes: keep at 1 — retrying a write can cause duplicates if the first write partially succeeded

---

## Dead-letter queue

Tasks that can't be routed (wrong worker_type, tier not available) or that fail all retries land in the dead-letter queue.

### Inspecting dead letters

**Via MCP tools:**

```text
workshop.deadletter.list  — returns all dead-letter entries with reason and timestamp
```

**Via CLI:**

```bash
uv run loom dead-letter monitor --nats-url nats://localhost:4222
```

**Via Workshop UI:**
Navigate to <http://localhost:8080/dead-letters>

### Replaying a dead letter

**Via MCP tools:**

```text
workshop.deadletter.replay  — re-submits the task to the router
```

Every replay is recorded in the audit trail (`ReplayRecord`) with:

- Original task details
- Original failure reason
- Replay timestamp
- Who triggered the replay

This audit trail is inspected during the weekly governance audit (GA).

### Common dead-letter causes

| Reason | Fix |
|--------|-----|
| `unknown_worker_type` | Worker name in pipeline config doesn't match any worker YAML file |
| `no_backends_available` | LLM backend for that tier is down (Ollama not running, API key expired) |
| `rate_limited` | Too many concurrent requests for that tier — wait and retry |
| `timeout_after_retries` | Worker consistently too slow — check LLM backend health |
| `validation_failed` | Worker output doesn't match output_schema — fix the worker config |

---

## Evaluation and quality baselines

### Running evaluations

Eval suites are sets of test cases (input + expected output) that measure worker quality.

```bash
# Via Workshop web UI
http://localhost:8080/workers/{name}/eval

# Via MCP tool
workshop.eval.run  with worker name + test suite
```

**Scoring methods:**

| Method | How it works | Best for |
|--------|-------------|----------|
| `field_match` | Checks specific output fields for expected values | SP, DE, XV — mechanical outputs |
| `exact_match` | Full output equality | TN — deterministic neutralization |
| `llm_judge` | Separate LLM call evaluates quality (0-1 scale) | IA, LA, PA, RT — analytical quality |

### Baselines and regression detection

**Setting a baseline:**

1. Run an eval suite and confirm the results are acceptable
2. Promote that run as the golden baseline:

   ```text
   WorkshopDB.promote_baseline(worker_name, run_id)
   ```

   Or use the Workshop UI "Promote to baseline" button.

**Comparing against baseline:**

1. Run a new eval (after changing a system prompt, switching models, etc.)
2. Compare against the baseline:

   ```text
   workshop.eval.compare  with worker name + new run_id
   ```

3. Results show per-case regression/improvement analysis

**When to set a new baseline:**

- After confirming that a system prompt change improves quality
- After switching to a new LLM model (and verifying quality)
- After the weekly governance audit confirms acceptable quality
- Never during a production session — only during dedicated tuning sessions

### Config impact analysis

Before changing a worker config, check what breaks:

```text
workshop.impact.analyze  with worker name
```

Returns:

- **Pipelines affected** — which pipelines use this worker
- **Direct stages** — which pipeline stages call this worker
- **Downstream stages** — what depends on this worker's output
- **Risk level** — "high" if downstream stages exist (output format changes will break them)

**Example:** Changing SP's output schema is high-risk because IA, XV, and DE all consume SP's output downstream in the standard pipeline.

---

## Troubleshooting

### Pipeline failures

| Symptom | Investigation | Resolution |
|---------|-------------|------------|
| Pipeline hangs indefinitely | Check TUI for stuck tasks; check NATS connectivity | Restart the stuck worker; verify NATS is running |
| Stage fails with `PipelineValidationError` | Check stage input/output schemas; enable `LOOM_TRACE=1` | Fix schema mismatch in worker config |
| Stage fails with `PipelineTimeoutError` | Check worker logs for slow LLM responses | Increase `timeout_seconds` or switch to faster model |
| Stage fails with `PipelineMappingError` | Input mapping references a field that doesn't exist in upstream output | Fix `input_mapping` paths in pipeline config |
| Audit pipeline returns partial results | One or more audit nodes failed (LA/PA/RT use `continue_partial`) | Check dead-letter queue for the failed auditor |

### Worker issues

| Symptom | Investigation | Resolution |
|---------|-------------|------------|
| Worker produces empty output | Check `LOOM_TRACE=1` for raw LLM response | System prompt may be too long or unclear |
| Worker produces non-JSON output | Check worker logs for parse errors | Add explicit JSON instructions to system prompt |
| Worker always returns same response | Check `reset_after_task: true` in config | Ensure stateless (no conversation memory) |
| Worker fails schema validation | Compare output against `output_schema_ref` | Fix system prompt to match expected output structure |
| Worker is very slow | Check token usage in test bench results | Reduce system prompt size; switch to faster model |

### Infrastructure issues

| Symptom | Investigation | Resolution |
|---------|-------------|------------|
| "NATS not reachable" | `curl http://localhost:8222/varz` | Start NATS: `docker start nats-itp` or `nats-server &` |
| "No LLM backends available" | Check `OLLAMA_URL` and `ANTHROPIC_API_KEY` | Start Ollama: `ollama serve`; verify API key |
| DuckDB query returns empty | Check `itp-workspace/itp.duckdb` exists | Run import: `uv run python pipeline/scripts/itp_import_to_duckdb.py` |
| MCP tools not appearing | Check Claude Desktop MCP logs | Verify config JSON syntax; restart Claude Desktop |
| Workshop won't start | Check port conflicts | Use different port: `loom workshop --port 8081` |

### Tracing issues

| Symptom | Investigation | Resolution |
|---------|-------------|------------|
| "Failed to export traces" in stderr | OTel collector not running | Start Jaeger or set correct `OTEL_EXPORTER_OTLP_ENDPOINT` |
| No spans in Jaeger | Tracing not initialized | Call `init_baft_tracing()` at startup; check service name `baft-itp` |
| Spans missing across actor boundaries | `_trace_context` not propagating | Check NATS message format; verify W3C traceparent injection |
| Tracing slows down workers | Exporter batching too aggressive | Tune `BatchSpanProcessor` settings or disable tracing |

---

## Configuration reference

### Environment variables

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `ITP_ROOT` | Yes | — | Parent directory of framework/, loom/, baft/ |
| `ANTHROPIC_API_KEY` | For standard/frontier tier | — | Claude API access |
| `OLLAMA_URL` | For local tier | `http://localhost:11434` | Ollama endpoint |
| `OLLAMA_MODEL` | No | `llama3.2:3b` | Default local model |
| `NATS_URL` | Yes | `nats://localhost:4222` | NATS server |
| `REDIS_URL` | No | `redis://localhost:6379` | Valkey (for checkpoints) |
| `BAFT_WORKSPACE` | No | `$ITP_ROOT/baft/itp-workspace` | Working directory |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | No | — | OTel collector (e.g., `http://localhost:4317`) |
| `LOOM_TRACE` | No | — | Set to `1` for full I/O debug logging |
| `LOOM_TRACE_CONTENT` | No | — | Set to `1` to record prompt/completion text in OTel span events |

### Key configuration files

| File | Purpose | Edit frequency |
|------|---------|---------------|
| `configs/workers/*.yaml` | Worker system prompts, I/O schemas, tiers | Occasional (tuning) |
| `configs/orchestrators/*.yaml` | Pipeline stages, dependencies, retries | Rare |
| `configs/schedulers/itp.yaml` | Scheduled tasks (cron, intervals) | Rare |
| `configs/mcp/itp.yaml` | MCP gateway tool exposure | Rare |
| `configs/knowledge/itp_silos.yaml` | Knowledge silo path mappings | When adding new silos |
| `pipeline/config/*.yaml` | Domain data (watch list, tier rules, etc.) | Regular (analyst-driven) |

### NATS subject conventions

| Subject | Purpose |
|---------|---------|
| `loom.tasks.incoming` | Router picks up new tasks |
| `loom.tasks.{worker_type}.{tier}` | Routed tasks for specific workers |
| `loom.tasks.dead_letter` | Failed/unroutable tasks |
| `loom.results.{goal_id}` | Results back to orchestrators |
| `loom.results.default` | Results from standalone tasks |
| `loom.goals.incoming` | Pipeline goals for orchestrators |
| `loom.control.reload` | Config hot-reload signal |
| `loom.scheduler.{name}` | Scheduler health-check |

---

## Silo isolation verification

The audit independence guarantee depends on correct knowledge silo configuration. To verify:

```bash
# Run the silo isolation tests
uv run pytest tests/test_baft_workers.py::TestSiloIsolation -v
```

This checks:

- LA, PA, RT have NO access to framework silos
- TN has ONLY terminology_registry + constitution
- AS has NO framework content
- SA has NO analytical framework

If any test fails, the audit independence is compromised. Do not run publication audits until the isolation is restored.

**Critical invariant:** Audit nodes (LA, PA, RT) must never see the ITP framework. They receive only TN-neutralized text. This is enforced by the silo configuration in each worker's YAML file and validated by the test suite.

---

## Performance tuning

### Common bottlenecks

1. **LLM response time** — the biggest factor. Local models (Ollama) are 3-7s, API calls are 5-30s.
2. **Pipeline sequential stages** — Tier 2 has 4 sequential stages, each waiting for the previous one.
3. **DuckDB import** — full import can take 30-60s for large framework datasets.
4. **NATS message serialization** — negligible for normal payloads, can matter for very large source bundles.

### Scaling options

**Horizontal (no code changes):**

```bash
# Run 3 SP workers for parallel source processing
uv run loom worker --config configs/workers/sp_source_processor.yaml --tier local &
uv run loom worker --config configs/workers/sp_source_processor.yaml --tier local &
uv run loom worker --config configs/workers/sp_source_processor.yaml --tier local &
```

NATS queue groups ensure each task goes to exactly one worker instance.

**Concurrent goals:**
Pipelines support `max_concurrent_goals: 4` (already configured). Multiple analysts can work simultaneously.

**Model selection:**

| Model | Speed | Quality | Cost |
|-------|-------|---------|------|
| `llama3.2:3b` | Fastest | Good for mechanical tasks | Free |
| `command-r7b:latest` | Fast | Best local JSON compliance | Free |
| `qwen2.5:7b` | Medium | Good analytical quality | Free |
| Claude Sonnet | Medium | High quality | Moderate |
| Claude Opus | Slow | Highest quality | High |

---

## LLM quality evaluation tests (DeepEval)

### Purpose

DeepEval tests provide standardized, repeatable quality metrics for analytical outputs. They use a local Ollama model as judge to evaluate whether pipeline outputs meet quality criteria -- complementing (not replacing) the operational eval baselines in Workshop.

### Setup

```bash
# Install the eval extra
uv sync --extra eval

# Ensure Ollama is running with the judge model
ollama pull command-r7b:latest
ollama serve
```

DeepEval telemetry is disabled by default via `tests/conftest.py`.

### Running eval tests

```bash
# Run only DeepEval tests
uv run pytest tests/ -m deepeval -v

# Skip DeepEval tests (default for CI / quick iteration)
uv run pytest tests/ -m "not deepeval"

# Run the specific eval test file
uv run pytest tests/test_deepeval_analysis.py -v
```

Tests are automatically skipped if `deepeval` is not installed or Ollama is not reachable.

### Available metrics

| Metric | Tests | What it measures |
|--------|-------|------------------|
| Claim Extraction Quality | `test_sp_claim_extraction` | SP extracts factual claims with correct epistemic tags and source attribution |
| Synthesis Faithfulness | `test_as_synthesis_faithfulness` | AS synthesis faithfully represents audit inputs without hallucination |

### Writing new eval tests

1. Add a `GEval` metric fixture with criteria, evaluation steps, and threshold
2. Create a test case with `input` (source material) and `actual_output` (pipeline output)
3. Use `assert_test(test_case, [metric])` to run the evaluation
4. Mark with `pytestmark = [pytest.mark.deepeval, skip_no_deepeval]`

All eval tests use `command-r7b:latest` via Ollama as judge -- no cloud API keys required.

---

*For analyst-facing guidance, see the [Analyst Guide](ANALYST_GUIDE.md).*
*For initial setup, see the [Setup Guide](SETUP.md).*
*For Claude Desktop connection, see the [Claude Desktop Guide](CLAUDE_DESKTOP_GUIDE.md).*
*For Loom framework troubleshooting, see [loom/docs/TROUBLESHOOTING.md](../../loom/docs/TROUBLESHOOTING.md).*
