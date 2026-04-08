#!/usr/bin/env bash
set -euo pipefail
# Validates task before creation
# Checks: title not empty, no duplicate IDs
INPUT=$(cat)
TASK_ID=$(echo "$INPUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('task_id',''))")
TITLE=$(echo "$INPUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('title',''))")

if [ -z "$TITLE" ]; then
  echo '{"block": true, "reason": "Task title cannot be empty"}'
  exit 0
fi

# Check duplicate
if [ -f ".agents/task-board.json" ]; then
  EXISTS=$(TASK_ID="$TASK_ID" python3 -c "import json,os; d=json.load(open('.agents/task-board.json')); print('yes' if any(t['id']==os.environ['TASK_ID'] for t in d['tasks']) else 'no')")
  if [ "$EXISTS" = "yes" ]; then
    echo "{\"block\": true, \"reason\": \"Task $TASK_ID already exists\"}"
    exit 0
  fi
fi

echo '{"allow": true}'
