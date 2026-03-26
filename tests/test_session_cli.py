"""Tests for the baft CLI — session management and preflight checks."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from baft.cli import main


@pytest.fixture
def runner():
    return CliRunner()


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------


class TestPreflight:
    """Tests for `baft preflight`."""

    def test_preflight_outputs_header(self, runner):
        """Preflight prints a header and check results."""
        with (
            patch("baft.cli._check_python_version", return_value=("[OK] Python 3.12.4", True)),
            patch("baft.cli._check_uv", return_value=("[OK] uv 0.6.3", True)),
            patch(
                "baft.cli._check_repos", return_value=("[OK] Repos: framework, loom, baft", True)
            ),
            patch("baft.cli._check_deps", return_value=("[OK] Dependencies installed", True)),
            patch(
                "baft.cli._check_env_vars", return_value=("[OK] Environment variables set", True)
            ),
            patch(
                "baft.cli._check_nats", return_value=("[OK] NATS reachable (localhost:4222)", True)
            ),
            patch(
                "baft.cli._check_ollama", return_value=("[OK] Ollama reachable (llama3.2:3b)", True)
            ),
            patch("baft.cli._check_duckdb", return_value=("[OK] DuckDB exists (14.2 MB)", True)),
            patch("baft.cli._check_framework_git", return_value=("[OK] Framework git clean", True)),
            patch(
                "baft.cli._check_framework_remote", return_value=("[OK] Framework up-to-date", True)
            ),
        ):
            result = runner.invoke(main, ["preflight"])

        assert result.exit_code == 0
        assert "Preflight Check" in result.output

    def test_preflight_exits_1_on_failure(self, runner):
        """Preflight exits with code 1 if any check fails."""
        with (
            patch("baft.cli._check_python_version", return_value=("[FAIL] Python 3.9", False)),
            patch("baft.cli._check_uv", return_value=("[OK] uv", True)),
            patch("baft.cli._check_repos", return_value=("[OK] Repos", True)),
            patch("baft.cli._check_deps", return_value=("[OK] Deps", True)),
            patch("baft.cli._check_env_vars", return_value=("[OK] Env", True)),
            patch("baft.cli._check_nats", return_value=("[OK] NATS", True)),
            patch("baft.cli._check_ollama", return_value=("[OK] Ollama", True)),
            patch("baft.cli._check_duckdb", return_value=("[OK] DuckDB", True)),
            patch("baft.cli._check_framework_git", return_value=("[OK] Git", True)),
            patch("baft.cli._check_framework_remote", return_value=("[OK] Remote", True)),
        ):
            result = runner.invoke(main, ["preflight"])

        assert result.exit_code == 1

    def test_preflight_counts_warnings(self, runner):
        """Warnings count separately from failures."""
        with (
            patch("baft.cli._check_python_version", return_value=("[OK] Python 3.12", True)),
            patch("baft.cli._check_uv", return_value=("[OK] uv", True)),
            patch("baft.cli._check_repos", return_value=("[OK] Repos", True)),
            patch("baft.cli._check_deps", return_value=("[OK] Deps", True)),
            patch("baft.cli._check_env_vars", return_value=("[WARN] Optional env vars", True)),
            patch("baft.cli._check_nats", return_value=("[OK] NATS", True)),
            patch("baft.cli._check_ollama", return_value=("[OK] Ollama", True)),
            patch("baft.cli._check_duckdb", return_value=("[OK] DuckDB", True)),
            patch("baft.cli._check_framework_git", return_value=("[WARN] Uncommitted", True)),
            patch("baft.cli._check_framework_remote", return_value=("[OK] Remote", True)),
        ):
            result = runner.invoke(main, ["preflight"])

        assert result.exit_code == 0
        assert "2 warnings" in result.output


# ---------------------------------------------------------------------------
# Session start
# ---------------------------------------------------------------------------


class TestSessionStart:
    """Tests for `baft session start`."""

    def test_start_with_auto_id(self, runner, tmp_path):
        """Session start auto-generates an ID when none provided."""
        fw = tmp_path / "framework"
        fw.mkdir()
        (fw / ".git").mkdir()

        with (
            patch("baft.cli._framework_dir", return_value=fw),
            patch("baft.cli._baft_dir", return_value=tmp_path),
            patch("baft.cli._git") as mock_git,
            patch("baft.cli._check_nats", return_value=("[OK] NATS", True)),
            patch("baft.cli._check_ollama", return_value=("[OK] Ollama", True)),
            patch("baft.sessions.register_session") as mock_register,
        ):
            mock_git.return_value = MagicMock(returncode=0, stdout="abc1234\n", stderr="")
            result = runner.invoke(main, ["session", "start"])

        assert result.exit_code == 0
        assert "session-" in result.output
        mock_register.assert_called_once()

    def test_start_with_explicit_id(self, runner, tmp_path):
        """Session start uses the provided session ID."""
        fw = tmp_path / "framework"
        fw.mkdir()
        (fw / ".git").mkdir()

        with (
            patch("baft.cli._framework_dir", return_value=fw),
            patch("baft.cli._baft_dir", return_value=tmp_path),
            patch("baft.cli._git") as mock_git,
            patch("baft.cli._check_nats", return_value=("[OK] NATS", True)),
            patch("baft.cli._check_ollama", return_value=("[OK] Ollama", True)),
            patch("baft.sessions.register_session") as mock_register,
        ):
            mock_git.return_value = MagicMock(returncode=0, stdout="abc1234\n", stderr="")
            result = runner.invoke(main, ["session", "start", "--session-id", "my-session"])

        assert result.exit_code == 0
        assert "my-session" in result.output
        mock_register.assert_called_once_with("my-session")

    def test_start_fails_if_git_pull_fails(self, runner, tmp_path):
        """Session start exits 1 if git pull fails (merge conflict)."""
        fw = tmp_path / "framework"
        fw.mkdir()
        (fw / ".git").mkdir()

        with (
            patch("baft.cli._framework_dir", return_value=fw),
            patch("baft.cli._baft_dir", return_value=tmp_path),
            patch("baft.cli._git") as mock_git,
        ):
            mock_git.return_value = MagicMock(returncode=1, stdout="", stderr="merge conflict")
            result = runner.invoke(main, ["session", "start"])

        assert result.exit_code == 1
        assert "pull failed" in result.output.lower() or "FAIL" in result.output

    def test_start_fails_if_nats_unreachable(self, runner, tmp_path):
        """Session start exits 1 if NATS is not reachable."""
        fw = tmp_path / "framework"
        fw.mkdir()
        (fw / ".git").mkdir()

        with (
            patch("baft.cli._framework_dir", return_value=fw),
            patch("baft.cli._baft_dir", return_value=tmp_path),
            patch("baft.cli._git") as mock_git,
            patch("baft.cli._check_nats", return_value=("[FAIL] NATS unreachable", False)),
            patch("baft.cli._check_ollama", return_value=("[OK] Ollama", True)),
        ):
            mock_git.return_value = MagicMock(returncode=0, stdout="abc1234\n", stderr="")
            result = runner.invoke(main, ["session", "start"])

        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# Session end
# ---------------------------------------------------------------------------


class TestSessionEnd:
    """Tests for `baft session end`."""

    def test_end_commits_and_pushes(self, runner, tmp_path):
        """Session end with --yes commits dirty framework and pushes."""
        fw = tmp_path / "framework"
        fw.mkdir()
        (fw / ".git").mkdir()

        call_count = {"n": 0}

        def mock_git_fn(args, cwd, **_kwargs):
            call_count["n"] += 1
            mock = MagicMock(returncode=0, stdout="", stderr="")
            if args[0] == "status":
                mock.stdout = "M data/some_file.yaml\n"
            return mock

        with (
            patch("baft.cli._framework_dir", return_value=fw),
            patch("baft.cli._git", side_effect=mock_git_fn),
            patch("baft.sessions.unregister_session") as mock_unreg,
            patch(
                "baft.sessions.get_active_sessions",
                return_value=[{"session_monitor_request": {"session_id": "test-session"}}],
            ),
        ):
            result = runner.invoke(main, ["session", "end", "--yes"])

        assert result.exit_code == 0
        assert "committed and pushed" in result.output.lower() or "ended" in result.output.lower()
        mock_unreg.assert_called_once()

    def test_end_no_changes(self, runner, tmp_path):
        """Session end with clean framework skips commit."""
        fw = tmp_path / "framework"
        fw.mkdir()
        (fw / ".git").mkdir()

        def mock_git_fn(args, cwd, **_kwargs):
            mock = MagicMock(returncode=0, stdout="", stderr="")
            return mock

        with (
            patch("baft.cli._framework_dir", return_value=fw),
            patch("baft.cli._git", side_effect=mock_git_fn),
            patch("baft.sessions.unregister_session"),
            patch(
                "baft.sessions.get_active_sessions",
                return_value=[{"session_monitor_request": {"session_id": "test-session"}}],
            ),
        ):
            result = runner.invoke(main, ["session", "end", "--yes"])

        assert result.exit_code == 0
        assert "No framework changes" in result.output

    def test_end_no_active_sessions(self, runner):
        """Session end with no active sessions reports and exits cleanly."""
        with patch("baft.sessions.get_active_sessions", return_value=[]):
            result = runner.invoke(main, ["session", "end"])

        assert result.exit_code == 0
        assert "No active sessions" in result.output

    def test_end_prompts_confirmation(self, runner, tmp_path):
        """Session end without --yes shows dirty files and prompts."""
        fw = tmp_path / "framework"
        fw.mkdir()
        (fw / ".git").mkdir()

        def mock_git_fn(args, cwd, **_kwargs):
            mock = MagicMock(returncode=0, stdout="", stderr="")
            if args[0] == "status":
                mock.stdout = "M data/variables.yaml\nM data/observations.yaml\n"
            return mock

        with (
            patch("baft.cli._framework_dir", return_value=fw),
            patch("baft.cli._git", side_effect=mock_git_fn),
            patch("baft.sessions.unregister_session"),
            patch(
                "baft.sessions.get_active_sessions",
                return_value=[{"session_monitor_request": {"session_id": "test-session"}}],
            ),
        ):
            # User declines — session should remain active
            result = runner.invoke(main, ["session", "end"], input="n\n")

        assert result.exit_code == 0
        assert "Aborted" in result.output

    def test_end_confirmation_yes(self, runner, tmp_path):
        """Session end with interactive confirmation proceeds on yes."""
        fw = tmp_path / "framework"
        fw.mkdir()
        (fw / ".git").mkdir()

        def mock_git_fn(args, cwd, **_kwargs):
            mock = MagicMock(returncode=0, stdout="", stderr="")
            if args[0] == "status":
                mock.stdout = "M data/variables.yaml\n"
            return mock

        with (
            patch("baft.cli._framework_dir", return_value=fw),
            patch("baft.cli._git", side_effect=mock_git_fn),
            patch("baft.sessions.unregister_session"),
            patch(
                "baft.sessions.get_active_sessions",
                return_value=[{"session_monitor_request": {"session_id": "test-session"}}],
            ),
        ):
            result = runner.invoke(main, ["session", "end"], input="y\n")

        assert result.exit_code == 0
        assert "ended" in result.output.lower()


# ---------------------------------------------------------------------------
# Session sorting
# ---------------------------------------------------------------------------


class TestSessionSorting:
    """Tests that get_active_sessions returns sessions sorted by last_active."""

    def test_sessions_sorted_most_recent_first(self, tmp_path):
        """Active sessions are sorted by last_active descending."""
        import json
        import time

        from baft.sessions import _SESSION_DIR, get_active_sessions

        # Create temp session dir
        session_dir = tmp_path / "sessions"
        session_dir.mkdir()

        now = time.time()
        # Write markers with different timestamps (older first in filesystem)
        for i, (sid, offset) in enumerate([
            ("old-session", -600),
            ("newest-session", -10),
            ("middle-session", -300),
        ]):
            marker = {"session_id": sid, "last_active": now + offset}
            (session_dir / f"{sid}.json").write_text(json.dumps(marker))

        with patch("baft.sessions._SESSION_DIR", session_dir):
            active = get_active_sessions()

        assert len(active) == 3
        ids = [s["session_monitor_request"]["session_id"] for s in active]
        assert ids == ["newest-session", "middle-session", "old-session"]


# ---------------------------------------------------------------------------
# Session status
# ---------------------------------------------------------------------------


class TestSessionStatus:
    """Tests for `baft session status`."""

    def test_status_shows_active_sessions(self, runner, tmp_path):
        """Status lists active sessions."""
        fw = tmp_path / "framework"
        fw.mkdir()
        (fw / ".git").mkdir()

        with (
            patch(
                "baft.sessions.get_active_sessions",
                return_value=[
                    {
                        "session_monitor_request": {
                            "session_id": "s1",
                            "current_tier": 2,
                            "operation_count": 5,
                        }
                    }
                ],
            ),
            patch("baft.cli._framework_dir", return_value=fw),
            patch("baft.cli._check_framework_git", return_value=("[OK] Clean", True)),
            patch("baft.cli._check_nats", return_value=("[OK] NATS", True)),
            patch("baft.cli._check_ollama", return_value=("[OK] Ollama", True)),
            patch("baft.cli._check_duckdb", return_value=("[OK] DuckDB", True)),
        ):
            result = runner.invoke(main, ["session", "status"])

        assert result.exit_code == 0
        assert "s1" in result.output

    def test_status_no_sessions(self, runner, tmp_path):
        """Status with no active sessions shows (none)."""
        fw = tmp_path / "framework"
        fw.mkdir()
        (fw / ".git").mkdir()

        with (
            patch("baft.sessions.get_active_sessions", return_value=[]),
            patch("baft.cli._framework_dir", return_value=fw),
            patch("baft.cli._check_framework_git", return_value=("[OK] Clean", True)),
            patch("baft.cli._check_nats", return_value=("[OK] NATS", True)),
            patch("baft.cli._check_ollama", return_value=("[OK] Ollama", True)),
            patch("baft.cli._check_duckdb", return_value=("[OK] DuckDB", True)),
        ):
            result = runner.invoke(main, ["session", "status"])

        assert result.exit_code == 0
        assert "(none)" in result.output


# ---------------------------------------------------------------------------
# Session sync-check
# ---------------------------------------------------------------------------


class TestSessionSyncCheck:
    """Tests for `baft session sync-check`."""

    def test_sync_check_up_to_date(self, runner, tmp_path):
        """Sync-check reports current when up-to-date."""
        fw = tmp_path / "framework"
        fw.mkdir()
        (fw / ".git").mkdir()

        def mock_git_fn(args, cwd, **_kwargs):
            mock = MagicMock(returncode=0, stderr="")
            if "rev-list" in args:
                mock.stdout = "0\n"
            else:
                mock.stdout = ""
            return mock

        with (
            patch("baft.cli._framework_dir", return_value=fw),
            patch("baft.cli._git", side_effect=mock_git_fn),
        ):
            result = runner.invoke(main, ["session", "sync-check"])

        assert result.exit_code == 0
        assert "current" in result.output.lower()

    def test_sync_check_behind(self, runner, tmp_path):
        """Sync-check warns when behind remote."""
        fw = tmp_path / "framework"
        fw.mkdir()
        (fw / ".git").mkdir()

        def mock_git_fn(args, cwd, **_kwargs):
            mock = MagicMock(returncode=0, stderr="")
            if args == ["rev-list", "--count", "HEAD..origin/main"]:
                mock.stdout = "3\n"
            elif args == ["rev-list", "--count", "origin/main..HEAD"]:
                mock.stdout = "0\n"
            else:
                mock.stdout = ""
            return mock

        with (
            patch("baft.cli._framework_dir", return_value=fw),
            patch("baft.cli._git", side_effect=mock_git_fn),
        ):
            result = runner.invoke(main, ["session", "sync-check"])

        assert result.exit_code == 0
        assert "3 new commits" in result.output


# ---------------------------------------------------------------------------
# Session sync
# ---------------------------------------------------------------------------


class TestSessionSync:
    """Tests for `baft session sync`."""

    def test_sync_pulls_and_imports(self, runner, tmp_path):
        """Sync pulls framework and runs DuckDB import."""
        fw = tmp_path / "framework"
        fw.mkdir()
        (fw / ".git").mkdir()

        # Create a fake import script
        scripts_dir = tmp_path / "pipeline" / "scripts"
        scripts_dir.mkdir(parents=True)
        (scripts_dir / "itp_import_to_duckdb.py").write_text("# stub")

        def mock_git_fn(args, cwd, **_kwargs):
            mock = MagicMock(returncode=0, stderr="")
            if args == ["rev-parse", "--short", "HEAD"]:
                mock.stdout = "abc1234\n"
            else:
                mock.stdout = ""
            return mock

        with (
            patch("baft.cli._framework_dir", return_value=fw),
            patch("baft.cli._baft_dir", return_value=tmp_path),
            patch("baft.cli._git", side_effect=mock_git_fn),
            patch("subprocess.run") as mock_subprocess,
        ):
            mock_subprocess.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = runner.invoke(main, ["session", "sync"])

        assert result.exit_code == 0
        assert "abc1234" in result.output

    def test_sync_fails_on_conflict(self, runner, tmp_path):
        """Sync exits 1 if pull fails."""
        fw = tmp_path / "framework"
        fw.mkdir()
        (fw / ".git").mkdir()

        with patch("baft.cli._framework_dir", return_value=fw), patch("baft.cli._git") as mock_git:
            mock_git.return_value = MagicMock(returncode=1, stdout="", stderr="conflict")
            result = runner.invoke(main, ["session", "sync"])

        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# Preflight individual checks (unit tests)
# ---------------------------------------------------------------------------


class TestPreflightChecks:
    """Unit tests for individual preflight check functions."""

    def test_check_python_version(self):
        from baft.cli import _check_python_version

        msg, ok = _check_python_version()
        # We're running on Python 3.11+ (required by pyproject.toml)
        assert ok
        assert "Python" in msg

    def test_check_nats_unreachable(self):
        """NATS check fails when port is closed."""
        from baft.cli import _check_nats

        with patch("baft.cli._nats_url", return_value="nats://127.0.0.1:19999"):
            msg, ok = _check_nats()
        assert not ok
        assert "unreachable" in msg.lower() or "FAIL" in msg

    def test_check_duckdb_missing(self, tmp_path):
        """DuckDB check fails when file doesn't exist."""
        from baft.cli import _check_duckdb

        with patch("baft.cli._workspace_dir", return_value=tmp_path):
            msg, ok = _check_duckdb()
        assert not ok

    def test_check_duckdb_exists(self, tmp_path):
        """DuckDB check passes when file exists."""
        from baft.cli import _check_duckdb

        (tmp_path / "itp.duckdb").write_bytes(b"x" * 1000)
        with patch("baft.cli._workspace_dir", return_value=tmp_path):
            msg, ok = _check_duckdb()
        assert ok

    def test_check_framework_git_clean(self, tmp_path):
        """Framework git check passes on clean repo."""
        from baft.cli import _check_framework_git

        fw = tmp_path / "framework"
        fw.mkdir()
        (fw / ".git").mkdir()
        with patch("baft.cli._framework_dir", return_value=fw), patch("baft.cli._git") as mock_git:
            mock_git.return_value = MagicMock(returncode=0, stdout="", stderr="")
            msg, ok = _check_framework_git()
        assert ok
        assert "clean" in msg.lower()

    def test_check_framework_git_dirty(self, tmp_path):
        """Framework git check warns on dirty repo."""
        from baft.cli import _check_framework_git

        fw = tmp_path / "framework"
        fw.mkdir()
        (fw / ".git").mkdir()
        with patch("baft.cli._framework_dir", return_value=fw), patch("baft.cli._git") as mock_git:
            mock_git.return_value = MagicMock(
                returncode=0, stdout="M file1.yaml\nM file2.yaml\n", stderr=""
            )
            msg, ok = _check_framework_git()
        assert ok  # Warning, not failure
        assert "2 files" in msg
