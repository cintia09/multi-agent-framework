#!/usr/bin/env bash
# skill-resolve/resolve-skill.sh — 4-tier skill lookup. See SKILL.md.
set -euo pipefail

NAME=""; PLUGIN=""; WORKSPACE=""

while [ $# -gt 0 ]; do
  case "$1" in
    --name)      NAME="$2"; shift 2 ;;
    --plugin)    PLUGIN="$2"; shift 2 ;;
    --workspace) WORKSPACE="$2"; shift 2 ;;
    --json)      shift ;;  # JSON is the only output mode; flag is a no-op
    -h|--help)
      sed -n '1,40p' "$(dirname "$0")/SKILL.md"; exit 0 ;;
    *) echo "resolve-skill.sh: unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [ -z "$NAME" ] || [ -z "$PLUGIN" ] || [ -z "$WORKSPACE" ]; then
  echo "resolve-skill.sh: --name, --plugin, --workspace are required" >&2
  exit 2
fi

# Default core dir = parent of skills/builtin/ that contains this script.
# Use `pwd -P` (physical path) so on macOS, where /var → /private/var via
# a symlink, Path.resolve() in Python compares against the same path.
if [ -z "${CODENOOK_CORE_DIR:-}" ]; then
  here="$(cd "$(dirname "$0")" && pwd -P)"
  CODENOOK_CORE_DIR="$(cd "$here/../../.." && pwd -P)"
fi

PYTHONIOENCODING=utf-8 \
CN_NAME="$NAME" \
CN_PLUGIN="$PLUGIN" \
CN_WORKSPACE="$WORKSPACE" \
CN_CORE_DIR="$CODENOOK_CORE_DIR" \
exec python3 "$(dirname "$0")/_resolve_skill.py"
