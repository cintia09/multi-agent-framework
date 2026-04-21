#!/usr/bin/env bash
# hitl-adapter/terminal.sh — non-interactive HITL queue manipulation.
#
# Subcommands:
#   list  [--json]                                       — pending entries
#   decide --id <id> --decision <approve|reject|needs_changes>
#          --reviewer <name> [--comment "..."]           — atomically resolve
#   show  --id <id>                                       — cat context file
#
# Each invocation does exactly one thing (terminal-mode design). An
# interactive REPL is out of scope for M4 — see SKILL.md "M6+ scope".
set -euo pipefail

SUBCMD="${1:-}"
[ $# -ge 1 ] && shift || true

ID=""; DECISION=""; REVIEWER=""; COMMENT=""; WORKSPACE="${CODENOOK_WORKSPACE:-}"
JSON="0"; RAW="0"

while [ $# -gt 0 ]; do
  case "$1" in
    --id)        ID="$2"; shift 2 ;;
    --decision)  DECISION="$2"; shift 2 ;;
    --reviewer)  REVIEWER="$2"; shift 2 ;;
    --comment)   COMMENT="$2"; shift 2 ;;
    --workspace) WORKSPACE="$2"; shift 2 ;;
    --json)      JSON="1"; shift ;;
    --raw)       RAW="1"; shift ;;
    -h|--help)
      sed -n '1,40p' "$(dirname "$0")/SKILL.md"; exit 0 ;;
    *) echo "terminal.sh: unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [ -z "$WORKSPACE" ]; then
  cur="$(pwd)"
  while [ "$cur" != "/" ]; do
    if [ -d "$cur/.codenook" ]; then WORKSPACE="$cur"; break; fi
    cur="$(dirname "$cur")"
  done
  if [ -z "$WORKSPACE" ]; then
    echo "terminal.sh: could not locate workspace" >&2; exit 2
  fi
fi
[ -d "$WORKSPACE" ] || { echo "terminal.sh: workspace not found: $WORKSPACE" >&2; exit 2; }

case "$SUBCMD" in
  list|decide|show) ;;
  "") echo "terminal.sh: subcommand required (list|decide|show)" >&2; exit 2 ;;
  *)  echo "terminal.sh: unknown subcommand: $SUBCMD" >&2; exit 2 ;;
esac

PYTHONIOENCODING=utf-8 \
CN_SUBCMD="$SUBCMD" \
CN_ID="$ID" \
CN_DECISION="$DECISION" \
CN_REVIEWER="$REVIEWER" \
CN_COMMENT="$COMMENT" \
CN_WORKSPACE="$WORKSPACE" \
CN_JSON="$JSON" \
CN_RAW="$RAW" \
exec python3 "$(dirname "$0")/_hitl.py"
