"""Live Telegram capture loop.

Wraps ``heddle.contrib.rag.ingestion.telegram_live.TelegramLiveIngestor``
in an async loop that periodically drains the buffer, chunks the posts,
embeds them via LM Studio, and writes them to the DuckDB store.

Designed to be run from ``service.py`` alongside the MCP server in a
single asyncio event loop (so MCP tools see captures in near-real-time
without a separate process). Can also be run standalone for capture-only
mode via ``baft itp-telegram serve --no-mcp``.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from heddle.contrib.rag.chunker.sentence_chunker import ChunkConfig, chunk_post
from heddle.contrib.rag.ingestion.telegram_live import TelegramLiveIngestor

from .channel_profiles import channel_handles
from .config import ITPTelegramConfig
from .store import open_store

logger = logging.getLogger(__name__)


@dataclass
class CaptureStatus:
    """Snapshot of the capture loop's state. Returned by the MCP tool."""

    running: bool = False
    channels_configured: int = 0
    channels_resolved: int = 0
    total_received: int = 0
    total_normalized: int = 0
    total_stored: int = 0
    buffer_size: int = 0
    flush_count: int = 0
    last_flush_unix: float | None = None
    last_error: str | None = None


@dataclass
class CaptureLoop:
    """Owns the TelegramLiveIngestor and the periodic flush task.

    Lifecycle:
        loop = CaptureLoop(cfg, channel_profiles)
        await loop.start()      # connect + register handler
        await loop.run()        # blocks until stop()
        await loop.stop()       # graceful drain + disconnect

    Shared state (``status``) is read by the MCP server's
    ``capture_status`` tool. No locking needed — single-threaded asyncio.
    """

    cfg: ITPTelegramConfig
    profiles: dict[str, Any]  # channel_handle (lower) -> ChannelEditorProfile
    status: CaptureStatus = field(default_factory=CaptureStatus)

    _ingestor: TelegramLiveIngestor | None = None
    _store: Any = None
    _stop_event: asyncio.Event | None = None
    _flush_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Connect to Telegram and prepare the store."""
        self.cfg.ensure_credentials()
        self.cfg.ensure_dirs()

        handles = channel_handles(self.profiles)
        if not handles:
            raise RuntimeError("No channels configured — channel_profiles is empty.")

        logger.info("Capture loop starting on %d channels", len(handles))

        self._ingestor = TelegramLiveIngestor(
            channels=list(handles),
            api_id=self.cfg.api_id,
            api_hash=self.cfg.api_hash,
            session_path=str(self.cfg.session_path),
            buffer_size=self.cfg.buffer_size,
        ).load()
        await self._ingestor.start()

        self._store = open_store(self.cfg)
        self._stop_event = asyncio.Event()

        ingest_status = self._ingestor.status()
        self.status.running = True
        self.status.channels_configured = ingest_status["channels_configured"]
        self.status.channels_resolved = ingest_status["channels_resolved"]

    async def run(self) -> None:
        """Run the periodic-flush loop until stop() is signaled."""
        if not self._stop_event:
            raise RuntimeError("Call start() before run().")

        chunk_cfg = ChunkConfig(
            target_chars=self.cfg.chunk_target_chars,
            max_chars=self.cfg.chunk_max_chars,
        )

        while not self._stop_event.is_set():
            # Sleep for the flush interval, but wake immediately on stop.
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.cfg.flush_interval_sec,
                )
            except asyncio.TimeoutError:
                pass  # normal interval tick

            await self._flush(chunk_cfg)

    async def stop(self) -> None:
        """Signal the loop to stop, drain remaining posts, and disconnect."""
        if self._stop_event:
            self._stop_event.set()

        if self._ingestor:
            chunk_cfg = ChunkConfig(
                target_chars=self.cfg.chunk_target_chars,
                max_chars=self.cfg.chunk_max_chars,
            )
            await self._flush(chunk_cfg)
            await self._ingestor.stop()
            self._ingestor = None

        if self._store:
            self._store.close()
            self._store = None

        self.status.running = False
        logger.info(
            "Capture loop stopped. flushes=%d total_stored=%d",
            self.status.flush_count,
            self.status.total_stored,
        )

    async def _flush(self, chunk_cfg: ChunkConfig) -> None:
        """Drain the ingestor buffer once and persist as embedded chunks.

        Embedding + DuckDB writes are blocking; offload to a thread.
        """
        if not self._ingestor or not self._store:
            return

        ingest_status = self._ingestor.status()
        self.status.total_received = ingest_status["total_received"]
        self.status.total_normalized = ingest_status["total_normalized"]
        self.status.buffer_size = ingest_status["buffer_size"]

        posts = list(self._ingestor.ingest())  # drains buffer
        if not posts:
            logger.debug("Flush: buffer empty (interval=%ds)", self.cfg.flush_interval_sec)
            return

        chunks = []
        for post in posts:
            chunks.extend(chunk_post(post, config=chunk_cfg))
        if not chunks:
            return

        try:
            count = await asyncio.to_thread(
                self._store.add_chunks,
                chunks,
                self.cfg.embed_batch_size,
            )
        except Exception as exc:
            self.status.last_error = f"flush failed: {exc}"
            logger.exception("Flush failed: %d posts dropped", len(posts))
            return

        loop = asyncio.get_running_loop()
        self.status.flush_count += 1
        self.status.total_stored += count
        self.status.last_flush_unix = loop.time()
        self.status.last_error = None

        logger.info(
            "Flushed %d posts → %d chunks → %d stored (run total: %d)",
            len(posts),
            len(chunks),
            count,
            self.status.total_stored,
        )
