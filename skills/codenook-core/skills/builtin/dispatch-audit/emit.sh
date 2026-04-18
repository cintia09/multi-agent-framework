#!/usr/bin/env bash
# dispatch-audit/emit.sh — append a redacted entry to .codenook/history/dispatch.jsonl
# and enforce the 500-char dispatch payload hard limit (architecture §3.1.7, v6 #T-3).
set -euo pipefail

ROLE=""; PAYLOAD=""; WORKSPACE="${CODENOOK_WORKSPACE:-}"
PAYLOAD_SET="0"

while [ $# -gt 0 ]; do
  case "$1" in
    --role)      ROLE="$2"; shift 2 ;;
    --payload)   PAYLOAD="$2"; PAYLOAD_SET="1"; shift 2 ;;
    --workspace) WORKSPACE="$2"; shift 2 ;;
    -h|--help)
      sed -n '1,40p' "$(dirname "$0")/SKILL.md"; exit 0 ;;
    *) echo "emit.sh: unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [ -z "$ROLE" ]; then
  echo "emit.sh: --role is required" >&2
  exit 2
fi
if [ "$PAYLOAD_SET" != "1" ]; then
  echo "emit.sh: --payload is required" >&2
  exit 2
fi
if [ -z "$WORKSPACE" ]; then
  # Upward search for a dir containing .codenook/
  cur="$(pwd)"
  while [ "$cur" != "/" ]; do
    if [ -d "$cur/.codenook" ]; then WORKSPACE="$cur"; break; fi
    cur="$(dirname "$cur")"
  done
  if [ -z "$WORKSPACE" ]; then
    echo "emit.sh: could not locate workspace (set --workspace or CODENOOK_WORKSPACE)" >&2
    exit 2
  fi
fi

if [ ! -d "$WORKSPACE" ]; then
  echo "emit.sh: workspace not found: $WORKSPACE" >&2
  exit 2
fi

PYTHONIOENCODING=utf-8 \
CN_ROLE="$ROLE" \
CN_PAYLOAD="$PAYLOAD" \
CN_WORKSPACE="$WORKSPACE" \
exec python3 "$(dirname "$0")/_emit.py"
