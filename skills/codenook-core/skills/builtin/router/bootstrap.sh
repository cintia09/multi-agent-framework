#!/usr/bin/env bash
# router/bootstrap.sh — first-agent self-bootstrap loader.
# See SKILL.md for full contract.
set -euo pipefail

USER_INPUT=""; USER_INPUT_SET="0"
WORKSPACE="${CODENOOK_WORKSPACE:-}"
TASK=""
JSON_OUT="0"

while [ $# -gt 0 ]; do
  case "$1" in
    --user-input) USER_INPUT="$2"; USER_INPUT_SET="1"; shift 2 ;;
    --workspace)  WORKSPACE="$2"; shift 2 ;;
    --task)       TASK="$2"; shift 2 ;;
    --json)       JSON_OUT="1"; shift ;;
    -h|--help)    sed -n '1,40p' "$(dirname "$0")/SKILL.md"; exit 0 ;;
    *) echo "bootstrap.sh: unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [ "$USER_INPUT_SET" != "1" ]; then
  echo "bootstrap.sh: --user-input is required" >&2
  exit 2
fi

if [ -z "$WORKSPACE" ]; then
  cur="$(pwd)"
  while [ "$cur" != "/" ]; do
    if [ -d "$cur/.codenook" ]; then WORKSPACE="$cur"; break; fi
    cur="$(dirname "$cur")"
  done
fi
if [ -z "$WORKSPACE" ] || [ ! -d "$WORKSPACE/.codenook" ]; then
  echo "bootstrap.sh: workspace not located (set --workspace)" >&2
  exit 2
fi

# Default core root: two levels up from this script (skills/builtin/router/).
DEFAULT_CORE="$(cd "$(dirname "$0")/../../.." && pwd)"
CORE_ROOT_RESOLVED="${CN_CORE_ROOT:-$DEFAULT_CORE}"

PYTHONIOENCODING=utf-8 \
CN_USER_INPUT="$USER_INPUT" \
CN_WORKSPACE="$WORKSPACE" \
CN_TASK="$TASK" \
CN_JSON="$JSON_OUT" \
CN_CORE_ROOT="$CORE_ROOT_RESOLVED" \
CN_DEFAULT_CORE="$DEFAULT_CORE" \
exec python3 "$(dirname "$0")/_bootstrap.py"
