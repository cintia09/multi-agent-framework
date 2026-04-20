#!/usr/bin/env bash
# hitl-adapter/html.sh — render a pending HITL entry as a self-contained
# .html file for human review. Decision submission still goes through
# `terminal.sh decide` (or the `codenook decide` wrapper). See SKILL.md.
#
# Usage:
#   html.sh render --id <hitl-entry-id> [--out <path>] [--workspace <dir>]
set -euo pipefail

SUBCMD="${1:-}"
[ $# -ge 1 ] && shift || true

ID=""; OUT=""; WORKSPACE="${CODENOOK_WORKSPACE:-}"

while [ $# -gt 0 ]; do
  case "$1" in
    --id)        ID="$2"; shift 2 ;;
    --out)       OUT="$2"; shift 2 ;;
    --workspace) WORKSPACE="$2"; shift 2 ;;
    -h|--help)
      sed -n '1,12p' "$0"; exit 0 ;;
    *) echo "html.sh: unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [ -z "$WORKSPACE" ]; then
  cur="$(pwd)"
  while [ "$cur" != "/" ]; do
    if [ -d "$cur/.codenook" ]; then WORKSPACE="$cur"; break; fi
    cur="$(dirname "$cur")"
  done
  if [ -z "$WORKSPACE" ]; then
    echo "html.sh: cannot find .codenook upwards; pass --workspace" >&2
    exit 2
  fi
fi

case "$SUBCMD" in
  render)
    CN_SUBCMD=render-html CN_WORKSPACE="$WORKSPACE" CN_ID="$ID" CN_OUT="$OUT" \
      python3 "$(dirname "$0")/_hitl.py"
    ;;
  ""|-h|--help)
    sed -n '1,12p' "$0"; exit 0 ;;
  *)
    echo "html.sh: unknown subcommand: $SUBCMD" >&2; exit 2 ;;
esac
