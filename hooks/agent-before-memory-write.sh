#!/usr/bin/env bash
set -euo pipefail
# Validates memory before writing
INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.file_path // ""')
CONTENT=$(echo "$INPUT" | jq -r '.content // ""')

if [ -z "$CONTENT" ]; then
  echo '{"block": true, "reason": "Memory content cannot be empty"}'
  exit 0
fi

case "$FILE_PATH" in
  .agents/memory/*)
    # Block path traversal
    if echo "$FILE_PATH" | grep -qF '..'; then
      echo '{"block": true, "reason": "Path traversal not allowed in memory path"}'
    else
      echo '{"allow": true}'
    fi
    ;;
  *) echo '{"block": true, "reason": "Memory must be written to .agents/memory/"}' ;;
esac
