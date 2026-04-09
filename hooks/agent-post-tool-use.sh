#!/usr/bin/env bash
# Multi-Agent Framework: Post-Tool-Use Hook
# Logs tool execution results to events.db for audit trail.
# Detects task-board changes and triggers: auto-dispatch, FSM validation, memory capture.

set -euo pipefail
HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.toolName')
TOOL_ARGS=$(echo "$INPUT" | jq -r '.toolArgs')
RESULT_TYPE=$(echo "$INPUT" | jq -r '.toolResult.resultType')
CWD=$(echo "$INPUT" | jq -r '.cwd')
# Validate TIMESTAMP is numeric to prevent SQL injection
TIMESTAMP_RAW=$(echo "$INPUT" | jq -r '.timestamp')
TIMESTAMP=$(echo "$TIMESTAMP_RAW" | grep -oE '^[0-9]+$' || date +%s)

AGENTS_DIR="$CWD/.agents"
EVENTS_DB="$AGENTS_DIR/events.db"
SNAPSHOT="$AGENTS_DIR/runtime/.task-board-snapshot.json"

# Only log if agent framework is initialized and events.db exists
[ -f "$EVENTS_DB" ] || exit 0

# Shared utilities
sql_escape() { echo "$1" | sed "s/'/''/g"; }

ACTIVE_AGENT="none"
ACTIVE_FILE="$AGENTS_DIR/runtime/active-agent"
[ -f "$ACTIVE_FILE" ] && ACTIVE_AGENT=$(sql_escape "$(cat "$ACTIVE_FILE")")

# Escape all input variables
TOOL_NAME_ESC=$(sql_escape "$TOOL_NAME")
RESULT_TYPE_ESC=$(sql_escape "$RESULT_TYPE")
TOOL_ARGS_ESC=$(echo "$TOOL_ARGS" | head -c 500 | sed "s/'/''/g")

# Log every tool use to events.db
sqlite3 "$EVENTS_DB" "INSERT INTO events (timestamp, event_type, agent, tool_name, detail) VALUES ($TIMESTAMP, 'tool_use', '$ACTIVE_AGENT', '$TOOL_NAME_ESC', '{\"result\":\"$RESULT_TYPE_ESC\",\"args\":\"$TOOL_ARGS_ESC\"}');"

# Detect task-board writes
if [ "$TOOL_NAME" = "edit" ] || [ "$TOOL_NAME" = "create" ]; then
  FILE_PATH=$(echo "$TOOL_ARGS" | jq -r '.path // empty' 2>/dev/null)
  if [[ "$FILE_PATH" =~ task-board\.json ]]; then
    sqlite3 "$EVENTS_DB" "INSERT INTO events (timestamp, event_type, agent, detail) VALUES ($TIMESTAMP, 'task_board_write', '$ACTIVE_AGENT', '{\"tool\":\"$TOOL_NAME_ESC\"}');"

    # Cache file content with validation to avoid processing corrupted JSON
    TASK_BOARD_CACHE=""
    if [ -f "$AGENTS_DIR/task-board.json" ]; then
      if jq empty "$AGENTS_DIR/task-board.json" 2>/dev/null; then
        TASK_BOARD_CACHE=$(cat "$AGENTS_DIR/task-board.json")
      else
        echo "⚠️ [ERROR] task-board.json is corrupted, skipping FSM checks" >&2
        TASK_BOARD_CACHE='{"tasks":[]}'
      fi
    fi

    # Source and run modules
    # shellcheck source=lib/auto-dispatch.sh
    source "$HOOK_DIR/lib/auto-dispatch.sh"
    run_auto_dispatch

    # shellcheck source=lib/fsm-validate.sh
    source "$HOOK_DIR/lib/fsm-validate.sh"
    run_fsm_validation

    # shellcheck source=lib/memory-capture.sh
    source "$HOOK_DIR/lib/memory-capture.sh"
    run_memory_capture

    # Update snapshot for next comparison
    if [ -n "$TASK_BOARD_CACHE" ]; then
      cp "$AGENTS_DIR/task-board.json" "$SNAPSHOT" 2>/dev/null || true
    fi
  fi
fi

# Detect state.json writes (agent state transitions)
if [ "$TOOL_NAME" = "edit" ] || [ "$TOOL_NAME" = "create" ]; then
  FILE_PATH=$(echo "$TOOL_ARGS" | jq -r '.path // empty' 2>/dev/null)
  if [[ "$FILE_PATH" =~ state\.json ]]; then
    AGENT_FROM_PATH=$(echo "$FILE_PATH" | sed -n 's|.*runtime/\([^/]*\).*|\1|p')
    AGENT_PATH_ESC=$(sql_escape "${AGENT_FROM_PATH:-unknown}")
    sqlite3 "$EVENTS_DB" "INSERT INTO events (timestamp, event_type, agent, detail) VALUES ($TIMESTAMP, 'state_change', '$AGENT_PATH_ESC', '{\"tool\":\"$TOOL_NAME_ESC\"}');"
  fi
fi
