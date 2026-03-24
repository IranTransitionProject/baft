# Claude Chat Project Setup

Instructions for configuring a Claude Chat (claude.ai) project to connect
to the ITP analytical system via MCP.

## 1. Start the MCP server

The MCP server must be running before Claude Chat can connect:

```bash
# From the baft directory
uv run loom mcp --config configs/mcp/itp.yaml --transport streamable-http --port 8765
```

Or use the convenience script:

```bash
bash scripts/run_mcp_server.sh --http --port 8765
```

## 2. Create a Claude project

1. Go to [claude.ai](https://claude.ai) → Projects → New Project
2. Name it "ITP Analytical Engine" (or similar)

## 3. Add MCP server connection

In the project settings, add an MCP server:

- **URL**: `http://localhost:8765/mcp`
- **Name**: `baft`

If connecting from a remote machine, replace `localhost` with the
server's hostname or IP.

## 4. Set project instructions

Paste the following into the project's "Custom Instructions" field:

---

You are assisting an ITP analyst. The analytical system runs on the Loom
framework with 13 specialized workers connected via NATS.

Follow the instructions in the connected knowledge file
`CLAUDE_CHAT_SESSION_INSTRUCTIONS.md` for session management procedures
(start, sync, end) and error handling.

Available tool namespaces:
- `process_sources`, `analyze_intelligence`, `validate_cross_refs`,
  `update_database`, `submit_input` — Core analytical tools
- `run_standard_pipeline`, `run_quick_pipeline`, `run_audit_pipeline` — Pipelines
- `session.*` — Session lifecycle (start, end, status, sync_check, sync)
- `workshop.*` — Worker testing, evaluation, config management
- `entities_*` — DuckDB entity search and queries

At session start, call `session.start` to initialize. Every 15 minutes,
call `session.sync_check` to check for remote updates. At session end,
ask the analyst for a description and call `session.end`.

---

## 5. Add knowledge files (optional)

Upload these docs as project knowledge for richer context:

- `docs/CLAUDE_CHAT_SESSION_INSTRUCTIONS.md` — Session management procedures
- `docs/ANALYST_GUIDE.md` — Non-technical analyst guide
- `docs/OPERATIONS_GUIDE.md` — Technical operations reference

## 6. Verify

Start a conversation in the project and ask Claude to call
`session.status`. It should return active sessions and service health.
If tools aren't available, check that the MCP server is running
and the connection URL is correct.
