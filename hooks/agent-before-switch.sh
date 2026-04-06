#!/usr/bin/env bash
set -euo pipefail
# Validates agent switch is allowed
# Input: JSON on stdin with {from_agent, to_agent, task_id}
# Output: JSON {allow:true} or {block:true, reason:"..."}

INPUT=$(cat)
FROM=$(echo "$INPUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('from_agent',''))")
TO=$(echo "$INPUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('to_agent',''))")

# Default: allow all switches
echo '{"allow": true}'
