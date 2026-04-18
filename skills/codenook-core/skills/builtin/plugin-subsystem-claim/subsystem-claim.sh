#!/usr/bin/env bash
set -euo pipefail
SRC=""; WORKSPACE=""; UPGRADE="0"; JSON_OUT="0"
while [ $# -gt 0 ]; do
  case "$1" in
    --src) SRC="$2"; shift 2 ;;
    --workspace) WORKSPACE="$2"; shift 2 ;;
    --upgrade) UPGRADE="1"; shift ;;
    --json) JSON_OUT="1"; shift ;;
    -h|--help) sed -n '1,40p' "$(dirname "$0")/SKILL.md"; exit 0 ;;
    *) echo "subsystem-claim.sh: unknown arg: $1" >&2; exit 2 ;;
  esac
done
[ -z "$SRC" ] && { echo "subsystem-claim.sh: --src required" >&2; exit 2; }
[ -d "$SRC" ] || { echo "subsystem-claim.sh: --src must be a directory" >&2; exit 2; }
CN_SRC="$SRC" CN_WORKSPACE="$WORKSPACE" CN_UPGRADE="$UPGRADE" CN_JSON="$JSON_OUT" \
  exec python3 "$(dirname "$0")/_subsystem_claim.py"
