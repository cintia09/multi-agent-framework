#!/usr/bin/env bash
set -euo pipefail
# Post-switch actions: log event, inject role context, suggest model
INPUT=$(cat)
AGENT=$(echo "$INPUT" | jq -r '.agent // ""')
CWD=$(echo "$INPUT" | jq -r '.cwd // "."')
AGENTS_DIR="$CWD/.agents"

sql_escape() { echo "$1" | sed "s/'/''/g"; }

# Log switch event
if [ -f "$AGENTS_DIR/events.db" ]; then
  AGENT_ESC=$(sql_escape "$AGENT")
  sqlite3 "$AGENTS_DIR/events.db" "INSERT INTO events(timestamp,event_type,agent,detail) VALUES(strftime('%s','now'),'agent_switch','$AGENT_ESC','Switched to $AGENT_ESC');" 2>/dev/null || true
fi

# Model resolution: check agent profile for configured model
MODEL=""
MODEL_HINT=""
for agents_dir in "${HOME}/.claude/agents" "${HOME}/.copilot/agents"; do
  PROFILE="${agents_dir}/${AGENT}.agent.md"
  if [ -f "$PROFILE" ]; then
    MODEL=$(sed -n '/^---$/,/^---$/p' "$PROFILE" | grep '^model:' | head -1 | sed 's/^model: *//; s/^"//; s/"$//')
    MODEL_HINT=$(sed -n '/^---$/,/^---$/p' "$PROFILE" | grep '^model_hint:' | head -1 | sed 's/^model_hint: *//; s/^"//; s/"$//')
    break
  fi
done

# Build response with model suggestion
if [ -n "$MODEL" ]; then
  echo "{\"status\": \"ok\", \"message\": \"📌 Agent ${AGENT} configured model: ${MODEL}. Use /model ${MODEL} to switch.\"}"
elif [ -n "$MODEL_HINT" ]; then
  echo "{\"status\": \"ok\", \"message\": \"💡 Agent ${AGENT} model hint: ${MODEL_HINT}\"}"
else
  echo '{"status": "ok"}'
fi
