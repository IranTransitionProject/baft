"""Gateway actors that translate non-Heddle protocols into ``TaskMessage``s.

Each module under this package is a gateway actor for one external
source.  See :doc:`docs/adr/001-gateway-actors-for-external-sources`
for the contract:

- Subscribe to the external protocol on one side.
- Build a ``TaskMessage`` whose payload conforms to one of the
  ``baft.contracts.*`` wrapper models (most commonly
  :class:`baft.contracts.core.SourceBundle`).
- Publish to ``heddle.tasks.incoming`` via Heddle's standard
  ``MessageBus`` (``InMemoryBus`` for tests, ``NATSBus`` in
  production).
- Skip-not-crash on malformed input (Heddle ADR-004); log
  ``gateway.malformed_input`` and continue.
- Carry no analytical state — translation only.

The legacy Telegram capture subsystem
(:mod:`baft.itp_telegram`) deliberately lives outside this package
because it has its own DuckDB store and MCP server.  Future
sources (RSS, HTTP webhooks, REST polls, etc.) belong here.

Heddle's gateway-actor guide:
https://getheddle.github.io/heddle/gateway-actors/
"""

from __future__ import annotations

__all__: list[str] = []
