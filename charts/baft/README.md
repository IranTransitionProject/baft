# Baft Helm Chart

Deploy the ITP analytical engine (baft + heddle) on Kubernetes.

## Quick start

```bash
# Create API key secret
kubectl create secret generic baft-api-keys \
  --from-literal=ANTHROPIC_API_KEY=sk-ant-...

# Install
helm install baft ./charts/baft

# With custom values
helm install baft ./charts/baft -f my-values.yaml
```

## What gets deployed

| Component | Replicas | Description |
|-----------|----------|-------------|
| NATS | 1 | Message bus |
| Valkey | 1 | Checkpoint store (optional) |
| Framework sync | 1 | git-sync + commit-agent sidecars |
| DuckDB import | CronJob | Incremental import every 30 min |
| Router | 1 | Deterministic task routing |
| Workers (13) | 1 each | SP, IA, DE, XV, IN, TN, LA, PA, RT, AS, SA, WT, NI |
| Pipelines (3) | 1 each | Quick, Standard, Audit |
| Scheduler | 1 | Cron-based task dispatch |
| Workshop | 1 | Web UI for testing and evaluation |
| MCP Gateway | 1 | Streamable HTTP for Claude Chat |
| Ollama | 1 | Local LLM (optional) |
| Jaeger | 1 | Distributed tracing (optional) |

## Key configuration

```yaml
# values.yaml overrides
anthropic:
  apiKeySecret: baft-api-keys     # Must exist before install

ollama:
  enabled: true                    # Set false for external Ollama
  gpu:
    enabled: true                  # Enable GPU scheduling
    type: nvidia

workshop:
  service:
    type: LoadBalancer             # Expose externally

mcp:
  transport: streamable-http
  port: 8765
```

## Constraints

- **DE worker must be replicas: 1** — serialized writes invariant
- **Baseline PVC is ReadWriteOnce** — only baseline-sync writes
- **Workers mount baseline read-only**
- **Secrets must never go in values.yaml**
