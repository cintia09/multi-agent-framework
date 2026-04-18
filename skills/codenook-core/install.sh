#!/usr/bin/env bash
# install.sh — top-level CodeNook plugin install CLI (M2).
#
# Thin wrapper around the install-orchestrator builtin skill. See
# skills/builtin/install-orchestrator/SKILL.md for full semantics.
#
# Usage:
#   install.sh --src <tarball|dir> [--upgrade] [--dry-run]
#              [--workspace <dir>] [--json]
#
# Exit codes:
#   0  installed (or dry-run pass)
#   1  any gate failed
#   2  usage / IO error
#   3  already installed (without --upgrade)

set -euo pipefail

SRC=""; WORKSPACE=""; UPGRADE=""; DRY_RUN=""; JSON_OUT=""
SHOWN_USAGE=0

usage() {
  cat >&2 <<'USAGE'
install.sh — install a CodeNook plugin into a workspace.

  --src <tarball|dir>   plugin source (.tar.gz / .tgz or directory)
  --workspace <dir>     workspace root (default: $PWD)
  --upgrade             allow installing over an existing plugin id
  --dry-run             run all gates but do not commit
  --json                emit machine-readable summary on stdout

Exit: 0 ok | 1 gate failure | 2 usage | 3 already installed (no --upgrade)
USAGE
  SHOWN_USAGE=1
}

while [ $# -gt 0 ]; do
  case "$1" in
    --src) SRC="$2"; shift 2 ;;
    --workspace) WORKSPACE="$2"; shift 2 ;;
    --upgrade) UPGRADE="--upgrade"; shift ;;
    --dry-run) DRY_RUN="--dry-run"; shift ;;
    --json) JSON_OUT="--json"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "install.sh: unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

if [ -z "$SRC" ]; then
  echo "install.sh: --src is required" >&2
  usage
  exit 2
fi
if [ -z "$WORKSPACE" ]; then
  WORKSPACE="$PWD"
fi
if [ ! -d "$WORKSPACE" ]; then
  echo "install.sh: --workspace must be an existing directory: $WORKSPACE" >&2
  exit 2
fi

CORE_ROOT="$(cd "$(dirname "$0")" && pwd)"
ORCH="$CORE_ROOT/skills/builtin/install-orchestrator/orchestrator.sh"

exec "$ORCH" --src "$SRC" --workspace "$WORKSPACE" \
  ${UPGRADE} ${DRY_RUN} ${JSON_OUT}
