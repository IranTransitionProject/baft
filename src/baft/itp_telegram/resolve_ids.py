"""Resolve channel handles to stable numeric Telegram IDs.

Telegram channel handles can change; numeric IDs do not. After
``baft itp-telegram auth`` writes a session file, this module connects
to Telegram and resolves each configured handle to its numeric ID,
writing the result to ``~/.heddle/itp_channel_ids.json`` so subsequent
runs (and the registry maintainer) have a stable mapping.

Output JSON shape::

    {
      "resolved_at": "2026-04-26T12:00:00Z",
      "channels": {
        "farsna": {
            "channel_id": 1006939659,
            "title": "Fars News Agency",
            "subscribers": 123456
        },
        ...
      },
      "failed": ["khamenei_ir", ...]
    }

Failures are logged and listed in ``failed`` — usually because the handle
is wrong, the channel is private, or the user account doesn't have
access. Re-run after correcting the registry.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .channel_profiles import load_itp_profiles
from .config import ITPTelegramConfig

logger = logging.getLogger(__name__)


async def _resolve(cfg: ITPTelegramConfig, output_path: Path) -> dict[str, Any]:
    try:
        from telethon import TelegramClient
    except ImportError as exc:
        raise RuntimeError(
            "telethon is not installed. Run `uv sync` from baft/ "
            "(after the `telegram` extra is added)."
        ) from exc

    cfg.ensure_credentials()
    cfg.ensure_dirs()

    profiles = load_itp_profiles(cfg.registry_path)
    handles = sorted({p.channel_handle for p in profiles.values() if p.channel_handle})

    client = TelegramClient(str(cfg.session_path), cfg.api_id, cfg.api_hash)
    resolved: dict[str, dict[str, Any]] = {}
    failed: list[str] = []

    async with client:
        if not await client.is_user_authorized():
            raise RuntimeError(
                "Telethon session is not authorized. "
                "Run `baft itp-telegram auth` first."
            )

        for handle in handles:
            try:
                entity = await client.get_entity(handle)
            except Exception as exc:  # noqa: BLE001 — telethon raises many specific types
                logger.warning("Could not resolve @%s: %s", handle, exc)
                failed.append(handle)
                continue

            entry: dict[str, Any] = {
                "channel_id": int(getattr(entity, "id", 0)),
                "title": getattr(entity, "title", handle),
            }
            try:
                full = await client.get_entity(handle)
                participants = getattr(full, "participants_count", None)
                if participants is not None:
                    entry["subscribers"] = int(participants)
            except Exception:  # noqa: BLE001
                pass

            resolved[handle.lower()] = entry
            logger.info("Resolved @%s → %s (%s)", handle, entry["channel_id"], entry["title"])

    payload = {
        "resolved_at": datetime.now(tz=UTC).isoformat(),
        "channels": resolved,
        "failed": failed,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    return payload


def run(cfg: ITPTelegramConfig, output_path: Path | None = None) -> dict[str, Any]:
    """Synchronous entry point for the CLI."""
    target = output_path or (cfg.pid_path.parent / "itp_channel_ids.json")
    return asyncio.run(_resolve(cfg, target))
