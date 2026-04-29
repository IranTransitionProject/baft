"""``baft itp-telegram`` CLI subcommand group.

Mounted onto ``baft.cli.main`` so the operator interacts with the whole
Telegram pipeline through one entry point. Subcommands:

- ``auth``           First-time Telethon phone auth (writes session file).
- ``channels``       List configured channels with bias + trust_weight.
- ``resolve-ids``    Resolve handles to numeric IDs (writes JSON).
- ``serve``          Run combined capture + MCP HTTP service (foreground).
- ``status``         Show PID file state + service liveness.
- ``stop``           Send SIGTERM to the running service.
- ``stats``          Print vector-store statistics.
- ``search``         One-off semantic search (debug/admin).
- ``daemon``         Manage launchd lifecycle (install/uninstall/restart/log).

All subcommands accept ``--lm-studio-url`` and ``--db-path`` overrides
so the operator can point at a different LM Studio server or test DB
without editing ``~/.heddle/.env``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
from pathlib import Path
from typing import Any

import click

from .config import ITPTelegramConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Common option decorators
# ---------------------------------------------------------------------------


def _common_options(f: Any) -> Any:
    """Apply CLI flags shared by most subcommands."""
    f = click.option(
        "--lm-studio-url",
        default=None,
        help="Override LM Studio base URL (default: $LM_STUDIO_URL).",
    )(f)
    f = click.option(
        "--db-path",
        default=None,
        type=click.Path(),
        help="Override RAG DuckDB path (default: ~/.heddle/itp_rag.duckdb).",
    )(f)
    f = click.option(
        "--registry",
        default=None,
        type=click.Path(),
        help="Override channel registry YAML path.",
    )(f)
    return f


def _resolve_cfg(
    lm_studio_url: str | None,
    db_path: str | None,
    registry: str | None,
) -> ITPTelegramConfig:
    cfg = ITPTelegramConfig.from_env()
    if lm_studio_url:
        cfg.lm_studio_url = lm_studio_url
    if db_path:
        cfg.db_path = Path(db_path).expanduser()
    if registry:
        cfg.registry_path = Path(registry).expanduser()
    return cfg


def _setup_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s — %(message)s",
    )


# ---------------------------------------------------------------------------
# MCP routing — when the daemon is running it owns the DuckDB write lock,
# so query-only CLI commands must talk to it over MCP HTTP rather than
# opening the DB file directly. (DuckDB does not allow cross-process
# sharing of a R/W database — see https://duckdb.org/docs/connect/concurrency.)
# ---------------------------------------------------------------------------


def _daemon_running(cfg: ITPTelegramConfig) -> bool:
    from .pid_manager import status as pid_status

    return pid_status(cfg.pid_path).running


def _call_mcp(cfg: ITPTelegramConfig, tool_name: str, args: dict[str, Any]) -> Any:
    """Call an MCP tool over HTTP. Used when the daemon owns the DB lock."""
    import asyncio

    from fastmcp import Client

    url = f"http://{cfg.mcp_host}:{cfg.mcp_port}/mcp/"

    async def _go() -> Any:
        async with Client(url) as client:
            r = await client.call_tool(tool_name, args)
            return r.data

    return asyncio.run(_go())


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------


@click.group(name="itp-telegram")
def itp_telegram() -> None:
    """ITP Telegram live capture + MCP HTTP server."""
    # Load ~/.heddle/.env if present so the daemon (running under launchd,
    # which doesn't source ~/.zshrc) picks up TELEGRAM_API_*, LM_STUDIO_URL,
    # etc. without a separate wrapper script. No-op when env is already set
    # (interactive shells where ~/.zshrc has already sourced .env win via
    # override=False).
    from pathlib import Path

    from dotenv import load_dotenv

    env_path = Path.home() / ".heddle" / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)


# ---------------------------------------------------------------------------
# auth
# ---------------------------------------------------------------------------


@itp_telegram.command()
def auth() -> None:
    """First-time Telethon phone authentication.

    Walks you through phone / login-code / 2FA prompts and persists a
    session file at $TELEGRAM_SESSION (default ~/.heddle/telegram.session).
    Run after credentials are populated in ~/.heddle/.env.
    """
    from .auth_bootstrap import main as auth_main

    raise SystemExit(auth_main())


# ---------------------------------------------------------------------------
# channels
# ---------------------------------------------------------------------------


@itp_telegram.command()
@_common_options
@click.option("--json", "as_json", is_flag=True, help="Emit JSON instead of a table.")
def channels(
    lm_studio_url: str | None,
    db_path: str | None,
    registry: str | None,
    as_json: bool,
) -> None:
    """List configured channels with bias + trust_weight."""
    from .channel_profiles import load_itp_profiles, merge_resolved_ids

    cfg = _resolve_cfg(lm_studio_url, db_path, registry)
    profiles = load_itp_profiles(cfg.registry_path)
    merge_resolved_ids(profiles, cfg.resolved_ids_path)

    if as_json:
        click.echo(json.dumps(
            {
                "count": len(profiles),
                "channels": [
                    {
                        "handle": p.channel_handle,
                        "name": p.channel_name,
                        "bias": p.bias.value,
                        "trust_weight": p.trust_weight,
                        "language": p.language.value,
                        "channel_id": p.channel_id or None,
                    }
                    for p in profiles.values()
                ],
            },
            indent=2,
            ensure_ascii=False,
        ))
        return

    click.echo()
    click.echo(click.style(f"  {len(profiles)} ITP channels", fg="cyan", bold=True))
    click.echo()
    fmt = "  {handle:<24} {bias:<14} trust={trust:<5} lang={lang:<3} {name}"
    for p in sorted(profiles.values(), key=lambda x: (-x.trust_weight, x.channel_handle or "")):
        click.echo(fmt.format(
            handle=f"@{p.channel_handle}",
            bias=p.bias.value,
            trust=f"{p.trust_weight:.2f}",
            lang=p.language.value,
            name=p.channel_name,
        ))
    click.echo()


# ---------------------------------------------------------------------------
# resolve-ids
# ---------------------------------------------------------------------------


@itp_telegram.command("resolve-ids")
@_common_options
@click.option(
    "--output",
    default=None,
    type=click.Path(),
    help="Output JSON path (default: ~/.heddle/itp_channel_ids.json).",
)
def resolve_ids_cmd(
    lm_studio_url: str | None,
    db_path: str | None,
    registry: str | None,
    output: str | None,
) -> None:
    """Resolve channel handles to numeric Telegram IDs (requires auth)."""
    from .resolve_ids import run as resolve_run

    _setup_logging()
    cfg = _resolve_cfg(lm_studio_url, db_path, registry)
    out_path = Path(output).expanduser() if output else None

    try:
        payload = resolve_run(cfg, out_path)
    except Exception as exc:
        click.echo(click.style(f"\n[FAIL] {exc}", fg="red"), err=True)
        raise SystemExit(1) from exc

    click.echo()
    click.echo(click.style(
        f"  Resolved {len(payload['channels'])} channels"
        f" ({len(payload['failed'])} failed)",
        fg="green",
        bold=True,
    ))
    if payload["failed"]:
        click.echo("  Failed: " + ", ".join(payload["failed"]))
    click.echo()


# ---------------------------------------------------------------------------
# serve
# ---------------------------------------------------------------------------


@itp_telegram.command()
@_common_options
@click.option("--mcp-host", default=None, help="MCP HTTP bind host (default: 127.0.0.1).")
@click.option("--mcp-port", default=None, type=int, help="MCP HTTP bind port (default: 8765).")
@click.option(
    "--flush-interval",
    default=None,
    type=int,
    help="Capture flush interval in seconds (default: 300).",
)
@click.option(
    "--no-capture",
    is_flag=True,
    help="Run MCP server only — no Telegram capture (no auth needed).",
)
@click.option("--no-mcp", is_flag=True, help="Run capture only — no MCP server.")
@click.option("-v", "--verbose", is_flag=True, help="Debug logging.")
def serve(
    lm_studio_url: str | None,
    db_path: str | None,
    registry: str | None,
    mcp_host: str | None,
    mcp_port: int | None,
    flush_interval: int | None,
    no_capture: bool,
    no_mcp: bool,
    verbose: bool,
) -> None:
    """Run the combined capture + MCP HTTP service.

    Foreground process; Ctrl-C drains the buffer and shuts down cleanly.
    Writes a PID file so `baft itp-telegram stop/status` can manage it.
    """
    _setup_logging(verbose=verbose)
    from .service import serve as service_serve

    cfg = _resolve_cfg(lm_studio_url, db_path, registry)
    if mcp_host:
        cfg.mcp_host = mcp_host
    if mcp_port:
        cfg.mcp_port = mcp_port
    if flush_interval:
        cfg.flush_interval_sec = flush_interval

    try:
        asyncio.run(service_serve(
            cfg,
            enable_capture=not no_capture,
            enable_mcp=not no_mcp,
        ))
    except KeyboardInterrupt:
        click.echo("\nInterrupted.")


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


@itp_telegram.command()
@_common_options
def status(
    lm_studio_url: str | None,
    db_path: str | None,
    registry: str | None,
) -> None:
    """Show PID file + liveness for the running service."""
    from .pid_manager import status as pid_status

    cfg = _resolve_cfg(lm_studio_url, db_path, registry)
    s = pid_status(cfg.pid_path)

    click.echo()
    click.echo(click.style("  ITP Telegram service status", fg="cyan", bold=True))
    if s.pid is None:
        click.echo("  pid file: (not present)")
        click.echo("  state:    not running")
    elif s.running:
        click.echo(f"  pid file: {cfg.pid_path}")
        click.echo(f"  pid:      {s.pid}")
        click.echo(f"  state:    {click.style('running', fg='green')}")
        click.echo(f"  mcp:      http://{cfg.mcp_host}:{cfg.mcp_port}/mcp")
    else:
        click.echo(f"  pid file: {cfg.pid_path} (stale)")
        click.echo(f"  pid:      {s.pid}")
        click.echo(f"  state:    {click.style('stale (process gone)', fg='yellow')}")
    click.echo(f"  db:       {cfg.db_path}")
    click.echo()


# ---------------------------------------------------------------------------
# stop
# ---------------------------------------------------------------------------


@itp_telegram.command()
@_common_options
def stop(
    lm_studio_url: str | None,
    db_path: str | None,
    registry: str | None,
) -> None:
    """Send SIGTERM to the running service (graceful drain)."""
    from .pid_manager import remove_pid, status as pid_status

    cfg = _resolve_cfg(lm_studio_url, db_path, registry)
    s = pid_status(cfg.pid_path)
    if s.pid is None:
        click.echo("No PID file. Nothing to stop.")
        return
    if not s.running:
        click.echo(f"PID {s.pid} is not running. Removing stale PID file.")
        remove_pid(cfg.pid_path)
        return

    try:
        os.kill(s.pid, signal.SIGTERM)
    except ProcessLookupError:
        click.echo(f"Process {s.pid} disappeared; removing PID file.")
        remove_pid(cfg.pid_path)
        return

    click.echo(f"Sent SIGTERM to {s.pid}. Service will drain and exit.")


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------


@itp_telegram.command()
@_common_options
def stats(
    lm_studio_url: str | None,
    db_path: str | None,
    registry: str | None,
) -> None:
    """Print vector-store statistics (works against an empty store).

    Routes through the running daemon's MCP server when one is up
    (DuckDB doesn't allow concurrent cross-process write/read),
    otherwise opens the DB file directly.
    """
    cfg = _resolve_cfg(lm_studio_url, db_path, registry)

    if _daemon_running(cfg):
        s = _call_mcp(cfg, "stats", {})
        source = "via running daemon (MCP)"
    else:
        from .store import open_store

        store = open_store(cfg)
        try:
            s = store.stats()
        finally:
            store.close()
        source = "direct DuckDB"

    click.echo()
    click.echo(click.style(f"  RAG store statistics  [{source}]", fg="cyan", bold=True))
    for k, v in s.items():
        click.echo(f"    {k}: {v}")
    click.echo()


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


@itp_telegram.command()
@_common_options
@click.argument("query")
@click.option("--limit", "-n", default=10, type=int)
@click.option("--min-score", default=0.3, type=float)
def search(
    lm_studio_url: str | None,
    db_path: str | None,
    registry: str | None,
    query: str,
    limit: int,
    min_score: float,
) -> None:
    """One-off semantic search against the vector store.

    Routes through the running daemon's MCP server when one is up
    (so results carry channel bias + trust_weight enrichment); falls
    back to a direct DuckDB read otherwise.
    """
    cfg = _resolve_cfg(lm_studio_url, db_path, registry)

    if _daemon_running(cfg):
        result = _call_mcp(cfg, "search_posts", {
            "query": query,
            "limit": limit,
            "min_score": min_score,
        })
        items = result.get("results", [])
        source = "via running daemon (MCP)"
    else:
        from .store import open_store

        store = open_store(cfg)
        try:
            raw = store.search(query, limit=limit, min_score=min_score)
        finally:
            store.close()
        # Normalize to MCP-shaped dicts so the display loop is uniform.
        items = [
            {
                "score": round(r.score, 3),
                "text": r.text,
                "channel_name": r.metadata.get("source_channel_name", ""),
                "channel_id": r.source_channel_id,
                "channel_bias": "unknown",
                "channel_trust": None,
                "source_id": r.source_global_id,
            }
            for r in raw
        ]
        source = "direct DuckDB (no bias enrichment)"

    if not items:
        click.echo(f"No results.  [{source}]")
        return

    click.echo()
    click.echo(click.style(
        f"  {len(items)} result(s) for: {query}  [{source}]",
        fg="cyan",
        bold=True,
    ))
    click.echo()
    for i, hit in enumerate(items, 1):
        score = float(hit.get("score", 0))
        score_color = "green" if score >= 0.7 else "yellow" if score >= 0.4 else "red"
        click.echo(click.style(f"  [{score:.3f}]", fg=score_color) + f"  #{i}")
        ch_name = hit.get("channel_name") or "?"
        ch_bias = hit.get("channel_bias") or "unknown"
        ch_trust = hit.get("channel_trust")
        trust_str = f" trust={ch_trust:.2f}" if isinstance(ch_trust, (int, float)) else ""
        click.echo(
            f"    Channel: {ch_name}  Bias: {ch_bias}{trust_str}  "
            f"Source: {hit.get('source_id', '?')}"
        )
        text = (hit.get("text") or "").replace("\n", " ")
        if len(text) > 200:
            text = text[:200] + "..."
        click.echo(f"    {text}")
        click.echo()


# ---------------------------------------------------------------------------
# daemon subgroup — launchd lifecycle wrappers
# ---------------------------------------------------------------------------

_LAUNCHD_LABEL = "com.itp.telegram"


def _deploy_dir() -> Path:
    """Locate baft/deploy/macos/ regardless of editable-vs-installed layout."""
    # cli.py → itp_telegram/ → baft/ → src/ → repo root
    return Path(__file__).resolve().parents[3] / "deploy" / "macos"


def _launchd_service_target() -> str:
    """`gui/<uid>/<label>` — the service-target form used by `launchctl kickstart`."""
    return f"gui/{os.getuid()}/{_LAUNCHD_LABEL}"


@itp_telegram.group()
def daemon() -> None:
    """Manage the macOS launchd agent (com.itp.telegram).

    Use this to install the service so it survives shell/desktop restarts,
    auto-starts at login, and restarts on crash. The agent runs
    `baft itp-telegram serve` as you (the logged-in user).
    """


@daemon.command("start")
@_common_options
def daemon_start(
    lm_studio_url: str | None,
    db_path: str | None,
    registry: str | None,
) -> None:
    """Start the service detached from this shell (nohup-style).

    Use when launchd is unavailable or blocked — for instance when the
    project lives on an external volume that macOS TCC restricts for
    launchd-spawned processes (see `daemon install` for the launchd path).

    The detached process is reparented to init (PPID 1), survives the
    shell that started it, and is killed by the existing
    `baft itp-telegram stop` command via its PID file.

    Trade-off vs `daemon install`: no auto-start at login, no
    auto-restart on crash. You re-run this after a reboot.
    """
    import subprocess
    import sys
    from .pid_manager import status as pid_status

    cfg = _resolve_cfg(lm_studio_url, db_path, registry)
    cfg.ensure_dirs()

    # Refuse to spawn a second daemon on top of a live one.
    s = pid_status(cfg.pid_path)
    if s.running:
        click.echo(click.style(
            f"Daemon already running (PID {s.pid}). Use `baft itp-telegram stop` first.",
            fg="yellow",
        ), err=True)
        raise SystemExit(1)
    if s.stale:
        click.echo(f"Removing stale PID file (pid {s.pid} is dead)")
        cfg.pid_path.unlink()

    log_path = cfg.log_path
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = log_path.open("ab")

    # start_new_session=True is Python's portable equivalent of setsid +
    # nohup combined: the child becomes a new session leader, won't get
    # SIGHUP when the controlling terminal closes, and is reparented to
    # init when this Python process exits.
    process = subprocess.Popen(
        [
            sys.argv[0], "itp-telegram", "serve",
            "--flush-interval", str(cfg.flush_interval_sec),
        ],
        stdin=subprocess.DEVNULL,
        stdout=log_file,
        stderr=log_file,
        start_new_session=True,
        close_fds=True,
        env={
            **os.environ,
            "PYTHONUNBUFFERED": "1",
        },
    )
    log_file.close()  # child still has its own fd

    click.echo(f"Started daemon (PID {process.pid}).")
    click.echo(f"  log:  {log_path}")
    click.echo(f"  pid:  {cfg.pid_path}  (written by service after telegram connect)")
    click.echo(f"  mcp:  http://{cfg.mcp_host}:{cfg.mcp_port}/mcp/")
    click.echo()
    click.echo("Useful commands:")
    click.echo("  baft itp-telegram daemon status   # full snapshot")
    click.echo("  baft itp-telegram daemon log -f   # follow log")
    click.echo("  baft itp-telegram stop            # graceful SIGTERM")


@daemon.command("install")
def daemon_install() -> None:
    """Install + load the launchd agent. Idempotent (replaces any prior copy).

    Note: macOS TCC blocks launchd-spawned processes from reading
    external volumes (anything under /Volumes/) without an explicit
    grant. If the project lives on an external SSD, use `daemon start`
    instead — it inherits TCC from your terminal session.
    """
    import subprocess

    script = _deploy_dir() / "install.sh"
    if not script.exists():
        click.echo(click.style(f"ERROR: {script} not found", fg="red"), err=True)
        raise SystemExit(1)
    rc = subprocess.run(["bash", str(script)], check=False).returncode
    raise SystemExit(rc)


@daemon.command("uninstall")
def daemon_uninstall() -> None:
    """Unload + remove the launchd agent. Preserves DB, session, .env."""
    import subprocess

    script = _deploy_dir() / "uninstall.sh"
    if not script.exists():
        click.echo(click.style(f"ERROR: {script} not found", fg="red"), err=True)
        raise SystemExit(1)
    rc = subprocess.run(["bash", str(script)], check=False).returncode
    raise SystemExit(rc)


@daemon.command("restart")
def daemon_restart() -> None:
    """Force a restart of the running agent (`launchctl kickstart -k`).

    Use after editing config or pulling code. If the agent is loaded but
    stopped (e.g. after `baft itp-telegram stop`), this also starts it.
    """
    import subprocess

    target = _launchd_service_target()
    result = subprocess.run(
        ["launchctl", "kickstart", "-k", target],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        click.echo(f"Kicked {target}. Service will be back up in a few seconds.")
    else:
        click.echo(click.style(
            f"launchctl kickstart failed: {result.stderr.strip() or result.stdout.strip()}",
            fg="red",
        ), err=True)
        click.echo(
            "If the agent isn't loaded, run: baft itp-telegram daemon install",
            err=True,
        )
        raise SystemExit(result.returncode)


@daemon.command("status")
@_common_options
def daemon_status(
    lm_studio_url: str | None,
    db_path: str | None,
    registry: str | None,
) -> None:
    """Show launchd state, PID, and MCP health for the agent."""
    import subprocess

    cfg = _resolve_cfg(lm_studio_url, db_path, registry)

    click.echo()
    click.echo(click.style("  ITP Telegram daemon status", fg="cyan", bold=True))
    click.echo()

    # launchctl knows about it?
    list_result = subprocess.run(
        ["launchctl", "list"],
        capture_output=True,
        text=True,
        check=False,
    )
    matching = [
        ln for ln in list_result.stdout.splitlines()
        if _LAUNCHD_LABEL in ln
    ]
    if matching:
        # Format: "<pid|->\t<exit|->\t<label>"
        parts = matching[0].split("\t")
        ld_pid = parts[0]
        ld_exit = parts[1] if len(parts) > 1 else "?"
        ld_state = (
            click.style("loaded + running", fg="green") if ld_pid != "-"
            else click.style("loaded but not running", fg="yellow")
        )
        click.echo(f"  launchd:    {ld_state}  (last_exit={ld_exit})")
    else:
        click.echo(f"  launchd:    {click.style('not installed', fg='red')}")
        click.echo("              Install: baft itp-telegram daemon install")

    # PID file + liveness (matches `baft itp-telegram status`)
    from .pid_manager import status as pid_status

    s = pid_status(cfg.pid_path)
    if s.pid is None:
        click.echo("  pid file:   (none)")
    elif s.running:
        click.echo(f"  pid file:   {s.pid} {click.style('(alive)', fg='green')}")
    else:
        click.echo(f"  pid file:   {s.pid} {click.style('(stale)', fg='yellow')}")

    # MCP health
    if s.running:
        try:
            data = _call_mcp(cfg, "capture_status", {})
            click.echo(
                f"  mcp:        {click.style('responding', fg='green')}  "
                f"http://{cfg.mcp_host}:{cfg.mcp_port}/mcp/"
            )
            click.echo(
                f"  capture:    received={data.get('total_received', 0)} "
                f"normalized={data.get('total_normalized', 0)} "
                f"stored={data.get('total_stored', 0)} "
                f"flushes={data.get('flush_count', 0)}"
            )
            if data.get("last_error"):
                click.echo(click.style(
                    f"  last error: {data['last_error']}", fg="yellow",
                ))
        except Exception as exc:  # noqa: BLE001
            click.echo(click.style(f"  mcp:        unreachable ({exc})", fg="yellow"))
    else:
        click.echo("  mcp:        (not running)")

    click.echo(f"  log:        {cfg.log_path}")
    click.echo(f"  db:         {cfg.db_path}")
    click.echo()


@daemon.command("log")
@click.option("-n", "lines", default=50, type=int, help="Initial lines (default 50).")
@click.option("-f", "follow", is_flag=True, help="Follow new lines (Ctrl-C to exit).")
@_common_options
def daemon_log(
    lm_studio_url: str | None,
    db_path: str | None,
    registry: str | None,
    lines: int,
    follow: bool,
) -> None:
    """Tail the daemon log."""
    import os as _os

    cfg = _resolve_cfg(lm_studio_url, db_path, registry)
    args = ["tail", f"-n{lines}"]
    if follow:
        args.append("-f")
    args.append(str(cfg.log_path))
    # exec replaces current process so Ctrl-C goes straight to tail
    _os.execvp(args[0], args)
