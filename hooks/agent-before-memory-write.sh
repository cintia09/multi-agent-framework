#!/usr/bin/env bash
set -euo pipefail
# Validates memory before writing
# Checks: non-empty content, valid file path
INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('file_path',''))")
CONTENT=$(echo "$INPUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('content',''))")

if [ -z "$CONTENT" ]; then
  echo '{"block": true, "reason": "Memory content cannot be empty"}'
  exit 0
fi

# Validate path is within .agents/memory/
case "$FILE_PATH" in
  .agents/memory/*) echo '{"allow": true}' ;;
  *) echo '{"block": true, "reason": "Memory must be written to .agents/memory/"}' ;;
esac
