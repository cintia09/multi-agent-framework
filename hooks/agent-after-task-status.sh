#!/usr/bin/env bash
set -euo pipefail
# After task status change: log event to events.db
INPUT=$(cat)
TASK_ID=$(echo "$INPUT" | jq -r '.task_id // ""')
NEW_STATUS=$(echo "$INPUT" | jq -r '.new_status // ""')
AGENT=$(echo "$INPUT" | jq -r '.agent // ""')
CWD=$(echo "$INPUT" | jq -r '.cwd // "."')
AGENTS_DIR="$CWD/.agents"

[ -z "$TASK_ID" ] || [ "$TASK_ID" = "null" ] && { echo '{"status": "ok"}'; exit 0; }

sql_escape() { echo "$1" | sed "s/'/''/g"; }

if [ -f "$AGENTS_DIR/events.db" ]; then
  TASK_ESC=$(sql_escape "$TASK_ID")
  STATUS_ESC=$(sql_escape "$NEW_STATUS")
  AGENT_ESC=$(sql_escape "$AGENT")
  sqlite3 "$AGENTS_DIR/events.db" "INSERT INTO events(timestamp,event_type,agent,task_id,detail) VALUES(strftime('%s','now'),'task_status_change','$AGENT_ESC','$TASK_ESC','Status changed to $STATUS_ESC');" 2>/dev/null || true
fi

echo '{"status": "ok"}'
