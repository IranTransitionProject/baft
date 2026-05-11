# Telegram Capture + MCP Gateway

This guide covers the live Telegram capture service and its MCP gateway —
the pipeline that turns 30+ Persian/Arabic/English channels into a
queryable RAG store with bias-weighted analysis tools, exposed to ITP
Chat (Claude) over MCP HTTP.

The whole subsystem lives in `baft/src/baft/itp_telegram/` and is driven
by `baft itp-telegram` CLI commands. It runs alongside the rest of Baft
(no shared NATS, no shared Workshop) and stores its own DuckDB at
`~/.heddle/itp_rag.duckdb`.

## Architecture

```text
                                    ┌──────────────────────────┐
                                    │  ITP Chat (claude.ai)    │
                                    │  ITP Code (Claude Desk)  │
                                    └─────────────┬────────────┘
                                                  │ MCP / HTTP
                                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│   baft itp-telegram serve   (single long-lived asyncio process)     │
│                                                                     │
│   ┌─────────────────────────┐         ┌───────────────────────────┐ │
│   │ Capture loop            │         │ FastMCP HTTP server       │ │
│   │ (Telethon NewMessage)   │         │ :8765/mcp/                │ │
│   │   ├─ buffer (deque)     │         │  ├─ search_posts          │ │
│   │   ├─ flush every 5 min  │         │  ├─ recent_posts          │ │
│   │   ├─ chunk_post()       │         │  ├─ list_channels         │ │
│   │   └─ embed → DuckDB     │         │  ├─ stats                 │ │
│   └────────────┬────────────┘         │  ├─ corroboration_check   │ │
│                │                      │  └─ capture_status        │ │
│                ▼                      └─────────────┬─────────────┘ │
│       ┌───────────────────────┐                     │               │
│       │ DuckDB vector store   │ ◄───────────────────┘               │
│       │ ~/.heddle/itp_rag...  │                                     │
│       └───────────────────────┘                                     │
└─────────────────────────────────────────────────────────────────────┘
                          │                              ▲
                          ▼                              │
                ┌──────────────────────┐    ┌────────────────────────┐
                │ LM Studio (host)     │    │ MTProto (Telethon)     │
                │ /v1/embeddings       │    │ to api.telegram.org    │
                │ /v1/chat/completions │    │                        │
                └──────────────────────┘    └────────────────────────┘
```

Both halves share an asyncio event loop, so the MCP `capture_status` tool
sees live counters from the capture loop without any IPC.

## Prerequisites

| Requirement | Install / Verify |
|---|---|
| LM Studio running with an embedding model loaded | Default: `text-embedding-nomic-embed-text-v1.5` at `http://localhost:1234/v1` |
| LM Studio non-thinking analyzer model loaded | Default: `google/gemma-4-26b-a4b` (or any non-thinking model that fits in your loaded context window) |
| Telegram API credentials | [my.telegram.org](https://my.telegram.org) → "API development tools" → grab `api_id` and `api_hash` |
| `~/.heddle/.env` (mode 600) | See "First-time setup" |
| `baft` on PATH | `ln -s $ITP_ROOT/baft/.venv/bin/baft ~/.local/bin/baft` (or `uv tool install`) |

## First-time setup

### 1. Credentials in `~/.heddle/.env`

```bash
# mode 600 — readable only by you
chmod 700 ~/.heddle
cat > ~/.heddle/.env <<'EOF'
# Telegram (https://my.telegram.org)
TELEGRAM_API_ID=<your numeric api_id>
TELEGRAM_API_HASH=<your 32-char hex>
TELEGRAM_PHONE=+1XXXXXXXXXX
TELEGRAM_SESSION=/Users/<you>/.heddle/telegram.session

# LM Studio
LM_STUDIO_URL=http://localhost:1234/v1
HEDDLE_LOCAL_BACKEND=lmstudio
HEDDLE_EMBEDDING_BACKEND=openai-compatible
EOF
chmod 600 ~/.heddle/.env
```

Add this to `~/.zshrc` so every shell picks it up:

```bash
if [ -f "$HOME/.heddle/.env" ]; then
    set -a; . "$HOME/.heddle/.env"; set +a
fi
```

### 2. Telethon phone authentication

```bash
baft itp-telegram auth
```

Walks you through the Telegram phone-code (and 2FA, if enabled) flow.
Persists a session token at `$TELEGRAM_SESSION`. Treat that file like
an SSH private key — `chmod 600`, no cloud sync, no commits (covered
by `*.session*` in `baft/.gitignore`).

### 3. Resolve channel handles to numeric IDs

```bash
baft itp-telegram resolve-ids
```

Reads `baft/pipeline/config/itp_telegram_channels.yaml` (the
analyst-curated registry), takes every channel with
`monitoring_priority` in `{critical, high}`, asks Telegram for the
numeric channel ID of each handle, and writes the result to
`~/.heddle/itp_channel_ids.json`. Failures (handle drift, deleted
channels, account-restricted channels) are listed in the `failed:`
field and skipped at runtime — they don't block startup.

The numeric IDs are required for bias enrichment (the `corroboration_check`
analyzer and search-result trust-weighting all key off `channel_id`).

## Running the service

### Detached daemon (recommended on this machine)

```bash
baft itp-telegram daemon start         # detaches via subprocess.Popen(start_new_session=True)
baft itp-telegram daemon status        # PID + MCP health + capture counters
baft itp-telegram daemon log -f        # follow log
baft itp-telegram stop                 # graceful SIGTERM (drains buffer)
```

The daemon process is reparented to PID 1 (init), so it survives:

- This shell exiting
- Claude Desktop / Claude Code restarts
- Any descendant terminal closing

It does **not** survive logout or reboot — re-run `daemon start` after.

### Foreground (dev / debug)

```bash
baft itp-telegram serve --flush-interval 60 -v
# Ctrl-C drains the buffer and shuts down cleanly.
```

### launchd (auto-start at login + crash recovery)

```bash
baft itp-telegram daemon install       # writes ~/Library/LaunchAgents/com.itp.telegram.plist
baft itp-telegram daemon restart       # launchctl kickstart -k
baft itp-telegram daemon uninstall
```

**macOS TCC pre-check.** The installer spawns a one-shot launchd probe
that tries to read `pyvenv.cfg` through the venv's actual python
interpreter — exactly what the daemon would do at startup. If Full Disk
Access is already granted, the probe passes and installation proceeds
even on `/Volumes/`. If the probe fails, the installer refuses with
three workarounds:

1. **Use `daemon start` instead** (inherits TCC from your terminal — works today, no reboot survival)
2. **Grant FDA to your venv's python interpreter** (System Settings → Privacy & Security → Full Disk Access → Cmd+Shift+G → paste the path the installer prints, then re-run install)
3. **Move the project to an internal-disk path** (cleanest long-term)

To skip the probe entirely: `SKIP_TCC_CHECK=1 baft itp-telegram daemon install`
(use at your own risk).

## Wiring Claude Desktop / Claude Code

Add this entry to `~/Library/Application Support/Claude/claude_desktop_config.json`,
preserving any existing `mcpServers` keys:

```json
{
  "mcpServers": {
    "itp-telegram": {
      "url": "http://127.0.0.1:8765/mcp/"
    }
  }
}
```

Quit + relaunch Claude Desktop. The 6 tools will appear in the MCP tools
indicator. They work alongside the regular Baft MCP gateway (which has
its own port and config — see [Claude Desktop Guide](CLAUDE_DESKTOP_GUIDE.md)).

## MCP tools

| Tool | Purpose |
|---|---|
| `search_posts(query, limit, min_score, channel_handles?)` | Semantic search across the vector store. Multilingual; results carry `channel_bias` and `channel_trust` for downstream weighting. |
| `recent_posts(hours_back, channel_handle?, limit)` | Time-windowed slice of the most recent posts. Use to check what just landed. |
| `list_channels()` | Returns all 39 configured channels with bias, trust_weight, language, and resolved channel_id. |
| `stats()` | DuckDB store totals — chunks, unique posts, channel count, time range. |
| `corroboration_check(claim, hours_back, min_score, max_posts)` | Pulls up to 15 posts semantically close to `claim`, hands them to LM Studio's analyzer (default `gemma-4-26b-a4b`), returns multi-channel corroborations with trust-weighted scores in bilingual EN+FA. |
| `capture_status()` | Live counters from the capture loop (received/normalized/stored/flush_count/buffer_size). |

### Notes on `corroboration_check`

This is a *narrative-cluster analyzer*, not a *fact-check verifier*: it
asks "what's corroborated across these posts?" rather than "is THIS
specific claim corroborated." Useful for spotting coordinated state-media
messaging; not a binary yes/no on a single claim.

The 15-post cap fits LM Studio's typical 4096-token loaded context. To
analyze more posts per call, reload the analyzer model with a larger
`n_ctx` in LM Studio's UI (32K is plenty) and bump the cap in
`baft/src/baft/itp_telegram/mcp_server.py:319`.

## Channel registry

The single source of truth is
`baft/pipeline/config/itp_telegram_channels.yaml` — analyst-maintained,
54 channels across 8 factional categories (regime official, IRGC
hardline, IRGC military, eschatological/Paydari/MASAF, reformist,
mainstream centrist, hardliner, breaking news, diaspora opposition,
civil society, religious authority, OSINT).

Inclusion at runtime: `monitoring_priority in {critical, high}` plus
non-`TBD_*` handles plus `status != "unverified"`. Plus 4 starter
overrides hardcoded in
`baft/src/baft/itp_telegram/channel_profiles.py:STARTER_EXTRAS`
(`khamenei_ir`, `Factnameh`, `Iranwire`, `tabnak`).

To add a channel: edit the YAML, then re-run `baft itp-telegram resolve-ids`
and `baft itp-telegram daemon restart` (or stop + start).

## Troubleshooting

| Symptom | Likely cause + fix |
|---|---|
| `daemon install` aborts with "TCC probe failed" | launchd can't read the venv (common on `/Volumes/`). Grant FDA to the python path shown, use `daemon start` instead, or override with `SKIP_TCC_CHECK=1`. |
| Daemon dies immediately, log shows `PermissionError: ... pyvenv.cfg` | macOS TCC blocked launchd from reading the venv. Same fix as above. |
| `0 posts captured` over 5+ minutes | Iran clock is ~midnight–05:00 IRST (overnight). Wait for morning. Or run `baft itp-telegram search "ایران"` to sanity-check the store. |
| `corroboration_check` returns `matches: 0` and log shows `lmstudio.http_error status=400 body={"error":"...n_keep:...n_ctx:..."}` | Analyzer prompt overflowed LM Studio's loaded context. Either reload the model with a larger `n_ctx`, or rely on the built-in 15-post cap. |
| `corroboration_check` returns `matches: 0` and log shows `lmstudio.budget_exhausted` | Analyzer model is a thinking model and burned `max_tokens` on `reasoning_content` before producing JSON. Switch to a non-thinking model in `cfg.analyzer_model` (default `google/gemma-4-26b-a4b`). |
| `baft itp-telegram stats` errors with DuckDB lock conflict | The CLI is detecting the running daemon and routing through MCP automatically. If this still happens, the PID file may be stale — `baft itp-telegram stop` then `daemon start`. |
| Channel handle won't resolve (`No user has X as username`) | Telegram handles can change. Cross-check on TGStat (`ir.tgstat.com`) and update `itp_telegram_channels.yaml`. |
| Search results show `channel_bias: unknown` and `trust: None` | Resolved-IDs JSON missing or stale. Run `baft itp-telegram resolve-ids` then `daemon restart`. |

## File map

```text
~/.heddle/
  .env                          # credentials + LM Studio URL (mode 600)
  telegram.session              # Telethon MTProto session (mode 600)
  itp_channel_ids.json          # handle → numeric channel_id map
  itp_rag.duckdb                # vector store
  itp_telegram.pid              # daemon PID file (auto-managed)
  itp_telegram.log              # daemon stdout+stderr (rotates manually)

baft/
  pipeline/config/
    itp_telegram_channels.yaml  # analyst-curated channel registry
  src/baft/itp_telegram/
    config.py                   # ITPTelegramConfig dataclass
    channel_profiles.py         # registry loader + bias mapping
    llm_backend.py              # LM Studio shim for heddle's analyzer
    store.py                    # DuckDB factory
    capture.py                  # capture loop
    mcp_server.py               # FastMCP server + 6 tool definitions
    service.py                  # combined runner (capture + MCP)
    auth_bootstrap.py           # `baft itp-telegram auth`
    resolve_ids.py              # `baft itp-telegram resolve-ids`
    pid_manager.py              # PID file + liveness helpers
    cli.py                      # Click subcommand group
  deploy/macos/
    install.sh                  # launchd plist generator (with launchd TCC probe)
    uninstall.sh
```
