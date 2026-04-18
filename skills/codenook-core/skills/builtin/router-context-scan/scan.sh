#!/usr/bin/env bash
# router-context-scan/scan.sh — workspace inventory for the router agent.
# See SKILL.md for full contract.
set -euo pipefail

WORKSPACE="${CODENOOK_WORKSPACE:-}"
MAX_TASKS="20"
JSON_OUT="0"

while [ $# -gt 0 ]; do
  case "$1" in
    --workspace) WORKSPACE="$2"; shift 2 ;;
    --max-tasks) MAX_TASKS="$2"; shift 2 ;;
    --json)      JSON_OUT="1"; shift ;;
    -h|--help)   sed -n '1,40p' "$(dirname "$0")/SKILL.md"; exit 0 ;;
    *) echo "scan.sh: unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [ -z "$WORKSPACE" ]; then
  cur="$(pwd)"
  while [ "$cur" != "/" ]; do
    if [ -d "$cur/.codenook" ]; then WORKSPACE="$cur"; break; fi
    cur="$(dirname "$cur")"
  done
  if [ -z "$WORKSPACE" ] || [ ! -d "$WORKSPACE/.codenook" ]; then
    echo "scan.sh: could not locate workspace (set --workspace)" >&2
    exit 2
  fi
fi

if [ ! -d "$WORKSPACE/.codenook" ]; then
  echo "scan.sh: workspace missing .codenook/: $WORKSPACE" >&2
  exit 2
fi

case "$MAX_TASKS" in
  ''|*[!0-9]*) echo "scan.sh: --max-tasks must be a positive integer" >&2; exit 2 ;;
esac

PYTHONIOENCODING=utf-8 \
CN_WORKSPACE="$WORKSPACE" \
CN_MAX_TASKS="$MAX_TASKS" \
CN_JSON="$JSON_OUT" \
exec python3 "$(dirname "$0")/_scan.py"
