"""Baft CLI — session management and preflight checks for the ITP analytical engine.

Provides ``baft preflight`` for environment validation and ``baft session``
subcommands for starting, ending, and monitoring analytical sessions.

Usage::

    baft preflight
    baft session start [--session-id NAME]
    baft session end [--message TEXT]
    baft session status
    baft session sync-check
    baft session sync
"""

from __future__ import annotations

import datetime as dt
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

import click
import structlog

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_OK = click.style("[OK]", fg="green")
_WARN = click.style("[WARN]", fg="yellow")
_FAIL = click.style("[FAIL]", fg="red")


def _baft_dir() -> Path:
    """Resolve baft repo root.

    Derived from this module's path: ``baft/src/baft/cli.py`` → ``baft/``.
    The ``__file__``-relative derivation is more reliable than relying on
    ``ITP_ROOT/baft`` because it tolerates non-standard directory names
    (e.g. ``baft-dev`` for a working copy).
    """
    return Path(__file__).resolve().parents[2]


def _itp_root() -> Path:
    """Resolve ITP_ROOT from env, or auto-detect as parent of baft repo."""
    env = os.getenv("ITP_ROOT")
    if env:
        return Path(env)
    return _baft_dir().parent


def _baseline_dir() -> Path:
    return _itp_root() / "baseline"


def _workspace_dir() -> Path:
    env = os.getenv("BAFT_WORKSPACE")
    if env:
        return Path(env)
    return _baft_dir() / "itp-workspace"


def _nats_url() -> str:
    return os.getenv("NATS_URL", "nats://localhost:4222")


def _ollama_url() -> str:
    return os.getenv("OLLAMA_URL", "http://localhost:11434")


def _git(args: list[str], cwd: Path, **kwargs: Any) -> subprocess.CompletedProcess[str]:
    """Run a git command and return the result."""
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        **kwargs,
    )


def _generate_session_id() -> str:
    """Generate a session id from the current timestamp."""
    return dt.datetime.now(tz=dt.UTC).strftime("session-%Y%m%d-%H%M%S")


# ---------------------------------------------------------------------------
# Preflight checks
# ---------------------------------------------------------------------------


def _check_python_version() -> tuple[str, bool]:
    v = sys.version_info
    version_str = f"{v.major}.{v.minor}.{v.micro}"
    if v >= (3, 11):
        return f"{_OK} Python {version_str}", True
    return f"{_FAIL} Python {version_str} (need >= 3.11)", False


def _check_uv() -> tuple[str, bool]:
    uv_path = shutil.which("uv")
    if uv_path:
        try:
            result = subprocess.run(
                ["uv", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            version = result.stdout.strip().split()[-1] if result.returncode == 0 else "?"
            return f"{_OK} uv {version}", True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
    return f"{_FAIL} uv not found. Install: curl -LsSf https://astral.sh/uv/install.sh | sh", False


def _check_repos() -> tuple[str, bool]:
    root = _itp_root()
    repos = ["baseline", "heddle", "baft"]
    present = [r for r in repos if (root / r).is_dir()]
    missing = [r for r in repos if r not in present]
    if not missing:
        return f"{_OK} Repos: {', '.join(present)}", True
    return f"{_FAIL} Missing repos: {', '.join(missing)} (in {root})", False


def _check_deps() -> tuple[str, bool]:
    try:
        result = subprocess.run(
            ["uv", "run", "python", "-c", "import heddle; import baft"],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=str(_baft_dir()),
            check=False,
        )
        if result.returncode == 0:
            return f"{_OK} Dependencies installed", True
        return f"{_FAIL} Dependencies not installed. Run: uv sync --extra dev", False
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return f"{_FAIL} Could not verify dependencies", False


def _check_env_vars() -> tuple[str, bool]:
    required = {
        "ITP_ROOT": os.getenv("ITP_ROOT"),
        "BAFT_WORKSPACE": os.getenv("BAFT_WORKSPACE"),
        "ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY"),
    }
    missing = [k for k, v in required.items() if not v]
    # ITP_ROOT and BAFT_WORKSPACE can be auto-detected
    critical_missing = [k for k in missing if k == "ANTHROPIC_API_KEY"]
    if not missing:
        return f"{_OK} Environment variables set", True
    if not critical_missing:
        return f"{_WARN} Optional env vars not set: {', '.join(missing)} (auto-detected)", True
    return f"{_FAIL} Missing: {', '.join(missing)}", False


def _check_nats() -> tuple[str, bool]:
    url = _nats_url()
    # Parse host:port from nats://host:port
    host_port = url.replace("nats://", "").split("/")[0]
    parts = host_port.split(":")
    host = parts[0]
    port = int(parts[1]) if len(parts) > 1 else 4222
    try:
        sock = socket.create_connection((host, port), timeout=3)
        sock.close()
        return f"{_OK} NATS reachable ({host}:{port})", True
    except (OSError, TimeoutError):
        return (
            f"{_FAIL} NATS unreachable at {host}:{port}. Start: docker run -p 4222:4222 nats:latest"
        ), False


def _check_ollama() -> tuple[str, bool]:
    url = _ollama_url()
    try:
        import httpx

        resp = httpx.get(f"{url}/api/tags", timeout=5)
        if resp.status_code == 200:
            models = [m["name"] for m in resp.json().get("models", [])]
            model_str = ", ".join(models[:3]) if models else "no models loaded"
            return f"{_OK} Ollama reachable ({model_str})", True
        return f"{_WARN} Ollama returned {resp.status_code}", True
    except Exception:
        return f"{_FAIL} Ollama unreachable at {url}. Start: ollama serve", False


def _check_duckdb() -> tuple[str, bool]:
    db_path = _workspace_dir() / "itp.duckdb"
    if not db_path.exists():
        return (
            f"{_FAIL} DuckDB not found at {db_path}. "
            "Run: python pipeline/scripts/itp_import_to_duckdb.py"
        ), False
    stat = db_path.stat()
    size_mb = stat.st_size / (1024 * 1024)
    age_hours = (dt.datetime.now().timestamp() - stat.st_mtime) / 3600
    if age_hours > 24:
        return (
            f"{_WARN} DuckDB exists ({size_mb:.1f} MB, updated {age_hours:.0f}h ago — stale)"
        ), True
    return f"{_OK} DuckDB exists ({size_mb:.1f} MB, updated {age_hours:.0f}h ago)", True


def _check_baseline_git() -> tuple[str, bool]:
    fw = _baseline_dir()
    if not (fw / ".git").is_dir():
        return f"{_FAIL} Baseline is not a git repo", False
    result = _git(["status", "--porcelain"], cwd=fw)
    if result.returncode != 0:
        return f"{_FAIL} git status failed: {result.stderr.strip()}", False
    if result.stdout.strip():
        lines = result.stdout.strip().split("\n")
        return f"{_WARN} Baseline has uncommitted changes ({len(lines)} files)", True
    return f"{_OK} Baseline git clean", True


def _check_baseline_remote() -> tuple[str, bool]:
    fw = _baseline_dir()
    fetch = _git(["fetch", "origin", "--quiet"], cwd=fw)
    if fetch.returncode != 0:
        return f"{_WARN} Could not fetch baseline remote", True

    behind = _git(["rev-list", "--count", "HEAD..origin/main"], cwd=fw)
    ahead = _git(["rev-list", "--count", "origin/main..HEAD"], cwd=fw)

    behind_n = int(behind.stdout.strip()) if behind.returncode == 0 else 0
    ahead_n = int(ahead.stdout.strip()) if ahead.returncode == 0 else 0

    if behind_n > 0 and ahead_n > 0:
        return f"{_WARN} Baseline diverged ({ahead_n} ahead, {behind_n} behind)", True
    if behind_n > 0:
        return f"{_WARN} Baseline is {behind_n} commits behind remote", True
    if ahead_n > 0:
        return f"{_OK} Baseline is {ahead_n} commits ahead of remote", True
    return f"{_OK} Baseline up-to-date with remote", True


def run_preflight() -> tuple[int, int, int]:
    """Run all preflight checks. Returns (passed, warnings, failed) counts."""
    checks = [
        _check_python_version,
        _check_uv,
        _check_repos,
        _check_deps,
        _check_env_vars,
        _check_nats,
        _check_ollama,
        _check_duckdb,
        _check_baseline_git,
        _check_baseline_remote,
    ]

    click.echo()
    click.echo(click.style("ITP Preflight Check", bold=True))
    click.echo("─" * 40)

    passed = warnings = failed = 0
    for check_fn in checks:
        msg, ok = check_fn()
        click.echo(f"  {msg}")
        if ok:
            if "[WARN]" in msg:
                warnings += 1
            else:
                passed += 1
        else:
            failed += 1

    click.echo("─" * 40)
    total = passed + warnings + failed
    summary_parts = []
    if passed:
        summary_parts.append(f"{passed} passed")
    if warnings:
        summary_parts.append(f"{warnings} warnings")
    if failed:
        summary_parts.append(f"{failed} failed")
    click.echo(f"  {', '.join(summary_parts)} (of {total} checks)")
    click.echo()

    return passed, warnings, failed


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------


@click.group()
def main() -> None:
    """Baft — ITP analytical engine CLI."""


# Mount the ITP Telegram subgroup. Imported at function-call time inside
# the lazy registration below so the top-level CLI stays fast and stays
# importable even when telethon / fastmcp aren't installed.
def _register_itp_telegram() -> None:
    from baft.itp_telegram.cli import itp_telegram

    main.add_command(itp_telegram)


_register_itp_telegram()


@main.command()
def preflight() -> None:
    """Run environment preflight checks."""
    _passed, _warnings, failed = run_preflight()
    if failed > 0:
        raise SystemExit(1)


# ---------------------------------------------------------------------------
# Session subgroup
# ---------------------------------------------------------------------------


@main.group()
def session() -> None:
    """Manage analytical sessions."""


@session.command()
@click.option("--session-id", default=None, help="Session identifier (auto-generated if omitted)")
def start(session_id: str | None) -> None:
    """Start an analytical session (pull baseline, import DuckDB, check services)."""
    from baft.sessions import register_session

    sid = session_id or _generate_session_id()
    click.echo(f"Starting session: {sid}")

    # 1. Pull baseline
    fw = _baseline_dir()
    if (fw / ".git").is_dir():
        click.echo("  Pulling baseline...")
        pull = _git(["pull", "--ff-only"], cwd=fw)
        if pull.returncode != 0:
            click.echo(f"  {_FAIL} Baseline pull failed: {pull.stderr.strip()}")
            click.echo("  Resolve merge conflicts manually, then retry.")
            raise SystemExit(1)
        # Get current commit
        head = _git(["rev-parse", "--short", "HEAD"], cwd=fw)
        commit = head.stdout.strip() if head.returncode == 0 else "unknown"
        click.echo(f"  {_OK} Baseline at commit {commit}")
    else:
        click.echo(f"  {_WARN} Baseline dir not a git repo — skipping pull")

    # 2. Incremental DuckDB import
    import_script = _baft_dir() / "pipeline" / "scripts" / "itp_import_to_duckdb.py"
    if import_script.exists():
        click.echo("  Running incremental DuckDB import...")
        result = subprocess.run(
            ["uv", "run", "python", str(import_script), "--incremental"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(_baft_dir()),
            check=False,
        )
        if result.returncode == 0:
            click.echo(f"  {_OK} DuckDB updated")
        else:
            click.echo(f"  {_WARN} DuckDB import had issues: {result.stderr.strip()[:200]}")
    else:
        click.echo(f"  {_WARN} Import script not found — skipping DuckDB import")

    # 3. Quick service checks
    _nats_msg, nats_ok = _check_nats()
    click.echo(f"  {_nats_msg}")
    _ollama_msg, _ollama_ok = _check_ollama()
    click.echo(f"  {_ollama_msg}")

    if not nats_ok:
        click.echo(f"\n  {_FAIL} NATS is required. Start it before proceeding.")
        raise SystemExit(1)

    # 4. Register session
    register_session(sid)
    click.echo(
        f"\n  Session {click.style(sid, bold=True)} is active. All core services operational."
    )


# ---------------------------------------------------------------------------
# session end — helpers
# ---------------------------------------------------------------------------


def _resolve_session_to_end(session_id: str | None, yes: bool) -> str | None:
    """Pick a session id to end, or return None if no active sessions exist."""
    from baft.sessions import get_active_sessions

    if session_id is not None:
        return session_id
    active = get_active_sessions()
    if not active:
        click.echo("No active sessions found.")
        return None
    sid = active[0]["session_monitor_request"]["session_id"]
    if len(active) > 1 and not yes:
        click.echo(f"  Multiple active sessions ({len(active)}). Ending most recent: {sid}")
    return sid


def _baseline_dirty_files(baseline: Path) -> list[str]:
    """Return porcelain status lines, or [] if not a git repo or clean."""
    if not (baseline / ".git").is_dir():
        return []
    status = _git(["status", "--porcelain"], cwd=baseline)
    if not status.stdout.strip():
        return []
    return [line.strip() for line in status.stdout.strip().split("\n") if line.strip()]


def _confirm_commit(sid: str, dirty_files: list[str]) -> bool:
    """Show pending changes and prompt for confirmation; True iff approved."""
    styled_sid = click.style(sid, bold=True)
    click.echo(f"\n  Session {styled_sid} — {len(dirty_files)} changed file(s):")
    for f in dirty_files[:20]:
        click.echo(f"    {f}")
    if len(dirty_files) > 20:
        click.echo(f"    ... and {len(dirty_files) - 20} more")
    click.echo()
    return click.confirm("  Commit and push these changes?", default=True)


def _commit_and_push_baseline(baseline: Path, sid: str, message: str) -> None:
    """Stage data/, commit, push. Exits non-zero on commit failure."""
    date_str = dt.datetime.now(tz=dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    desc = message or "analytical session updates"
    commit_msg = f"Session {sid}: {desc} — {date_str}"

    # Stage only data/ (analytical content), not repo config.
    _git(["add", "data/"], cwd=baseline)
    # Also stage any other tracked-file changes (but not untracked junk).
    _git(["add", "-u"], cwd=baseline)
    commit = _git(["commit", "-m", commit_msg], cwd=baseline)
    if commit.returncode != 0:
        click.echo(f"  {_FAIL} Commit failed: {commit.stderr.strip()}")
        raise SystemExit(1)

    push = _git(["push"], cwd=baseline)
    if push.returncode == 0:
        click.echo(f"  {_OK} Baseline changes committed and pushed.")
    else:
        click.echo(f"  {_WARN} Committed locally but push failed: {push.stderr.strip()}")
        click.echo("  Run `baft session sync-check` then push manually.")


@session.command()
@click.option("--session-id", default=None, help="Session to end (uses most recent if omitted)")
@click.option("--message", "-m", default="", help="Commit message describing session work")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
def end(session_id: str | None, message: str, yes: bool) -> None:
    """End an analytical session (commit baseline, push, unregister)."""
    from baft.sessions import unregister_session

    sid = _resolve_session_to_end(session_id, yes)
    if sid is None:
        return

    baseline = _baseline_dir()
    dirty_files = _baseline_dirty_files(baseline)

    if dirty_files and not yes and not _confirm_commit(sid, dirty_files):
        click.echo("  Aborted. Session still active.")
        return

    unregister_session(sid)

    if not (baseline / ".git").is_dir():
        click.echo(f"  {_WARN} Baseline not a git repo — skipping commit")
    elif dirty_files:
        _commit_and_push_baseline(baseline, sid, message)
    else:
        click.echo("  No baseline changes to commit.")

    click.echo(f"\n  Session {click.style(sid, bold=True)} ended.")


@session.command()
def status() -> None:
    """Show active sessions and system health."""
    from baft.sessions import get_active_sessions

    # Active sessions
    active = get_active_sessions()
    click.echo(click.style("\nActive sessions", bold=True))
    if active:
        for s in active:
            info = s["session_monitor_request"]
            click.echo(
                f"  • {info['session_id']} (tier {info.get('current_tier', '?')}, "
                f"ops {info.get('operation_count', 0)})"
            )
    else:
        click.echo("  (none)")

    # Baseline git
    click.echo(click.style("\nBaseline status", bold=True))
    msg, _ = _check_baseline_git()
    click.echo(f"  {msg}")

    # Services
    click.echo(click.style("\nServices", bold=True))
    nats_msg, _ = _check_nats()
    click.echo(f"  {nats_msg}")
    ollama_msg, _ = _check_ollama()
    click.echo(f"  {ollama_msg}")
    db_msg, _ = _check_duckdb()
    click.echo(f"  {db_msg}")
    click.echo()


@session.command("sync-check")
def sync_check() -> None:
    """Check if the baseline remote has new commits."""
    fw = _baseline_dir()
    if not (fw / ".git").is_dir():
        click.echo(f"{_FAIL} Baseline is not a git repo")
        raise SystemExit(1)

    click.echo("Fetching remote...")
    fetch = _git(["fetch", "origin", "--quiet"], cwd=fw)
    if fetch.returncode != 0:
        click.echo(f"{_FAIL} Could not fetch: {fetch.stderr.strip()}")
        raise SystemExit(1)

    behind = _git(["rev-list", "--count", "HEAD..origin/main"], cwd=fw)
    ahead = _git(["rev-list", "--count", "origin/main..HEAD"], cwd=fw)
    behind_n = int(behind.stdout.strip()) if behind.returncode == 0 else 0
    ahead_n = int(ahead.stdout.strip()) if ahead.returncode == 0 else 0

    if behind_n > 0 and ahead_n > 0:
        click.echo(f"{_WARN} Baseline has diverged ({ahead_n} ahead, {behind_n} behind).")
        click.echo("  Manual resolution needed: cd $ITP_ROOT/baseline && git status")
    elif behind_n > 0:
        click.echo(f"{_WARN} Baseline has {behind_n} new commits from remote.")
        click.echo("  Run `baft session sync` to pull and re-import.")
    elif ahead_n > 0:
        click.echo(f"You have {ahead_n} local commits not yet pushed.")
    else:
        click.echo(f"{_OK} Baseline is current.")


@session.command()
def sync() -> None:
    """Pull baseline updates and run incremental DuckDB import."""
    fw = _baseline_dir()
    if not (fw / ".git").is_dir():
        click.echo(f"{_FAIL} Baseline is not a git repo")
        raise SystemExit(1)

    click.echo("Pulling baseline...")
    pull = _git(["pull", "--ff-only"], cwd=fw)
    if pull.returncode != 0:
        click.echo(f"{_FAIL} Pull failed (conflict?): {pull.stderr.strip()}")
        raise SystemExit(1)

    head = _git(["rev-parse", "--short", "HEAD"], cwd=fw)
    commit = head.stdout.strip() if head.returncode == 0 else "unknown"

    # Incremental import
    import_script = _baft_dir() / "pipeline" / "scripts" / "itp_import_to_duckdb.py"
    if import_script.exists():
        click.echo("Running incremental DuckDB import...")
        result = subprocess.run(
            ["uv", "run", "python", str(import_script), "--incremental"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(_baft_dir()),
            check=False,
        )
        if result.returncode == 0:
            click.echo(f"{_OK} Synced to {commit}. DuckDB updated.")
        else:
            click.echo(f"{_WARN} Synced to {commit} but DuckDB import had issues.")
    else:
        click.echo(f"{_OK} Synced to {commit}. (Import script not found — skipped DuckDB.)")
