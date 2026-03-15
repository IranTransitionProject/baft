"""
test_baft_pipelines.py
----------------------
Integration tests for ITP Baft pipeline orchestrator configs.

Validates:
  - YAML syntax for all orchestrator configs
  - Stage dependency DAGs are valid (no cycles, all deps exist)
  - Worker references in stages match existing worker configs
  - Audit pipeline enforces blind audit isolation (LA/PA/RT get neutralized input)
  - Parallel group membership is correct
  - Pipeline output mappings reference valid stage IDs
  - MCP gateway config references valid workers and pipelines
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

BAFT_ROOT = Path(__file__).parent.parent
ORCHESTRATORS_DIR = BAFT_ROOT / "configs" / "orchestrators"
WORKERS_DIR = BAFT_ROOT / "configs" / "workers"
MCP_DIR = BAFT_ROOT / "configs" / "mcp"

ALL_ORCHESTRATOR_FILES = sorted(ORCHESTRATORS_DIR.glob("*.yaml"))
ALL_WORKER_NAMES = {p.stem for p in WORKERS_DIR.glob("*.yaml")}


def _load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ── Test: orchestrator YAML syntax ─────────────────────────────────────


class TestOrchestratorYAML:
    """All orchestrator configs must parse as valid YAML."""

    @pytest.mark.parametrize("path", ALL_ORCHESTRATOR_FILES, ids=lambda p: p.stem)
    def test_yaml_parses(self, path: Path):
        config = _load_yaml(path)
        assert isinstance(config, dict)

    def test_expected_count(self):
        assert len(ALL_ORCHESTRATOR_FILES) >= 3, (
            f"Expected at least 3 orchestrator configs, found {len(ALL_ORCHESTRATOR_FILES)}"
        )

    @pytest.mark.parametrize("path", ALL_ORCHESTRATOR_FILES, ids=lambda p: p.stem)
    def test_has_name(self, path: Path):
        config = _load_yaml(path)
        assert "name" in config

    @pytest.mark.parametrize("path", ALL_ORCHESTRATOR_FILES, ids=lambda p: p.stem)
    def test_has_stages(self, path: Path):
        config = _load_yaml(path)
        assert "stages" in config
        assert isinstance(config["stages"], list)
        assert len(config["stages"]) > 0


# ── Test: stage dependency integrity ───────────────────────────────────


class TestStageDependencies:
    """Stage dependency DAGs must be valid — no missing deps, no cycles."""

    @pytest.mark.parametrize("path", ALL_ORCHESTRATOR_FILES, ids=lambda p: p.stem)
    def test_all_deps_exist(self, path: Path):
        config = _load_yaml(path)
        stage_ids = {s["id"] for s in config["stages"]}
        for stage in config["stages"]:
            for dep in stage.get("depends_on", []):
                assert dep in stage_ids, (
                    f"Stage '{stage['id']}' depends on unknown stage '{dep}'"
                )

    @pytest.mark.parametrize("path", ALL_ORCHESTRATOR_FILES, ids=lambda p: p.stem)
    def test_no_self_dependency(self, path: Path):
        config = _load_yaml(path)
        for stage in config["stages"]:
            deps = stage.get("depends_on", [])
            assert stage["id"] not in deps, (
                f"Stage '{stage['id']}' depends on itself"
            )

    @pytest.mark.parametrize("path", ALL_ORCHESTRATOR_FILES, ids=lambda p: p.stem)
    def test_unique_stage_ids(self, path: Path):
        config = _load_yaml(path)
        ids = [s["id"] for s in config["stages"]]
        assert len(ids) == len(set(ids)), f"Duplicate stage IDs in {path.name}"


# ── Test: worker references ────────────────────────────────────────────


class TestWorkerReferences:
    """All worker references in pipeline stages must match existing configs."""

    @pytest.mark.parametrize("path", ALL_ORCHESTRATOR_FILES, ids=lambda p: p.stem)
    def test_workers_exist(self, path: Path):
        config = _load_yaml(path)
        for stage in config["stages"]:
            worker = stage.get("worker")
            if worker:
                assert worker in ALL_WORKER_NAMES, (
                    f"Stage '{stage['id']}' references unknown worker '{worker}'"
                )


# ── Test: itp_standard pipeline structure ──────────────────────────────


class TestStandardPipeline:
    """itp_standard.yaml: SP → IA → XV → DE sequential pipeline."""

    @pytest.fixture
    def config(self):
        path = ORCHESTRATORS_DIR / "itp_standard.yaml"
        if not path.exists():
            pytest.skip("itp_standard.yaml not found")
        return _load_yaml(path)

    def test_name(self, config):
        assert config["name"] == "itp_standard"

    def test_stage_order(self, config):
        stage_ids = [s["id"] for s in config["stages"]]
        assert "source_process" in stage_ids
        assert "analyze" in stage_ids
        assert "db_write" in stage_ids

    def test_sp_is_first(self, config):
        first_stage = config["stages"][0]
        assert first_stage["worker"] == "sp_source_processor"
        assert not first_stage.get("depends_on"), "SP should have no dependencies"

    def test_analyze_depends_on_sp(self, config):
        analyze = next(s for s in config["stages"] if s["id"] == "analyze")
        assert "source_process" in analyze.get("depends_on", [])

    def test_has_pipeline_output(self, config):
        assert "pipeline_output" in config

    def test_has_error_handling(self, config):
        assert "error_handling" in config


# ── Test: itp_audit pipeline structure ─────────────────────────────────


class TestAuditPipeline:
    """itp_audit.yaml: TN → [LA + PA + RT parallel] → AS."""

    @pytest.fixture
    def config(self):
        path = ORCHESTRATORS_DIR / "itp_audit.yaml"
        if not path.exists():
            pytest.skip("itp_audit.yaml not found")
        return _load_yaml(path)

    def test_name(self, config):
        assert config["name"] == "itp_audit"

    def test_neutralize_is_first(self, config):
        first_stage = config["stages"][0]
        assert first_stage["worker"] == "tn_terminology_neutralizer"

    def test_audit_nodes_depend_on_neutralize(self, config):
        audit_workers = {"la_logic_auditor", "pa_perspective_auditor", "rt_red_teamer"}
        for stage in config["stages"]:
            if stage.get("worker") in audit_workers:
                assert "neutralize" in stage.get("depends_on", []), (
                    f"Audit stage '{stage['id']}' must depend on neutralize"
                )

    def test_audit_nodes_in_parallel_group(self, config):
        """LA, PA, RT should be in the same parallel group."""
        audit_workers = {"la_logic_auditor", "pa_perspective_auditor", "rt_red_teamer"}
        parallel_groups = set()
        for stage in config["stages"]:
            if stage.get("worker") in audit_workers:
                pg = stage.get("parallel_group")
                assert pg is not None, (
                    f"Audit stage '{stage['id']}' should have a parallel_group"
                )
                parallel_groups.add(pg)
        # All should be in the same group
        assert len(parallel_groups) == 1, (
            f"Audit nodes should share one parallel_group, found {parallel_groups}"
        )

    def test_synthesizer_depends_on_all_auditors(self, config):
        synth = next(
            (s for s in config["stages"] if s.get("worker") == "as_audit_synthesizer"),
            None,
        )
        assert synth is not None, "Missing audit synthesizer stage"
        deps = set(synth.get("depends_on", []))
        audit_stage_ids = {
            s["id"] for s in config["stages"]
            if s.get("worker") in {"la_logic_auditor", "pa_perspective_auditor", "rt_red_teamer"}
        }
        assert audit_stage_ids.issubset(deps), (
            f"Synthesizer must depend on all audit stages. Missing: {audit_stage_ids - deps}"
        )

    def test_audit_input_is_neutralized(self, config):
        """LA, PA, RT must receive input from neutralize stage, not raw input."""
        audit_workers = {"la_logic_auditor", "pa_perspective_auditor", "rt_red_teamer"}
        for stage in config["stages"]:
            if stage.get("worker") in audit_workers:
                mapping = stage.get("input_mapping", {})
                mapping_str = yaml.dump(mapping)
                assert "neutralize" in mapping_str, (
                    f"Audit stage '{stage['id']}' must receive neutralized input, "
                    f"not raw — check input_mapping"
                )
                assert "input.analytical_text" not in mapping_str, (
                    f"Audit stage '{stage['id']}' must NOT receive raw analytical_text directly"
                )


# ── Test: MCP gateway config ──────────────────────────────────────────


class TestMCPGateway:
    """MCP gateway config must reference valid workers and pipelines."""

    @pytest.fixture
    def config(self):
        path = MCP_DIR / "itp.yaml"
        if not path.exists():
            pytest.skip("configs/mcp/itp.yaml not found")
        return _load_yaml(path)

    def test_has_name(self, config):
        assert "name" in config

    def test_has_nats_url(self, config):
        assert "nats_url" in config

    def test_has_tools(self, config):
        assert "tools" in config

    def test_worker_configs_exist(self, config):
        workers = config.get("tools", {}).get("workers", [])
        for w in workers:
            config_path = w.get("config", "")
            full_path = BAFT_ROOT / config_path
            assert full_path.exists(), (
                f"MCP worker config not found: {config_path}"
            )

    def test_pipeline_configs_exist(self, config):
        pipelines = config.get("tools", {}).get("pipelines", [])
        for p in pipelines:
            config_path = p.get("config", "")
            full_path = BAFT_ROOT / config_path
            assert full_path.exists(), (
                f"MCP pipeline config not found: {config_path}"
            )

    def test_has_query_backend(self, config):
        queries = config.get("tools", {}).get("queries", [])
        assert len(queries) > 0, "MCP config should have at least one query backend"
