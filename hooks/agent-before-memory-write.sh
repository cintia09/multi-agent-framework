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
  .agents/memory/*) echo '{"allow": true}' ;;
  *) echo '{"block": true, "reason": "Memory must be written to .agents/memory/"}' ;;
esac
