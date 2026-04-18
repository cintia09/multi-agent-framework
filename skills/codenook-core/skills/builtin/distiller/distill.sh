#!/usr/bin/env bash
# distiller/distill.sh — route distilled knowledge artifact + audit log.
# See SKILL.md.
set -euo pipefail

PLUGIN=""; TOPIC=""; CONTENT=""; WORKSPACE=""

while [ $# -gt 0 ]; do
  case "$1" in
    --plugin)    PLUGIN="$2"; shift 2 ;;
    --topic)     TOPIC="$2"; shift 2 ;;
    --content)   CONTENT="$2"; shift 2 ;;
    --workspace) WORKSPACE="$2"; shift 2 ;;
    -h|--help)
      sed -n '1,40p' "$(dirname "$0")/SKILL.md"; exit 0 ;;
    *) echo "distill.sh: unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [ -z "$PLUGIN" ] || [ -z "$TOPIC" ] || [ -z "$CONTENT" ] || [ -z "$WORKSPACE" ]; then
  echo "distill.sh: --plugin, --topic, --content, --workspace are required" >&2
  exit 2
fi

if [ ! -f "$CONTENT" ]; then
  echo "distill.sh: content file not found: $CONTENT" >&2
  exit 2
fi

PYTHONIOENCODING=utf-8 \
CN_PLUGIN="$PLUGIN" \
CN_TOPIC="$TOPIC" \
CN_CONTENT="$CONTENT" \
CN_WORKSPACE="$WORKSPACE" \
exec python3 "$(dirname "$0")/_distill.py"
