#!/usr/bin/env bash
set -euo pipefail
# Validates task before creation
INPUT=$(cat)
TASK_ID=$(echo "$INPUT" | jq -r '.task_id // ""')
TITLE=$(echo "$INPUT" | jq -r '.title // ""')

if [ -z "$TITLE" ]; then
  echo '{"block": true, "reason": "Task title cannot be empty"}'
  exit 0
fi

# Check duplicate
if [ -f ".agents/task-board.json" ]; then
  EXISTS=$(jq -r --arg tid "$TASK_ID" '[.tasks[] | select(.id == $tid)] | length' .agents/task-board.json 2>/dev/null || echo 0)
  if [ "$EXISTS" -gt 0 ]; then
    echo "{\"block\": true, \"reason\": \"Task $TASK_ID already exists\"}"
    exit 0
  fi
fi

echo '{"allow": true}'
