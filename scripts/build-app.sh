#!/usr/bin/env bash
# Build baft deployment ZIP for Loom Workshop app deployment.
#
# Output: dist/baft-{version}.zip
# Contents: manifest.yaml, configs/, pipeline/config/, selected scripts
set -euo pipefail

cd "$(dirname "$0")/.."

VERSION=$(python3 -c "
import tomllib
with open('pyproject.toml', 'rb') as f:
    print(tomllib.load(f)['project']['version'])
")

OUTDIR="dist"
OUT="${OUTDIR}/baft-${VERSION}.zip"

mkdir -p "$OUTDIR"
rm -f "$OUT"

echo "Building baft app bundle v${VERSION}..."

zip -r "$OUT" \
    manifest.yaml \
    configs/ \
    pipeline/config/ \
    scripts/resolve_config.py \
    pipeline/scripts/itp_import_to_duckdb.py \
    -x "*.pyc" "__pycache__/*"

echo "Built: $OUT ($(du -h "$OUT" | cut -f1))"
echo ""
echo "Deploy via Workshop UI: upload $OUT at http://localhost:8080/apps"
