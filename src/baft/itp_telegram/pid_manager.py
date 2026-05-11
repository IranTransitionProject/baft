"""PID file lifecycle for the ITP Telegram service.

Used by ``baft itp-telegram serve`` (writes), ``status`` (reads), and
``stop`` (reads + signals).
"""

from __future__ import annotations

import contextlib
import errno
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class PidStatus:
    """Resolved state of the PID file at a given moment."""

    pid: int | None
    running: bool
    stale: bool  # PID file present but no live process


def write_pid(path: Path, pid: int | None = None) -> None:
    """Write the given PID (defaults to current process) to ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{pid or os.getpid()}\n")


def read_pid(path: Path) -> int | None:
    """Read the PID from ``path``, or return ``None`` if absent or malformed."""
    if not path.exists():
        return None
    try:
        return int(path.read_text().strip())
    except (ValueError, OSError):
        return None


def remove_pid(path: Path) -> None:
    """Remove the PID file if it exists."""
    with contextlib.suppress(FileNotFoundError):
        path.unlink()


def is_running(pid: int) -> bool:
    """Check whether ``pid`` is a live process (kill -0)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but is owned by someone else; treat as running.
        return True
    except OSError as exc:
        if exc.errno == errno.ESRCH:
            return False
        raise
    return True


def status(path: Path) -> PidStatus:
    """Combined read + liveness check."""
    pid = read_pid(path)
    if pid is None:
        return PidStatus(pid=None, running=False, stale=False)
    alive = is_running(pid)
    return PidStatus(pid=pid, running=alive, stale=not alive)
