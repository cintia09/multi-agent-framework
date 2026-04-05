#!/bin/bash
# Multi-Agent Framework: Post-Tool-Use Hook
# Logs tool execution results to events.db for audit trail.
# Detects task-board changes and logs state transitions.

set -e
INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.toolName')
TOOL_ARGS=$(echo "$INPUT" | jq -r '.toolArgs')
RESULT_TYPE=$(echo "$INPUT" | jq -r '.toolResult.resultType')
CWD=$(echo "$INPUT" | jq -r '.cwd')
TIMESTAMP=$(echo "$INPUT" | jq -r '.timestamp')

AGENTS_DIR="$CWD/.agents"
EVENTS_DB="$AGENTS_DIR/events.db"

# Only log if agent framework is initialized and events.db exists
[ -f "$EVENTS_DB" ] || exit 0

# Read active agent
ACTIVE_AGENT="none"
ACTIVE_FILE="$AGENTS_DIR/runtime/active-agent"
[ -f "$ACTIVE_FILE" ] && ACTIVE_AGENT=$(cat "$ACTIVE_FILE")

# Escape single quotes for SQL
TOOL_ARGS_ESCAPED=$(echo "$TOOL_ARGS" | sed "s/'/''/g" | head -c 500)

# Log every tool use to events.db
sqlite3 "$EVENTS_DB" "INSERT INTO events (timestamp, event_type, agent, tool_name, detail) VALUES ($TIMESTAMP, 'tool_use', '$ACTIVE_AGENT', '$TOOL_NAME', '{\"result\":\"$RESULT_TYPE\",\"args\":\"$TOOL_ARGS_ESCAPED\"}');"

# Detect task-board writes
if [ "$TOOL_NAME" = "edit" ] || [ "$TOOL_NAME" = "create" ]; then
  FILE_PATH=$(echo "$TOOL_ARGS" | jq -r '.path // empty' 2>/dev/null)
  if [[ "$FILE_PATH" =~ task-board\.json ]]; then
    sqlite3 "$EVENTS_DB" "INSERT INTO events (timestamp, event_type, agent, detail) VALUES ($TIMESTAMP, 'task_board_write', '$ACTIVE_AGENT', '{\"tool\":\"$TOOL_NAME\"}');"

    # --- AUTO-DISPATCH (G2) ---
    # When task-board.json changes, send messages to the next agent in FSM
    if [ -f "$AGENTS_DIR/task-board.json" ]; then
      jq -c '.tasks[]' "$AGENTS_DIR/task-board.json" 2>/dev/null | while read -r TASK; do
        TASK_ID=$(echo "$TASK" | jq -r '.id')
        STATUS=$(echo "$TASK" | jq -r '.status')
        TITLE=$(echo "$TASK" | jq -r '.title')

        # Map status to target agent (only dispatch on "arrival" statuses)
        case "$STATUS" in
          created)    TARGET="designer" ;;
          reviewing)  TARGET="reviewer" ;;
          testing)    TARGET="tester" ;;
          accepting)  TARGET="acceptor" ;;
          *)          TARGET="" ;;
        esac

        [ -z "$TARGET" ] && continue

        TARGET_INBOX="$AGENTS_DIR/runtime/$TARGET/inbox.json"
        [ -f "$TARGET_INBOX" ] || continue

        # Duplicate prevention: skip if message for same task+status already exists
        EXISTING=$(jq --arg tid "$TASK_ID" --arg status "$STATUS" \
          '[.messages[] | select(.task_id == $tid and (.content | contains($status)))] | length' \
          "$TARGET_INBOX" 2>/dev/null || echo 0)
        [ "$EXISTING" -gt 0 ] && continue

        MSG_ID="MSG-auto-${TASK_ID}-${STATUS}"
        NOW_ISO=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

        jq --arg id "$MSG_ID" --arg from "$ACTIVE_AGENT" --arg to "$TARGET" \
           --arg tid "$TASK_ID" --arg status "$STATUS" --arg title "$TITLE" \
           --arg ts "$NOW_ISO" \
           '.messages += [{"id":$id,"from":$from,"to":$to,"type":"task_update","task_id":$tid,"content":"Task \($tid) [\($title)] status changed to \($status). Please process.","timestamp":$ts,"read":false}]' \
           "$TARGET_INBOX" > "${TARGET_INBOX}.tmp" && mv "${TARGET_INBOX}.tmp" "$TARGET_INBOX"

        sqlite3 "$EVENTS_DB" "INSERT INTO events (timestamp, event_type, agent, task_id, detail) VALUES ($TIMESTAMP, 'auto_dispatch', '$TARGET', '$TASK_ID', '{\"from_status\":\"$STATUS\",\"from_agent\":\"$ACTIVE_AGENT\"}');" 2>/dev/null || true
      done
    fi
  fi
fi

# Detect state.json writes (agent state transitions)
if [ "$TOOL_NAME" = "edit" ] || [ "$TOOL_NAME" = "create" ]; then
  FILE_PATH=$(echo "$TOOL_ARGS" | jq -r '.path // empty' 2>/dev/null)
  if [[ "$FILE_PATH" =~ state\.json ]]; then
    AGENT_FROM_PATH=$(echo "$FILE_PATH" | grep -oP 'runtime/\K[^/]+' || true)
    sqlite3 "$EVENTS_DB" "INSERT INTO events (timestamp, event_type, agent, detail) VALUES ($TIMESTAMP, 'state_change', '${AGENT_FROM_PATH:-unknown}', '{\"tool\":\"$TOOL_NAME\"}');"
  fi
fi
