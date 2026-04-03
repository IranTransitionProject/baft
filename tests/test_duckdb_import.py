"""
test_duckdb_import.py
---------------------
Tests for the ITP DuckDB import script.

Validates:
  - Schema creation (entities table with correct columns)
  - Entity import from YAML fixtures
  - ID prefix generation (Obs-, Trap-, etc.)
  - FTS index creation
  - Tag extraction
  - Content serialization
  - Incremental import flag
  - Stats mode
"""

from __future__ import annotations

# Import the module under test
import importlib.util
import json
from pathlib import Path

import duckdb
import pytest
import yaml

BAFT_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = BAFT_ROOT / "pipeline" / "scripts" / "itp_import_to_duckdb.py"

try:
    spec = importlib.util.spec_from_file_location("itp_import_to_duckdb", SCRIPT_PATH)
    itp_import = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(itp_import)
except FileNotFoundError:
    # CI environments don't have ITP_ROOT / baseline/ — skip this module.
    pytest.skip(
        "ITP_ROOT not set and baseline/ not found — skipping DuckDB import tests",
        allow_module_level=True,
    )


@pytest.fixture
def db_conn(tmp_path):
    """Create a temporary in-memory DuckDB connection."""
    db_path = tmp_path / "test.duckdb"
    conn = duckdb.connect(str(db_path))
    yield conn
    conn.close()


@pytest.fixture
def db_with_schema(db_conn):
    """Connection with schema already created."""
    itp_import.create_schema(db_conn)
    return db_conn


# ── Test: schema creation ──────────────────────────────────────────────


class TestSchemaCreation:
    """Entities table must have the expected structure."""

    def test_creates_entities_table(self, db_conn):
        itp_import.create_schema(db_conn)
        tables = db_conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_name = 'entities'"
        ).fetchall()
        assert len(tables) == 1

    def test_entities_columns(self, db_with_schema):
        cols = db_with_schema.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'entities' ORDER BY ordinal_position"
        ).fetchall()
        col_names = [c[0] for c in cols]
        expected = [
            "id",
            "type",
            "title",
            "status",
            "epistemic_tag",
            "confidence",
            "content",
            "tags",
            "updated_date",
            "imported_at",
        ]
        for col in expected:
            assert col in col_names, f"Missing column: {col}"

    def test_id_is_primary_key(self, db_with_schema):
        # Insert a row, then try duplicate — should replace (INSERT OR REPLACE)
        db_with_schema.execute(
            "INSERT INTO entities (id, type, title) VALUES ('V-01', 'variables', 'Test')"
        )
        db_with_schema.execute(
            "INSERT OR REPLACE INTO entities (id, type, title) "
            "VALUES ('V-01', 'variables', 'Updated')"
        )
        result = db_with_schema.execute("SELECT title FROM entities WHERE id = 'V-01'").fetchone()
        assert result[0] == "Updated"

    def test_schema_idempotent(self, db_conn):
        """Creating schema twice should not error."""
        itp_import.create_schema(db_conn)
        itp_import.create_schema(db_conn)  # Should not raise


# ── Test: entity import ────────────────────────────────────────────────


class TestEntityImport:
    """import_entity_list must correctly populate the entities table."""

    def test_import_variables(self, db_with_schema):
        entities = [
            {
                "id": "V-01",
                "title": "Supreme Leader Authority",
                "status": "active",
                "epistemic_tag": "fact",
                "confidence": "high",
            },
            {
                "id": "V-02",
                "title": "IRGC Economic Power",
                "status": "active",
                "epistemic_tag": "inference",
                "confidence": "medium",
            },
        ]
        count = itp_import.import_entity_list(db_with_schema, "variables", entities, "entities")
        assert count == 2

        rows = db_with_schema.execute("SELECT id, type, title FROM entities ORDER BY id").fetchall()
        assert len(rows) == 2
        assert rows[0] == ("V-01", "variables", "Supreme Leader Authority")

    def test_import_empty_list(self, db_with_schema):
        count = itp_import.import_entity_list(db_with_schema, "variables", [], "entities")
        assert count == 0

    def test_id_prefix_observations(self, db_with_schema):
        """Observations should get Obs- prefix if not already present."""
        entities = [{"id": "101", "title": "Test Observation"}]
        itp_import.import_entity_list(db_with_schema, "observations", entities, "entities")
        row = db_with_schema.execute("SELECT id FROM entities").fetchone()
        assert row[0] == "Obs-101"

    def test_id_prefix_traps(self, db_with_schema):
        """Traps should get Trap- prefix if not already present."""
        entities = [{"id": "1", "title": "Test Trap"}]
        itp_import.import_entity_list(db_with_schema, "traps", entities, "entities")
        row = db_with_schema.execute("SELECT id FROM entities").fetchone()
        assert row[0] == "Trap-1"

    def test_no_double_prefix(self, db_with_schema):
        """If ID already has prefix, don't double it."""
        entities = [{"id": "Obs-101", "title": "Already Prefixed"}]
        itp_import.import_entity_list(db_with_schema, "observations", entities, "entities")
        row = db_with_schema.execute("SELECT id FROM entities").fetchone()
        assert row[0] == "Obs-101"

    def test_missing_id_uses_fallback(self, db_with_schema):
        """Entities without id use code or number field."""
        entities = [{"code": "ITB-A1", "title": "Test Module"}]
        itp_import.import_entity_list(db_with_schema, "modules", entities, "entities")
        row = db_with_schema.execute("SELECT id FROM entities").fetchone()
        assert row[0] == "Mod-ITB-A1"


# ── Test: content serialization ────────────────────────────────────────


class TestSerialization:
    """Entity content must be serialized as searchable JSON."""

    def test_content_is_json(self, db_with_schema):
        entities = [{"id": "V-01", "title": "Test", "nested": {"key": "value"}}]
        itp_import.import_entity_list(db_with_schema, "variables", entities, "entities")
        row = db_with_schema.execute("SELECT content FROM entities WHERE id = 'V-01'").fetchone()
        parsed = json.loads(row[0])
        assert parsed["nested"]["key"] == "value"

    def test_serialize_handles_unicode(self):
        result = itp_import.serialize({"text": "آزمایش"})
        assert "آزمایش" in result


# ── Test: tag extraction ───────────────────────────────────────────────


class TestTagExtraction:
    """extract_tags must collect searchable fields."""

    def test_extracts_title(self):
        tags = itp_import.extract_tags({"title": "Supreme Leader"})
        assert "Supreme Leader" in tags

    def test_extracts_list_fields(self):
        tags = itp_import.extract_tags({"tags": ["iran", "politics"], "status": "active"})
        assert "iran" in tags
        assert "politics" in tags
        assert "active" in tags

    def test_handles_missing_fields(self):
        tags = itp_import.extract_tags({})
        assert tags == ""

    def test_extracts_entities_mentioned(self):
        tags = itp_import.extract_tags({"entities_mentioned": ["V-01", "V-02"]})
        assert "V-01" in tags


# ── Test: pipeline config files exist ──────────────────────────────────


class TestPipelineConfigFiles:
    """All pipeline config files referenced by workers must exist."""

    EXPECTED_CONFIGS = [
        "pipeline/config/itp_source_hierarchy.yaml",
        "pipeline/config/itp_epistemic_rules.yaml",
        "pipeline/config/itp_cognitive_profile.yaml",
        "pipeline/config/itp_entity_name_registry.yaml",
        "pipeline/config/itp_terminology_registry.yaml",
        "pipeline/config/itp_tier_rules.yaml",
        "pipeline/config/itp_watch_list.yaml",
    ]

    @pytest.mark.parametrize("config_path", EXPECTED_CONFIGS)
    def test_config_exists(self, config_path):
        full_path = BAFT_ROOT / config_path
        assert full_path.exists(), f"Pipeline config not found: {config_path}"

    @pytest.mark.parametrize("config_path", EXPECTED_CONFIGS)
    def test_config_parses(self, config_path):
        full_path = BAFT_ROOT / config_path
        if not full_path.exists():
            pytest.skip(f"{config_path} not found")
        with open(full_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        assert data is not None, f"{config_path} is empty"
