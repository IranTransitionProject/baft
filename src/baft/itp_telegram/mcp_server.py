"""FastMCP server for the ITP Telegram RAG store.

Builds a ``FastMCP`` instance that exposes search, listing, and analysis
tools to MCP clients (Claude Desktop, ITP Chat, etc.) over either
streamable-HTTP or stdio transport.

Tools:
    search_posts          Semantic search across the vector store.
    recent_posts          Most recent stored posts (optional channel filter).
    list_channels         Configured ITP channels with bias + trust_weight.
    stats                 Vector-store statistics.
    corroboration_check   LLM-backed multi-channel corroboration finder.
    capture_status        Snapshot of the capture daemon (when running in
                          combined-service mode; returns ``running: false``
                          if invoked from an MCP-only process).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from fastmcp import FastMCP

from .channel_profiles import by_channel_id
from .llm_backend import LMStudioLLMBackend
from .store import open_store

if TYPE_CHECKING:
    from .capture import CaptureStatus
    from .config import ITPTelegramConfig

logger = logging.getLogger(__name__)


_INSTRUCTIONS = (
    "ITP Telegram RAG tools. Search a multilingual vector store of "
    "Iranian-relevant Telegram channels (Persian/Arabic/Hebrew/Turkish). "
    "Channel trust weights are pre-configured per channel bias "
    "(state_media ~0.3, state_aligned ~0.4-0.65, opposition ~0.7, "
    "independent ~0.8, fact_check ~0.9). Use search_posts for semantic "
    "queries, recent_posts for time-windowed snapshots, "
    "corroboration_check to test a claim across channels, list_channels "
    "to see what's being captured."
)


def build_mcp(
    cfg: ITPTelegramConfig,
    profiles: dict[str, Any],
    capture_status_ref: CaptureStatus | None = None,
) -> FastMCP:
    """Construct the ``FastMCP`` server. Caller decides transport.

    Args:
        cfg: Resolved ITP config.
        profiles: ``{handle_lower: ChannelEditorProfile}`` from
            ``channel_profiles.load_itp_profiles``.
        capture_status_ref: Live status object owned by the capture loop
            when running in combined-service mode. ``None`` when serving
            MCP-only against an existing DuckDB store.
    """
    mcp = FastMCP(name="itp-telegram", instructions=_INSTRUCTIONS)

    # Pre-build the bias/trust lookup we'll need in search-result enrichment.
    by_id = by_channel_id(profiles)

    # Heddle's analyzer (BaseAnalysisActor._format_posts) resolves bias by
    # looking up channel_id in heddle.contrib.rag.ingestion.telegram_ingestor.
    # DEFAULT_PROFILES — which only ships with 4 channels. Inject our 34
    # resolved ITP profiles so the LLM prompt actually carries bias labels
    # for the channels we capture, otherwise everything reads as "unknown".
    from heddle.contrib.rag.ingestion.telegram_ingestor import DEFAULT_PROFILES

    DEFAULT_PROFILES.update(by_id)

    def _enrich_result(row: Any) -> dict[str, Any]:
        profile = by_id.get(row.source_channel_id)
        bias = profile.bias.value if profile else "unknown"
        trust = profile.trust_weight if profile else None
        ts = row.metadata.get("timestamp_unix")
        return {
            "score": round(row.score, 3),
            "text": row.text,
            "channel_id": row.source_channel_id,
            "channel_name": row.metadata.get("source_channel_name", ""),
            "channel_bias": bias,
            "channel_trust": trust,
            "source_id": row.source_global_id,
            "timestamp_unix": ts,
            "timestamp_iso": (
                datetime.fromtimestamp(ts, tz=UTC).isoformat() if ts else None
            ),
        }

    def _resolve_channel_ids(handles: list[str]) -> list[int]:
        wanted = {h.lstrip("@").lower() for h in handles}
        return [
            p.channel_id
            for key, p in profiles.items()
            if key in wanted and p.channel_id
        ]

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------

    @mcp.tool()
    def search_posts(
        query: str,
        limit: int = 10,
        min_score: float = 0.3,
        channel_handles: list[str] | None = None,
    ) -> dict:
        """Semantic search across the Telegram vector store.

        Args:
            query: Search query in Persian, English, Arabic, or mixed.
            limit: Max number of results (default 10).
            min_score: Minimum cosine similarity (0.0-1.0, default 0.3).
            channel_handles: Optional filter — list of handles like
                ``["farsna", "IranIntl_Fa"]`` (with or without @). Only
                returns posts from these channels. Channels that haven't
                been resolved to numeric IDs yet are silently skipped.

        Returns:
            ``{count, results: [{score, text, channel_id, channel_name,
            channel_bias, channel_trust, source_id, timestamp_iso}, ...]}``.
        """
        store = open_store(cfg)
        try:
            channel_ids = (
                _resolve_channel_ids(channel_handles) if channel_handles else None
            )
            results = store.search(
                query,
                limit=limit,
                min_score=min_score,
                channel_ids=channel_ids,
            )
            return {
                "count": len(results),
                "results": [_enrich_result(r) for r in results],
            }
        finally:
            store.close()

    @mcp.tool()
    def stats() -> dict:
        """Vector-store statistics — total chunks, channels, time range.

        Returns ``{"total_chunks": 0}`` for an empty store (e.g. before
        any live capture has occurred).
        """
        store = open_store(cfg)
        try:
            return store.stats()
        finally:
            store.close()

    @mcp.tool()
    def list_channels() -> dict:
        """List all configured channels with bias and trust_weight."""
        return {
            "count": len(profiles),
            "channels": [
                {
                    "handle": p.channel_handle,
                    "name": p.channel_name,
                    "bias": p.bias.value,
                    "trust_weight": p.trust_weight,
                    "language": p.language.value,
                    "channel_id": p.channel_id or None,
                    "description": p.description,
                }
                for p in profiles.values()
            ],
        }

    @mcp.tool()
    def recent_posts(
        hours_back: int = 6,
        channel_handle: str | None = None,
        limit: int = 50,
    ) -> dict:
        """Most recent stored posts, optionally filtered by channel.

        Args:
            hours_back: Look back this many hours from "now" (default 6).
            channel_handle: Optional single channel filter (with or without @).
            limit: Max posts (default 50).
        """
        cutoff = int(datetime.now(tz=UTC).timestamp()) - (hours_back * 3600)
        store = open_store(cfg)
        try:
            conn = store._conn
            where = ["timestamp_unix >= ?"]
            params: list[Any] = [cutoff]
            if channel_handle:
                key = channel_handle.lstrip("@").lower()
                profile = profiles.get(key)
                if profile and profile.channel_id:
                    where.append("source_channel_id = ?")
                    params.append(profile.channel_id)
                else:
                    return {
                        "count": 0,
                        "results": [],
                        "warning": (
                            f"channel '{channel_handle}' not resolved to numeric ID yet "
                            "(run `baft itp-telegram resolve-ids` after auth)."
                        ),
                    }
            params.append(limit)
            rows = conn.execute(
                f"""SELECT chunk_id, text, source_channel_id, source_global_id,
                           source_channel_name, timestamp_unix
                    FROM rag_chunks
                    WHERE {' AND '.join(where)}
                    ORDER BY timestamp_unix DESC
                    LIMIT ?""",
                params,
            ).fetchall()
            results = []
            for row in rows:
                ts = row[5]
                profile = by_id.get(row[2])
                results.append({
                    "text": row[1],
                    "channel_id": row[2],
                    "channel_name": row[4],
                    "channel_bias": profile.bias.value if profile else "unknown",
                    "channel_trust": profile.trust_weight if profile else None,
                    "source_id": row[3],
                    "timestamp_unix": ts,
                    "timestamp_iso": (
                        datetime.fromtimestamp(ts, tz=UTC).isoformat() if ts else None
                    ),
                })
            return {"count": len(results), "results": results}
        finally:
            store.close()

    @mcp.tool()
    def corroboration_check(
        claim: str,
        hours_back: int = 24,
        min_score: float = 0.4,
        max_posts: int = 30,
    ) -> dict:
        """Check whether a claim is corroborated across channels.

        Pulls posts semantically close to ``claim`` from the last
        ``hours_back`` hours, packages them as a single mux window,
        and asks LM Studio (via heddle's ``CorroborationFinder``) to
        produce supporting/contradicting channel lists with a
        trust-weighted score.

        Args:
            claim: The factual claim to test (any language).
            hours_back: How far back to search (default 24h).
            min_score: Semantic-search similarity floor (default 0.4).
            max_posts: Cap on posts fed to the LLM (default 30).

        Returns:
            ``{count, matches: [...], analyzed_posts: N, warning: str?}``.
            ``matches`` follows ``CorroborationMatch.model_dump()`` shape.
        """
        # Lazy imports so mcp_server stays importable when heddle.contrib
        # extras aren't installed (e.g. in a docs-only environment).
        from heddle.contrib.rag.analysis.llm_analyzers import CorroborationFinder
        from heddle.contrib.rag.schemas.mux import MuxEntry
        from heddle.contrib.rag.schemas.post import Language, NormalizedPost

        cutoff = int(datetime.now(tz=UTC).timestamp()) - (hours_back * 3600)
        store = open_store(cfg)
        try:
            results = store.search(claim, limit=max_posts, min_score=min_score)
            results = [r for r in results if (r.metadata.get("timestamp_unix") or 0) >= cutoff]
            if len(results) < 3:
                return {
                    "count": 0,
                    "matches": [],
                    "analyzed_posts": len(results),
                    "warning": (
                        "Not enough matching posts in the time window for "
                        "corroboration analysis (need >=3 posts across >=2 channels)."
                    ),
                }

            # Reconstruct the minimum NormalizedPost / MuxEntry needed by the analyzer.
            # MuxEntry's channel_id/channel_name/text/timestamp are computed_field
            # properties on .post, so we don't pass them as kwargs — only the
            # required mux_seq, the post itself, and the synthetic window_id.
            entries: list[MuxEntry] = []
            window_start_ts = min(r.metadata.get("timestamp_unix") or cutoff for r in results)
            window_end_ts = max(r.metadata.get("timestamp_unix") or cutoff for r in results)
            window_id = f"corroboration:{int(window_start_ts)}-{int(window_end_ts)}"
            for idx, r in enumerate(results):
                ts = r.metadata.get("timestamp_unix") or cutoff
                channel_name = r.metadata.get("source_channel_name", "")
                profile = by_id.get(r.source_channel_id)
                post = NormalizedPost(
                    global_id=r.source_global_id,
                    source_channel_id=r.source_channel_id,
                    source_channel_name=channel_name,
                    message_id=0,
                    timestamp=datetime.fromtimestamp(ts, tz=UTC),
                    timestamp_unix=ts,
                    text_raw=r.text,
                    text_clean=r.text,
                    text_rtl=True,
                    language=profile.language if profile else Language.UNKNOWN,
                )
                entries.append(MuxEntry(
                    mux_seq=idx,
                    post=post,
                    window_id=window_id,
                ))

            # Cap entries to keep the prompt under the analyzer model's
            # context window. LM Studio's default n_ctx is often 4096; with
            # ~150 tokens/post + ~700 tokens of system+instructions and a
            # ~1024-token output budget, 15 posts fits comfortably. Bump
            # max_posts (or reload the model with larger n_ctx in LM Studio)
            # for richer analysis.
            analyzer_input = entries[: min(len(entries), max_posts, 30)]

            llm = LMStudioLLMBackend(
                model=cfg.analyzer_model,
                base_url=cfg.lm_studio_url,
                max_tokens=1024,  # conservative — leaves room in 4K context
            )
            finder = CorroborationFinder(actor_id="itp.mcp.corroboration", llm=llm)
            matches = finder.analyze(analyzer_input)

            return {
                "count": len(matches),
                "matches": [m.model_dump(mode="json") for m in matches],
                "analyzed_posts": len(entries),
            }
        finally:
            store.close()

    @mcp.tool()
    def capture_status() -> dict:
        """Snapshot of the capture daemon.

        Returns the live status when MCP runs alongside capture in the
        combined service. When MCP runs standalone (no capture), returns
        ``{"running": false, "mode": "mcp-only"}``.
        """
        if capture_status_ref is None:
            return {"running": False, "mode": "mcp-only"}
        s = capture_status_ref
        return {
            "running": s.running,
            "mode": "combined",
            "channels_configured": s.channels_configured,
            "channels_resolved": s.channels_resolved,
            "total_received": s.total_received,
            "total_normalized": s.total_normalized,
            "total_stored": s.total_stored,
            "buffer_size": s.buffer_size,
            "flush_count": s.flush_count,
            "last_flush_unix": s.last_flush_unix,
            "last_error": s.last_error,
        }

    return mcp
