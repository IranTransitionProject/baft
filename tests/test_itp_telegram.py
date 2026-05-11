"""
test_itp_telegram.py
--------------------
Unit tests for the ``baft.itp_telegram`` subsystem.

Scope: stdlib-level wrappers (config, pid_manager), thin adapters
(store, llm_backend, channel_profiles), structural construction
(mcp_server, service.serve guard), and Click command surfaces (cli).

The Telegram client (telethon), LM Studio HTTP, and DuckDB are mocked
or shimmed; nothing here touches the network or persistent storage.
"""

from __future__ import annotations

import json
import os
import signal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from click.testing import CliRunner

# ── pid_manager ────────────────────────────────────────────────────────


class TestPidManager:
    def test_write_pid_uses_current_pid_by_default(self, tmp_path: Path):
        from baft.itp_telegram.pid_manager import read_pid, write_pid

        path = tmp_path / "svc.pid"
        write_pid(path)
        assert read_pid(path) == os.getpid()

    def test_write_pid_creates_parent_dirs(self, tmp_path: Path):
        from baft.itp_telegram.pid_manager import read_pid, write_pid

        path = tmp_path / "nested" / "dirs" / "svc.pid"
        write_pid(path, pid=12345)
        assert read_pid(path) == 12345

    def test_read_pid_missing_returns_none(self, tmp_path: Path):
        from baft.itp_telegram.pid_manager import read_pid

        assert read_pid(tmp_path / "nope.pid") is None

    def test_read_pid_malformed_returns_none(self, tmp_path: Path):
        from baft.itp_telegram.pid_manager import read_pid

        path = tmp_path / "bad.pid"
        path.write_text("not a number\n")
        assert read_pid(path) is None

    def test_remove_pid_is_idempotent(self, tmp_path: Path):
        from baft.itp_telegram.pid_manager import remove_pid, write_pid

        path = tmp_path / "svc.pid"
        write_pid(path, pid=1)
        remove_pid(path)
        remove_pid(path)  # missing — must not raise
        assert not path.exists()

    def test_is_running_true_for_self(self):
        from baft.itp_telegram.pid_manager import is_running

        assert is_running(os.getpid()) is True

    def test_is_running_false_for_unused_pid(self):
        from baft.itp_telegram.pid_manager import is_running

        # PID 2**22 is reliably unused on macOS/Linux (max is typically 2**15-2**22)
        # but kernel.pid_max can be higher; use a value that's deliberately huge.
        assert is_running(2_147_483_640) is False

    def test_status_no_file(self, tmp_path: Path):
        from baft.itp_telegram.pid_manager import status

        s = status(tmp_path / "nope.pid")
        assert s.pid is None
        assert s.running is False
        assert s.stale is False

    def test_status_running(self, tmp_path: Path):
        from baft.itp_telegram.pid_manager import status, write_pid

        path = tmp_path / "svc.pid"
        write_pid(path)  # current pid
        s = status(path)
        assert s.pid == os.getpid()
        assert s.running is True
        assert s.stale is False

    def test_status_stale(self, tmp_path: Path):
        from baft.itp_telegram.pid_manager import status, write_pid

        path = tmp_path / "svc.pid"
        write_pid(path, pid=2_147_483_640)
        s = status(path)
        assert s.pid == 2_147_483_640
        assert s.running is False
        assert s.stale is True


# ── config ─────────────────────────────────────────────────────────────


class TestITPTelegramConfig:
    def test_defaults_have_heddle_paths(self):
        from baft.itp_telegram.config import ITPTelegramConfig

        cfg = ITPTelegramConfig()
        heddle = Path.home() / ".heddle"
        assert cfg.session_path == heddle / "telegram.session"
        assert cfg.db_path == heddle / "itp_rag.duckdb"
        assert cfg.pid_path == heddle / "itp_telegram.pid"
        assert cfg.log_path == heddle / "itp_telegram.log"

    def test_default_registry_path_under_baft(self):
        from baft.itp_telegram.config import ITPTelegramConfig

        cfg = ITPTelegramConfig()
        assert cfg.registry_path.parts[-3:] == ("pipeline", "config", "itp_telegram_channels.yaml")

    def test_from_env_picks_up_telegram_credentials(self, monkeypatch):
        from baft.itp_telegram.config import ITPTelegramConfig

        monkeypatch.setenv("TELEGRAM_API_ID", "12345")
        monkeypatch.setenv("TELEGRAM_API_HASH", "abc123")
        monkeypatch.setenv("LM_STUDIO_URL", "http://example:5678/v1")
        cfg = ITPTelegramConfig.from_env()
        assert cfg.api_id == 12345
        assert cfg.api_hash == "abc123"
        assert cfg.lm_studio_url == "http://example:5678/v1"

    def test_from_env_handles_bad_api_id(self, monkeypatch):
        from baft.itp_telegram.config import ITPTelegramConfig

        monkeypatch.setenv("TELEGRAM_API_ID", "not-a-number")
        cfg = ITPTelegramConfig.from_env()
        assert cfg.api_id == 0  # falls back, no exception

    def test_from_env_session_override(self, monkeypatch, tmp_path):
        from baft.itp_telegram.config import ITPTelegramConfig

        custom = tmp_path / "custom.session"
        monkeypatch.setenv("TELEGRAM_SESSION", str(custom))
        cfg = ITPTelegramConfig.from_env()
        assert cfg.session_path == custom

    def test_ensure_dirs_creates_parents(self, tmp_path):
        from baft.itp_telegram.config import ITPTelegramConfig

        cfg = ITPTelegramConfig()
        cfg.session_path = tmp_path / "a" / "session"
        cfg.db_path = tmp_path / "b" / "db"
        cfg.pid_path = tmp_path / "c" / "pid"
        cfg.log_path = tmp_path / "d" / "log"
        cfg.ensure_dirs()
        for p in (cfg.session_path, cfg.db_path, cfg.pid_path, cfg.log_path):
            assert p.parent.is_dir()

    def test_ensure_credentials_raises_when_missing(self):
        from baft.itp_telegram.config import ITPTelegramConfig

        cfg = ITPTelegramConfig()  # defaults: api_id=0, api_hash=""
        with pytest.raises(RuntimeError, match="TELEGRAM_API_ID"):
            cfg.ensure_credentials()

    def test_ensure_credentials_ok_when_set(self):
        from baft.itp_telegram.config import ITPTelegramConfig

        cfg = ITPTelegramConfig()
        cfg.api_id = 1
        cfg.api_hash = "h"
        cfg.ensure_credentials()  # no raise


# ── store ──────────────────────────────────────────────────────────────


class TestStore:
    def test_open_store_wires_lm_studio(self, tmp_path):
        from baft.itp_telegram import store as store_mod
        from baft.itp_telegram.config import ITPTelegramConfig

        cfg = ITPTelegramConfig()
        cfg.db_path = tmp_path / "db" / "itp.duckdb"
        cfg.lm_studio_url = "http://x:1/v1"
        cfg.embedding_model = "test-embed"
        cfg.pid_path = tmp_path / "pid"
        cfg.log_path = tmp_path / "log"
        cfg.session_path = tmp_path / "session"

        fake_store = MagicMock()
        fake_store.initialize.return_value = fake_store

        with patch.object(store_mod, "DuckDBVectorStore", return_value=fake_store) as ctor:
            result = store_mod.open_store(cfg)

        ctor.assert_called_once_with(
            db_path=str(cfg.db_path),
            embedding_backend="openai-compatible",
            embedding_url="http://x:1/v1",
            embedding_model="test-embed",
        )
        fake_store.initialize.assert_called_once()
        assert result is fake_store
        # ensure_dirs side effect
        assert cfg.db_path.parent.is_dir()


# ── channel_profiles ───────────────────────────────────────────────────


def _registry_yaml(tmp_path: Path) -> Path:
    """Build a minimal registry YAML covering all branches under test."""
    registry = {
        "categories": [
            {
                "monitoring_priority": "critical",
                "faction": "regime_official",
                "channels": [
                    {"handle": "@StateOne", "name_en": "State One", "language": "fa"},
                    {"handle": "TBD_X", "name_en": "Placeholder"},  # filtered: TBD_
                    {"handle": "@unverified_one", "name_en": "U1", "status": "unverified"},
                ],
            },
            {
                "monitoring_priority": "high",
                "faction": "diaspora_opposition",
                "channels": [
                    {"handle": "@OppositionFa", "name_en": "Opp", "language": "fa"},
                ],
            },
            {
                "monitoring_priority": "medium",  # filtered out by priorities
                "faction": "non_aligned",
                "channels": [
                    {"handle": "@MediumPriority", "name_en": "Mid"},
                ],
            },
        ]
    }
    path = tmp_path / "registry.yaml"
    path.write_text(yaml.safe_dump(registry))
    return path


class TestChannelProfiles:
    def test_load_registry_missing_raises(self, tmp_path: Path):
        from baft.itp_telegram.channel_profiles import load_registry

        with pytest.raises(FileNotFoundError):
            load_registry(tmp_path / "absent.yaml")

    def test_load_registry_empty_returns_dict(self, tmp_path: Path):
        from baft.itp_telegram.channel_profiles import load_registry

        path = tmp_path / "empty.yaml"
        path.write_text("")
        assert load_registry(path) == {}

    def test_load_itp_profiles_filters_and_maps(self, tmp_path: Path):
        from heddle.contrib.rag.schemas.post import ChannelBias

        from baft.itp_telegram.channel_profiles import STARTER_EXTRAS, load_itp_profiles

        registry = _registry_yaml(tmp_path)
        profiles = load_itp_profiles(registry)

        # critical + high should produce StateOne + OppositionFa.
        # All STARTER_EXTRAS are layered in unconditionally.
        assert "stateone" in profiles
        assert "oppositionfa" in profiles
        # Filtered: TBD_X, unverified_one, MediumPriority.
        assert not any(k.startswith("tbd_") for k in profiles)
        assert "unverified_one" not in profiles
        assert "mediumpriority" not in profiles
        # Starter extras present.
        for k in STARTER_EXTRAS:
            assert k in profiles
        # Faction → bias mapping.
        assert profiles["stateone"].bias == ChannelBias.STATE_MEDIA
        assert profiles["oppositionfa"].bias == ChannelBias.OPPOSITION
        # Trust weight comes from the faction table.
        assert profiles["stateone"].trust_weight == pytest.approx(0.30)
        assert profiles["oppositionfa"].trust_weight == pytest.approx(0.70)

    def test_channel_handles_prepends_at_sign(self, tmp_path: Path):
        from baft.itp_telegram.channel_profiles import channel_handles, load_itp_profiles

        profiles = load_itp_profiles(_registry_yaml(tmp_path))
        handles = channel_handles(profiles)
        for h in handles:
            assert h.startswith("@")

    def test_by_channel_id_skips_unresolved(self, tmp_path: Path):
        from baft.itp_telegram.channel_profiles import by_channel_id, load_itp_profiles

        profiles = load_itp_profiles(_registry_yaml(tmp_path))
        index = by_channel_id(profiles)
        # Registry-derived entries have channel_id=0 (unresolved); they should NOT
        # appear in the by-id index. STARTER_EXTRAS with hardcoded IDs (factnameh,
        # iranwire) should appear.
        assert 0 not in index
        # Spot-check known starter IDs.
        assert any(p.channel_handle.lower() == "factnameh" for p in index.values())

    def test_merge_resolved_ids_backfills(self, tmp_path: Path):
        from baft.itp_telegram.channel_profiles import load_itp_profiles, merge_resolved_ids

        profiles = load_itp_profiles(_registry_yaml(tmp_path))
        resolved = tmp_path / "resolved.json"
        resolved.write_text(json.dumps({
            "channels": {
                "StateOne": {"channel_id": 999_001, "title": "State One"},
                "OppositionFa": {"channel_id": 999_002, "title": "Opp"},
                "unknown_handle": {"channel_id": 1, "title": "?"},  # ignored
            }
        }))
        merge_resolved_ids(profiles, resolved)
        assert profiles["stateone"].channel_id == 999_001
        assert profiles["oppositionfa"].channel_id == 999_002

    def test_merge_resolved_ids_missing_file_is_noop(self, tmp_path: Path):
        from baft.itp_telegram.channel_profiles import load_itp_profiles, merge_resolved_ids

        profiles = load_itp_profiles(_registry_yaml(tmp_path))
        before = profiles["stateone"].channel_id
        merge_resolved_ids(profiles, tmp_path / "absent.json")
        assert profiles["stateone"].channel_id == before  # unchanged

    def test_merge_resolved_ids_malformed_json_is_noop(self, tmp_path: Path):
        from baft.itp_telegram.channel_profiles import load_itp_profiles, merge_resolved_ids

        profiles = load_itp_profiles(_registry_yaml(tmp_path))
        bad = tmp_path / "bad.json"
        bad.write_text("not json at all")
        before = profiles["stateone"].channel_id
        merge_resolved_ids(profiles, bad)
        assert profiles["stateone"].channel_id == before


# ── llm_backend ────────────────────────────────────────────────────────


class TestLMStudioLLMBackend:
    def test_url_gets_v1_suffix_when_missing(self):
        from baft.itp_telegram.llm_backend import LMStudioLLMBackend

        backend = LMStudioLLMBackend(model="m", base_url="http://x:1234")
        assert backend._base_url == "http://x:1234/v1"

    def test_url_keeps_v1_when_present(self):
        from baft.itp_telegram.llm_backend import LMStudioLLMBackend

        backend = LMStudioLLMBackend(model="m", base_url="http://x:1234/v1")
        assert backend._base_url == "http://x:1234/v1"

    def test_url_strips_trailing_slash(self):
        from baft.itp_telegram.llm_backend import LMStudioLLMBackend

        backend = LMStudioLLMBackend(model="m", base_url="http://x:1234/v1/")
        assert backend._base_url == "http://x:1234/v1"

    def test_complete_returns_content_on_success(self):
        from baft.itp_telegram import llm_backend as mod

        backend = mod.LMStudioLLMBackend(model="m", base_url="http://x:1")
        fake_resp = MagicMock()
        fake_resp.ok = True
        fake_resp.json.return_value = {
            "choices": [{"message": {"content": "hello"}, "finish_reason": "stop"}]
        }
        with patch.object(mod.requests, "post", return_value=fake_resp):
            assert backend.complete("sys", "usr") == "hello"

    def test_complete_rescues_reasoning_content(self):
        from baft.itp_telegram import llm_backend as mod

        backend = mod.LMStudioLLMBackend(model="m", base_url="http://x:1")
        fake_resp = MagicMock()
        fake_resp.ok = True
        fake_resp.json.return_value = {
            "choices": [{
                "message": {"content": "", "reasoning_content": "rescued"},
                "finish_reason": "stop",
            }]
        }
        with patch.object(mod.requests, "post", return_value=fake_resp):
            assert backend.complete("sys", "usr") == "rescued"

    def test_complete_returns_empty_json_after_all_retries_fail(self):
        from baft.itp_telegram import llm_backend as mod

        backend = mod.LMStudioLLMBackend(model="m", base_url="http://x:1")
        with (
            patch.object(mod.requests, "post", side_effect=RuntimeError("boom")),
            patch.object(mod.time, "sleep"),  # don't actually wait between retries
        ):
            result = backend.complete("sys", "usr")
        assert result == "{}"


# ── mcp_server ─────────────────────────────────────────────────────────


class TestMCPServer:
    def _build(self, tmp_path: Path):
        from baft.itp_telegram.channel_profiles import load_itp_profiles
        from baft.itp_telegram.config import ITPTelegramConfig
        from baft.itp_telegram.mcp_server import build_mcp

        cfg = ITPTelegramConfig()
        cfg.db_path = tmp_path / "test.duckdb"
        profiles = load_itp_profiles(_registry_yaml(tmp_path))
        return build_mcp(cfg, profiles, capture_status_ref=None), profiles

    def test_build_mcp_constructs_fastmcp(self, tmp_path):
        mcp, _profiles = self._build(tmp_path)
        # FastMCP has a name attribute.
        assert mcp.name == "itp-telegram"


# ── service ────────────────────────────────────────────────────────────


class TestService:
    def test_serve_rejects_both_disabled(self):
        import asyncio

        from baft.itp_telegram.config import ITPTelegramConfig
        from baft.itp_telegram.service import serve

        cfg = ITPTelegramConfig()
        with pytest.raises(ValueError, match="At least one"):
            asyncio.run(serve(cfg, enable_capture=False, enable_mcp=False))


# ── cli ────────────────────────────────────────────────────────────────


@pytest.fixture
def isolated_cfg(tmp_path, monkeypatch):
    """Point ITPTelegramConfig at a writeable tmp tree, plus a fake registry."""
    monkeypatch.setenv("HOME", str(tmp_path))  # _heddle_dir → tmp_path/.heddle
    monkeypatch.delenv("TELEGRAM_API_ID", raising=False)
    monkeypatch.delenv("TELEGRAM_API_HASH", raising=False)
    monkeypatch.delenv("TELEGRAM_SESSION", raising=False)
    monkeypatch.delenv("LM_STUDIO_URL", raising=False)
    registry = _registry_yaml(tmp_path)
    return {"registry": str(registry), "tmp_path": tmp_path}


class TestCLI:
    def test_channels_table_output(self, isolated_cfg):
        from baft.itp_telegram.cli import itp_telegram

        runner = CliRunner()
        result = runner.invoke(
            itp_telegram,
            ["channels", "--registry", isolated_cfg["registry"]],
        )
        assert result.exit_code == 0, result.output
        assert "ITP channels" in result.output
        assert "@StateOne" in result.output

    def test_channels_json_output(self, isolated_cfg):
        from baft.itp_telegram.cli import itp_telegram

        runner = CliRunner()
        result = runner.invoke(
            itp_telegram,
            ["channels", "--registry", isolated_cfg["registry"], "--json"],
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["count"] > 0
        assert any(c["handle"] == "StateOne" for c in payload["channels"])

    def test_status_no_pid_file(self, isolated_cfg):
        from baft.itp_telegram.cli import itp_telegram

        runner = CliRunner()
        result = runner.invoke(
            itp_telegram,
            ["status", "--registry", isolated_cfg["registry"]],
        )
        assert result.exit_code == 0
        assert "not present" in result.output
        assert "not running" in result.output

    def test_stop_no_pid_file(self, isolated_cfg):
        from baft.itp_telegram.cli import itp_telegram

        runner = CliRunner()
        result = runner.invoke(
            itp_telegram,
            ["stop", "--registry", isolated_cfg["registry"]],
        )
        assert result.exit_code == 0
        assert "Nothing to stop" in result.output

    def test_stop_stale_pid_is_cleaned(self, isolated_cfg, tmp_path):
        from baft.itp_telegram.cli import itp_telegram
        from baft.itp_telegram.pid_manager import write_pid

        pid_file = tmp_path / ".heddle" / "itp_telegram.pid"
        write_pid(pid_file, pid=2_147_483_640)
        runner = CliRunner()
        result = runner.invoke(
            itp_telegram,
            ["stop", "--registry", isolated_cfg["registry"]],
        )
        assert result.exit_code == 0
        assert "not running" in result.output or "stale" in result.output
        assert not pid_file.exists()

    def test_stop_sends_sigterm_to_live_pid(self, isolated_cfg, tmp_path):
        from baft.itp_telegram import cli as cli_mod
        from baft.itp_telegram.cli import itp_telegram
        from baft.itp_telegram.pid_manager import write_pid

        pid_file = tmp_path / ".heddle" / "itp_telegram.pid"
        # Write our own pid (definitely alive) so the live-process branch fires.
        write_pid(pid_file)

        runner = CliRunner()
        # `os` is a module singleton, so patch_object(cli_mod.os, "kill")
        # also catches the os.kill(pid, 0) liveness probe in
        # pid_manager.is_running. Assert on the SIGTERM call rather than
        # call count.
        with patch.object(cli_mod.os, "kill") as mock_kill:
            result = runner.invoke(
                itp_telegram,
                ["stop", "--registry", isolated_cfg["registry"]],
            )

        assert result.exit_code == 0
        mock_kill.assert_any_call(os.getpid(), signal.SIGTERM)
        assert "SIGTERM" in result.output
