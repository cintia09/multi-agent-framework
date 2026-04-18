#!/usr/bin/env bash
# queue-runner/queue.sh — generic FIFO queue operations
set -euo pipefail

SUBCMD=""; QUEUE=""; PAYLOAD=""; FILTER=""; WORKSPACE="${CODENOOK_WORKSPACE:-}"; PAYLOAD_SET="0"

if [ $# -eq 0 ]; then
  echo "queue.sh: subcommand required (enqueue|dequeue|peek|list|size)" >&2
  exit 2
fi

SUBCMD="$1"; shift

while [ $# -gt 0 ]; do
  case "$1" in
    --queue)     QUEUE="$2"; shift 2 ;;
    --payload)   PAYLOAD="$2"; PAYLOAD_SET="1"; shift 2 ;;
    --filter)    FILTER="$2"; shift 2 ;;
    --workspace) WORKSPACE="$2"; shift 2 ;;
    -h|--help)
      sed -n '1,30p' "$(dirname "$0")/SKILL.md"; exit 0 ;;
    *) echo "queue.sh: unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [ -z "$QUEUE" ]; then
  echo "queue.sh: --queue is required" >&2
  exit 2
fi

if [ "$SUBCMD" = "enqueue" ] && [ "$PAYLOAD_SET" != "1" ]; then
  echo "queue.sh: enqueue requires --payload" >&2
  exit 2
fi

if [ -z "$WORKSPACE" ]; then
  cur="$(pwd)"
  while [ "$cur" != "/" ]; do
    if [ -d "$cur/.codenook" ]; then WORKSPACE="$cur"; break; fi
    cur="$(dirname "$cur")"
  done
  if [ -z "$WORKSPACE" ]; then
    echo "queue.sh: could not locate workspace (set --workspace or CODENOOK_WORKSPACE)" >&2
    exit 2
  fi
fi

if [ ! -d "$WORKSPACE" ]; then
  echo "queue.sh: workspace not found: $WORKSPACE" >&2
  exit 2
fi

PYTHONIOENCODING=utf-8 \
CN_SUBCMD="$SUBCMD" \
CN_QUEUE="$QUEUE" \
CN_PAYLOAD="$PAYLOAD" \
CN_FILTER="$FILTER" \
CN_WORKSPACE="$WORKSPACE" \
exec python3 "$(dirname "$0")/_queue.py"
