#!/usr/bin/env bash
set -euo pipefail
# After task status change: log event to events.db
INPUT=$(cat)
TASK_ID=$(echo "$INPUT" | jq -r '.task_id // ""')
NEW_STATUS=$(echo "$INPUT" | jq -r '.new_status // ""')
AGENT=$(echo "$INPUT" | jq -r '.agent // ""')
AGENTS_DIR="${CWD:-.}/.agents"

sql_escape() { echo "$1" | sed "s/'/''/g"; }

if [ -f "$AGENTS_DIR/events.db" ]; then
  TASK_ESC=$(sql_escape "$TASK_ID")
  STATUS_ESC=$(sql_escape "$NEW_STATUS")
  AGENT_ESC=$(sql_escape "$AGENT")
  if ! sqlite3 "$AGENTS_DIR/events.db" "INSERT INTO events(timestamp,event_type,agent,task_id,detail) VALUES(strftime('%s','now'),'task_status_change','$AGENT_ESC','$TASK_ESC','Status changed to $STATUS_ESC');" 2>/dev/null; then
    echo "Warning: Failed to log task_status_change event" >&2
  fi
fi

echo '{"status": "ok"}'
