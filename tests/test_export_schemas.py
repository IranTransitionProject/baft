"""
test_export_schemas.py
----------------------
Regression tests for ``tools/export_baft_schemas.py``.

These tests stay green only as long as the script's CLI contract and the
on-disk schemas under ``baft-schemas/v1/`` agree with what the live
``baft.contracts`` Pydantic models produce.  CI also runs
``--check`` directly as a job; this file is the in-tree mirror so test
failures show up in pytest output and coverage reports.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

BAFT_ROOT = Path(__file__).parent.parent
SCHEMAS_DIR = BAFT_ROOT / "baft-schemas" / "v1"
EXPORT_SCRIPT = BAFT_ROOT / "tools" / "export_baft_schemas.py"


class TestExportScript:
    """The script imports cleanly, has a sensible export list, and round-trips."""

    def test_script_exists(self):
        assert EXPORT_SCRIPT.exists()

    def test_exports_table_matches_contracts(self):
        """Every public model in baft.contracts.__all__ has a schema export."""
        import baft.contracts
        from tools.export_baft_schemas import _EXPORTS

        exported_classes = {model.__name__ for _stem, model in _EXPORTS}
        public = set(baft.contracts.__all__)
        missing = public - exported_classes
        assert not missing, (
            f"Contracts missing from export list: {sorted(missing)}. "
            "Add them to tools/export_baft_schemas.py::_EXPORTS."
        )

    def test_export_stems_are_unique(self):
        from tools.export_baft_schemas import _EXPORTS

        stems = [stem for stem, _ in _EXPORTS]
        assert len(stems) == len(set(stems)), "Duplicate filename stems in _EXPORTS"


class TestSchemasOnDisk:
    """The committed schemas under baft-schemas/v1/ are consistent and current."""

    def test_directory_exists(self):
        assert SCHEMAS_DIR.is_dir(), (
            "baft-schemas/v1/ missing. Run: uv run python tools/export_baft_schemas.py"
        )

    def test_every_export_has_a_committed_file(self):
        from tools.export_baft_schemas import _EXPORTS

        missing = [
            stem for stem, _ in _EXPORTS if not (SCHEMAS_DIR / f"{stem}.schema.json").exists()
        ]
        assert not missing, f"Missing schema files: {missing}"

    def test_no_drift_between_disk_and_models(self):
        """Run the script's --check mode in-process; exit 0 iff no drift."""
        result = subprocess.run(
            [sys.executable, str(EXPORT_SCRIPT), "--check"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, (
            f"Schema drift detected.\nstderr: {result.stderr}\n"
            f"stdout: {result.stdout}\n"
            "Run: uv run python tools/export_baft_schemas.py  (then commit)"
        )

    @pytest.mark.parametrize(
        "stem",
        ["source_bundle", "extracted_claims", "validation_result", "audit_report"],
    )
    def test_each_schema_is_valid_json_with_expected_keys(self, stem: str):
        """Spot-check that the exported JSON Schema has the right shape."""
        path = SCHEMAS_DIR / f"{stem}.schema.json"
        data = json.loads(path.read_text())
        # Every Pydantic-derived schema has at least "title", "type", and "properties".
        assert data.get("type") == "object"
        assert "properties" in data
        assert "title" in data
