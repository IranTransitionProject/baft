#!/usr/bin/env python3
"""Resolve silo references in baft worker configs to concrete file paths.

Baft worker configs use ``silo: <name>`` in knowledge_sources.  Loom's runtime
expects ``path:`` + ``inject_as:`` entries.  This script bridges the two.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import yaml

BAFT_DIR = Path(__file__).parent.parent
SILO_INDEX = BAFT_DIR / "configs" / "knowledge" / "itp_silos.yaml"


def _resolve_itp_root() -> Path:
    """Find the ITP project root from env var or parent directory."""
    if "ITP_ROOT" in os.environ:
        return Path(os.environ["ITP_ROOT"])
    candidate = BAFT_DIR.parent
    if (candidate / "baseline" / "data").is_dir():
        return candidate
    raise FileNotFoundError("Cannot find ITP project root. Set ITP_ROOT env var.")


def load_silo_index(silo_path: Path) -> dict:
    """Load and expand env vars in silo index."""
    itp_root = str(_resolve_itp_root())
    raw = silo_path.read_text()
    # Expand ${ITP_ROOT} manually (os.path.expandvars only handles $VAR)
    raw = raw.replace("${ITP_ROOT}", itp_root)
    raw = os.path.expandvars(raw)
    data = yaml.safe_load(raw)
    return data.get("silos", {})


def resolve_worker_config(config_path: Path, silos: dict) -> dict:
    """Resolve silo references in a worker config to concrete paths."""
    config = yaml.safe_load(config_path.read_text())

    knowledge_sources = config.get("knowledge_sources", [])
    if not knowledge_sources:
        return config

    resolved = []
    for source in knowledge_sources:
        silo_name = source.get("silo")
        if silo_name:
            silo_def = silos.get(silo_name)
            if not silo_def:
                print(f"WARNING: Silo '{silo_name}' not found in index", file=sys.stderr)
                continue
            for s in silo_def.get("sources", []):
                p = Path(s["path"])
                if not p.is_absolute():
                    p = BAFT_DIR / p
                resolved.append(
                    {
                        "path": str(p),
                        "inject_as": s.get("inject_as", "reference"),
                    }
                )
        else:
            # Direct path reference — pass through
            resolved.append(source)

    config["knowledge_sources"] = resolved
    return config


def main() -> None:
    """CLI entry point for resolving silo references."""
    parser = argparse.ArgumentParser(description="Resolve silo refs in worker config")
    parser.add_argument("config", help="Path to worker YAML config")
    parser.add_argument("-o", "--output", help="Output path (default: stdout)")
    parser.add_argument("--silo-index", default=str(SILO_INDEX), help="Path to silo index YAML")
    args = parser.parse_args()

    silos = load_silo_index(Path(args.silo_index))
    resolved = resolve_worker_config(Path(args.config), silos)

    output = yaml.dump(resolved, default_flow_style=False, allow_unicode=True, sort_keys=False)

    if args.output:
        Path(args.output).write_text(output)
        print(f"Resolved config written to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
