#!/usr/bin/env bash
# validators/post-test.sh — mechanical post-condition check after the
# tester phase. Verifies the tester's output file exists and has the
# verdict frontmatter (no semantic interpretation; that is the
# orchestrator's job).
set -euo pipefail
TID="${1:?usage: post-test.sh <task_id>}"
OUT=".codenook/tasks/$TID/outputs/phase-9-tester.md"
[ -f "$OUT" ] || { echo "post-test: missing $OUT" >&2; exit 1; }
head -10 "$OUT" | grep -q '^verdict:' \
  || { echo "post-test: $OUT lacks verdict frontmatter" >&2; exit 1; }
exit 0
