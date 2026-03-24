#!/bin/sh
# Git commit agent sidecar — periodically commits and pushes framework changes.
# Environment variables:
#   COMMIT_INTERVAL — seconds between cycles (default: 900)
#   COMMIT_MESSAGE  — commit message prefix (default: "Auto-commit")
#   FRAMEWORK_DIR   — path to framework repo (default: /data/framework)

INTERVAL="${COMMIT_INTERVAL:-900}"
MESSAGE="${COMMIT_MESSAGE:-Auto-commit: analytical session updates}"
DIR="${FRAMEWORK_DIR:-/data/framework}"

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
