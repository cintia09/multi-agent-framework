#!/usr/bin/env bash
set -euo pipefail
# When a goal is verified: update progress tracking
INPUT=$(cat)
TASK_ID=$(echo "$INPUT" | jq -r '.task_id // ""')

sql_escape() { echo "$1" | sed "s/'/''/g"; }

if [ -f ".agents/events.db" ]; then
  TASK_ID_ESC=$(sql_escape "$TASK_ID")
  if ! sqlite3 .agents/events.db "INSERT INTO events(timestamp,event_type,task_id,detail) VALUES(strftime('%s','now'),'goal_verified','$TASK_ID_ESC','Goal verified');" 2>/dev/null; then
    echo "Warning: Failed to log goal_verified event" >&2
  fi
fi

echo '{"status": "ok"}'
