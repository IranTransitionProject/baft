# Analyst Guide — Working with Baft

**Audience:** ITP analysts using Baft through Claude Desktop, Claude Code, or the Workshop web UI. No programming knowledge required.

---

## What Baft does for you

Baft is the engine behind your analytical workflow. When you chat with Claude and ask it to process a source, run an analysis, or update the database, Baft handles the structured work behind the scenes. It:

- **Extracts factual claims** from source material (news articles, Telegram channels, reports)
- **Analyzes claims** against the ITP analytical framework (variables, scenarios, traps, gaps)
- **Validates** cross-references and consistency before writing changes
- **Persists** validated results to the YAML database
- **Audits** publication-bound analysis through blind review (three independent reviewers)
- **Monitors** your session quality and cognitive load
- **Scans** watch list items and narrative patterns daily

You interact with Baft through Claude. Claude sees Baft's capabilities as tools it can call on your behalf.

---

## Your tools

When Claude is connected to Baft, it has access to these tools:

### Direct worker tools

| Tool | What it does | When to use |
|------|-------------|-------------|
| `process_sources` | Extracts structured claims from raw text | When you have new source material to process |
| `analyze_intelligence` | Produces analytical output (observations, variable assessments, scenario updates) | After source processing, or for standalone analysis |
| `update_database` | Writes validated changes to the YAML database | After analysis produces an integration spec |
| `validate_cross_refs` | Checks entity IDs, module codes, and relationship consistency | Before database commits |
| `submit_input` | Captures a quick note or observation for later processing | Time-sensitive findings that need immediate capture |

### Pipeline tools (recommended for most work)

| Tool | Stages | When to use |
|------|--------|-------------|
| `run_quick_pipeline` | XV validate -> DE write | Simple field updates, status changes, formatting fixes |
| `run_standard_pipeline` | SP -> IA -> XV -> DE | New source integration, variable updates, gap analysis |
| `run_audit_pipeline` | TN -> [LA + PA + RT] -> AS | Before publishing any brief or major thesis revision |

### Query tools

| Tool | What it does |
|------|-------------|
| `itp_search` | Full-text search across all entities |
| `itp_filter` | Filter entities by type, status, confidence, epistemic tag |
| `itp_stats` | Aggregate statistics (counts by type, status, tag) |
| `itp_get` | Get a single entity by ID |

### Workshop tools (for tuning and evaluation)

These tools let you manage worker configurations, test workers, and track quality:

| Tool | What it does |
|------|-------------|
| `workshop.worker.list` | List all worker configs with name and tier |
| `workshop.worker.get` | View a worker's full configuration |
| `workshop.worker.update` | Update a worker's system prompt or settings |
| `workshop.worker.test` | Test a worker against a sample payload |
| `workshop.eval.run` | Run an evaluation suite against a worker |
| `workshop.eval.compare` | Compare eval results against a quality baseline |
| `workshop.impact.analyze` | See which pipelines are affected by changing a worker |
| `workshop.deadletter.list` | View failed/unroutable tasks |
| `workshop.deadletter.replay` | Retry a failed task |

---

## Common workflows

### Processing new source material (Tier 2)

This is the most common workflow. You have a new report, article, or Telegram message to integrate.

**What to say to Claude:**

> Here is a new report from [source]. Process this through the standard pipeline.
>
> [paste or attach source text]

**What happens behind the scenes:**

1. **SP** (Source Processor) extracts factual claims with epistemic tags (Fact, Inference, Uncertain, Speculation)
2. **IA** (Intelligence Analyst) analyzes claims against the framework, produces observations, variable assessments, and an integration spec
3. **XV** (Cross-Validator) checks that all entity references are valid and consistent
4. **DE** (Database Engineer) writes the validated changes to the YAML database

If IA flags the analysis as publication-ready, Baft automatically escalates to a Tier 3 audit.

**What can go wrong and what to do:**

| Symptom | Cause | What to do |
|---------|-------|------------|
| SP produces few or no claims | Source text too short or ambiguous | Ask Claude to show SP's raw output; provide more context |
| XV fails validation | Entity IDs don't match existing records | Review the entity refs in IA's output; correct and resubmit |
| Pipeline times out | Worker or LLM backend overloaded | Wait a minute and try again; check with your tech support |

### Quick database update (Tier 1)

For simple changes that don't need full analysis — status updates, formatting fixes, adding a note to an existing observation.

**What to say to Claude:**

> Update the status of variable VAR-042 to "active"

or

> Add this observation to OBS-100: "Recent reporting confirms continued activity"

**What happens:** XV validates the entity reference, then DE writes the change directly.

### Publication audit (Tier 3)

Before publishing a brief or making a major thesis revision, run a blind audit. Three independent reviewers examine a neutralized version of your analysis.

**What to say to Claude:**

> Run a publication audit on Brief BR-015 before we publish.

**What happens:**

1. **TN** (Terminology Neutralizer) strips ITP-specific terms so reviewers can't identify the framework
2. **LA** (Logic Auditor) checks logical reasoning and argument structure
3. **PA** (Perspective Auditor) evaluates for perspective bias and blind spots
4. **RT** (Red Teamer) challenges core claims and looks for alternative explanations
5. **AS** (Audit Synthesizer) merges all three reviews into an actionable report

All three reviewers run in parallel and are completely blind — they cannot see the ITP framework, only the neutralized text.

**Reading the audit report:**

The report includes:
- **Overall verdict:** Pass, Pass with Revisions, or Escalate
- **Logic findings:** Gaps in reasoning, unsupported claims, circular arguments
- **Perspective findings:** Bias indicators, missing viewpoints, assumptions
- **Red team challenges:** Each with a strength score (1-10); scores >= 8 trigger escalation
- **Integration patch:** Suggested changes to the original analysis

### Querying the database

You can search, filter, and get statistics about entities at any time.

**Examples:**

> How many active observations do we have by epistemic tag?

> Show me all gaps related to nuclear program

> What is the current status of entity ENT-042?

> Find all variables with confidence below 0.5

---

## Improving worker quality

Over time you may want to tune how workers behave — adjusting their instructions, testing with different inputs, or comparing quality across model changes.

### Testing a worker

Ask Claude to test a worker with a specific input:

> Test the source processor with this sample text: [text]

Claude calls `workshop.worker.test` and returns the worker's output along with timing, token usage, and schema validation results.

### Running an evaluation suite

An eval suite is a set of test cases with known expected outputs. Running one shows you how well a worker performs:

> Run the eval suite for the source processor

Claude calls `workshop.eval.run` and returns scores for each test case. Scoring methods:
- **Field match** — checks that specific output fields contain expected values
- **Exact match** — checks for exact output equality
- **LLM judge** — uses a separate LLM to evaluate quality on correctness, completeness, and format

### Comparing against a baseline

After establishing a "golden" eval run as your quality baseline, you can compare new runs against it to detect regressions:

> Compare this eval run against the baseline for the source processor

This shows per-case improvements and regressions, helping you catch quality degradation before it affects your work.

### Checking change impact

Before changing a worker's configuration, check what else it affects:

> What pipelines would be affected if I change the intelligence analyst?

Claude calls `workshop.impact.analyze` and shows you which pipelines use that worker, which downstream stages depend on it, and the risk level (high if downstream stages exist).

---

## Monitoring and debugging

### The TUI dashboard

If you have a terminal available, you can watch pipeline execution in real time:

```bash
uv run loom ui --nats-url nats://localhost:4222
```

This shows four panels:
- **Goals** — active pipeline goals, their status, and how long they've been running
- **Tasks** — individual worker tasks, which model tier is handling them, elapsed time
- **Pipeline** — stage-by-stage execution with wall time per stage
- **Events** — scrolling log of all system messages

**Keyboard shortcuts:** `q` to quit, `c` to clear the event log, `r` to refresh

The TUI is read-only — it observes what's happening but never changes anything. Safe to run alongside production work.

### Failed tasks (dead-letter queue)

Sometimes tasks fail — a worker times out, an LLM produces invalid output, or a network glitch interrupts communication. These failed tasks land in the dead-letter queue.

**Viewing failed tasks:**

> Show me the dead-letter queue

Claude calls `workshop.deadletter.list` and shows you each failed task with:
- What worker it was intended for
- Why it failed
- When it failed

**Retrying a failed task:**

> Replay dead-letter entry DL-042

Claude calls `workshop.deadletter.replay`, which re-submits the task to the router. Every replay is recorded in the audit trail for governance reviews.

### Pipeline reliability

Baft automatically retries failed pipeline stages:
- **Local tier** workers (SP, XV, TN, DE) retry up to **2 times** — these use fast local models, so retries are cheap
- **Standard and frontier tier** workers (IA, LA, PA, RT, AS) retry up to **1 time** — these use expensive API calls, so retries are conservative
- Only **transient failures** are retried (timeouts, temporary errors). If a worker produces output that fails schema validation, it won't be retried — that's a configuration issue, not a transient failure

### The Workshop web UI

For more hands-on worker management, you can use the Workshop web interface:

```bash
uv run loom workshop --port 8080
```

Open http://localhost:8080 in your browser. The Workshop provides:
- **Worker list** — all 13 workers with their tier, description, and status
- **Test bench** — test any worker with custom inputs and see full outputs
- **Eval dashboard** — run evaluation suites, compare against baselines, track quality over time
- **Pipeline editor** — view and modify pipeline stage configurations
- **Dead-letter inspector** — browse failed tasks with full details

---

## Understanding the tier system

Every analytical task runs at a specific tier, which determines the LLM model used:

| Tier | Model | Cost | Speed | Used for |
|------|-------|------|-------|----------|
| Local | Ollama (llama3.2:3b) | Free | Fast (3-7s) | SP, DE, XV, IN, TN, SA — mechanical tasks |
| Standard | Claude Sonnet | Moderate | Medium (5-15s) | LA, PA, AS, WT, NI — analytical tasks |
| Frontier | Claude Opus | High | Slower (10-30s) | IA, RT — complex reasoning tasks |

The system automatically selects the right tier for each worker. You don't need to think about this — it's handled by the worker configurations.

---

## Understanding epistemic tags

Every claim extracted from source material gets an epistemic tag:

| Tag | Meaning | Confidence band |
|-----|---------|-----------------|
| **Fact** | Directly observable or verifiable | 0.8 - 1.0 |
| **Inference** | Logically derived from known facts | 0.5 - 0.8 |
| **Uncertain** | Plausible but unverified | 0.3 - 0.5 |
| **Speculation** | Hypothetical, requires significant assumptions | 0.0 - 0.3 |

These tags flow through the entire pipeline — from SP's extraction through IA's analysis to DE's database writes. They help you and the audit system assess the reliability of analytical conclusions.

---

## Daily routine

### Before your session

1. **Pull latest framework data** (if others have been working):
   ```bash
   cd ~/IranTransitionProject/framework && git pull
   ```
2. **Update DuckDB** (if framework changed):
   ```bash
   cd ~/IranTransitionProject/baft
   uv run python pipeline/scripts/itp_import_to_duckdb.py --incremental
   ```
3. **Start workers** (if not already running):
   ```bash
   bash scripts/run_workers.sh
   ```

### During your session

Work through Claude as described above. The standard pattern:
1. Process sources (Tier 2 pipeline)
2. Review IA's output for accuracy
3. Confirm or reject XV's validation
4. Commit approved changes to the framework

### After your session

```bash
cd ~/IranTransitionProject/framework
git add -A
git commit -m "Session: [date] — [brief description]"
git push
```

The framework repository is the analytical source of truth. Every session's work should be committed and pushed.

---

## Getting help

| Problem | Who to ask | What to tell them |
|---------|-----------|-------------------|
| Claude doesn't see Baft tools | Tech support | "MCP tools not appearing" — they'll check the config |
| Worker produces wrong output | Review the system prompt | Use `workshop.worker.get` to see current config |
| Pipeline keeps timing out | Tech support | Which pipeline, what input, and the error message |
| Quality has degraded | Run an eval comparison | Use `workshop.eval.compare` against your baseline |
| Need to change how a worker behaves | Use `workshop.worker.update` or ask tech support | Describe what output you expect vs. what you're getting |

For detailed technical troubleshooting, see the [Operations Guide](OPERATIONS_GUIDE.md).

For connection setup, see the [Claude Desktop Guide](CLAUDE_DESKTOP_GUIDE.md).
