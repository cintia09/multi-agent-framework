#!/usr/bin/env bash
# install-orchestrator/orchestrator.sh — runs the 12-gate pipeline.
set -euo pipefail
SRC=""; WORKSPACE=""; UPGRADE="0"; DRY_RUN="0"; JSON_OUT="0"
while [ $# -gt 0 ]; do
  case "$1" in
    --src) SRC="$2"; shift 2 ;;
    --workspace) WORKSPACE="$2"; shift 2 ;;
    --upgrade) UPGRADE="1"; shift ;;
    --dry-run) DRY_RUN="1"; shift ;;
    --json) JSON_OUT="1"; shift ;;
    -h|--help) sed -n '1,40p' "$(dirname "$0")/SKILL.md"; exit 0 ;;
    *) echo "orchestrator.sh: unknown arg: $1" >&2; exit 2 ;;
  esac
done
[ -z "$SRC" ] && { echo "orchestrator.sh: --src required" >&2; exit 2; }
[ -z "$WORKSPACE" ] && { echo "orchestrator.sh: --workspace required" >&2; exit 2; }
CN_SRC="$SRC" CN_WORKSPACE="$WORKSPACE" CN_UPGRADE="$UPGRADE" \
CN_DRY_RUN="$DRY_RUN" CN_JSON="$JSON_OUT" \
CN_REQUIRE_SIG="${CODENOOK_REQUIRE_SIG:-0}" \
CN_BUILTIN_DIR="$(cd "$(dirname "$0")/.." && pwd)" \
CN_CORE_VERSION="$(cat "$(dirname "$0")/../../../VERSION" 2>/dev/null | tr -d '[:space:]')" \
  exec python3 "$(dirname "$0")/_orchestrator.py"
