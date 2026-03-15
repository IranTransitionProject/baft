"""
test_baft_workers.py
--------------------
Unit tests for ITP Baft worker configurations.

Validates:
  - YAML syntax for all 13 worker configs
  - Required fields present (name, system_prompt, default_tier, input/output schemas)
  - Knowledge silo isolation rules (audit independence)
  - Silo references resolve in itp_silos.yaml
  - Schema structures are valid JSON Schema objects
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

BAFT_ROOT = Path(__file__).parent.parent
WORKERS_DIR = BAFT_ROOT / "configs" / "workers"
SILOS_PATH = BAFT_ROOT / "configs" / "knowledge" / "itp_silos.yaml"

ALL_WORKER_FILES = sorted(WORKERS_DIR.glob("*.yaml"))

# Workers that MUST NOT have ITP framework or database silos
BLIND_AUDIT_NODES = {"la_logic_auditor", "pa_perspective_auditor", "rt_red_teamer"}
# Workers that must not have framework content (but may have audit outputs)
NO_FRAMEWORK_NODES = BLIND_AUDIT_NODES | {"as_audit_synthesizer"}
# TN must only have terminology registry
TN_NODE = "tn_terminology_neutralizer"
# SA must not have analytical framework
SA_NODE = "sa_session_advisor"

# Silos that are isolation_required (from itp_silos.yaml)
ISOLATED_SILOS = {"framework_full", "database_current", "cognitive_profile"}
# Framework-related silo names
FRAMEWORK_SILOS = {"framework_full", "database_current", "framework_schemas"}

# Valid tiers
VALID_TIERS = {"local", "standard", "frontier"}


def _load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_silos() -> dict:
    if not SILOS_PATH.exists():
        pytest.skip("itp_silos.yaml not found")
    return _load_yaml(SILOS_PATH)


def _get_worker_name(path: Path) -> str:
    """Extract worker name from config file."""
    config = _load_yaml(path)
    return config.get("name", path.stem)


# ── Test: all worker files parse as valid YAML ─────────────────────────


class TestWorkerYAMLSyntax:
    """All 13 worker config files must parse without error."""

    @pytest.mark.parametrize("worker_path", ALL_WORKER_FILES, ids=lambda p: p.stem)
    def test_yaml_parses(self, worker_path: Path):
        config = _load_yaml(worker_path)
        assert isinstance(config, dict), f"{worker_path.name} did not parse to a dict"

    def test_expected_worker_count(self):
        assert len(ALL_WORKER_FILES) >= 13, (
            f"Expected at least 13 worker configs, found {len(ALL_WORKER_FILES)}"
        )


# ── Test: required fields ──────────────────────────────────────────────


class TestWorkerRequiredFields:
    """Each worker config must have name, description, system_prompt, default_tier."""

    @pytest.mark.parametrize("worker_path", ALL_WORKER_FILES, ids=lambda p: p.stem)
    def test_has_name(self, worker_path: Path):
        config = _load_yaml(worker_path)
        assert "name" in config, f"Missing 'name' in {worker_path.name}"
        assert isinstance(config["name"], str)

    @pytest.mark.parametrize("worker_path", ALL_WORKER_FILES, ids=lambda p: p.stem)
    def test_has_description(self, worker_path: Path):
        config = _load_yaml(worker_path)
        assert "description" in config, f"Missing 'description' in {worker_path.name}"

    @pytest.mark.parametrize("worker_path", ALL_WORKER_FILES, ids=lambda p: p.stem)
    def test_has_system_prompt(self, worker_path: Path):
        config = _load_yaml(worker_path)
        assert "system_prompt" in config, f"Missing 'system_prompt' in {worker_path.name}"
        assert isinstance(config["system_prompt"], str)
        assert len(config["system_prompt"]) > 50, "system_prompt too short"

    @pytest.mark.parametrize("worker_path", ALL_WORKER_FILES, ids=lambda p: p.stem)
    def test_has_valid_tier(self, worker_path: Path):
        config = _load_yaml(worker_path)
        assert "default_tier" in config, f"Missing 'default_tier' in {worker_path.name}"
        assert config["default_tier"] in VALID_TIERS, (
            f"Invalid tier '{config['default_tier']}' — expected one of {VALID_TIERS}"
        )


# ── Test: input/output schemas ─────────────────────────────────────────


class TestWorkerSchemas:
    """Worker I/O schemas must be valid JSON Schema objects."""

    @pytest.mark.parametrize("worker_path", ALL_WORKER_FILES, ids=lambda p: p.stem)
    def test_has_input_schema(self, worker_path: Path):
        config = _load_yaml(worker_path)
        assert "input_schema" in config, f"Missing 'input_schema' in {worker_path.name}"
        schema = config["input_schema"]
        assert isinstance(schema, dict), "input_schema must be a dict"
        assert schema.get("type") == "object", "input_schema.type must be 'object'"

    @pytest.mark.parametrize("worker_path", ALL_WORKER_FILES, ids=lambda p: p.stem)
    def test_has_output_schema(self, worker_path: Path):
        config = _load_yaml(worker_path)
        assert "output_schema" in config, f"Missing 'output_schema' in {worker_path.name}"
        schema = config["output_schema"]
        assert isinstance(schema, dict), "output_schema must be a dict"
        assert schema.get("type") == "object", "output_schema.type must be 'object'"

    @pytest.mark.parametrize("worker_path", ALL_WORKER_FILES, ids=lambda p: p.stem)
    def test_schemas_have_properties(self, worker_path: Path):
        config = _load_yaml(worker_path)
        for schema_key in ("input_schema", "output_schema"):
            schema = config.get(schema_key, {})
            if isinstance(schema, dict):
                has_props = (
                    "properties" in schema
                    or "oneOf" in schema
                    or "anyOf" in schema
                )
                assert has_props, (
                    f"{worker_path.name}: {schema_key} missing 'properties' (or oneOf/anyOf)"
                )

    @pytest.mark.parametrize("worker_path", ALL_WORKER_FILES, ids=lambda p: p.stem)
    def test_schemas_have_required_list(self, worker_path: Path):
        config = _load_yaml(worker_path)
        for schema_key in ("input_schema", "output_schema"):
            schema = config.get(schema_key, {})
            if isinstance(schema, dict) and "required" in schema:
                assert isinstance(schema["required"], list), (
                    f"{worker_path.name}: {schema_key}.required must be a list"
                )


# ── Test: knowledge silo isolation ─────────────────────────────────────


class TestSiloIsolation:
    """Audit independence: blind nodes must NOT reference framework silos."""

    def _get_silo_refs(self, config: dict) -> set[str]:
        """Extract silo names referenced in knowledge_sources."""
        refs = set()
        for ks in config.get("knowledge_sources", []):
            if isinstance(ks, dict) and "silo" in ks:
                refs.add(ks["silo"])
        return refs

    def _get_file_refs(self, config: dict) -> list[str]:
        """Extract file paths referenced in knowledge_sources."""
        paths = []
        for ks in config.get("knowledge_sources", []):
            if isinstance(ks, dict) and "path" in ks:
                paths.append(ks["path"])
        return paths

    @pytest.mark.parametrize("worker_name", sorted(BLIND_AUDIT_NODES))
    def test_blind_nodes_no_isolated_silos(self, worker_name: str):
        """LA, PA, RT must NOT reference any isolation_required silo."""
        worker_path = WORKERS_DIR / f"{worker_name}.yaml"
        if not worker_path.exists():
            pytest.skip(f"{worker_name}.yaml not found")
        config = _load_yaml(worker_path)
        silo_refs = self._get_silo_refs(config)
        violations = silo_refs & ISOLATED_SILOS
        assert not violations, (
            f"{worker_name} references isolated silos {violations} — audit independence violated"
        )

    @pytest.mark.parametrize("worker_name", sorted(BLIND_AUDIT_NODES))
    def test_blind_nodes_no_framework_silos(self, worker_name: str):
        """LA, PA, RT must NOT reference any framework content silo."""
        worker_path = WORKERS_DIR / f"{worker_name}.yaml"
        if not worker_path.exists():
            pytest.skip(f"{worker_name}.yaml not found")
        config = _load_yaml(worker_path)
        silo_refs = self._get_silo_refs(config)
        violations = silo_refs & FRAMEWORK_SILOS
        assert not violations, (
            f"{worker_name} references framework silos {violations} — audit independence violated"
        )

    @pytest.mark.parametrize("worker_name", sorted(BLIND_AUDIT_NODES))
    def test_blind_nodes_no_framework_paths(self, worker_name: str):
        """LA, PA, RT must NOT have file paths pointing to framework/ data."""
        worker_path = WORKERS_DIR / f"{worker_name}.yaml"
        if not worker_path.exists():
            pytest.skip(f"{worker_name}.yaml not found")
        config = _load_yaml(worker_path)
        file_refs = self._get_file_refs(config)
        framework_refs = [p for p in file_refs if "framework" in p.lower() or "FRAMEWORK" in p]
        assert not framework_refs, (
            f"{worker_name} references framework paths {framework_refs} — audit independence violated"
        )

    def test_tn_only_terminology_registry(self):
        """TN must ONLY reference the terminology_registry silo."""
        worker_path = WORKERS_DIR / f"{TN_NODE}.yaml"
        if not worker_path.exists():
            pytest.skip("tn_terminology_neutralizer.yaml not found")
        config = _load_yaml(worker_path)
        silo_refs = self._get_silo_refs(config)
        file_refs = self._get_file_refs(config)

        # Silo refs should only be terminology_registry (or empty if inline path)
        allowed_silos = {"terminology_registry"}
        violations = silo_refs - allowed_silos
        assert not violations, (
            f"TN references unexpected silos {violations} — should only use terminology_registry"
        )

        # File refs should only point to terminology registry
        for path in file_refs:
            assert "terminology" in path.lower(), (
                f"TN references non-terminology path: {path}"
            )

    def test_as_no_framework_content(self):
        """AS must NOT have ITP framework content — only audit outputs."""
        worker_path = WORKERS_DIR / "as_audit_synthesizer.yaml"
        if not worker_path.exists():
            pytest.skip("as_audit_synthesizer.yaml not found")
        config = _load_yaml(worker_path)
        silo_refs = self._get_silo_refs(config)
        violations = silo_refs & FRAMEWORK_SILOS
        assert not violations, (
            f"AS references framework silos {violations} — should only see audit outputs"
        )

    def test_sa_no_analytical_framework(self):
        """SA must NOT have analytical framework — only cognitive profile."""
        worker_path = WORKERS_DIR / f"{SA_NODE}.yaml"
        if not worker_path.exists():
            pytest.skip("sa_session_advisor.yaml not found")
        config = _load_yaml(worker_path)
        silo_refs = self._get_silo_refs(config)
        analytical_silos = {"framework_full", "database_current"}
        violations = silo_refs & analytical_silos
        assert not violations, (
            f"SA references analytical silos {violations} — should only use cognitive_profile"
        )


# ── Test: silo references resolve ──────────────────────────────────────


class TestSiloResolution:
    """All silo names referenced by workers must exist in itp_silos.yaml."""

    def test_all_silo_refs_resolve(self):
        silo_config = _load_silos()
        defined_silos = set(silo_config.get("silos", {}).keys())

        unresolved = []
        for worker_path in ALL_WORKER_FILES:
            config = _load_yaml(worker_path)
            for ks in config.get("knowledge_sources", []):
                if isinstance(ks, dict) and "silo" in ks:
                    if ks["silo"] not in defined_silos:
                        unresolved.append((worker_path.stem, ks["silo"]))

        assert not unresolved, (
            f"Unresolved silo references: {unresolved}"
        )


# ── Test: worker naming conventions ────────────────────────────────────


class TestWorkerNaming:
    """Worker config filenames must match the internal name field."""

    @pytest.mark.parametrize("worker_path", ALL_WORKER_FILES, ids=lambda p: p.stem)
    def test_filename_matches_name(self, worker_path: Path):
        config = _load_yaml(worker_path)
        assert config["name"] == worker_path.stem, (
            f"Filename '{worker_path.stem}' != config name '{config['name']}'"
        )
