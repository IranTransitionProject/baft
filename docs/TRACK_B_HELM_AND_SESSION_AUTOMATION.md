# Track B: Helm Deployment and Session Automation

**Instruction document for Claude Code — v0.3.0 baseline**

This document describes the work to be done across the heddle, baft, and
baseline repositories. It is written as a specification for Claude Code
to execute, not as end-user documentation. Read it fully before starting
any implementation.

---

## Current state (as of 2026-03-23)

### Repository versions

| Repo | Version | Tag | CI | Notes |
|---|---|---|---|---|
| heddle | 0.8.0 | v0.8.0 | Green | MkDocs docs, 90% coverage, 1472 tests |
| baft | 0.3.0 | v0.3.0 | Green | 356 tests, contracts package, DeepEval |
| docman | 0.5.0 | v0.5.0 | Green | MarkItDown + Docling backends |
| baseline  | unversioned | none | Green (validate.yml) | YAML database, 22 modules, 17 briefs |

### Existing infrastructure

- `heddle/docker-compose.yml` — NATS + Valkey + Workshop + Router
- `heddle/docker/` — 4 Dockerfiles (orchestrator, workshop, router, worker)
- `heddle/k8s/` — 8 Kustomize manifests (namespace, NATS, Redis, orchestrator,
  router, worker, workshop, kustomization.yaml)
- `baft/docs/SETUP.md` — Complete local installation guide (12 steps)
- `baft/scripts/run_workers.sh` — Worker launcher script
- `baseline/scripts/setup.sh` — Framework env setup
- `baseline/scripts/watch_session_log.sh` — File watcher for Chat integration

### What does NOT exist yet

- No Helm chart anywhere
- No session start/stop automation (manual `git pull`, manual DuckDB import)
- No framework sync checking during sessions
- No Claude project file for Chat-based session management
- No environment prerequisite checker beyond `heddle preflight`

---

## Part 1: Helm chart for local/cluster deployment

### Goal

`helm install baft ./charts/baft` deploys the entire ITP analytical system
including baseline git sync, DuckDB import, NATS, workers, router,
pipelines, Workshop, and MCP gateway.

### Where to create it

Create `charts/baft/` in the **baft** repository (not heddle). Baft is the
application — heddle is the framework. The chart packages the baft application
deployment.

### Chart structure

```text
charts/baft/
├── Chart.yaml
├── values.yaml
├── templates/
│   ├── _helpers.tpl
│   ├── namespace.yaml
│   ├── secrets.yaml
│   ├── configmap-env.yaml
│   │
│   ├── # Infrastructure
│   ├── nats-deployment.yaml
│   ├── nats-service.yaml
│   ├── valkey-deployment.yaml        # optional (redis checkpoint store)
│   ├── valkey-service.yaml
│   ├── valkey-pvc.yaml
│   │
│   ├── # Framework git sync
│   ├── baseline-pvc.yaml            # PersistentVolumeClaim for baseline clone
│   ├── baseline-sync-deployment.yaml # git-sync + commit-agent sidecars
│   │
│   ├── # DuckDB
│   ├── duckdb-pvc.yaml               # Persistent DuckDB storage
│   ├── duckdb-import-job.yaml         # Initial full import
│   ├── duckdb-import-cronjob.yaml     # Periodic incremental import
│   │
│   ├── # Ollama (optional subchart or external)
│   ├── ollama-deployment.yaml
│   ├── ollama-service.yaml
│   │
│   ├── # Core actors
│   ├── router-deployment.yaml
│   ├── worker-deployment.yaml         # One Deployment per worker (13 total)
│   ├── pipeline-deployment.yaml       # 3 pipeline orchestrators
│   ├── scheduler-deployment.yaml
│   │
│   ├── # User-facing services
│   ├── workshop-deployment.yaml
│   ├── workshop-service.yaml
│   ├── mcp-deployment.yaml
│   ├── mcp-service.yaml
│   │
│   ├── # Optional: observability
│   ├── jaeger-deployment.yaml
│   ├── jaeger-service.yaml
│   │
│   └── # Ingress (optional)
│       └── ingress.yaml
└── README.md                          # Helm chart usage documentation
```

### values.yaml design

```yaml
# -- Global settings
namespace: baft
image:
  registry: ghcr.io/irantransitionproject
  tag: v0.3.0
  pullPolicy: IfNotPresent

# -- Framework git sync
baseline:
  repo: "https://github.com/IranTransitionProject/baseline.git"
  branch: main
  # For SSH: use "git@github.com:IranTransitionProject/baseline.git"
  # and set baseline.sshKeySecret
  sshKeySecret: ""              # K8s Secret name containing id_rsa
  gitTokenSecret: ""            # K8s Secret name containing GITHUB_TOKEN
  syncInterval: 60              # Seconds between git pull
  commitAgent:
    enabled: true
    interval: 900               # Seconds between commit+push (15 min)
    message: "Auto-commit: analytical session updates"

# -- DuckDB import
duckdb:
  importSchedule: "*/30 * * * *"  # Incremental import every 30 min
  storage: 5Gi

# -- LLM backends
anthropic:
  apiKeySecret: baft-api-keys     # K8s Secret name
  apiKeyField: ANTHROPIC_API_KEY

ollama:
  enabled: true
  model: "llama3.2:3b"
  image: ollama/ollama:latest
  gpu:
    enabled: false
    type: nvidia                  # nvidia or amd
    count: 1
  storage: 10Gi                   # Model storage PVC
  # External Ollama (when enabled: false)
  externalUrl: ""                 # e.g. "http://ollama.internal:11434"

# -- NATS
nats:
  image: nats:2.10-alpine
  monitoring: true                # Enable HTTP monitoring on :8222

# -- Valkey (Redis-compatible checkpoint store)
valkey:
  enabled: true
  image: valkey/valkey:8-alpine
  storage: 1Gi

# -- Workers
workers:
  # Default resource limits (override per-worker below)
  resources:
    requests:
      memory: 128Mi
      cpu: 100m
    limits:
      memory: 512Mi
      cpu: 500m
  # Per-worker settings
  sp: { replicas: 1 }
  ia: { replicas: 1 }             # Frontier tier — expensive
  de: { replicas: 1 }             # MUST be 1 (serialize_writes)
  xv: { replicas: 1 }
  in: { replicas: 1 }
  tn: { replicas: 1 }
  la: { replicas: 1 }
  pa: { replicas: 1 }
  rt: { replicas: 1 }             # Frontier tier — expensive
  as: { replicas: 1 }
  sa: { replicas: 1 }
  wt: { replicas: 1 }
  ni: { replicas: 1 }

# -- Router
router:
  replicas: 1

# -- Pipeline orchestrators
pipelines:
  quick: { enabled: true, replicas: 1 }
  standard: { enabled: true, replicas: 1 }
  audit: { enabled: true, replicas: 1 }

# -- Scheduler
scheduler:
  enabled: true

# -- Workshop UI
workshop:
  enabled: true
  replicas: 1
  service:
    type: NodePort
    port: 8080
    nodePort: 30080
  ingress:
    enabled: false
    host: workshop.local
    tls: false

# -- MCP Gateway
mcp:
  enabled: true
  transport: streamable-http
  port: 8765
  service:
    type: ClusterIP

# -- Observability
jaeger:
  enabled: false
  image: jaegertracing/jaeger:latest

# -- Environment (injected into all pods)
env:
  ITP_ROOT: /data/baseline
  BAFT_WORKSPACE: /data/workspace
  NATS_URL: nats://nats:4222
```

### Framework sync architecture

Use the official `registry.k8s.io/git-sync/git-sync:v4` container image.

**Deployment: baseline-sync**

```text
Pod:
  initContainer: git-sync (one-shot clone)
  containers:
    - git-sync (continuous pull every syncInterval seconds)
    - commit-agent (cron loop: git add -A && git diff --cached --quiet || git commit && git push)
  volumes:
    - baseline-data PVC (ReadWriteOnce)
```

Workers mount the baseline PVC as read-only via `subPath`. The DE worker
and DuckDB import job also mount it read-only — they write to the DuckDB
PVC, not to the baseline volume.

**The commit-agent sidecar** is a minimal shell script:

```bash
#!/bin/sh
while true; do
  sleep $COMMIT_INTERVAL
  cd /data/baseline
  git add -A
  if ! git diff --cached --quiet; then
    git commit -m "$COMMIT_MESSAGE — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    git push || echo "Push failed — will retry next cycle"
  fi
done
```

Mount git credentials from the Secret specified in `baseline.sshKeySecret`
or `baseline.gitTokenSecret`.

### Container images needed

The existing Dockerfiles in `heddle/docker/` need to be adapted for baft.
Create new Dockerfiles in `baft/docker/`:

```text
baft/docker/
├── Dockerfile.worker       # Base worker image (heddle + baft installed)
├── Dockerfile.router       # Router image
├── Dockerfile.pipeline     # Pipeline orchestrator image
├── Dockerfile.workshop     # Workshop UI image
├── Dockerfile.mcp          # MCP gateway image
├── Dockerfile.import       # DuckDB import job image
└── Dockerfile.commit-agent # Git commit sidecar (alpine + git)
```

All application images should:

1. Start from `python:3.12-slim`
2. Install uv
3. Copy heddle source and install it
4. Copy baft source and install it
5. Copy configs/ directory
6. Set ENTRYPOINT to the appropriate `heddle` CLI command

The commit-agent image is just `alpine/git` with the shell script above.

### Implementation order

1. Create `charts/baft/Chart.yaml` and `values.yaml`
2. Create `templates/_helpers.tpl` with standard label/selector helpers
3. Create infrastructure templates (NATS, Valkey, secrets, configmap)
4. Create baseline-sync templates (PVC, deployment with git-sync + commit-agent)
5. Create DuckDB templates (PVC, import job, import cronjob)
6. Create worker templates (one Deployment per worker, parameterized from values)
7. Create router, pipeline, scheduler templates
8. Create Workshop and MCP templates
9. Create optional Ollama and Jaeger templates
10. Create Dockerfiles in `baft/docker/`
11. Test with `helm template` (dry-run validation)
12. Test with `helm install --dry-run`
13. Document in `charts/baft/README.md`

### Key constraints

- **DE must be replicas: 1** — serialize_writes is a hard invariant
- **Baseline PVC must be ReadWriteOnce** — only the baseline-sync pod writes
- **Workers mount baseline as read-only** — via volumeMount.readOnly: true
- **DuckDB PVC is ReadWriteOnce** — only DE and import jobs write to it
- **Ollama needs GPU scheduling** if gpu.enabled: true — use
  `nvidia.com/gpu` or `amd.com/gpu` resource requests
- **Secrets must never be in values.yaml** — always reference K8s Secrets
- **All images tagged with baft version** — not `latest`

---

## Part 2: Session automation

### Goal

Automate the repetitive parts of starting and ending analytical sessions:

1. **Session start**: pull baseline, check for upstream changes, incremental
   DuckDB import, verify services, register session
2. **Session end**: commit baseline changes, push, unregister session
3. **During session**: periodically check if baseline remote has new commits
   (someone else pushed), warn the analyst

### Implementation: `heddle session` CLI commands

Add to `baft/src/baft/cli.py` (new file) or extend heddle's CLI via a plugin.

**Preferred approach**: Create a `baft` CLI that wraps heddle commands and adds
session automation. This keeps baft-specific logic out of heddle.

```text
baft session start [--session-id NAME]
baft session end [--message "description"]
baft session status
baft session sync-check
```

#### `baft session start`

1. `cd $ITP_ROOT/baseline && git pull --ff-only`
   - If pull fails (merge conflict), warn and abort
2. `cd $ITP_ROOT/baft && uv run python pipeline/scripts/itp_import_to_duckdb.py --incremental`
3. Run `heddle preflight` equivalent checks:
   - NATS reachable at $NATS_URL
   - Ollama reachable at $OLLAMA_URL
   - ANTHROPIC_API_KEY is set and non-empty
   - DuckDB file exists at $BAFT_WORKSPACE/itp.duckdb
   - Framework directory exists at $ITP_ROOT/baseline/data/
4. Register session: `baft.sessions.register_session(session_id)`
5. Print summary: "Session started. Framework at commit [hash]. DuckDB
   updated. All services reachable."

#### `baft session end`

1. Unregister session: `baft.sessions.unregister_session(session_id)`
2. `cd $ITP_ROOT/baseline`
3. `git add -A`
4. If there are changes:
   - `git commit -m "Session [session_id]: [message] — [date]"`
   - `git push`
   - Print: "Framework changes committed and pushed."
5. If no changes:
   - Print: "No baseline changes to commit."

#### `baft session status`

1. Show active sessions from `baft.sessions.get_active_sessions()`
2. Show baseline git status (clean/dirty, current commit, behind remote?)
3. Show service health (NATS, Ollama, DuckDB file age)

#### `baft session sync-check`

1. `cd $ITP_ROOT/baseline && git fetch origin --quiet`
2. Compare `HEAD` with `origin/main`:
   - If behind: warn "Framework has N new commits from remote. Run
     `baft session sync` to pull and re-import."
   - If ahead: info "You have N local commits not yet pushed."
   - If diverged: warn "Framework has diverged from remote. Manual
     resolution needed."
   - If up-to-date: "Framework is current."

This command should be callable on a schedule (see Part 3 below).

#### `baft session sync`

1. `git pull --ff-only` (abort if conflict)
2. `uv run python pipeline/scripts/itp_import_to_duckdb.py --incremental`
3. Print: "Synced to [commit]. DuckDB updated."

### Implementation details

Create these files:

```text
baft/src/baft/cli.py          # Click CLI group with session commands
baft/pyproject.toml            # Add [project.scripts] baft = "baft.cli:main"
baft/tests/test_session_cli.py # Tests for session commands
```

The CLI should use Click (already a heddle dependency). Each command should
be testable with `click.testing.CliRunner`.

Environment checks should use `heddle.cli.preflight` internals where possible
rather than reimplementing them.

Git operations should use `subprocess.run(["git", ...])` with proper error
handling — do NOT use gitpython or any git library. Keep it simple.

---

## Part 3: Claude Chat project setup for session management

### Goal

When an analyst opens a Claude Chat project that points at the ITP repos,
Claude should be able to:

1. Guide them through session start (or do it automatically via MCP)
2. Periodically check for baseline sync during the session
3. Help them commit and push at session end

### Claude project file

Create `baft/.claude/project.md` (or wherever Claude projects read from)
with instructions that tell Claude Chat how to manage sessions.

**Important**: Claude Chat does NOT have direct CLI access. It works through
MCP tools. The session automation must be exposed as MCP tools so Chat can
invoke them.

### New MCP tools for session management

Add these tools to the baft MCP gateway config (`configs/mcp/itp.yaml`):

```yaml
tools:
  workshop:
    # ... existing workshop tools ...
  session:
    enable: [start, end, status, sync_check, sync]
```

And implement them in heddle's MCP workshop bridge or as a new session bridge:

```text
session.start       — Pull baseline, import DuckDB, check services, register
session.end         — Commit baseline, push, unregister
session.status      — Active sessions, git status, service health
session.sync_check  — Check if remote baseline has new commits
session.sync        — Pull baseline + incremental DuckDB import
```

These tools call the same logic as the `baft session` CLI commands.

### Claude Chat instructions

Create `baft/docs/CLAUDE_CHAT_SESSION_INSTRUCTIONS.md`:

```markdown
# ITP Session Management — Instructions for Claude

You are assisting an ITP analyst. The analytical system runs on the Loom
framework with 13 specialized workers connected via NATS.

## At session start

When the analyst starts a new session or says they want to begin work:

1. Call `session.start` to initialize the session
2. If any checks fail, report them clearly and suggest fixes
3. Confirm: "Session [id] is active. Framework is at [commit].
   All services are operational."

## During the session

Every 15 minutes (or when the analyst asks), call `session.sync_check`:

- If the baseline has new remote commits, tell the analyst:
  "The baseline has been updated by another session. Would you like
  me to sync now, or continue with the current version?"
- If they say yes, call `session.sync`

## At session end

When the analyst says they're done or wants to end the session:

1. Ask: "Would you like me to commit the baseline changes from this
   session? If so, please provide a brief description."
2. Call `session.end` with their message
3. Confirm the commit hash and that push succeeded

## Prerequisites to verify

Before any session operations, verify:

- The MCP connection to the baft server is active (you can call tools)
- The `session.*` tools are available in the tool list
- If tools are missing, tell the analyst: "The session management tools
  are not available. Please ensure the MCP server is running with
  `uv run heddle mcp --config configs/mcp/itp.yaml`"

## Error handling

- If `session.start` reports NATS is unreachable: "NATS is not running.
  Start it with: `docker start nats-itp`"
- If `session.start` reports Ollama is unreachable: "Ollama is not
  running. Start it with: `ollama serve`"
- If `session.end` push fails: "Push failed — this usually means
  the remote has new commits. Let me check..." then call sync_check
- If framework has diverged: "The baseline has diverged from remote.
  This needs manual resolution. Open a terminal and run
  `cd $ITP_ROOT/baseline && git status` to see the conflict."
```

### Claude project configuration

The analyst's Claude project should have:

1. **Project instructions** that point to the session management doc
2. **MCP server connection** to the baft MCP gateway
3. **Knowledge files** (optional): ANALYST_GUIDE.md, SETUP.md

The project instructions file should be minimal — just bootstrap to the
full instructions:

```markdown
# ITP Analytical Engine

This project connects to the ITP analytical system via MCP.

## Setup

Ensure the MCP server is running:
`uv run heddle mcp --config configs/mcp/itp.yaml --transport streamable-http --port 8765`

## Session management

Follow the instructions in `docs/CLAUDE_CHAT_SESSION_INSTRUCTIONS.md`
for session start, sync checking, and session end procedures.

## Available tools

- `itp.*` — Analytical pipeline tools (process sources, analyze, validate, update)
- `workshop.*` — Worker testing, evaluation, config management
- `session.*` — Session lifecycle (start, end, status, sync)
- DuckDB query tools — Search and filter the analytical database
```

---

## Part 4: Environment prerequisite checker

### Goal

A single command that validates the entire environment is ready for
analytical work, with clear fix instructions for each failure.

### Implementation

Extend `baft session start` (and the `session.start` MCP tool) to run
a comprehensive check. But also make it available standalone:

```bash
baft preflight
```

**Checks (in order):**

1. **Python version** — >= 3.11
2. **uv installed** — `which uv`
3. **Repos present** — $ITP_ROOT/baseline, $ITP_ROOT/heddle, $ITP_ROOT/baft exist
4. **Dependencies installed** — `uv run python -c "import heddle; import baft"`
5. **Environment variables** — ITP_ROOT, BAFT_WORKSPACE, ANTHROPIC_API_KEY set
6. **NATS reachable** — TCP connect to $NATS_URL
7. **Ollama reachable** — HTTP GET $OLLAMA_URL/api/tags
8. **Ollama model present** — Expected model in tag list
9. **DuckDB file exists** — $BAFT_WORKSPACE/itp.duckdb
10. **DuckDB not stale** — mtime < 24 hours (warn if older)
11. **Framework git clean** — no uncommitted changes (warn only)
12. **Framework not behind remote** — `git fetch && git rev-list --count HEAD..origin/main`

Output format:

```text
ITP Preflight Check
───────────────────
[OK] Python 3.12.4
[OK] uv 0.6.3
[OK] Repos: baseline, heddle, baft
[OK] Dependencies installed
[OK] Environment variables set
[OK] NATS reachable (localhost:4222)
[OK] Ollama reachable (localhost:11434)
[OK] Ollama model: llama3.2:3b
[OK] DuckDB exists (14.2 MB, updated 2h ago)
[WARN] Framework has uncommitted changes (3 files)
[OK] Framework up-to-date with remote

11/12 checks passed, 1 warning
```

---

## Implementation sequence

### Phase 1: Session CLI + preflight (do first)

1. Create `baft/src/baft/cli.py` with Click commands
2. Add `[project.scripts]` entry in pyproject.toml
3. Implement `baft preflight`
4. Implement `baft session start/end/status/sync-check/sync`
5. Write tests with CliRunner
6. Update CLAUDE.md

### Phase 2: Session MCP tools

1. Create `heddle/src/heddle/mcp/session_bridge.py` (or extend workshop_bridge)
2. Add session tool discovery to `workshop_discovery.py`
3. Wire into MCP server dispatch
4. Write tests
5. Update configs/mcp/itp.yaml

### Phase 3: Claude Chat project setup

1. Create `baft/docs/CLAUDE_CHAT_SESSION_INSTRUCTIONS.md`
2. Create project instructions file
3. Test with Claude Chat + MCP connection
4. Document in SETUP.md

### Phase 4: Helm chart

1. Create `charts/baft/` structure
2. Implement templates (infrastructure → baseline-sync → workers → services)
3. Create Dockerfiles in `baft/docker/`
4. Test with `helm template` dry-run
5. Test with local k8s (minikube or Docker Desktop Kubernetes)
6. Document in `charts/baft/README.md`
7. Add CI step to lint the Helm chart (`helm lint`)

### Phase 5: Container images + CI

1. Set up GitHub Container Registry (ghcr.io) publishing
2. Add GitHub Actions workflow for building and pushing images
3. Tag images with baft version
4. Update Helm chart to reference published images

---

## Testing strategy

### Session CLI tests

Test with `click.testing.CliRunner`. Mock:

- `subprocess.run` for git commands
- `baft.sessions` for register/unregister
- Network checks (NATS, Ollama) with socket mocks

### Session MCP tool tests

Follow the pattern in `tests/test_mcp_workshop_bridge.py`:

- Mock the session bridge components
- Test each tool action
- Test error paths (NATS down, git conflict, etc.)

### Helm chart tests

- `helm lint charts/baft/`
- `helm template baft charts/baft/ -f values.yaml` (dry-run)
- Validate generated YAML with `kubeval` or `kubeconform`
- Optionally: `helm test` with a simple connectivity check

---

## Files to create (summary)

### In baft/

```text
src/baft/cli.py                                  # Session CLI commands
docker/Dockerfile.worker                          # Worker container image
docker/Dockerfile.router                          # Router container image
docker/Dockerfile.pipeline                        # Pipeline orchestrator image
docker/Dockerfile.workshop                        # Workshop UI image
docker/Dockerfile.mcp                             # MCP gateway image
docker/Dockerfile.import                          # DuckDB import job image
docker/Dockerfile.commit-agent                    # Git commit sidecar
charts/baft/Chart.yaml                            # Helm chart metadata
charts/baft/values.yaml                           # Default configuration
charts/baft/README.md                             # Helm usage guide
charts/baft/templates/_helpers.tpl                # Template helpers
charts/baft/templates/*.yaml                      # ~20 template files
docs/CLAUDE_CHAT_SESSION_INSTRUCTIONS.md          # Chat session management guide
tests/test_session_cli.py                         # CLI tests
```

### In heddle/

```text
src/heddle/mcp/session_bridge.py                    # Session MCP tool dispatch
```

### Files to modify

```text
baft/pyproject.toml          # Add [project.scripts] baft = "baft.cli:main"
baft/CLAUDE.md               # Document session CLI, Helm chart
baft/docs/SETUP.md           # Add session automation section
heddle/src/heddle/mcp/workshop_discovery.py  # Add session tool definitions
heddle/src/heddle/mcp/server.py              # Wire session bridge
baft/configs/mcp/itp.yaml               # Add session tool group
```

---

## Key decisions already made

1. **Framework is a live git clone** — not a static artifact. Analysts commit
   to it regularly. This is the source of truth for all analytical data.

2. **Dead-letter MCP tools are opt-in** — The in-memory consumer is not wired
   to live NATS in the MCP path. Tools exist but only operate on locally
   stored entries. Explicitly documented as a limitation.

3. **DE must always be replicas: 1** — serialize_writes is a design invariant.
   This constraint must be enforced in the Helm chart values validation.

4. **Audit independence is config-enforced** — LA, PA, RT, AS, TN, SA have
   restricted knowledge_sources. The Helm chart must mount baseline data
   read-only and must NOT change silo mappings.

5. **Session management goes through MCP** — Claude Chat cannot run CLI
   commands directly. All session operations must be available as MCP tools
   for Chat to invoke them.

6. **Baft CLI wraps heddle** — Session commands are baft-specific, not
   baseline-level. The `baft` CLI is a thin wrapper that calls heddle
   internals + baft session logic.
