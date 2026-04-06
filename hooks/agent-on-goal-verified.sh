#!/usr/bin/env bash
set -euo pipefail
# When a goal is verified: update progress tracking
INPUT=$(cat)
TASK_ID=$(echo "$INPUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('task_id',''))")

if [ -f ".agents/events.db" ]; then
  sqlite3 .agents/events.db "INSERT INTO events(timestamp,event_type,task_id,detail) VALUES(strftime('%s','now'),'goal_verified','$TASK_ID','Goal verified')"
fi

echo '{"status": "ok"}'
