#!/usr/bin/env bash
# init.sh — M9.1 builtin "init" skill.
#
# Scaffolds the workspace memory skeleton in $PWD/.codenook/memory/:
#   knowledge/  skills/  history/  config.yaml
#
# Idempotent: safe to re-run; existing files / directories are preserved.
# A .gitignore entry is added for the index-snapshot file.

set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$(cd "$SELF_DIR/../_lib" && pwd)"

WS="${1:-$PWD}"

PYTHONPATH="$LIB_DIR" python3 - "$WS" <<'PY'
import sys
import memory_layer as ml

ws = sys.argv[1]
ml.init_memory_skeleton(ws)
PY

# Append the snapshot file to a workspace-local .gitignore so it is not
# accidentally committed.
gi="$WS/.codenook/memory/.gitignore"
if [ ! -f "$gi" ]; then
  printf '.index-snapshot.json\n' > "$gi"
elif ! grep -qx '.index-snapshot.json' "$gi"; then
  printf '.index-snapshot.json\n' >> "$gi"
fi

# M10.6: workspace-local .gitignore for the task-chain snapshot
# (mirrors the M9.1 memory snapshot pattern; same one-file-per-area rule).
mkdir -p "$WS/.codenook/tasks"
gi="$WS/.codenook/tasks/.gitignore"
if [ ! -f "$gi" ]; then
  printf '.chain-snapshot.json\n' > "$gi"
elif ! grep -qx '.chain-snapshot.json' "$gi"; then
  printf '.chain-snapshot.json\n' >> "$gi"
fi
