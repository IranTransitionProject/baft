"""
test_new_loom_features.py
-------------------------
Tests for newly adopted Loom features in Baft:
  1. OpenTelemetry tracing integration
  2. Per-stage max_retries on all pipeline configs
  3. ResultStream availability (audit pipeline parallel group)
  4. Workshop MCP tools in MCP config
  5. Config impact analysis availability
  6. Eval baselines (workshop DB)
  7. Dead-letter replay audit trail
  8. TUI dashboard availability
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

BAFT_ROOT = Path(__file__).parent.parent
ORCHESTRATORS_DIR = BAFT_ROOT / "configs" / "orchestrators"
MCP_CONFIG = BAFT_ROOT / "configs" / "mcp" / "itp.yaml"
MANIFEST = BAFT_ROOT / "manifest.yaml"


def _load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ── 1. OpenTelemetry tracing integration ──────────────────────────────


class TestTracingIntegration:
    """Baft tracing module works (with or without OTel installed)."""

    def test_init_baft_tracing_returns_bool(self):
        """init_baft_tracing always returns a bool, never raises."""
        from baft.tracing import init_baft_tracing

        result = init_baft_tracing()
        assert isinstance(result, bool)

    def test_get_baft_tracer_returns_object(self):
        """get_baft_tracer always returns a usable tracer."""
        from baft.tracing import get_baft_tracer

        tracer = get_baft_tracer("baft.test")
        assert tracer is not None
        # Must support start_as_current_span (real or no-op)
        assert hasattr(tracer, "start_as_current_span")

    def test_tracer_span_context_manager(self):
        """Tracer spans work as context managers (real or no-op)."""
        from baft.tracing import get_baft_tracer

        tracer = get_baft_tracer("baft.test")
        with tracer.start_as_current_span("test_span") as span:
            span.set_attribute("test.key", "test_value")
            # Should not raise

    def test_loom_tracing_inject_extract_noop(self):
        """Loom inject/extract are safe to call without OTel."""
        from loom.tracing import extract_trace_context, inject_trace_context

        carrier: dict = {}
        inject_trace_context(carrier)
        extract_trace_context(carrier)
        # Without OTel installed: carrier unchanged, ctx is None
        # With OTel installed: carrier may have _trace_context key
        assert isinstance(carrier, dict)

    def test_manifest_includes_otel_extra(self):
        """Manifest declares otel as a required extra."""
        manifest = _load_yaml(MANIFEST)
        assert "otel" in manifest["required_extras"]


# ── 2. Per-stage max_retries on pipeline configs ──────────────────────


class TestPerStageRetries:
    """All pipeline stages should have max_retries configured."""

    @pytest.mark.parametrize(
        "config_name",
        ["itp_standard.yaml", "itp_audit.yaml", "itp_quick.yaml"],
    )
    def test_all_stages_have_max_retries(self, config_name: str):
        path = ORCHESTRATORS_DIR / config_name
        if not path.exists():
            pytest.skip(f"{config_name} not found")
        config = _load_yaml(path)
        for stage in config["stages"]:
            assert "max_retries" in stage, (
                f"Stage '{stage['id']}' in {config_name} missing max_retries"
            )
            assert isinstance(stage["max_retries"], int)
            assert stage["max_retries"] >= 1, f"Stage '{stage['id']}' max_retries should be >= 1"

    def test_standard_sp_has_retries(self):
        config = _load_yaml(ORCHESTRATORS_DIR / "itp_standard.yaml")
        sp = next(s for s in config["stages"] if s["id"] == "source_process")
        assert sp["max_retries"] == 2, "SP (local tier) should retry twice"

    def test_standard_ia_conservative_retries(self):
        config = _load_yaml(ORCHESTRATORS_DIR / "itp_standard.yaml")
        ia = next(s for s in config["stages"] if s["id"] == "analyze")
        assert ia["max_retries"] <= 2, "IA (frontier tier) retries should be conservative"

    def test_audit_panel_has_retries(self):
        config = _load_yaml(ORCHESTRATORS_DIR / "itp_audit.yaml")
        audit_ids = {"logic_audit", "perspective_audit", "red_team"}
        for stage in config["stages"]:
            if stage["id"] in audit_ids:
                assert stage["max_retries"] >= 1, (
                    f"Audit stage '{stage['id']}' should have max_retries"
                )


# ── 3. ResultStream availability ──────────────────────────────────────


class TestResultStreamAvailability:
    """ResultStream is importable and usable for audit pipeline patterns."""

    def test_result_stream_importable(self):
        from loom.orchestrator.stream import ResultStream

        assert ResultStream is not None

    def test_result_callback_protocol_importable(self):
        from loom.orchestrator.stream import ResultCallback

        assert ResultCallback is not None

    def test_audit_pipeline_has_parallel_group(self):
        """Audit pipeline parallel group is configured for streaming collection."""
        config = _load_yaml(ORCHESTRATORS_DIR / "itp_audit.yaml")
        parallel_stages = [s for s in config["stages"] if s.get("parallel_group")]
        assert len(parallel_stages) == 3, "Expected 3 stages in audit_panel parallel group"


# ── 4. Workshop MCP tools in MCP config ───────────────────────────────


class TestWorkshopMCPTools:
    """MCP config includes Workshop tools section."""

    @pytest.fixture
    def config(self):
        if not MCP_CONFIG.exists():
            pytest.skip("configs/mcp/itp.yaml not found")
        return _load_yaml(MCP_CONFIG)

    def test_has_workshop_section(self, config):
        tools = config.get("tools", {})
        assert "workshop" in tools, "MCP config must have tools.workshop section"

    def test_workshop_has_configs_dir(self, config):
        workshop = config["tools"]["workshop"]
        assert "configs_dir" in workshop

    def test_workshop_enables_required_groups(self, config):
        workshop = config["tools"]["workshop"]
        enabled = set(workshop.get("enable", []))
        required = {"worker", "test", "eval", "impact"}
        assert required.issubset(enabled), f"Workshop must enable {required}, found {enabled}"

    def test_workshop_enables_deadletter(self, config):
        """Dead-letter tools are enabled for governance audit trail."""
        workshop = config["tools"]["workshop"]
        enabled = set(workshop.get("enable", []))
        assert "deadletter" in enabled, (
            "Workshop should enable deadletter for governance audit trail"
        )

    def test_workshop_tool_discovery(self, config):
        """Workshop tools can be discovered from the config."""
        from loom.mcp.workshop_discovery import discover_workshop_tools

        workshop_config = config["tools"]["workshop"]
        tools = discover_workshop_tools(workshop_config)
        tool_names = {t["name"] for t in tools}
        # Should have worker CRUD + test + eval + impact + deadletter tools
        assert "workshop.worker.list" in tool_names
        assert "workshop.worker.test" in tool_names
        assert "workshop.eval.run" in tool_names
        assert "workshop.impact.analyze" in tool_names
        assert "workshop.deadletter.list" in tool_names
        assert "workshop.deadletter.replay" in tool_names


# ── 5. Config impact analysis ─────────────────────────────────────────


class TestConfigImpactAnalysis:
    """Config impact analysis module is available and functional."""

    def test_get_impact_importable(self):
        from loom.workshop.config_impact import get_impact

        assert callable(get_impact)

    def test_impact_returns_valid_structure(self):
        """get_impact returns a valid structure with expected keys."""
        from loom.workshop.config_impact import get_impact
        from loom.workshop.config_manager import ConfigManager

        cm = ConfigManager(configs_dir=str(BAFT_ROOT / "configs"))
        impact = get_impact("sp_source_processor", cm)
        assert isinstance(impact, dict)
        assert "worker_name" in impact
        assert "pipelines" in impact
        assert "risk" in impact
        assert impact["worker_name"] == "sp_source_processor"

    def test_impact_helper_functions(self):
        """Internal dependency inference and downstream detection work."""
        from loom.workshop.config_impact import _find_downstream, _infer_dependencies

        # Simulate a pipeline with stages in get_impact's expected format
        stages = [
            {"name": "sp", "worker_type": "sp_source_processor", "input_mapping": {"x": "goal.x"}},
            {
                "name": "ia",
                "worker_type": "ia_intelligence_analyst",
                "input_mapping": {"y": "sp.output"},
            },
            {
                "name": "de",
                "worker_type": "de_database_engineer",
                "input_mapping": {"z": "ia.result"},
            },
        ]
        deps = _infer_dependencies(stages)
        assert "sp" in deps["ia"]

        downstream = _find_downstream({"sp"}, deps)
        assert "ia" in downstream
        assert "de" in downstream


# ── 6. Eval baselines ────────────────────────────────────────────────


class TestEvalBaselines:
    """Workshop DB supports eval baselines for regression detection."""

    def test_workshop_db_importable(self):
        from loom.workshop.db import WorkshopDB

        assert WorkshopDB is not None

    def test_workshop_db_has_baseline_methods(self):
        from loom.workshop.db import WorkshopDB

        assert hasattr(WorkshopDB, "promote_baseline")
        assert hasattr(WorkshopDB, "compare_against_baseline")

    def test_eval_runner_importable(self):
        from loom.workshop.eval_runner import EvalRunner

        assert EvalRunner is not None

    def test_eval_runner_supports_llm_judge(self):
        """EvalRunner should accept llm_judge scoring mode."""
        from loom.workshop.eval_runner import EvalRunner

        # The scoring parameter acceptance is validated at call time,
        # but we can verify the class exists and is importable.
        assert callable(getattr(EvalRunner, "run_suite", None))


# ── 7. Dead-letter replay audit trail ────────────────────────────────


class TestDeadLetterAuditTrail:
    """Dead-letter consumer supports replay tracking."""

    def test_dead_letter_consumer_importable(self):
        from loom.router.dead_letter import DeadLetterConsumer

        assert DeadLetterConsumer is not None

    def test_replay_record_importable(self):
        from loom.router.dead_letter import ReplayRecord

        assert ReplayRecord is not None

    def test_dead_letter_has_replay_log(self):
        from loom.router.dead_letter import DeadLetterConsumer

        assert hasattr(DeadLetterConsumer, "replay_log")
        assert hasattr(DeadLetterConsumer, "replay_count")

    def test_manifest_includes_workshop_extra(self):
        """Manifest declares workshop as required (needed for dead-letter UI)."""
        manifest = _load_yaml(MANIFEST)
        assert "workshop" in manifest["required_extras"]


# ── 8. TUI dashboard availability ────────────────────────────────────


class TestTUIDashboard:
    """TUI dashboard is importable and ready for use."""

    def test_tui_app_importable(self):
        from loom.tui.app import LoomDashboard

        assert LoomDashboard is not None

    def test_tui_tracked_models_importable(self):
        from loom.tui.app import TrackedGoal, TrackedStage, TrackedTask

        assert TrackedGoal is not None
        assert TrackedTask is not None
        assert TrackedStage is not None

    def test_manifest_includes_tui_extra(self):
        """Manifest declares tui as required extra."""
        manifest = _load_yaml(MANIFEST)
        assert "tui" in manifest["required_extras"]


# ── Cross-cutting: dependency declarations ───────────────────────────


class TestDependencyDeclarations:
    """pyproject.toml and manifest declare all needed extras."""

    def test_pyproject_includes_all_extras(self):
        import tomllib

        pyproject_path = BAFT_ROOT / "pyproject.toml"
        with open(pyproject_path, "rb") as f:
            pyproject = tomllib.load(f)

        deps = pyproject["project"]["dependencies"]
        loom_dep = next(d for d in deps if d.startswith("loom"))
        for extra in ("mcp", "duckdb", "rag", "workshop", "tui", "otel"):
            assert extra in loom_dep, f"loom dependency missing extra: {extra}"

    def test_manifest_extras_match_pyproject(self):
        import tomllib

        pyproject_path = BAFT_ROOT / "pyproject.toml"
        with open(pyproject_path, "rb") as f:
            pyproject = tomllib.load(f)

        manifest = _load_yaml(MANIFEST)
        manifest_extras = set(manifest["required_extras"])

        # All manifest extras should be in the loom dependency
        loom_dep = next(d for d in pyproject["project"]["dependencies"] if d.startswith("loom"))
        for extra in manifest_extras:
            if extra != "scheduler":  # scheduler is a separate dep (croniter)
                assert extra in loom_dep, (
                    f"Manifest extra '{extra}' not in pyproject.toml loom dependency"
                )
