#!/usr/bin/env bash
# config-resolve/resolve.sh — 4-layer deep-merge + model symbol expansion.
# See SKILL.md for full contract.
set -euo pipefail

PLUGIN=""; TASK=""; WORKSPACE=""; CATALOG=""

while [ $# -gt 0 ]; do
  case "$1" in
    --plugin)    PLUGIN="$2"; shift 2 ;;
    --task)      TASK="$2"; shift 2 ;;
    --workspace) WORKSPACE="$2"; shift 2 ;;
    --catalog)   CATALOG="$2"; shift 2 ;;
    -h|--help)
      sed -n '1,40p' "$(dirname "$0")/SKILL.md"; exit 0 ;;
    *) echo "resolve.sh: unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [ -z "$PLUGIN" ] || [ -z "$WORKSPACE" ]; then
  echo "resolve.sh: --plugin and --workspace are required" >&2
  exit 2
fi

# Default catalog: workspace state.json (M1 tests always pass --catalog explicitly).
if [ -z "$CATALOG" ]; then
  CATALOG="$WORKSPACE/.codenook/state.json"
fi

PYTHONIOENCODING=utf-8 \
CN_PLUGIN="$PLUGIN" \
CN_TASK="$TASK" \
CN_WORKSPACE="$WORKSPACE" \
CN_CATALOG="$CATALOG" \
exec python3 "$(dirname "$0")/_resolve.py"
