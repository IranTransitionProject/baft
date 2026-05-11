# ADR-001: Gateway-actor pattern for external sources beyond Telegram

**Status:** Accepted (scaffolding; no gateway implementations yet).
**Pairs with:** Heddle's [Gateway Actors](https://getheddle.github.io/heddle/gateway-actors/) guide.

## Context

Baft's analytical pipeline runs on the Heddle actor mesh, consuming
``TaskMessage``s off ``heddle.tasks.incoming``. Today the only
non-MCP source of analytical input is the ITP Telegram subsystem
(``src/baft/itp_telegram/``), which is intentionally **not** wired
to the main NATS bus — it ingests messages into its own DuckDB
vector store and exposes them via a separate FastMCP HTTP server.
That separation is documented in [CLAUDE.md](../../CLAUDE.md) and
exists because the Telegram capture daemon has very different
operational requirements (Telethon session lifecycle, network
isolation, TCC permissions, optional offline runs) from the main
analytical pipeline.

Heddle v0.9.2 introduced an explicit pattern for bridging
non-Heddle-native external sources into the bus: the **gateway
actor**. As baft scales analytical coverage beyond Telegram —
RSS feeds, mailing lists, REST APIs, MQTT-spoken IoT
attestations, etc. — each new source needs a translation layer
that turns the external protocol into ``TaskMessage``s on the
Heddle bus.

The question for baft: where do these gateways live, what do they
share, and what's the contract they expose upward?

## Decision

**New non-Telegram external sources are added as gateway actors
under ``src/baft/gateways/<source>.py``. Each gateway:**

1. **Subscribes to the source on one side** (HTTP webhook listener,
   RSS poller, MQTT subscriber, etc.).
2. **Builds a ``TaskMessage`` whose payload matches an existing
   baft contract** — typically ``baft.contracts.core.SourceBundle``
   for ingestion-grade input, so the SP worker can process it
   downstream like any other source.
3. **Publishes to ``heddle.tasks.incoming``** via Heddle's
   standard ``MessageBus`` interface (``InMemoryBus`` for tests,
   ``NATSBus`` in production).
4. **Skips, never crashes, on malformed input** (per Heddle
   [ADR-004](https://getheddle.github.io/heddle/adr/004-skip-not-crash-on-malformed/)).
   A misformatted external payload turns into a logged
   ``gateway.malformed_input`` event, not a crashed gateway.
5. **Carries no analytical state.** Gateways are pure
   translators; if a normalisation step needs the entity registry
   or terminology rules, that work belongs in a dedicated worker
   (SP / TN / etc.), not the gateway.

The directory ``src/baft/gateways/`` is scaffolded with a
docstring-only ``__init__.py`` describing the contract.
Implementations land per-source.

## Why this shape

| Constraint | How the pattern satisfies it |
| --- | --- |
| One operational supervisor per source | Each gateway runs as its own ``BaseActor`` subclass, scheduled by ``heddle`` like any other worker. ``baft itp-telegram daemon`` already shows the standalone-subprocess form for the legacy carve-out. |
| Source-specific failure modes don't poison the pipeline | A wedged HTTP listener fails its gateway only; nothing downstream sees malformed input because the gateway emits validated ``TaskMessage``s. |
| Pipeline doesn't care where input came from | Once a gateway publishes a ``SourceBundle``, the rest of the pipeline (SP → IA → XV → DE) treats it identically to MCP-injected input. |
| Foreign-language SDKs can replace a gateway | The published wire contract is the same JSON Schema baft already exports under ``baft-schemas/v1/source_bundle.schema.json``. A future Swift/.NET gateway can replace a Python one without touching baft. |

## Alternatives considered

### Carve every new source into its own subsystem like Telegram (rejected)

The Telegram subsystem owns its own DuckDB, MCP server, and
launchd lifecycle because Telegram's constraints (Telethon
sessions, network reachability, throttling) are unusual. Most
future sources (HTTP webhooks, RSS, mailing-list ingestion) don't
have those constraints; carving each into a parallel subsystem
would duplicate operational state and split the analytical bus.

### Make SP polyglot (rejected)

SP could accept native protocol payloads (Telegram JSON, RSS XML,
HTTP webhook bodies, etc.) directly. Rejected because SP is an
LLM-driven worker — its prompt-engineering surface is already
load-bearing for claim extraction. Bolting protocol parsing onto
its system prompt would couple unrelated change axes and grow the
prompt past the bounded-context discipline that gives SP its
reliability.

### MQTT-only adapter via NATS server config (kept as option for MQTT sources)

For external systems that natively speak MQTT v3.1.1, Heddle's
gateway-actors guide recommends enabling NATS' built-in MQTT
listener instead of writing a Python gateway. This ADR doesn't
preclude that option — when a future ITP source emits MQTT (e.g.
an IoT attestation device), use the NATS-MQTT adapter and a thin
contract-shaping actor downstream rather than a full gateway.

## Consequences

- New external sources have one place to live: ``src/baft/gateways/``.
- Existing Telegram subsystem stays where it is. This ADR does
  not retroactively migrate it; the carve-out remains intentional.
- ``baft-schemas/v1/`` (exported in tandem with this ADR) is the
  cross-language contract gateways target. Any non-Python gateway
  generates its types from that schema directory.
- The first concrete gateway implementation will write ADR-002
  documenting source-specific normalisation choices.
