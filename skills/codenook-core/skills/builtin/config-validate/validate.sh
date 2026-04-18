#!/usr/bin/env bash
# config-validate/validate.sh — field-level validation of a merged config JSON.
# See SKILL.md for the contract.
set -euo pipefail

CONFIG=""; SCHEMA=""; JSON_OUT="0"

while [ $# -gt 0 ]; do
  case "$1" in
    --config) CONFIG="$2"; shift 2 ;;
    --schema) SCHEMA="$2"; shift 2 ;;
    --json)   JSON_OUT="1"; shift ;;
    -h|--help)
      sed -n '1,40p' "$(dirname "$0")/SKILL.md"; exit 0 ;;
    *) echo "validate.sh: unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [ -z "$CONFIG" ]; then
  echo "validate.sh: --config <merged.json> is required" >&2
  exit 2
fi

if [ ! -f "$CONFIG" ]; then
  echo "validate.sh: config file not found: $CONFIG" >&2
  exit 2
fi

if [ -z "$SCHEMA" ]; then
  SCHEMA="$(dirname "$0")/config-schema.yaml"
fi

if [ ! -f "$SCHEMA" ]; then
  echo "validate.sh: schema file not found: $SCHEMA" >&2
  exit 2
fi

PYTHONIOENCODING=utf-8 \
CN_CONFIG="$CONFIG" \
CN_SCHEMA="$SCHEMA" \
CN_JSON="$JSON_OUT" \
exec python3 "$(dirname "$0")/_validate.py"
