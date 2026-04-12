#!/usr/bin/env bash
# HITL Verification Gate — programmatic enforcement
# Checks that HITL approval exists before allowing status advancement.
#
# Usage: hitl-verify.sh <task_id> <current_status>
# Exit 0 = transition allowed
# Exit 1 = HITL required but not completed (blocks transition)

set -euo pipefail

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 is required for HITL verification" >&2
  exit 1
fi

PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
if [ -d "$PROJECT_ROOT/.github/codenook" ]; then
  CODENOOK_DIR="$PROJECT_ROOT/.github/codenook"
elif [ -d "$PROJECT_ROOT/.claude/codenook" ]; then
  CODENOOK_DIR="$PROJECT_ROOT/.claude/codenook"
else
  echo "ERROR: codenook directory not found" >&2
  exit 1
fi

TASK_BOARD="$CODENOOK_DIR/task-board.json"
CONFIG="$CODENOOK_DIR/config.json"

task_id="${1:-}"
current_status="${2:-}"

if [ -z "$task_id" ] || [ -z "$current_status" ]; then
  echo "Usage: hitl-verify.sh <task_id> <current_status>"
  exit 1
fi

# Input validation
if ! echo "$task_id" | grep -qE '^T-[0-9]+$'; then
  echo "ERROR: Invalid task_id format (expected T-NNN)" >&2
  exit 1
fi

# Statuses that require HITL approval before advancing
HITL_STATUSES="designing_done implementing_done review_done test_done accepted"

if ! echo " $HITL_STATUSES " | grep -q " $current_status "; then
  exit 0  # Not a HITL gate status, allow
fi

# Check if HITL is enabled in config
if [ -f "$CONFIG" ]; then
  hitl_enabled=$(python3 -c "
import json, sys
try:
    c = json.load(open(sys.argv[1]))
    print(str(c.get('hitl', {}).get('enabled', True)).lower())
except: print('true')
" "$CONFIG" 2>/dev/null || echo "true")
else
  hitl_enabled="true"
fi

if [ "$hitl_enabled" = "false" ]; then
  exit 0  # HITL disabled globally, allow
fi

# Check feedback_history for approval at current status
if [ ! -f "$TASK_BOARD" ]; then
  echo "ERROR: task-board.json not found at $TASK_BOARD" >&2
  exit 1
fi

has_approval=$(python3 -c "
import json, sys

task_id = sys.argv[1]
current_status = sys.argv[2]

tb = json.load(open(sys.argv[3]))
for t in tb.get('tasks', []):
    if t.get('id') == task_id:
        history = t.get('feedback_history', [])
        # Find the latest feedback entry matching this HITL gate
        for entry in reversed(history):
            if entry.get('from_status') == current_status:
                if entry.get('decision') == 'approve':
                    print('yes')
                    sys.exit(0)
                else:
                    print('no')
                    sys.exit(0)
        break
print('no')
" "$task_id" "$current_status" "$TASK_BOARD" 2>/dev/null || echo "no")

if [ "$has_approval" = "yes" ]; then
  exit 0
else
  echo ""
  echo "⛔ HITL GATE BLOCKED"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "  Task:   $task_id"
  echo "  Status: $current_status"
  echo "  Reason: Human approval required before advancing."
  echo ""
  echo "  You MUST:"
  echo "    1. Run the HITL adapter to present output for review"
  echo "    2. Collect human approval (approve/feedback)"
  echo "    3. Record decision in feedback_history"
  echo "    4. Only then advance the status"
  echo ""
  echo "  Do NOT skip this step or modify task-board.json directly."
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  exit 1
fi
