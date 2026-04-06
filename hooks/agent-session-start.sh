#!/bin/bash
# Multi-Agent Framework: Session Start Hook
# Checks agent state and pending items when a session begins.
# Output is ignored by the AI tool — we only log to events.db.

set -e
INPUT=$(cat)
CWD=$(echo "$INPUT" | jq -r '.cwd')
SOURCE=$(echo "$INPUT" | jq -r '.source')
TIMESTAMP=$(echo "$INPUT" | jq -r '.timestamp')

AGENTS_DIR="$CWD/.agents"

# Only act if this project has been initialized with the agent framework
[ -d "$AGENTS_DIR/runtime" ] || exit 0

EVENTS_DB="$AGENTS_DIR/events.db"

# Initialize events.db if it doesn't exist
if [ ! -f "$EVENTS_DB" ]; then
  sqlite3 "$EVENTS_DB" <<'SQL'
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp INTEGER NOT NULL,
  event_type TEXT NOT NULL,
  agent TEXT,
  task_id TEXT,
  tool_name TEXT,
  detail TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_agent ON events(agent);
CREATE INDEX IF NOT EXISTS idx_events_task ON events(task_id);
SQL
fi

# Read active agent (if any)
ACTIVE_AGENT=""
ACTIVE_FILE="$AGENTS_DIR/runtime/active-agent"
[ -f "$ACTIVE_FILE" ] && ACTIVE_AGENT=$(cat "$ACTIVE_FILE")

# Log session start event
sqlite3 "$EVENTS_DB" "INSERT INTO events (timestamp, event_type, agent, detail) VALUES ($TIMESTAMP, 'session_start', '${ACTIVE_AGENT:-none}', '{\"source\":\"$SOURCE\"}');"

# Count pending messages across all agents
TOTAL_MSGS=0
for inbox in "$AGENTS_DIR"/runtime/*/inbox.json; do
  [ -f "$inbox" ] || continue
  COUNT=$(jq '.messages | length' "$inbox" 2>/dev/null || echo 0)
  TOTAL_MSGS=$((TOTAL_MSGS + COUNT))
done

# Count active tasks
ACTIVE_TASKS=0
if [ -f "$AGENTS_DIR/task-board.json" ]; then
  ACTIVE_TASKS=$(jq '[.tasks[] | select(.status != "accepted" and .status != "blocked")] | length' "$AGENTS_DIR/task-board.json" 2>/dev/null || echo 0)
fi

# Log summary (stderr goes to the tool log, not to LLM)
if [ "$TOTAL_MSGS" -gt 0 ] || [ "$ACTIVE_TASKS" -gt 0 ]; then
  echo "Agent Framework: ${TOTAL_MSGS} pending messages, ${ACTIVE_TASKS} active tasks" >&2
fi

# Staleness check (G4) — warn about inactive tasks/agents
HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
STALE_OUTPUT=$("$HOOK_DIR/agent-staleness-check.sh" "$AGENTS_DIR" 24 2>/dev/null || true)
if echo "$STALE_OUTPUT" | grep -q "⚠️"; then
  echo "$STALE_OUTPUT" >&2
fi
