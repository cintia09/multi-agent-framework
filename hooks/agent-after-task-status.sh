#!/usr/bin/env bash
set -euo pipefail
# After task status change: log event, trigger memory capture, notify
INPUT=$(cat)
TASK_ID=$(echo "$INPUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('task_id',''))")
NEW_STATUS=$(echo "$INPUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('new_status',''))")
AGENT=$(echo "$INPUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('agent',''))")

# Log event
if [ -f ".agents/events.db" ]; then
  sqlite3 .agents/events.db "INSERT INTO events(timestamp,event_type,agent,task_id,detail) VALUES(strftime('%s','now'),'task_status_change','$AGENT','$TASK_ID','Status changed to $NEW_STATUS')"
fi

# Trigger memory capture on acceptance
if [ "$NEW_STATUS" = "accepted" ]; then
  if [ -f ".agents/scripts/memory-index.sh" ]; then
    bash .agents/scripts/memory-index.sh 2>/dev/null || true
  elif [ -f "scripts/memory-index.sh" ]; then
    bash scripts/memory-index.sh 2>/dev/null || true
  fi
fi

echo '{"status": "ok"}'
