"""Vector-store factory for the ITP Telegram pipeline.

Wraps ``heddle.contrib.rag.vectorstore.duckdb_store.DuckDBVectorStore``
with the LM Studio embedding settings so callers don't have to remember
the magic ``embedding_backend="openai-compatible"`` flag.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from heddle.contrib.rag.vectorstore.duckdb_store import DuckDBVectorStore

if TYPE_CHECKING:
    from .config import ITPTelegramConfig


def open_store(cfg: ITPTelegramConfig) -> DuckDBVectorStore:
    """Open and initialize the ITP RAG store wired to LM Studio.

    Caller owns ``store.close()``. The DuckDB file at ``cfg.db_path``
    is created on first use; missing parent dirs are created.
    """
    cfg.ensure_dirs()
    store = DuckDBVectorStore(
        db_path=str(cfg.db_path),
        embedding_backend="openai-compatible",
        embedding_url=cfg.lm_studio_url,
        embedding_model=cfg.embedding_model,
    )
    return store.initialize()
