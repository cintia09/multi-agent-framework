#!/usr/bin/env bash
set -euo pipefail
# Post-switch actions: log event, inject role context
INPUT=$(cat)
AGENT=$(echo "$INPUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('agent',''))")

# Log to events.db
if [ -f ".agents/events.db" ]; then
  sqlite3 .agents/events.db "INSERT INTO events(timestamp,event_type,agent,detail) VALUES(strftime('%s','now'),'agent_switch','$AGENT','Switched to $AGENT')"
fi

echo '{"status": "ok"}'
