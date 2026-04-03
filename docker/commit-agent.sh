#!/bin/sh
# Git commit agent sidecar — periodically commits and pushes baseline changes.
# Environment variables:
#   COMMIT_INTERVAL — seconds between cycles (default: 900)
#   COMMIT_MESSAGE  — commit message prefix (default: "Auto-commit")
#   BASELINE_DIR    — path to baseline repo (default: /data/baseline)

INTERVAL="${COMMIT_INTERVAL:-900}"
MESSAGE="${COMMIT_MESSAGE:-Auto-commit: analytical session updates}"
DIR="${BASELINE_DIR:-/data/baseline}"

echo "Commit agent started: interval=${INTERVAL}s, dir=${DIR}"

while true; do
  sleep "$INTERVAL"
  cd "$DIR" || continue
  git add -A
  if ! git diff --cached --quiet; then
    git commit -m "${MESSAGE} — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    git push || echo "Push failed — will retry next cycle"
  fi
done
