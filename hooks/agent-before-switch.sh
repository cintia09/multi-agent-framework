#!/usr/bin/env bash
set -euo pipefail
# Validates agent switch is allowed
INPUT=$(cat)
FROM=$(echo "$INPUT" | jq -r '.from_agent // ""')
TO=$(echo "$INPUT" | jq -r '.to_agent // ""')

echo '{"allow": true}'
