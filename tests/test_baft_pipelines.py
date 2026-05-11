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
                assert dep in stage_ids, f"Stage '{stage['id']}' depends on unknown stage '{dep}'"

    @pytest.mark.parametrize("path", ALL_ORCHESTRATOR_FILES, ids=lambda p: p.stem)
    def test_no_self_dependency(self, path: Path):
        config = _load_yaml(path)
        for stage in config["stages"]:
            deps = stage.get("depends_on", [])
            assert stage["id"] not in deps, f"Stage '{stage['id']}' depends on itself"

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
                assert pg is not None, f"Audit stage '{stage['id']}' should have a parallel_group"
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
            s["id"]
            for s in config["stages"]
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
            assert full_path.exists(), f"MCP worker config not found: {config_path}"

    def test_pipeline_configs_exist(self, config):
        pipelines = config.get("tools", {}).get("pipelines", [])
        for p in pipelines:
            config_path = p.get("config", "")
            full_path = BAFT_ROOT / config_path
            assert full_path.exists(), f"MCP pipeline config not found: {config_path}"

    def test_has_query_backend(self, config):
        queries = config.get("tools", {}).get("queries", [])
        assert len(queries) > 0, "MCP config should have at least one query backend"


# ── Test: stage and escalation conditions evaluate correctly ───────────
#
# Heddle's PipelineOrchestrator._evaluate_condition accepts only
# 3-token `path op value` expressions with == / !=.  Anything else
# returns False under HEDDLE_STRICT_CONDITIONS=1 (the v0.9.2 default),
# silently disabling whatever stage owns the condition.  String literals
# must be UNQUOTED — `... != 'FAIL'` compares against the literal string
# "'FAIL'" and is always True, defeating the guard.
#
# These tests exercise every condition string in baft's pipeline configs
# against the real heddle evaluator with synthetic contexts that mirror
# the worker output shapes.  They would have caught both bugs fixed in
# the v0.3.1 patch.


class TestPipelineConditionEvaluation:
    """Every `condition:` in baft's pipelines parses under heddle's grammar."""

    @pytest.fixture(scope="class")
    def evaluator(self):
        from heddle.orchestrator.pipeline import PipelineOrchestrator

        return PipelineOrchestrator._evaluate_condition

    def _collect_conditions(self) -> list[tuple[str, str, str]]:
        """Return (pipeline_name, location, condition_string) for every condition."""
        rows: list[tuple[str, str, str]] = []
        for path in ALL_ORCHESTRATOR_FILES:
            config = _load_yaml(path)
            for stage in config.get("stages", []):
                cond = stage.get("condition")
                if cond:
                    rows.append((path.stem, f"stage:{stage['id']}", cond))
            for esc in config.get("escalation", []) or []:
                cond = esc.get("condition")
                if cond:
                    rows.append((path.stem, "escalation", cond))
        return rows

    def test_every_condition_is_three_tokens(self, evaluator):
        """All conditions must satisfy heddle's 3-token grammar."""
        offenders = []
        for pipeline, location, cond in self._collect_conditions():
            if len(cond.split()) != 3:
                offenders.append(f"{pipeline}/{location}: {cond!r}")
        assert not offenders, (
            "Heddle v0.9.2 evaluates non-3-token conditions as False by default "
            "(HEDDLE_STRICT_CONDITIONS=1), silently disabling the owning stage. "
            "Offenders:\n  " + "\n  ".join(offenders)
        )

    def test_no_quoted_enum_literals(self, evaluator):
        """String literals on the RHS must be unquoted bare tokens."""
        offenders = []
        for pipeline, location, cond in self._collect_conditions():
            parts = cond.split()
            if len(parts) != 3:
                continue  # already covered above
            rhs = parts[2]
            if (rhs.startswith("'") and rhs.endswith("'")) or (
                rhs.startswith('"') and rhs.endswith('"')
            ):
                offenders.append(f"{pipeline}/{location}: {cond!r}")
        assert not offenders, (
            "Heddle's evaluator does not strip surrounding quotes, so quoted "
            "literals never match the unquoted worker output. Use bare tokens "
            "(e.g. `... != FAIL`, not `... != 'FAIL'`). Offenders:\n  "
            + "\n  ".join(offenders)
        )

    # ── Per-pipeline semantic truth tables ────────────────────────────

    def test_itp_standard_db_write_runs_on_pass(self, evaluator):
        """itp_standard: db_write runs when XV returns PASS."""
        config = _load_yaml(ORCHESTRATORS_DIR / "itp_standard.yaml")
        stage = next(s for s in config["stages"] if s["id"] == "db_write")
        context = {
            "stages": {
                "cross_validate": {
                    "output": {"validation_result": {"overall_status": "PASS"}}
                }
            }
        }
        assert evaluator(stage["condition"], context) is True

    def test_itp_standard_db_write_skips_on_fail(self, evaluator):
        """itp_standard: db_write is skipped when XV returns FAIL."""
        config = _load_yaml(ORCHESTRATORS_DIR / "itp_standard.yaml")
        stage = next(s for s in config["stages"] if s["id"] == "db_write")
        context = {
            "stages": {
                "cross_validate": {
                    "output": {"validation_result": {"overall_status": "FAIL"}}
                }
            }
        }
        assert evaluator(stage["condition"], context) is False

    def test_itp_standard_escalation_on_publication_flag(self, evaluator):
        """itp_standard: escalation fires when IA sets publication_flag=true."""
        config = _load_yaml(ORCHESTRATORS_DIR / "itp_standard.yaml")
        esc = config["escalation"][0]
        context = {
            "stages": {"analyze": {"output": {"analytical_output": {"publication_flag": True}}}}
        }
        assert evaluator(esc["condition"], context) is True

    def test_itp_standard_escalation_skips_when_publication_flag_false(self, evaluator):
        """itp_standard: escalation does not fire when publication_flag=false."""
        config = _load_yaml(ORCHESTRATORS_DIR / "itp_standard.yaml")
        esc = config["escalation"][0]
        context = {
            "stages": {"analyze": {"output": {"analytical_output": {"publication_flag": False}}}}
        }
        assert evaluator(esc["condition"], context) is False

    def test_itp_quick_de_write_runs_on_pass(self, evaluator):
        """itp_quick: de_write runs when XV returns PASS (including empty-input no-op)."""
        config = _load_yaml(ORCHESTRATORS_DIR / "itp_quick.yaml")
        stage = next(s for s in config["stages"] if s["id"] == "de_write")
        context = {
            "stages": {
                "xv_validate": {
                    "output": {"validation_result": {"overall_status": "PASS"}}
                }
            }
        }
        assert evaluator(stage["condition"], context) is True

    def test_itp_quick_de_write_skips_on_fail(self, evaluator):
        """itp_quick: de_write is skipped when XV returns FAIL."""
        config = _load_yaml(ORCHESTRATORS_DIR / "itp_quick.yaml")
        stage = next(s for s in config["stages"] if s["id"] == "de_write")
        context = {
            "stages": {
                "xv_validate": {
                    "output": {"validation_result": {"overall_status": "FAIL"}}
                }
            }
        }
        assert evaluator(stage["condition"], context) is False

    def test_itp_audit_escalation_on_required(self, evaluator):
        """itp_audit: escalation fires when AS sets escalation_required=true."""
        config = _load_yaml(ORCHESTRATORS_DIR / "itp_audit.yaml")
        esc = config["escalation"][0]
        context = {
            "stages": {
                "synthesize": {"output": {"audit_report": {"escalation_required": True}}}
            }
        }
        assert evaluator(esc["condition"], context) is True

    def test_itp_audit_escalation_skips_when_not_required(self, evaluator):
        """itp_audit: escalation is skipped when AS sets escalation_required=false."""
        config = _load_yaml(ORCHESTRATORS_DIR / "itp_audit.yaml")
        esc = config["escalation"][0]
        context = {
            "stages": {
                "synthesize": {"output": {"audit_report": {"escalation_required": False}}}
            }
        }
        assert evaluator(esc["condition"], context) is False
