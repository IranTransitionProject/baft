# Local Setup Guide

**Baft v0.3.0 — ITP Analytical Engine**

This guide walks through setting up the complete ITP analytical system
on a local machine. By the end you will have all four repositories cloned,
dependencies installed, services running, and be ready to process your
first analytical session.

---

## Prerequisites

| Requirement | Version | Install |
|---|---|---|
| Python | 3.11+ | [python.org](https://www.python.org/downloads/) or `brew install python@3.13` |
| uv | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Git | 2.x+ | `brew install git` or [git-scm.com](https://git-scm.com/) |
| Docker | 24+ | [Docker Desktop](https://www.docker.com/products/docker-desktop/) (for NATS) |
| Ollama | 0.3+ | [ollama.com](https://ollama.com/) |

**API keys** (for standard and frontier tier workers):

```bash
export ANTHROPIC_API_KEY="sk-ant-..."   # Required for IA, LA, PA, AS, WT, NI workers
```

---

## 1. Clone repositories

All four repos live side-by-side under a common parent directory:

```bash
mkdir -p ~/IranTransitionProject && cd ~/IranTransitionProject

git clone git@github.com:IranTransitionProject/framework.git
git clone git@github.com:IranTransitionProject/loom.git
git clone git@github.com:IranTransitionProject/baft.git
git clone git@github.com:IranTransitionProject/docman.git   # optional
```

Expected layout:

```text
~/IranTransitionProject/          # $ITP_ROOT
├── framework/                    # YAML analytical database (live repo)
├── loom/                         # Actor-based LLM framework
├── baft/                         # ITP application layer
└── docman/                       # Document processing (optional)
```

---

## 2. Install dependencies

Baft resolves loom from the adjacent directory automatically via
`[tool.uv.sources]` in `pyproject.toml` — no manual linking needed.

```bash
# Install loom with all extras
cd ~/IranTransitionProject/loom
uv sync --all-extras

# Install baft
cd ~/IranTransitionProject/baft
uv sync --extra dev

# Verify
uv run python -c "import loom; print(f'Loom {loom.__version__}')"
uv run python -c "import baft; print('Baft OK')"
```

---

## 3. Set environment variables

Add these to your shell profile (`~/.zshrc`, `~/.bashrc`, etc.):

```bash
# ITP project root (parent of framework/, loom/, baft/)
export ITP_ROOT="$HOME/IranTransitionProject"

# Workspace for DuckDB and working files
export BAFT_WORKSPACE="$ITP_ROOT/baft/itp-workspace"

# LLM backends
export ANTHROPIC_API_KEY="sk-ant-..."              # Claude API
export OLLAMA_URL="http://localhost:11434"          # Local Ollama
export OLLAMA_MODEL="llama3.2:3b"                   # Default local model

# Infrastructure
export NATS_URL="nats://localhost:4222"
```

Reload: `source ~/.zshrc`

---

## 4. Pull an Ollama model

The local tier workers (SP, DE, XV, IN, TN, SA) use Ollama for inference:

```bash
ollama pull llama3.2:3b       # Recommended starter model (~2GB)
ollama serve                  # Start if not already running
```

Verify: `curl -s http://localhost:11434/api/tags | python3 -m json.tool`

---

## 5. Start NATS

NATS is the message bus connecting all actors. The simplest path:

```bash
docker run -d --name nats-itp \
  -p 4222:4222 \
  -p 8222:8222 \
  nats:latest --http_port 8222
```

Verify: `curl -s http://localhost:8222/varz | head -5`

---

## 6. Import framework data to DuckDB

The framework repository is a collection of YAML files. The import script
converts them into a queryable DuckDB database:

```bash
cd ~/IranTransitionProject/baft
mkdir -p itp-workspace

# Full import (first time)
uv run python pipeline/scripts/itp_import_to_duckdb.py

# Incremental import (subsequent runs — only changed files)
uv run python pipeline/scripts/itp_import_to_duckdb.py --incremental
```

This creates `itp-workspace/itp.duckdb` used by the DE and query workers.

---

## 7. Start workers

The included script resolves knowledge silo references, starts the router,
and launches all workers:

```bash
# Start router + all Tier 1-2 workers
bash scripts/run_workers.sh

# Or start minimal (Tier 1 only: DE, XV, IN)
bash scripts/run_workers.sh --tier1

# Check status
cat .worker-logs/*.log

# Stop everything
bash scripts/run_workers.sh --stop
```

**What starts:**

| Worker | Tier | Purpose |
|---|---|---|
| Router | — | Deterministic task routing |
| DE | local | Database integration (DuckDB writes) |
| XV | local | Cross-reference validation |
| IN | local | Quick note capture |
| SP | local | Source processing (Tier 2 only) |
| IA | standard | Intelligence analysis (Tier 2 only) |

---

## 8. Connect via MCP (Claude Desktop / Cursor)

The MCP gateway exposes all baft workers and pipelines as tools:

```bash
# stdio transport (for Claude Desktop)
uv run loom mcp --config configs/mcp/itp.yaml

# HTTP transport (for Cursor, web clients)
uv run loom mcp --config configs/mcp/itp.yaml --transport streamable-http --port 8765
```

### Claude Desktop configuration

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "baft": {
      "command": "uv",
      "args": [
        "run", "--project", "/Users/YOU/IranTransitionProject/baft",
        "loom", "mcp", "--config", "configs/mcp/itp.yaml"
      ],
      "env": {
        "ITP_ROOT": "/Users/YOU/IranTransitionProject",
        "ANTHROPIC_API_KEY": "sk-ant-...",
        "OLLAMA_URL": "http://localhost:11434",
        "NATS_URL": "nats://localhost:4222"
      }
    }
  }
}
```

Replace `/Users/YOU/IranTransitionProject` with your actual path.

---

## 9. Run the Workshop (optional)

The Workshop is a web UI for testing workers, running evaluations, comparing
quality baselines, and managing pipeline configurations:

```bash
cd ~/IranTransitionProject/baft
uv run loom workshop --port 8080

# With NATS metrics (optional)
uv run loom workshop --port 8080 --nats-url nats://localhost:4222
```

Open <http://localhost:8080> to access:

- **Worker list** — all 13 workers with tier and status
- **Test bench** — run any worker against sample inputs
- **Eval dashboard** — run test suites, compare against golden baselines
- **Pipeline editor** — view and modify pipeline stage configurations
- **Dead-letter inspector** — browse failed tasks with replay option

Workshop tools are also available as MCP tools (`workshop.worker.test`,
`workshop.eval.run`, etc.) — analysts can use them directly through Claude.
See the [Analyst Guide](ANALYST_GUIDE.md) for details.

---

## 10. Start the TUI dashboard (optional)

The terminal UI shows real-time pipeline execution — goals, tasks, stages,
and all NATS events:

```bash
uv run loom ui --nats-url nats://localhost:4222
```

This is a read-only observer. Keyboard: `q` quit, `c` clear log, `r` refresh.

See the [Operations Guide](OPERATIONS_GUIDE.md) for detailed panel descriptions.

---

## 11. Set up tracing (optional)

For end-to-end distributed tracing across pipeline stages:

```bash
# Start a Jaeger collector (Docker)
docker run -d --name jaeger \
  -p 16686:16686 \
  -p 4317:4317 \
  jaegertracing/jaeger:latest

# Set the endpoint
export OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4317"
```

Traces are visible at <http://localhost:16686>. Search for service `baft-itp`.

Tracing is fully optional — when the OTel SDK is not configured, all
tracing calls are no-ops with zero overhead.

---

## 12. Verify end-to-end

Run the smoke tests to confirm everything is wired correctly:

```bash
cd ~/IranTransitionProject/baft

# Unit tests (no infrastructure needed)
uv run pytest tests/ -v -m "not e2e"

# End-to-end smoke test (needs NATS + workers running)
uv run pytest tests/test_e2e_smoke.py -v
```

---

## Daily workflow

### Before a session

```bash
# Pull latest framework data
cd ~/IranTransitionProject/framework && git pull

# Re-import if framework changed
cd ~/IranTransitionProject/baft
uv run python pipeline/scripts/itp_import_to_duckdb.py --incremental

# Start workers (if not already running)
bash scripts/run_workers.sh
```

### During a session

Use the MCP tools through Claude Desktop or the Workshop web UI.
The standard analytical workflow:

1. **`process_sources`** — Extract claims from source material
2. **`analyze_intelligence`** — Analyze against the framework
3. **`validate_cross_refs`** — Check consistency
4. **`update_database`** — Persist to the framework

Or use the pipeline tools:

- **`run_standard_pipeline`** — Full SP → IA → XV → DE cycle
- **`run_audit_pipeline`** — Blind audit before publication

### After a session

```bash
# Commit framework changes
cd ~/IranTransitionProject/framework
git add -A
git commit -m "Session: [date] — [brief description]"
git push
```

The framework repository is the analytical source of truth. Every
observation, variable assessment, and scenario update should be committed
and pushed after each session.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `NATS not reachable` | `docker start nats-itp` or re-run the docker run command |
| `No LLM backends available` | Check `OLLAMA_URL` and `ANTHROPIC_API_KEY` are set |
| `Worker crashed` | Check logs in `.worker-logs/` — common cause is missing env vars |
| `DuckDB import fails` | Ensure `$ITP_ROOT/framework/data/` exists and has YAML files |
| `MCP connection refused` | Ensure NATS is running and workers are started first |
| `uv sync fails` | Ensure `../loom` directory exists (baft resolves loom from adjacent dir) |

For framework-level troubleshooting, see
[loom/docs/TROUBLESHOOTING.md](../../loom/docs/TROUBLESHOOTING.md).

---

## Architecture overview

```text
Claude Desktop / Cursor
       │ MCP (stdio or HTTP)
       ▼
┌─────────────────┐
│  MCP Gateway    │──── DuckDB queries (itp_search, itp_filter, itp_stats)
│  (loom mcp)     │──── Framework YAML as MCP resources
└────────┬────────┘
         │ NATS
         ▼
┌─────────────────┐    ┌────────────────────────────────┐
│  Router         │───▶│  Workers (13 actors)           │
│  (deterministic)│    │  SP, IA, DE, XV, IN, TN,       │
└─────────────────┘    │  LA, PA, RT, AS, SA, WT, NI    │
         │             └────────────────────────────────┘
         ▼                        │
┌─────────────────┐               ▼
│  Pipeline Orch  │    ┌────────────────────────────────┐
│  Tier 2 / Tier 3│    │  DuckDB        │  Framework    │
└─────────────────┘    │  (itp.duckdb)  │  (YAML/Git)   │
                       └────────────────────────────────┘
```

---

*For Loom framework documentation, see [loom/docs/GETTING_STARTED.md](../../loom/docs/GETTING_STARTED.md).*
*For Kubernetes deployment, see [loom/docs/KUBERNETES.md](../../loom/docs/KUBERNETES.md).*
*For document processing, see [docman/CLAUDE.md](../../docman/CLAUDE.md).*
