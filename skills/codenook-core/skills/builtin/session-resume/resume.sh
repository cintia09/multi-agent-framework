#!/usr/bin/env bash
# session-resume/resume.sh — session state summary
set -euo pipefail

WORKSPACE="${CODENOOK_WORKSPACE:-}"; JSON="0"

while [ $# -gt 0 ]; do
  case "$1" in
    --workspace) WORKSPACE="$2"; shift 2 ;;
    --json)      JSON="1"; shift ;;
    -h|--help)
      sed -n '1,40p' "$(dirname "$0")/SKILL.md"; exit 0 ;;
    *) echo "resume.sh: unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [ -z "$WORKSPACE" ]; then
  cur="$(pwd)"
  while [ "$cur" != "/" ]; do
    if [ -d "$cur/.codenook" ]; then WORKSPACE="$cur"; break; fi
    cur="$(dirname "$cur")"
  done
  if [ -z "$WORKSPACE" ]; then
    echo "resume.sh: could not locate workspace (set --workspace or CODENOOK_WORKSPACE)" >&2
    exit 2
  fi
fi

if [ ! -d "$WORKSPACE" ]; then
  echo "resume.sh: workspace not found: $WORKSPACE" >&2
  exit 2
fi

PYTHONIOENCODING=utf-8 \
CN_WORKSPACE="$WORKSPACE" \
CN_JSON="$JSON" \
exec python3 "$(dirname "$0")/_resume.py"
