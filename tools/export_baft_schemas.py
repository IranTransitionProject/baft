"""Export Baft's worker I/O Pydantic models to JSON Schema.

The wrappers in ``baft.contracts`` (``SourceBundle``, ``ExtractedClaims``,
``AnalyticalInput``, etc.) are the on-bus shapes that baft workers expect
and emit.  Heddle resolves them at config-load time via
``input_schema_ref`` / ``output_schema_ref``, but foreign consumers
(a future Swift companion app, a .NET integration, a separate evaluator)
need them in a stable on-disk form.

This script writes one JSON Schema per wrapper class to
``baft-schemas/v1/<snake_name>.schema.json`` with stable sort order and
a trailing newline so the output is git-diffable.  CI runs the script
in ``--check`` mode and fails on drift — the same pattern Heddle uses
for its wire-envelope schemas (see ``heddle/tools/export_schemas.py``).

Usage::

    uv run python tools/export_baft_schemas.py            # rewrite baft-schemas/v1/
    uv run python tools/export_baft_schemas.py --check    # CI: exit 1 on drift
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pydantic import BaseModel

from baft.contracts import (
    AnalyticalInput,
    AnalyticalOutput,
    AuditReport,
    AuditRequest,
    ExtractedClaims,
    InboxItem,
    IntegrationRequest,
    IntegrationResult,
    LAaudit,
    NeutralizationRequest,
    NeutralizationResult,
    NIoutput,
    NIrequest,
    NoteInput,
    PAaudit,
    RTaudit,
    SAadvisory,
    SessionMonitorRequest,
    SourceBundle,
    SynthesisRequest,
    ValidationRequest,
    ValidationResult,
    WatchRequest,
    WatchResults,
)

# (filename_stem, model).  Explicit stems sidestep the acronym-vs-CamelCase
# ambiguity in classes like ``LAaudit`` (→ ``la_audit``, not ``l_aaudit``)
# and match the naming used in worker YAML configs.
_EXPORTS: list[tuple[str, type[BaseModel]]] = [
    ("analytical_input", AnalyticalInput),
    ("analytical_output", AnalyticalOutput),
    ("audit_report", AuditReport),
    ("audit_request", AuditRequest),
    ("extracted_claims", ExtractedClaims),
    ("inbox_item", InboxItem),
    ("integration_request", IntegrationRequest),
    ("integration_result", IntegrationResult),
    ("la_audit", LAaudit),
    ("neutralization_request", NeutralizationRequest),
    ("neutralization_result", NeutralizationResult),
    ("ni_output", NIoutput),
    ("ni_request", NIrequest),
    ("note_input", NoteInput),
    ("pa_audit", PAaudit),
    ("rt_audit", RTaudit),
    ("sa_advisory", SAadvisory),
    ("session_monitor_request", SessionMonitorRequest),
    ("source_bundle", SourceBundle),
    ("synthesis_request", SynthesisRequest),
    ("validation_request", ValidationRequest),
    ("validation_result", ValidationResult),
    ("watch_request", WatchRequest),
    ("watch_results", WatchResults),
]

_OUTPUT_DIR = Path(__file__).resolve().parents[1] / "baft-schemas" / "v1"


def _render(model: type[BaseModel]) -> str:
    """Render a model's JSON Schema with stable sort + trailing newline."""
    schema: dict[str, Any] = model.model_json_schema()
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def _write_all() -> list[Path]:
    """Write every export to disk.  Returns the list of paths written."""
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for stem, model in _EXPORTS:
        path = _OUTPUT_DIR / f"{stem}.schema.json"
        path.write_text(_render(model), encoding="utf-8")
        written.append(path)
    return written


def _check_all() -> int:
    """Compare on-disk schemas against the live render.  Return shell exit code."""
    drift: list[str] = []
    missing: list[str] = []
    for stem, model in _EXPORTS:
        path = _OUTPUT_DIR / f"{stem}.schema.json"
        expected = _render(model)
        if not path.exists():
            missing.append(stem)
            continue
        actual = path.read_text(encoding="utf-8")
        if expected != actual:
            drift.append(stem)
    if missing or drift:
        msg = ["Baft schema drift detected."]
        if missing:
            msg.append("  Missing: " + ", ".join(missing))
        if drift:
            msg.append("  Drifted: " + ", ".join(drift))
        msg.append("  Run `uv run python tools/export_baft_schemas.py` and commit the result.")
        sys.stderr.write("\n".join(msg) + "\n")
        return 1
    return 0


def main() -> int:
    """CLI entry point — exports schemas, or in ``--check`` mode reports drift."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if the on-disk schemas don't match the live Pydantic output.",
    )
    args = parser.parse_args()
    if args.check:
        return _check_all()
    written = _write_all()
    for path in written:
        sys.stdout.write(f"wrote {path.relative_to(Path.cwd())}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
