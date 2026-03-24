# Helm Deployment Guide

## Overview

The Baft Helm chart deploys the full ITP analytical engine onto Kubernetes. A single `helm install` creates:

- **13 worker pods** (SP, IA, DE, XV, IN, TN, LA, PA, RT, AS, SA, WT, NI) -- each running a Loom worker or processor
- **Router** -- dispatches tasks to workers via NATS subjects
- **3 pipeline orchestrators** -- Quick (Tier 1), Standard (Tier 2), Audit (Tier 3)
- **Scheduler** -- cron-driven actors (WT daily, NI daily, SA every 15 min, etc.)
- **NATS** -- message bus (nats:2.10-alpine)
- **Valkey** -- Redis-compatible checkpoint store
- **Ollama** -- local LLM backend (optional GPU acceleration)
- **DuckDB import CronJob** -- incremental YAML-to-DuckDB import
- **Framework git-sync sidecar** -- keeps the framework repo current on a shared PVC
- **Commit agent** -- auto-commits analytical session changes back to git
- **Workshop UI** -- web interface for worker testing, eval, and config management
- **MCP gateway** -- exposes workers and DuckDB queries as MCP tools
- **Jaeger** (optional) -- distributed tracing UI

## Prerequisites

| Requirement | Minimum |
|---|---|
| kubectl | v1.27+ configured for target cluster |
| helm | v3.12+ |
| Container registry | Pull access to `ghcr.io/irantransitionproject` |
| Kubernetes cluster | 4 CPU / 8 GB RAM (no GPU) or 8 CPU / 16 GB RAM (with Ollama GPU) |

Create the API key secret before installing:

```bash
kubectl create namespace baft

kubectl create secret generic baft-api-keys \
  --namespace baft \
  --from-literal=ANTHROPIC_API_KEY="sk-ant-..."
```

If using SSH-based git sync, also create:

```bash
kubectl create secret generic framework-ssh-key \
  --namespace baft \
  --from-file=id_rsa=$HOME/.ssh/id_rsa_deploy
```

## Quick Start

```bash
# Clone and install with defaults
helm install baft ./charts/baft --namespace baft

# Or override key values inline
helm install baft ./charts/baft --namespace baft \
  --set anthropic.apiKeySecret=baft-api-keys \
  --set ollama.gpu.enabled=true \
  --set workshop.service.type=LoadBalancer
```

Verify the rollout:

```bash
kubectl get pods -n baft
kubectl logs -n baft deployment/router --tail=20
```

## Configuration

All options live in `charts/baft/values.yaml`. Override with `--set` flags or a custom values file (`-f custom.yaml`).

### Framework Git Sync

```yaml
framework:
  repo: "https://github.com/IranTransitionProject/framework.git"
  branch: main
  sshKeySecret: ""          # Secret name with id_rsa key (SSH auth)
  gitTokenSecret: ""        # Secret name with GITHUB_TOKEN (HTTPS auth)
  syncInterval: 60          # Seconds between pulls
  storage: 2Gi              # PVC size for framework checkout
  commitAgent:
    enabled: true
    interval: 900            # 15 min between auto-commits
    message: "Auto-commit: analytical session updates"
```

Set exactly one of `sshKeySecret` or `gitTokenSecret`. Leave both empty only for public repos.

### DuckDB Import Schedule

```yaml
duckdb:
  importSchedule: "*/30 * * * *"   # Cron expression
  storage: 5Gi                      # PVC for DuckDB files
```

The CronJob runs `itp_import_to_duckdb.py --incremental` on the specified schedule.

### LLM Backends

```yaml
anthropic:
  apiKeySecret: baft-api-keys     # Must exist in namespace
  apiKeyField: ANTHROPIC_API_KEY  # Key within the Secret

ollama:
  enabled: true
  model: "llama3.2:3b"
  gpu:
    enabled: false
    type: nvidia               # nvidia or amd
    count: 1
  storage: 10Gi               # PVC for model weights
  externalUrl: ""              # Set when enabled: false (use external Ollama)
```

To use an Ollama instance outside the cluster, set `ollama.enabled: false` and `ollama.externalUrl: "http://ollama-host:11434"`.

### Worker Replicas

```yaml
workers:
  resources:
    requests: { memory: 128Mi, cpu: 100m }
    limits:   { memory: 512Mi, cpu: 500m }
  sp: { replicas: 1 }
  ia: { replicas: 1 }
  de: { replicas: 1 }   # MUST be 1 -- serialized DuckDB writes
  # ... 10 more workers
```

**DE must remain at 1 replica.** It is a Loom processor with `max_concurrent=1` to serialize DuckDB writes. Scaling any other worker is safe.

### Workshop Service

```yaml
workshop:
  enabled: true
  service:
    type: NodePort          # NodePort or LoadBalancer
    port: 8080
    nodePort: 30080         # Only used with NodePort
  ingress:
    enabled: false
    host: workshop.local
    tls: false
```

### MCP Gateway

```yaml
mcp:
  enabled: true
  transport: streamable-http
  port: 8765
  service:
    type: ClusterIP         # ClusterIP, NodePort, or LoadBalancer
```

For Claude Desktop connections from outside the cluster, change to `NodePort` or use `kubectl port-forward`.

### Jaeger Observability

```yaml
jaeger:
  enabled: false            # Set true to deploy Jaeger all-in-one
  image: jaegertracing/jaeger:latest
```

When enabled, the `OTEL_EXPORTER_OTLP_ENDPOINT` env var is automatically set on all pods.

## Framework Git Sync

The chart deploys a git-sync sidecar alongside a shared PVC:

1. **PVC** (`framework-pvc`, size from `framework.storage`) holds the checked-out framework repo.
2. **git-sync container** pulls from `framework.repo` / `framework.branch` every `syncInterval` seconds.
3. **All worker and pipeline pods** mount the PVC at `/data/framework` (the `ITP_ROOT` path).
4. **Commit agent** (when `commitAgent.enabled: true`) runs in a separate container, periodically staging changes, committing, and pushing back to the remote.

Authentication priority:

- `sshKeySecret` -- mounts the Secret as `/root/.ssh/id_rsa` in the sync container
- `gitTokenSecret` -- injects `GITHUB_TOKEN` env var; the sync rewrites the repo URL to `https://x-access-token:$GITHUB_TOKEN@github.com/...`

## GPU Scheduling

To run Ollama with GPU acceleration:

```yaml
ollama:
  enabled: true
  gpu:
    enabled: true
    type: nvidia    # or amd
    count: 1
```

**NVIDIA** -- requires the [NVIDIA device plugin](https://github.com/NVIDIA/k8s-device-plugin) installed on the cluster. The chart requests `nvidia.com/gpu: <count>`.

**AMD** -- requires the [AMD GPU device plugin](https://github.com/ROCm/k8s-device-plugin). The chart requests `amd.com/gpu: <count>`.

Ensure at least one node has the corresponding GPU resource available. Use node labels or taints if GPUs are on dedicated nodes.

## Accessing Services

### Workshop UI

```bash
# NodePort (default)
# Browse to http://<node-ip>:30080

# Port-forward (any service type)
kubectl port-forward -n baft svc/workshop 8080:8080
# Browse to http://localhost:8080
```

### MCP Gateway

```bash
# Port-forward for Claude Desktop / Claude Code
kubectl port-forward -n baft svc/mcp-gateway 8765:8765

# Then configure Claude with:
#   transport: streamable-http
#   url: http://localhost:8765/mcp
```

### Jaeger UI

```bash
kubectl port-forward -n baft svc/jaeger 16686:16686
# Browse to http://localhost:16686
# Filter by service: baft-itp
```

### NATS Monitoring

```bash
kubectl port-forward -n baft svc/nats 8222:8222
# Browse to http://localhost:8222/varz
```

## Troubleshooting

### Secret not found

```text
Error: secret "baft-api-keys" not found
```

Create the secret before installing. It must be in the `baft` namespace:

```bash
kubectl create secret generic baft-api-keys -n baft \
  --from-literal=ANTHROPIC_API_KEY="sk-ant-..."
```

### PVC stuck in Pending

```text
PersistentVolumeClaim is stuck in Pending
```

Your cluster likely lacks a default StorageClass. Check with `kubectl get sc`. Either set a default or specify one in your values override:

```yaml
# custom-values.yaml -- not in the chart, add as needed
# Use your cluster's storage class name
```

For local development clusters (minikube, kind), ensure the default provisioner is enabled.

### Image pull errors

```text
ErrImagePull / ImagePullBackOff
```

Verify registry access:

```bash
kubectl create secret docker-registry ghcr-creds -n baft \
  --docker-server=ghcr.io \
  --docker-username=<github-user> \
  --docker-password=<ghcr-pat>
```

Then add `imagePullSecrets` to your values override.

### Workers CrashLoopBackOff

Check logs for the failing worker:

```bash
kubectl logs -n baft deployment/worker-ia --tail=50
```

Common causes:

- Missing `ANTHROPIC_API_KEY` -- frontier/standard tier workers need it
- NATS not ready -- workers retry connection but crash after exhausting backoff
- Framework PVC not mounted -- check `kubectl describe pod` for volume mount errors

### Ollama model not loading

```bash
kubectl logs -n baft deployment/ollama --tail=30
```

If the model download hangs, the Ollama PVC may be too small. Increase `ollama.storage` (the default `10Gi` handles models up to ~7B parameters).

### DuckDB import failing

```bash
kubectl logs -n baft job/<latest-import-job> --tail=30
```

The import script needs the framework PVC mounted and readable. Verify the CronJob's volume mounts match the git-sync PVC name.
