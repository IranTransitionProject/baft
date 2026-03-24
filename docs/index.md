# Baft

**ITP analytical engine — application layer on the Loom framework.**

Baft provides ITP-specific worker configurations, pipeline definitions, knowledge silo mappings, and utility scripts for the multi-agent intelligence analysis system.

## Quick start

```bash
# Install dependencies (requires Python 3.11+)
uv sync --extra dev

# Run unit tests
uv run pytest tests/ -v -m "not e2e and not deepeval"

# Build docs locally
uv sync --extra docs
uv run mkdocs serve
```

## Pipeline tiers

| Tier | Config | Flow | Use case |
|------|--------|------|----------|
| **Quick** | `itp_quick.yaml` | Single worker dispatch | DE updates, XV checks, IN capture |
| **Standard** | `itp_standard.yaml` | SP → IA → XV → DE | Full source analysis |
| **Audit** | `itp_audit.yaml` | TN → [LA + PA + RT] → AS | Independent audit cycle |

## Workers

Baft configures 13 workers across three batches:

- **Core (Tier 1–2):** SP, IA, DE, XV, IN
- **Audit (Tier 3):** TN, LA, PA, RT, AS
- **Background:** SA, WT, NI

## Project links

- [📘 Baft documentation](https://irantransitionproject.github.io/baft/) (this site)
- [Loom framework docs](https://irantransitionproject.github.io/loom/)
- [GitHub repository](https://github.com/IranTransitionProject/baft)
