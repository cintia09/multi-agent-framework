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

# Inbox summary: check for unread messages
INBOX_MSG=""
INBOX_FILE="$AGENTS_DIR/runtime/$AGENT/inbox.json"
if [ -f "$INBOX_FILE" ]; then
  UNREAD=$(jq '[.messages[] | select(.read == false)] | length' "$INBOX_FILE" 2>/dev/null || echo 0)
  URGENT=$(jq '[.messages[] | select(.read == false and .priority == "urgent")] | length' "$INBOX_FILE" 2>/dev/null || echo 0)
  if [ "$URGENT" -gt 0 ]; then
    INBOX_MSG="🔴 ${UNREAD} unread messages (${URGENT} URGENT). Check inbox first!"
  elif [ "$UNREAD" -gt 0 ]; then
    INBOX_MSG="📬 ${UNREAD} unread messages in inbox."
  fi
fi

# Document pipeline: list available input documents for this agent
DOC_MSG=""
if [ -f "$AGENTS_DIR/task-board.json" ]; then
  # Find current task for this agent
  CURRENT_TASK=$(jq -r --arg agent "$AGENT" \
    '[.tasks[] | select((.assigned_to // "") == $agent and .status != "accepted" and .status != "blocked")] | .[0] | .id // empty' \
    "$AGENTS_DIR/task-board.json" 2>/dev/null)
  if [ -n "$CURRENT_TASK" ]; then
    DOCS_DIR="$AGENTS_DIR/docs/$CURRENT_TASK"
    if [ -d "$DOCS_DIR" ]; then
      DOC_LIST=$(find "$DOCS_DIR" -maxdepth 1 -name "*.md" -type f -exec basename {} \; 2>/dev/null | sort | tr '\n' ',' | sed 's/,$//')
      [ -n "$DOC_LIST" ] && DOC_MSG="📄 Task ${CURRENT_TASK} docs: ${DOC_LIST}. Read input docs before starting."
    fi
  fi
fi

# Build response with model suggestion + inbox + document info
if [ -n "$MODEL" ]; then
  MSG="📌 Agent ${AGENT} configured model: ${MODEL}. Use /model ${MODEL} to switch."
  [ -n "$INBOX_MSG" ] && MSG="${MSG} ${INBOX_MSG}"
  [ -n "$DOC_MSG" ] && MSG="${MSG} ${DOC_MSG}"
  jq -n --arg msg "$MSG" '{status:"ok",message:$msg}'
elif [ -n "$MODEL_HINT" ]; then
  MSG="💡 Agent ${AGENT} model hint: ${MODEL_HINT}"
  [ -n "$INBOX_MSG" ] && MSG="${MSG} ${INBOX_MSG}"
  [ -n "$DOC_MSG" ] && MSG="${MSG} ${DOC_MSG}"
  jq -n --arg msg "$MSG" '{status:"ok",message:$msg}'
else
  COMBINED=""
  [ -n "$INBOX_MSG" ] && COMBINED="$INBOX_MSG"
  [ -n "$DOC_MSG" ] && COMBINED="${COMBINED:+$COMBINED }${DOC_MSG}"
  if [ -n "$COMBINED" ]; then
    jq -n --arg msg "$COMBINED" '{status:"ok",message:$msg}'
  else
    echo '{"status": "ok"}'
  fi
fi
