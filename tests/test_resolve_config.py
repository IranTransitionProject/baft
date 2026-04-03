"""
Tests for scripts/resolve_config.py (unit tests).

Covers:
    1. _resolve_itp_root() -- env var, auto-detection, missing raises error.
    2. load_silo_index() -- ${ITP_ROOT} expansion, returns silos dict.
    3. resolve_worker_config() -- silo resolution, unknown silo warning,
       no knowledge_sources passthrough, direct path passthrough,
       relative path resolution via BAFT_DIR.

Uses tmp_path for fake silo index and worker config YAML files.
Monkeypatches os.environ for ITP_ROOT and module-level BAFT_DIR.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

# Add baft/scripts to the path so we can import resolve_config directly.
BAFT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(BAFT_ROOT / "scripts"))

import resolve_config

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_itp_root(tmp_path):
    """Create a fake ITP project root with baseline/data directory."""
    itp_root = tmp_path / "itp_project"
    (itp_root / "baseline" / "data").mkdir(parents=True)
    return itp_root


@pytest.fixture
def silo_index_file(tmp_path):
    """Create a silo index YAML file with ${ITP_ROOT} references."""
    silo_data = {
        "silos": {
            "framework_full": {
                "sources": [
                    {
                        "path": "${ITP_ROOT}/baseline/output/itb_full.md",
                        "inject_as": "analytical_framework",
                    },
                    {
                        "path": "${ITP_ROOT}/baseline/output/isa_full.md",
                        "inject_as": "stress_architecture",
                    },
                ]
            },
            "entity_names": {
                "sources": [
                    {
                        "path": "pipeline/config/itp_entity_name_registry.yaml",
                        "inject_as": "entity_names",
                    },
                ]
            },
        }
    }
    path = tmp_path / "silos.yaml"
    path.write_text(yaml.dump(silo_data))
    return path


@pytest.fixture
def worker_config_with_silo(tmp_path):
    """Create a worker config YAML that references a silo."""
    config = {
        "name": "test_worker",
        "system_prompt": "Test prompt",
        "knowledge_sources": [
            {"silo": "framework_full"},
        ],
    }
    path = tmp_path / "worker.yaml"
    path.write_text(yaml.dump(config))
    return path


@pytest.fixture
def worker_config_no_sources(tmp_path):
    """Create a worker config YAML with no knowledge_sources."""
    config = {
        "name": "simple_worker",
        "system_prompt": "Simple prompt",
    }
    path = tmp_path / "simple_worker.yaml"
    path.write_text(yaml.dump(config))
    return path


@pytest.fixture
def worker_config_direct_path(tmp_path):
    """Create a worker config YAML with direct path references (no silo)."""
    config = {
        "name": "direct_worker",
        "system_prompt": "Direct prompt",
        "knowledge_sources": [
            {"path": "/absolute/path/to/file.yaml", "inject_as": "reference"},
        ],
    }
    path = tmp_path / "direct_worker.yaml"
    path.write_text(yaml.dump(config))
    return path


@pytest.fixture
def worker_config_unknown_silo(tmp_path):
    """Create a worker config referencing a silo that doesn't exist."""
    config = {
        "name": "bad_worker",
        "system_prompt": "Bad prompt",
        "knowledge_sources": [
            {"silo": "nonexistent_silo"},
        ],
    }
    path = tmp_path / "bad_worker.yaml"
    path.write_text(yaml.dump(config))
    return path


# ---------------------------------------------------------------------------
# _resolve_itp_root tests
# ---------------------------------------------------------------------------


class TestResolveItpRoot:
    """Tests for _resolve_itp_root()."""

    def test_env_var_used_when_set(self, monkeypatch, fake_itp_root):
        """ITP_ROOT env var should be used directly when set."""
        monkeypatch.setenv("ITP_ROOT", str(fake_itp_root))

        result = resolve_config._resolve_itp_root()

        assert result == fake_itp_root

    def test_auto_detection_from_parent(self, monkeypatch, fake_itp_root):
        """When ITP_ROOT is not set, auto-detect from BAFT_DIR.parent."""
        monkeypatch.delenv("ITP_ROOT", raising=False)

        # Make BAFT_DIR point to a child of fake_itp_root so .parent works.
        fake_baft = fake_itp_root / "baft"
        fake_baft.mkdir()
        monkeypatch.setattr(resolve_config, "BAFT_DIR", fake_baft)

        result = resolve_config._resolve_itp_root()

        assert result == fake_itp_root

    def test_missing_raises_error(self, monkeypatch, tmp_path):
        """When ITP_ROOT is not set and auto-detection fails, raise FileNotFoundError."""
        monkeypatch.delenv("ITP_ROOT", raising=False)

        # Point BAFT_DIR to a directory whose parent lacks baseline/data.
        empty_dir = tmp_path / "no_baseline" / "baft"
        empty_dir.mkdir(parents=True)
        monkeypatch.setattr(resolve_config, "BAFT_DIR", empty_dir)

        with pytest.raises(FileNotFoundError, match="Cannot find ITP project root"):
            resolve_config._resolve_itp_root()

    def test_env_var_takes_precedence_over_auto(self, monkeypatch, fake_itp_root, tmp_path):
        """Even if auto-detection would work, the env var should win."""
        custom_root = tmp_path / "custom_root"
        custom_root.mkdir()
        monkeypatch.setenv("ITP_ROOT", str(custom_root))

        # BAFT_DIR.parent has baseline/data, but env var should override.
        fake_baft = fake_itp_root / "baft"
        fake_baft.mkdir(exist_ok=True)
        monkeypatch.setattr(resolve_config, "BAFT_DIR", fake_baft)

        result = resolve_config._resolve_itp_root()

        assert result == custom_root


# ---------------------------------------------------------------------------
# load_silo_index tests
# ---------------------------------------------------------------------------


class TestLoadSiloIndex:
    """Tests for load_silo_index()."""

    def test_expands_itp_root_in_paths(self, monkeypatch, fake_itp_root, silo_index_file):
        """${ITP_ROOT} in silo paths should be replaced with the resolved root."""
        monkeypatch.setenv("ITP_ROOT", str(fake_itp_root))

        silos = resolve_config.load_silo_index(silo_index_file)

        sources = silos["framework_full"]["sources"]
        assert str(fake_itp_root) in sources[0]["path"]
        assert "${ITP_ROOT}" not in sources[0]["path"]

    def test_returns_silos_dict(self, monkeypatch, fake_itp_root, silo_index_file):
        """Should return the 'silos' key contents from the YAML."""
        monkeypatch.setenv("ITP_ROOT", str(fake_itp_root))

        silos = resolve_config.load_silo_index(silo_index_file)

        assert "framework_full" in silos
        assert "entity_names" in silos

    def test_empty_silos_returns_empty_dict(self, monkeypatch, fake_itp_root, tmp_path):
        """A YAML file with no 'silos' key should return empty dict."""
        monkeypatch.setenv("ITP_ROOT", str(fake_itp_root))

        empty_silo = tmp_path / "empty_silos.yaml"
        empty_silo.write_text(yaml.dump({"other_key": "value"}))

        silos = resolve_config.load_silo_index(empty_silo)

        assert silos == {}


# ---------------------------------------------------------------------------
# resolve_worker_config tests
# ---------------------------------------------------------------------------


class TestResolveWorkerConfig:
    """Tests for resolve_worker_config()."""

    def test_silo_reference_resolved(
        self, monkeypatch, fake_itp_root, silo_index_file, worker_config_with_silo
    ):
        """Silo references should be expanded to concrete path + inject_as entries."""
        monkeypatch.setenv("ITP_ROOT", str(fake_itp_root))
        silos = resolve_config.load_silo_index(silo_index_file)

        result = resolve_config.resolve_worker_config(worker_config_with_silo, silos)

        ks = result["knowledge_sources"]
        assert len(ks) == 2  # framework_full has 2 sources
        assert ks[0]["inject_as"] == "analytical_framework"
        assert str(fake_itp_root) in ks[0]["path"]
        assert ks[1]["inject_as"] == "stress_architecture"

    def test_no_knowledge_sources_returns_unchanged(self, worker_config_no_sources):
        """Config with no knowledge_sources should be returned as-is."""
        result = resolve_config.resolve_worker_config(worker_config_no_sources, {})

        assert result["name"] == "simple_worker"
        assert (
            "knowledge_sources" not in result
            or result.get("knowledge_sources") is None
            or result.get("knowledge_sources") == []
        )

    def test_direct_path_passes_through(self, worker_config_direct_path):
        """Sources without a 'silo' key should be passed through unchanged."""
        result = resolve_config.resolve_worker_config(worker_config_direct_path, {})

        ks = result["knowledge_sources"]
        assert len(ks) == 1
        assert ks[0]["path"] == "/absolute/path/to/file.yaml"
        assert ks[0]["inject_as"] == "reference"

    def test_unknown_silo_skipped_with_warning(self, worker_config_unknown_silo, capsys):
        """An unknown silo name should print a warning and skip (not crash)."""
        result = resolve_config.resolve_worker_config(worker_config_unknown_silo, {})

        # The unknown silo source should be skipped entirely.
        ks = result["knowledge_sources"]
        assert len(ks) == 0

        # Warning should be printed to stderr.
        captured = capsys.readouterr()
        assert "nonexistent_silo" in captured.err
        assert "WARNING" in captured.err

    def test_relative_path_resolved_via_baft_dir(self, monkeypatch, fake_itp_root, tmp_path):
        """Relative paths in silo sources should be resolved relative to BAFT_DIR."""
        monkeypatch.setenv("ITP_ROOT", str(fake_itp_root))

        fake_baft = tmp_path / "baft"
        fake_baft.mkdir()
        monkeypatch.setattr(resolve_config, "BAFT_DIR", fake_baft)

        silos = {
            "local_silo": {
                "sources": [
                    {"path": "pipeline/config/registry.yaml", "inject_as": "registry"},
                ]
            }
        }

        config = {
            "name": "test",
            "knowledge_sources": [{"silo": "local_silo"}],
        }
        config_path = tmp_path / "test_worker.yaml"
        config_path.write_text(yaml.dump(config))

        result = resolve_config.resolve_worker_config(config_path, silos)

        ks = result["knowledge_sources"]
        assert len(ks) == 1
        assert ks[0]["path"] == str(fake_baft / "pipeline" / "config" / "registry.yaml")

    def test_absolute_path_in_silo_not_modified(self, monkeypatch, fake_itp_root, tmp_path):
        """Absolute paths in silo sources should not be modified by BAFT_DIR."""
        monkeypatch.setenv("ITP_ROOT", str(fake_itp_root))

        silos = {
            "abs_silo": {
                "sources": [
                    {"path": "/absolute/existing/file.yaml", "inject_as": "data"},
                ]
            }
        }

        config = {
            "name": "test",
            "knowledge_sources": [{"silo": "abs_silo"}],
        }
        config_path = tmp_path / "abs_worker.yaml"
        config_path.write_text(yaml.dump(config))

        result = resolve_config.resolve_worker_config(config_path, silos)

        ks = result["knowledge_sources"]
        assert ks[0]["path"] == "/absolute/existing/file.yaml"

    def test_default_inject_as_is_reference(self, monkeypatch, fake_itp_root, tmp_path):
        """When inject_as is missing from silo source, default to 'reference'."""
        monkeypatch.setenv("ITP_ROOT", str(fake_itp_root))

        silos = {
            "no_inject_silo": {
                "sources": [
                    {"path": "/some/path.yaml"},  # No inject_as key
                ]
            }
        }

        config = {
            "name": "test",
            "knowledge_sources": [{"silo": "no_inject_silo"}],
        }
        config_path = tmp_path / "no_inject_worker.yaml"
        config_path.write_text(yaml.dump(config))

        result = resolve_config.resolve_worker_config(config_path, silos)

        ks = result["knowledge_sources"]
        assert ks[0]["inject_as"] == "reference"
