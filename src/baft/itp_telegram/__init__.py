"""ITP Telegram capture + MCP gateway.

Wires Heddle's Telegram live ingestor and DuckDB RAG store to an
HTTP-transport FastMCP server, with an LM Studio LLM/embedding backend.

Submodules:

- ``config``           — runtime paths, defaults, model names.
- ``channel_profiles`` — load curated registry + emit Heddle profiles.
- ``llm_backend``      — LM Studio shim for ``llm_analyzers.LLMBackend``.
- ``store``            — factory for the RAG vector store.
- ``capture``          — async live-capture loop.
- ``mcp_server``       — FastMCP HTTP server + tool definitions.
- ``service``          — combined long-lived runner (capture + MCP).
- ``auth_bootstrap``   — first-time Telethon phone auth helper.
- ``pid_manager``      — PID file lifecycle for the service.
- ``cli``              — Click subcommand group, mounted on ``baft``.
"""

from __future__ import annotations

__all__ = [
    "auth_bootstrap",
    "capture",
    "channel_profiles",
    "cli",
    "config",
    "llm_backend",
    "mcp_server",
    "pid_manager",
    "service",
    "store",
]
