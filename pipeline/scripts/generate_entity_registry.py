#!/usr/bin/env python3
"""
generate_entity_registry.py
-----------------------------
Populate the entity_ids section of itp_entity_name_registry.yaml from
the live framework/data/ YAML files. Run this after any session that
adds new entity IDs.

Updates only the entity_ids section — preserves manual entries above.

Usage:
  python pipeline/scripts/generate_entity_registry.py
  python pipeline/scripts/generate_entity_registry.py --check   # dry run, show counts
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import yaml

FRAMEWORK_REPO = Path(os.environ.get("FRAMEWORK_REPO", Path.home() / "Developer" / "Repositories" / "framework"))
DATA_DIR = FRAMEWORK_REPO / "data"
BAFT_DIR = Path(__file__).parent.parent.parent
REGISTRY_PATH = BAFT_DIR / "pipeline" / "config" / "itp_entity_name_registry.yaml"

ENTITY_FILES = {
    "variables":    DATA_DIR / "variables.yaml",
    "observations": DATA_DIR / "observations.yaml",
    "scenarios":    DATA_DIR / "scenarios.yaml",
    "traps":        DATA_DIR / "traps.yaml",
    "gaps":         DATA_DIR / "gaps.yaml",
    "sessions":     DATA_DIR / "sessions.yaml",
}

BRIEFS_DIR = DATA_DIR / "briefs"


def extract_ids(data: dict | list, entity_type: str) -> list[str]:
    """Extract all entity IDs from a YAML data structure."""
    ids = []
    items = data if isinstance(data, list) else data.get("entries", data.get(entity_type, data.get(entity_type.rstrip("s"), [])))
    if not items and isinstance(data, dict):
        for v in data.values():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                items = v
                break
    for item in (items or []):
        if isinstance(item, dict):
            # Try 'id' first, then 'number' (sessions use number)
            eid = item.get("id") or item.get("number")
            if eid is not None:
                ids.append(str(eid))
    return sorted(ids)


def extract_brief_ids() -> list[str]:
    """Extract brief IDs from individual files in data/briefs/."""
    ids = []
    if not BRIEFS_DIR.exists():
        return ids
    for bf in sorted(BRIEFS_DIR.glob("*.yaml")):
        with open(bf, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if isinstance(data, dict):
            bid = data.get("id") or bf.stem.upper()
            ids.append(str(bid))
    return sorted(ids)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Dry run — show counts only")
    args = parser.parse_args()

    all_ids: dict[str, list[str]] = {}
    for entity_type, yaml_path in ENTITY_FILES.items():
        if not yaml_path.exists():
            print(f"  [WARN] Not found: {yaml_path}")
            all_ids[entity_type] = []
            continue
        with open(yaml_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        ids = extract_ids(data, entity_type)
        all_ids[entity_type] = ids
        print(f"  {entity_type:<15} {len(ids):>4} IDs")

    # Briefs are individual files in data/briefs/
    brief_ids = extract_brief_ids()
    all_ids["briefs"] = brief_ids
    print(f"  {'briefs':<15} {len(brief_ids):>4} IDs")

    if args.check:
        print(f"\nTotal: {sum(len(v) for v in all_ids.values())} entity IDs")
        print("(Dry run — registry not updated)")
        return

    # Read current registry
    with open(REGISTRY_PATH, encoding="utf-8") as f:
        registry = yaml.safe_load(f)

    # Update entity_ids section
    registry["entity_ids"] = all_ids
    registry["generated"] = str(__import__("datetime").date.today())
    registry["status"] = "generated"

    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        yaml.dump(registry, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    print(f"\nRegistry updated: {REGISTRY_PATH}")
    print(f"Total: {sum(len(v) for v in all_ids.values())} entity IDs written")


if __name__ == "__main__":
    main()
