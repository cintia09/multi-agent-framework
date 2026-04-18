#!/usr/bin/env bash
# plugin-format/format-check.sh — Install gate G01.
set -euo pipefail

SRC=""; JSON_OUT="0"

while [ $# -gt 0 ]; do
  case "$1" in
    --src) SRC="$2"; shift 2 ;;
    --json) JSON_OUT="1"; shift ;;
    -h|--help) sed -n '1,40p' "$(dirname "$0")/SKILL.md"; exit 0 ;;
    *) echo "format-check.sh: unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [ -z "$SRC" ]; then
  echo "format-check.sh: --src <dir> is required" >&2
  exit 2
fi
if [ ! -d "$SRC" ]; then
  echo "format-check.sh: --src must be an existing directory: $SRC" >&2
  exit 2
fi

CN_SRC="$SRC" CN_JSON="$JSON_OUT" \
  exec python3 "$(dirname "$0")/_format_check.py"
