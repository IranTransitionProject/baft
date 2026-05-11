"""Combined long-lived service: live capture + MCP HTTP server.

Hosts both halves in a single asyncio event loop and a single OS process,
so MCP tools see capture state directly (no inter-process bus) and the
operator only has one PID to supervise.

The CLI entry point is ``baft itp-telegram serve``. Either half can be
disabled with ``--no-capture`` or ``--no-mcp``:

- ``--no-mcp``     capture-only (writes to DuckDB, exposes nothing).
- ``--no-capture`` MCP-only against the existing DuckDB store. Useful
  before Telegram auth is set up, or when the operator runs capture
  on a different machine.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
from typing import TYPE_CHECKING, Any

from .capture import CaptureLoop, CaptureStatus
from .channel_profiles import load_itp_profiles, merge_resolved_ids
from .mcp_server import build_mcp
from .pid_manager import remove_pid, write_pid

if TYPE_CHECKING:
    from .config import ITPTelegramConfig

logger = logging.getLogger(__name__)


async def _run_mcp(mcp: Any, host: str, port: int) -> None:
    """Run the FastMCP server in streamable-HTTP mode.

    FastMCP 3.x supports the ``"http"`` transport, which speaks
    streamable-HTTP per the MCP spec.
    """
    await mcp.run_async(transport="http", host=host, port=port)


async def serve(
    cfg: ITPTelegramConfig,
    *,
    enable_capture: bool = True,
    enable_mcp: bool = True,
) -> None:
    """Run the combined service. Returns when either half exits."""
    if not enable_capture and not enable_mcp:
        raise ValueError("At least one of --capture / --mcp must be enabled.")

    cfg.ensure_dirs()
    profiles = load_itp_profiles(cfg.registry_path)
    if not profiles:
        raise RuntimeError(
            f"No channels loaded from {cfg.registry_path}. "
            "Verify the registry file exists and has critical/high entries."
        )
    # Backfill numeric channel_ids from the resolve-ids JSON so MCP
    # tools can enrich search results with bias + trust_weight.
    merge_resolved_ids(profiles, cfg.resolved_ids_path)

    capture_loop: CaptureLoop | None = None
    capture_status_ref: CaptureStatus | None = None
    if enable_capture:
        capture_loop = CaptureLoop(cfg=cfg, profiles=profiles)
        capture_status_ref = capture_loop.status
        await capture_loop.start()

    mcp_task: asyncio.Task | None = None
    capture_task: asyncio.Task | None = None
    tasks: list[asyncio.Task] = []

    if enable_mcp:
        mcp = build_mcp(cfg, profiles, capture_status_ref=capture_status_ref)
        logger.info("Serving MCP at http://%s:%d/mcp", cfg.mcp_host, cfg.mcp_port)
        mcp_task = asyncio.create_task(
            _run_mcp(mcp, cfg.mcp_host, cfg.mcp_port),
            name="itp-mcp",
        )
        tasks.append(mcp_task)

    if capture_loop:
        capture_task = asyncio.create_task(capture_loop.run(), name="itp-capture")
        tasks.append(capture_task)

    # Signal handlers — graceful shutdown on SIGINT / SIGTERM.
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            # add_signal_handler is unavailable on Windows; ignore.
            pass

    write_pid(cfg.pid_path)
    logger.info("ITP Telegram service started (pid file: %s)", cfg.pid_path)

    try:
        # Wait for either: a signal, MCP exit, or capture exit (whichever first).
        wait_set: list[asyncio.Task] = [asyncio.create_task(stop_event.wait())]
        wait_set.extend(tasks)
        done, _pending = await asyncio.wait(
            wait_set,
            return_when=asyncio.FIRST_COMPLETED,
        )
        for t in done:
            exc = t.exception() if not t.cancelled() else None
            if exc:
                logger.exception("Service task raised: %s", exc)
    finally:
        logger.info("Shutting down ITP Telegram service...")
        if capture_loop:
            await capture_loop.stop()
        if mcp_task and not mcp_task.done():
            mcp_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await mcp_task
        if capture_task and not capture_task.done():
            capture_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await capture_task
        remove_pid(cfg.pid_path)
        logger.info("Service stopped.")
