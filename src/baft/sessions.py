"""
Active session tracking for scheduler expansion.

The ``get_active_sessions()`` function is called by the scheduler's
``expand_from`` mechanism to determine which sessions are currently
active. It returns one context dict per session, which the scheduler
merges into the SA task payload.

Session tracking uses a simple file-based approach: each active MCP
connection writes a session marker file to the workspace. The marker
contains the session_id and last activity timestamp.

Alternative implementations could query DuckDB, Redis, or NATS
for active session state.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()

# Default workspace directory for session markers.
_SESSION_DIR = Path("~/.heddle/sessions").expanduser()

# Sessions inactive for more than this many seconds are considered stale.
_STALE_THRESHOLD_SECONDS = 1800  # 30 minutes


def get_active_sessions() -> list[dict[str, Any]]:
    """Return a list of context dicts for currently active sessions.

    Each dict is merged into the SA task payload by the scheduler.
    Returns an empty list if no sessions are active.

    Session markers are JSON files in ``~/.heddle/sessions/`` with format::

        {"session_id": "abc123", "last_active": 1711234567.0, "analyst": "..."}
    """
    if not _SESSION_DIR.exists():
        return []

    now = time.time()
    raw: list[dict[str, Any]] = []

    for marker_path in _SESSION_DIR.glob("*.json"):
        try:
            data = json.loads(marker_path.read_text())
            last_active = data.get("last_active", 0)
            if now - last_active > _STALE_THRESHOLD_SECONDS:
                continue
            raw.append(data)
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning(
                "sessions.marker_read_failed",
                path=str(marker_path),
                error=str(exc),
            )

    # Sort by last_active descending so [0] is genuinely most recent.
    raw.sort(key=lambda d: d.get("last_active", 0), reverse=True)

    active: list[dict[str, Any]] = [
        {
            "session_monitor_request": {
                "session_id": d["session_id"],
                "transcript": d.get("transcript", ""),
                "session_start": d.get("session_start", ""),
                "session_objective": d.get("session_objective", ""),
                "current_tier": d.get("current_tier", 2),
                "operation_count": d.get("operation_count", 0),
            },
        }
        for d in raw
    ]

    logger.info("sessions.active_count", count=len(active))
    return active


def register_session(session_id: str, **kwargs: Any) -> None:
    """Write or update a session marker file.

    Called by the MCP bridge or CLI when a session starts or is active.
    """
    _SESSION_DIR.mkdir(parents=True, exist_ok=True)
    marker = {
        "session_id": session_id,
        "last_active": time.time(),
        **kwargs,
    }
    marker_path = _SESSION_DIR / f"{session_id}.json"
    marker_path.write_text(json.dumps(marker))


def unregister_session(session_id: str) -> None:
    """Remove a session marker file when a session ends."""
    marker_path = _SESSION_DIR / f"{session_id}.json"
    marker_path.unlink(missing_ok=True)
