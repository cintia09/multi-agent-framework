#!/usr/bin/env bash
# validators/post-draft.sh -- mechanical post-condition check after the
# drafter phase. Verifies the expected output file exists and has YAML
# frontmatter with a verdict field.
#
# Invoked by orchestrator-tick.run_post_validate as:
#   <script> <task_id>
# CWD == workspace root.
set -euo pipefail
TID="${1:?usage: post-draft.sh <task_id>}"
OUT=".codenook/tasks/${TID}/outputs/phase-2-drafter.md"
[ -f "$OUT" ] || { echo "post-draft: missing $OUT" >&2; exit 1; }
head -10 "$OUT" | grep -q '^verdict:' \
  || { echo "post-draft: $OUT lacks verdict frontmatter" >&2; exit 1; }
exit 0
