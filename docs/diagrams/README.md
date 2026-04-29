# Diagram sources

`.drawio` files in this directory are the source of truth for architecture
and concept diagrams. CI auto-exports them to SVG on every change.

## How it works

- `.drawio` files in this directory are exported to SVG by CI
  (`.github/workflows/build-diagrams.yml`)
- Exported SVGs land in `docs/images/` with `--embed-diagram` so they are
  re-openable in draw.io
- Edit `.drawio` files in draw.io desktop or the web editor at
  <https://app.diagrams.net>

## Adding a new diagram

1. Create or save the diagram as `docs/diagrams/<name>.drawio`
2. Open a PR — the workflow exports `docs/images/<name>.svg` and commits it
3. Reference the SVG from docs as `![Caption](images/<name>.svg)`

## Existing diagrams

| File | Description |
|------|-------------|
| `three-repo-architecture.drawio` | How Baseline, Heddle, and Baft fit together |
| `pipeline-data-flow.drawio` | Standard, audit, and quick orchestrator paths |
| `worker-map.drawio` | All 13 worker nodes and their relationships |
| `silo-isolation.drawio` | Knowledge silo boundaries and data flow |
| `analyst-workflow.drawio` | End-to-end analyst session via HI-A |
| `telegram-capture.drawio` | Telegram ingestion pipeline architecture |
| `pipeline-orchestration-bpmn.drawio` | Pipeline orchestration in BPMN 2.0 notation (foreshadows executable workflows) |
