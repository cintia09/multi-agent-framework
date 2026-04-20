#!/usr/bin/env bash
# validators/post-build.sh — mechanical post-condition check after the
# builder phase. Verifies the expected output file exists and has YAML
# frontmatter with a verdict field.
#
# Invoked by orchestrator-tick.run_post_validate as:
#   <script> <task_id>
# CWD == workspace root.
set -euo pipefail
TID="${1:?usage: post-build.sh <task_id>}"
OUT=".codenook/tasks/$TID/outputs/phase-5-builder.md"
[ -f "$OUT" ] || { echo "post-build: missing $OUT" >&2; exit 1; }
head -10 "$OUT" | grep -q '^verdict:' \
  || { echo "post-build: $OUT lacks verdict frontmatter" >&2; exit 1; }
exit 0
