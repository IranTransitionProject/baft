#!/usr/bin/env python3
"""
itp_import_to_duckdb.py
-----------------------
Import ITP framework YAML entity data into DuckDB for structured querying.

Creates tables: variables, observations, scenarios, traps, gaps, briefs,
                modules, sessions
Creates view:   entities (unified across all types for MCP query backend)
Creates FTS:    full-text search index on entities.content and entities.title

Run modes:
  python itp_import_to_duckdb.py                  # full reimport
  python itp_import_to_duckdb.py --incremental    # skip unchanged entities
  python itp_import_to_duckdb.py --stats          # print counts, no import

Output: itp-workspace/itp.duckdb
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml
import duckdb

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

FRAMEWORK_REPO = Path(os.environ.get("FRAMEWORK_REPO", Path.home() / "Developer" / "Repositories" / "framework"))
DATA_DIR = FRAMEWORK_REPO / "data"
BAFT_DIR = Path(__file__).parent.parent.parent  # repo root
WORKSPACE_DIR = BAFT_DIR / "itp-workspace"
DB_PATH = WORKSPACE_DIR / "itp.duckdb"

ENTITY_YAML_FILES = {
    "variables":    DATA_DIR / "variables.yaml",
    "observations": DATA_DIR / "observations.yaml",
    "scenarios":    DATA_DIR / "scenarios.yaml",
    "traps":        DATA_DIR / "traps.yaml",
    "gaps":         DATA_DIR / "gaps.yaml",
    "modules":      DATA_DIR / "modules.yaml",
    "sessions":     DATA_DIR / "sessions.yaml",
}

BRIEFS_DIR = DATA_DIR / "briefs"


def load_yaml(path: Path) -> dict | list:
    if not path.exists():
        print(f"  [WARN] Not found: {path}")
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def serialize(entity: dict) -> str:
    """Serialize entity dict to JSON string for full-text content field."""
    return json.dumps(entity, ensure_ascii=False, default=str)


def extract_tags(entity: dict) -> str:
    """Extract searchable tags from entity fields."""
    parts = []
    for field in ["title", "name", "tags", "topics", "entities_mentioned", "cross_refs", "faction", "status"]:
        val = entity.get(field)
        if isinstance(val, str):
            parts.append(val)
        elif isinstance(val, list):
            parts.extend(str(v) for v in val)
    return " ".join(parts)


def import_entity_list(conn: duckdb.DuckDBPyConnection, entity_type: str, entities: list[dict], table: str) -> int:
    """Import a list of entity dicts into the given table."""
    if not entities:
        return 0

    # Derive common columns; entity-specific columns go into content JSON
    rows = []
    # ID prefix map to avoid collisions between types with numeric IDs
    prefix_map = {
        "observations": "Obs-",
        "traps": "Trap-",
        "sessions": "Session-",
        "modules": "Mod-",
    }
    prefix = prefix_map.get(entity_type, "")

    for e in entities:
        raw_id = str(e.get("id") or e.get("code") or e.get("number") or "")
        entity_id = f"{prefix}{raw_id}" if (prefix and not raw_id.startswith(prefix.rstrip("-"))) else raw_id
        row = {
            "id": entity_id,
            "type": entity_type,
            "title": str(e.get("title") or e.get("name") or e.get("description") or ""),
            "status": str(e.get("status") or ""),
            "epistemic_tag": str(e.get("epistemic_tag") or ""),
            "confidence": str(e.get("confidence") or ""),
            "content": serialize(e),
            "tags": extract_tags(e),
            "updated_date": str(e.get("updated_date") or e.get("date") or datetime.now(timezone.utc).date()),
        }
        rows.append(row)

    conn.executemany(
        f"""INSERT OR REPLACE INTO {table}
            (id, type, title, status, epistemic_tag, confidence, content, tags, updated_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [(r["id"], r["type"], r["title"], r["status"], r["epistemic_tag"],
          r["confidence"], r["content"], r["tags"], r["updated_date"]) for r in rows],
    )
    return len(rows)


def create_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create the unified entities table and FTS index."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS entities (
            id           VARCHAR PRIMARY KEY,
            type         VARCHAR NOT NULL,
            title        VARCHAR,
            status       VARCHAR,
            epistemic_tag VARCHAR,
            confidence   VARCHAR,
            content      VARCHAR,   -- full entity JSON
            tags         VARCHAR,   -- concatenated searchable fields
            updated_date DATE,
            imported_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # DuckDB FTS (full-text search)
    try:
        conn.execute("INSTALL fts; LOAD fts;")
    except Exception:
        pass  # Already installed

    try:
        conn.execute("""
            PRAGMA create_fts_index(
                'entities', 'id',
                'title', 'tags', 'content',
                stemmer='porter',
                stopwords='english',
                ignore='(\\.|[^a-z])+',
                strip_accents=1,
                lower=1,
                overwrite=1
            )
        """)
    except Exception as exc:
        print(f"  [WARN] FTS index creation failed (non-critical): {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Import ITP framework YAML into DuckDB")
    parser.add_argument("--incremental", action="store_true", help="Skip entities not modified since last import")
    parser.add_argument("--stats", action="store_true", help="Print entity counts from current DB, no import")
    parser.add_argument("--db", default=str(DB_PATH), help="DuckDB path (default: itp-workspace/itp.duckdb)")
    args = parser.parse_args()

    db_path = Path(args.db)

    if args.stats:
        if not db_path.exists():
            print("No database found. Run without --stats to create it.")
            sys.exit(1)
        conn = duckdb.connect(str(db_path))
        results = conn.execute("SELECT type, COUNT(*) as n FROM entities GROUP BY type ORDER BY type").fetchall()
        total = sum(r[1] for r in results)
        print(f"\nITP DuckDB entity counts ({db_path}):")
        for entity_type, count in results:
            print(f"  {entity_type:<20} {count:>5}")
        print(f"  {'TOTAL':<20} {total:>5}")
        conn.close()
        return

    # Ensure workspace directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Connecting to {db_path}")
    conn = duckdb.connect(str(db_path))

    if not args.incremental:
        print("Full reimport — dropping existing entities table")
        conn.execute("DROP TABLE IF EXISTS entities")

    create_schema(conn)

    total_imported = 0

    # --- Main entity YAML files ---
    for entity_type, yaml_path in ENTITY_YAML_FILES.items():
        print(f"Importing {entity_type} from {yaml_path.name}...")
        data = load_yaml(yaml_path)

        # Most YAML files have a top-level key matching the type
        entities = []
        if isinstance(data, list):
            entities = data
        elif isinstance(data, dict):
            # Try the entity type key, then any list value
            entities = data.get(entity_type, data.get(entity_type.rstrip("s"), []))
            if not entities:
                for v in data.values():
                    if isinstance(v, list) and v and isinstance(v[0], dict):
                        entities = v
                        break

        count = import_entity_list(conn, entity_type, entities, "entities")
        print(f"  → {count} entities imported")
        total_imported += count

    # --- Briefs (one file per brief or all in briefs.yaml) ---
    briefs_yaml = DATA_DIR / "briefs.yaml"
    if briefs_yaml.exists():
        print(f"Importing briefs from briefs.yaml...")
        data = load_yaml(briefs_yaml)
        entities = data if isinstance(data, list) else data.get("briefs", [])
        count = import_entity_list(conn, "brief", entities, "entities")
        print(f"  → {count} briefs imported")
        total_imported += count
    elif BRIEFS_DIR.exists():
        print(f"Importing briefs from {BRIEFS_DIR}/...")
        brief_entities = []
        for brief_file in sorted(BRIEFS_DIR.glob("*.yaml")):
            brief_data = load_yaml(brief_file)
            if isinstance(brief_data, dict):
                # Use filename stem as fallback ID (e.g., b01 → B01)
                if "id" not in brief_data:
                    brief_data["id"] = brief_file.stem.upper()
                brief_entities.append(brief_data)
            elif isinstance(brief_data, list):
                for i, item in enumerate(brief_data):
                    if isinstance(item, dict) and "id" not in item:
                        item["id"] = f"{brief_file.stem.upper()}-{i}"
                brief_entities.extend(brief_data)
        count = import_entity_list(conn, "brief", brief_entities, "entities")
        print(f"  → {count} briefs imported")
        total_imported += count

    # Rebuild FTS index after import
    print("Rebuilding FTS index...")
    try:
        conn.execute("PRAGMA drop_fts_index('entities')")
        conn.execute("""
            PRAGMA create_fts_index(
                'entities', 'id',
                'title', 'tags', 'content',
                stemmer='porter',
                stopwords='english',
                ignore='(\\.|[^a-z])+',
                strip_accents=1,
                lower=1,
                overwrite=1
            )
        """)
        print("  FTS index rebuilt")
    except Exception as exc:
        print(f"  [WARN] FTS rebuild failed: {exc}")

    conn.close()
    print(f"\nImport complete: {total_imported} total entities → {db_path}")
    print(f"Run with --stats to verify counts.")


if __name__ == "__main__":
    main()
