# Using Baft as an MCP Analytical Engine with Claude Desktop

This guide walks through connecting Baft's multi-agent analytical pipeline to Claude Desktop (macOS or Windows), so that a Claude chat session becomes the human interface (HI-A) to the ITP analytical system.

## How it works

```text
┌─────────────────────┐     MCP (stdio or HTTP)      ┌──────────────────┐
│   Claude Desktop    │ ◄──────────────────────────► │  Heddle MCP Server │
│   (HI-A node)       │                              │  (baft gateway)  │
└─────────────────────┘                              └────────┬─────────┘
                                                              │ NATS bus
                                              ┌───────────────┼───────────────┐
                                              ▼               ▼               ▼
                                         ┌─────────┐   ┌──────────┐   ┌──────────┐
                                         │ Router  │   │ Workers  │   │ DuckDB   │
                                         │         │   │ SP,IA,DE │   │ Queries  │
                                         │         │   │ XV,TN,...│   │          │
                                         └─────────┘   └──────────┘   └──────────┘
```

Claude Desktop connects to the Heddle MCP server, which exposes Baft's workers and pipelines as MCP tools. When you ask Claude to process a source or run an analysis, Claude calls the appropriate tool, which routes through NATS to the right worker, and the structured result flows back into the chat.

**What Claude sees as tools:**

- `process_sources` — Extract claims from raw source material (SP worker)
- `analyze_intelligence` — Analytical assessment against ITP framework (IA worker)
- `update_database` — Persist validated changes to YAML database (DE worker)
- `validate_cross_refs` — Check entity reference consistency (XV worker)
- `submit_input` — Quick note capture for time-sensitive findings (IN worker)
- `run_quick_pipeline` — Tier 1: direct database operation (XV → DE)
- `run_standard_pipeline` — Tier 2: full analytical cycle (SP → IA → XV → DE)
- `run_audit_pipeline` — Tier 3: publication audit with blind review (TN → LA+PA+RT → AS)
- `itp_search`, `itp_filter`, `itp_stats`, `itp_get` — DuckDB entity queries
- `workshop.worker.list`, `workshop.worker.get`, `workshop.worker.update` — Worker config management
- `workshop.worker.test` — Test a worker against a sample payload
- `workshop.eval.run`, `workshop.eval.compare` — Run evaluations and compare against baselines
- `workshop.impact.analyze` — Check which pipelines are affected by a config change
- `workshop.deadletter.list`, `workshop.deadletter.replay` — Dead-letter queue inspection and retry

**What Claude sees as resources:**

- `variables.yaml`, `observations.yaml`, `scenarios.yaml`, `traps.yaml`, `gaps.yaml`, `modules.yaml`, `sessions.yaml` — readable ITP baseline data files

### See also: ITP Telegram MCP gateway

A separate MCP server (`itp-telegram` on `127.0.0.1:8765/mcp/`) exposes
live Telegram capture from 30+ Persian/Arabic/English channels with
bias-weighted search and LLM-backed corroboration analysis. It runs
alongside the main Baft gateway documented here — both can be registered
in `claude_desktop_config.json` simultaneously. See
[Telegram Capture + MCP](TELEGRAM_CAPTURE.md) for setup and tool details.

---

## Prerequisites

### Software

| Requirement | Install | Verify |
|-------------|---------|--------|
| Python 3.11+ | [python.org](https://www.python.org/) or `brew install python@3.11` | `python3 --version` |
| uv | `curl -LsSf https://astral.sh/uv/install.sh \| sh` | `uv --version` |
| NATS server | `brew install nats-server` or Docker | `nats-server --version` |
| Ollama | [ollama.com](https://ollama.com/) | `ollama --version` |
| Claude Desktop | [claude.ai/download](https://claude.ai/download) | Open the app |

### API keys

| Key | For | Get it |
|-----|-----|--------|
| `ANTHROPIC_API_KEY` | IA worker (frontier tier) and audit workers | [console.anthropic.com](https://console.anthropic.com/) |

### Repository layout

All three repos must be siblings in the same parent directory:

```text
ITP_ROOT/               # e.g. ~/Projects/ITP
├── baseline/           # ITP YAML database
│   └── data/
│       ├── variables.yaml
│       ├── observations.yaml
│       └── ...
├── heddle/               # Actor mesh framework
└── baft/               # This repo — ITP application layer
```

---

## Step 1: Install dependencies

```bash
cd /path/to/baft

# Install baft + heddle (heddle resolved from ../heddle automatically)
uv sync --extra dev
```

This creates `.venv/` and installs all dependencies including Heddle as an editable path dependency.

## Step 2: Pull a local model for Ollama

Local-tier workers (SP, DE, XV, IN, TN) use Ollama. Pull the default model:

```bash
ollama pull llama3.2:3b
```

You can use a different model by setting `OLLAMA_MODEL`:

```bash
export OLLAMA_MODEL="llama3.2:3b"   # default
export OLLAMA_MODEL="qwen2.5:7b"    # alternative
```

To test which models work best for each role, use the audition script:

```bash
uv run python scripts/audition_models.py --role de --all-providers
```

## Step 3: Import baseline data to DuckDB

This creates the queryable entity database used by the `itp_search`, `itp_filter`, `itp_stats`, and `itp_get` tools:

```bash
export ITP_ROOT="/path/to/ITP"   # parent of baseline/, heddle/, baft/
uv run python pipeline/scripts/itp_import_to_duckdb.py
```

After initial import, use `--incremental` for updates:

```bash
uv run python pipeline/scripts/itp_import_to_duckdb.py --incremental
```

## Step 4: Set environment variables

Add these to your shell profile (`~/.zshrc`, `~/.bashrc`, etc.):

```bash
# Required
export ANTHROPIC_API_KEY="sk-ant-api03-..."
export ITP_ROOT="/path/to/ITP"

# Optional (defaults shown)
export NATS_URL="nats://localhost:4222"
export OLLAMA_URL="http://localhost:11434"
export OLLAMA_MODEL="llama3.2:3b"
```

---

## Option A: Claude Desktop with stdio transport (recommended)

This is the simplest setup. Claude Desktop spawns the MCP server directly as a child process via stdio. No HTTP, no ports, no network configuration.

### A1. Start the backend (workers + NATS)

The unified script starts NATS, the router, and all workers:

```bash
cd /path/to/baft

# Start everything except MCP (MCP will be spawned by Claude Desktop)
bash scripts/run_workers.sh
```

Verify workers are running:

```bash
# Check process status
cat .worker-pids

# Check NATS health
curl -s http://localhost:8222/varz | python3 -m json.tool
```

### A2. Configure Claude Desktop

Open Claude Desktop's config file:

1. Open Claude Desktop
2. Click **Claude** menu (top menu bar) → **Settings...**
3. Go to **Developer** tab
4. Click **Edit Config**

This opens the config file at:

- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

Add the Baft MCP server configuration:

#### macOS

```json
{
  "mcpServers": {
    "baft": {
      "command": "/path/to/baft/.venv/bin/heddle",
      "args": [
        "mcp",
        "--config",
        "/path/to/baft/configs/mcp/itp.yaml"
      ],
      "env": {
        "ANTHROPIC_API_KEY": "sk-ant-api03-...",
        "ITP_ROOT": "/path/to/ITP",
        "NATS_URL": "nats://localhost:4222",
        "OLLAMA_URL": "http://localhost:11434",
        "OLLAMA_MODEL": "llama3.2:3b"
      }
    }
  }
}
```

#### Windows

```json
{
  "mcpServers": {
    "baft": {
      "command": "C:\\path\\to\\baft\\.venv\\Scripts\\heddle.exe",
      "args": [
        "mcp",
        "--config",
        "C:\\path\\to\\baft\\configs\\mcp\\itp.yaml"
      ],
      "env": {
        "ANTHROPIC_API_KEY": "sk-ant-api03-...",
        "ITP_ROOT": "C:\\path\\to\\ITP",
        "NATS_URL": "nats://localhost:4222",
        "OLLAMA_URL": "http://localhost:11434",
        "OLLAMA_MODEL": "llama3.2:3b"
      }
    }
  }
}
```

**Finding the heddle binary path:**

```bash
# macOS / Linux
which heddle                              # if installed globally
# or use the venv path directly:
echo "$(cd /path/to/baft && pwd)/.venv/bin/heddle"

# Windows (PowerShell)
(Get-Command heddle).Source
# or:
Join-Path (Resolve-Path .\baft\.venv\Scripts) "heddle.exe"
```

### A3. Restart Claude Desktop

Fully quit Claude Desktop (don't just close the window):

- **macOS:** Right-click dock icon → Quit, or Cmd+Q
- **Windows:** Right-click system tray icon → Exit

Reopen Claude Desktop. You should see the MCP tools icon (hammer) in the chat input area. Click it to verify Baft's tools are listed.

### A4. Verify the connection

In a new Claude conversation, try:

> Search for entities related to "IRGC"

Claude should call `itp_search` and return structured results from the DuckDB database.

---

## Option B: Streamable HTTP transport

Use this if:

- You want the MCP server running independently of Claude Desktop
- You're connecting from claude.ai (web) instead of Claude Desktop
- You want to share the MCP server across multiple clients

### B1. Start everything with HTTP

The unified script can start the full stack including an HTTP MCP server:

```bash
cd /path/to/baft
bash scripts/baft.sh start --http
```

This starts: NATS → router → workers → MCP server (HTTP on port 8765).

Verify:

```bash
# Health check
curl http://127.0.0.1:8765/health

# Should return: {"status": "ok", "name": "baft"}
```

### B2a. Connect from Claude Desktop (HTTP)

In `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "baft": {
      "url": "http://127.0.0.1:8765/mcp"
    }
  }
}
```

Restart Claude Desktop after saving.

### B2b. Connect from claude.ai (web)

1. Go to [claude.ai](https://claude.ai/) → Settings → Connectors
2. Scroll to **Add custom connector**
3. Enter the URL: `http://127.0.0.1:8765/mcp`
4. Click **Add**

> **Note:** claude.ai custom connectors require the server to be reachable from your browser. For local development this works if both run on the same machine. For remote access you would need to expose the port (with appropriate authentication — see "Production considerations" below).

### B3. Manage the server

```bash
bash scripts/baft.sh status     # Show running processes
bash scripts/baft.sh logs       # Tail all logs
bash scripts/baft.sh logs ia_intelligence_analyst  # Tail specific worker
bash scripts/baft.sh stop       # Stop everything
```

---

## Option C: Claude Code (CLI)

Claude Code connects to MCP servers via stdio. Add the server to your Claude Code MCP config:

```bash
claude mcp add baft -- /path/to/baft/.venv/bin/heddle mcp --config /path/to/baft/configs/mcp/itp.yaml
```

Or manually in `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "baft": {
      "command": "/path/to/baft/.venv/bin/heddle",
      "args": ["mcp", "--config", "/path/to/baft/configs/mcp/itp.yaml"],
      "env": {
        "ANTHROPIC_API_KEY": "sk-ant-...",
        "ITP_ROOT": "/path/to/ITP",
        "NATS_URL": "nats://localhost:4222"
      }
    }
  }
}
```

Start workers separately (Claude Code spawns only the MCP server, not the workers):

```bash
bash scripts/run_workers.sh
```

---

## Typical analytical workflows

Once connected, here are the common patterns for using Baft through Claude:

### Quick database operation (Tier 1)

> Update the status of variable VAR-042 to "active"

Claude calls `run_quick_pipeline` → XV validates the entity ID → DE writes the change.

### Source analysis cycle (Tier 2)

> Here is a new report from Fars News about IRGC economic activities.
> [paste or attach source text]
> Process this through the standard pipeline.

Claude calls `run_standard_pipeline`:

1. **SP** extracts structured claims with epistemic tags
2. **IA** interprets claims against the analytical framework, produces integration spec
3. **XV** validates all cross-references
4. **DE** persists to the YAML database

### Publication audit (Tier 3)

> Run a publication audit on Brief BR-015 before we publish.

Claude calls `run_audit_pipeline`:

1. **TN** strips ITP-specific terminology for blind review
2. **LA**, **PA**, **RT** run in parallel — each receives only neutralized text
3. **AS** synthesizes findings and produces an integration patch

### Ad-hoc queries

> How many active observations do we have by epistemic tag?

Claude calls `itp_stats` with `group_by: epistemic_tag`.

> Show me all gaps related to nuclear program

Claude calls `itp_search` with `query: "nuclear program"`, `entity_type: "gap"`.

### Direct worker invocation

> Validate these cross-references: ENT-001, ENT-002, ENT-015

Claude calls `validate_cross_refs` directly with the entity list.

---

## Troubleshooting

### Tools not appearing in Claude Desktop

1. **Check the config JSON is valid.** Use a JSON validator. A single trailing comma breaks it.
2. **Verify the heddle binary path.** Run the `command` + `args` manually in a terminal:

   ```bash
   /path/to/baft/.venv/bin/heddle mcp --config /path/to/baft/configs/mcp/itp.yaml
   ```

   You should see no output (it's waiting on stdio). Press Ctrl-C to exit.
3. **Check Claude Desktop logs:**
   - macOS: `~/Library/Logs/Claude/mcp*.log`
   - Windows: `%APPDATA%\Claude\logs\mcp*.log`

   ```bash
   tail -50 ~/Library/Logs/Claude/mcp-server-baft.log
   ```

4. **Ensure NATS is running** before the MCP server starts:

   ```bash
   curl -s http://localhost:8222/varz
   ```

### Tool calls timing out

- Default worker timeout is 60 seconds, pipeline timeout is 300 seconds.
- Check that workers are running: `bash scripts/baft.sh status` or `cat .worker-pids`
- Check worker logs for errors: `bash scripts/baft.sh logs ia_intelligence_analyst`
- Verify Ollama is serving: `curl http://localhost:11434/api/tags`

### "NATS connection refused"

Workers and the MCP server need NATS to be running:

```bash
# Option 1: native
nats-server -p 4222 --http_port 8222 &

# Option 2: Docker
docker run -d --name nats-baft -p 4222:4222 -p 8222:8222 nats:latest --http_port 8222
```

### "Silo not found" warnings

The `resolve_config.py` script expands `silo:` references in worker configs. Ensure `ITP_ROOT` points to the correct directory and that `baseline/data/` exists:

```bash
ls $ITP_ROOT/baseline/data/
```

### Windows-specific issues

- Use forward slashes or escaped backslashes in JSON paths: `"C:/path/to/baft"` or `"C:\\path\\to\\baft"`
- If `heddle.exe` is not found, try using `python` as the command:

  ```json
  {
    "command": "C:\\path\\to\\baft\\.venv\\Scripts\\python.exe",
    "args": ["-m", "heddle.cli.main", "mcp", "--config", "C:\\path\\to\\baft\\configs\\mcp\\itp.yaml"]
  }
  ```

- Ensure NATS is installed or running in Docker Desktop

---

## Monitoring and quality tools

Once connected, you also have access to tools for monitoring and quality management:

### Worker testing and evaluation

Ask Claude to test a worker or run evaluations:

> Test the source processor with this sample text: [text]
>
> Run the eval suite for the intelligence analyst
>
> Compare eval results against the baseline

See the [Analyst Guide](ANALYST_GUIDE.md) for detailed workflows.

### Dead-letter queue

Failed tasks land in the dead-letter queue. Ask Claude:

> Show me the dead-letter queue
>
> Replay dead-letter entry DL-042

### TUI dashboard

For real-time monitoring, open a terminal and run:

```bash
uv run heddle ui --nats-url nats://localhost:4222
```

### Workshop web UI

For hands-on worker management:

```bash
uv run heddle workshop --port 8080
```

See the [Operations Guide](OPERATIONS_GUIDE.md) for technical details.

---

## Production considerations

For deployments beyond local development:

- **Authentication:** The streamable-http transport currently has no authentication. For network-exposed deployments, add a reverse proxy (nginx, Caddy) with TLS and bearer token validation.
- **Process management:** Use `systemd` (Linux), `launchd` (macOS), or a process manager like `supervisord` to keep NATS, workers, and the MCP server running.
- **Monitoring:** NATS exposes metrics at `:8222`. Worker logs are in `.worker-logs/`. Use the TUI dashboard for real-time observation. Set up OpenTelemetry tracing for end-to-end pipeline visibility.
- **Scaling:** Workers use NATS queue groups for competing-consumer load balancing. Start multiple instances of the same worker for horizontal scaling.
- **Quality tracking:** Use eval baselines to detect quality regressions when changing models or prompts.

---

## Quick reference

| Task | Command |
|------|---------|
| Install | `cd baft && uv sync --extra dev` |
| Import DuckDB | `uv run python pipeline/scripts/itp_import_to_duckdb.py` |
| Start everything (stdio) | Workers: `bash scripts/run_workers.sh` + Claude Desktop config |
| Start everything (HTTP) | `bash scripts/baft.sh start --http` |
| Stop everything | `bash scripts/baft.sh stop` |
| Check status | `bash scripts/baft.sh status` |
| View logs | `bash scripts/baft.sh logs [worker_name]` |
| Run tests | `uv run pytest tests/ -v -m "not e2e"` |
| Audition models | `uv run python scripts/audition_models.py --role de --all-providers` |
