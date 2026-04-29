"""Runtime configuration for the ITP Telegram service.

Centralizes paths, model names, network settings, and intervals so the
rest of the package never reads ``os.environ`` or hardcodes paths
directly. Constructed once in ``cli.py`` and threaded through.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _heddle_dir() -> Path:
    return Path.home() / ".heddle"


def _itp_root() -> Path:
    """Resolve ITP_ROOT env var, falling back to baft repo's parent."""
    env = os.environ.get("ITP_ROOT")
    if env:
        return Path(env)
    # baft/src/baft/itp_telegram/config.py → baft/ → ITP root
    return Path(__file__).resolve().parents[3].parent


@dataclass
class ITPTelegramConfig:
    """Resolved runtime config for the capture daemon and MCP server.

    Fields with environment variables are resolved at construction time
    (``from_env``); everything else takes the dataclass default.
    """

    # --- LM Studio ---
    lm_studio_url: str = "http://localhost:1234/v1"
    embedding_model: str = "text-embedding-nomic-embed-text-v1.5"
    # Non-thinking MoE — emits direct JSON, no reasoning-budget burn.
    # Thinking models (qwen3.x, deepseek-r1, olmo-3-think) work too but
    # need much larger max_tokens to leave room for the JSON answer.
    analyzer_model: str = "google/gemma-4-26b-a4b"

    # --- Telegram ---
    api_id: int = 0
    api_hash: str = ""
    session_path: Path = field(default_factory=lambda: _heddle_dir() / "telegram.session")

    # --- RAG store ---
    db_path: Path = field(default_factory=lambda: _heddle_dir() / "itp_rag.duckdb")

    # --- Channel registry ---
    registry_path: Path = field(
        default_factory=lambda: _itp_root() / "baft" / "pipeline" / "config"
        / "itp_telegram_channels.yaml"
    )

    # --- MCP HTTP transport ---
    mcp_host: str = "127.0.0.1"
    mcp_port: int = 8765

    # --- Capture loop ---
    flush_interval_sec: int = 300
    chunk_target_chars: int = 400
    chunk_max_chars: int = 600
    embed_batch_size: int = 64
    buffer_size: int = 10_000

    # --- Service lifecycle ---
    pid_path: Path = field(default_factory=lambda: _heddle_dir() / "itp_telegram.pid")
    log_path: Path = field(default_factory=lambda: _heddle_dir() / "itp_telegram.log")

    # --- Resolved channel IDs (written by `baft itp-telegram resolve-ids`) ---
    resolved_ids_path: Path = field(
        default_factory=lambda: _heddle_dir() / "itp_channel_ids.json"
    )

    @classmethod
    def from_env(cls) -> ITPTelegramConfig:
        """Construct from environment variables with safe defaults.

        Reads ``LM_STUDIO_URL``, ``TELEGRAM_API_ID``, ``TELEGRAM_API_HASH``,
        ``TELEGRAM_SESSION``. All optional — missing credentials are flagged
        by ``ensure_credentials()`` only when the capture loop needs them.
        """
        cfg = cls()
        cfg.lm_studio_url = os.environ.get("LM_STUDIO_URL", cfg.lm_studio_url)
        try:
            cfg.api_id = int(os.environ.get("TELEGRAM_API_ID", "0"))
        except ValueError:
            cfg.api_id = 0
        cfg.api_hash = os.environ.get("TELEGRAM_API_HASH", "")
        session_env = os.environ.get("TELEGRAM_SESSION")
        if session_env:
            cfg.session_path = Path(session_env)
        return cfg

    def ensure_dirs(self) -> None:
        """Create parent directories for any path we own."""
        for p in (self.session_path, self.db_path, self.pid_path, self.log_path):
            p.parent.mkdir(parents=True, exist_ok=True)

    def ensure_credentials(self) -> None:
        """Raise ``RuntimeError`` if api_id/hash are not set.

        Called by the capture loop, not by the MCP server (which can run
        against the existing DuckDB store with no Telegram credentials).
        """
        missing = []
        if not self.api_id:
            missing.append("TELEGRAM_API_ID")
        if not self.api_hash:
            missing.append("TELEGRAM_API_HASH")
        if missing:
            raise RuntimeError(
                "Telegram credentials missing: "
                + ", ".join(missing)
                + ". Set them in ~/.heddle/.env (chmod 600) and re-source the shell."
            )
