#!/usr/bin/env bash
set -euo pipefail
# Post-switch actions: log event, inject role context
INPUT=$(cat)
AGENT=$(echo "$INPUT" | jq -r '.agent // ""')

sql_escape() { echo "$1" | sed "s/'/''/g"; }

if [ -f ".agents/events.db" ]; then
  AGENT_ESC=$(sql_escape "$AGENT")
  if ! sqlite3 .agents/events.db "INSERT INTO events(timestamp,event_type,agent,detail) VALUES(strftime('%s','now'),'agent_switch','$AGENT_ESC','Switched to $AGENT_ESC');" 2>/dev/null; then
    echo "Warning: Failed to log agent_switch event" >&2
  fi
fi

echo '{"status": "ok"}'
