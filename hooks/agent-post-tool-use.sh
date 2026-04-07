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

    # === FSM Transition Validation ===
    # Validate that status changes follow legal FSM transitions
    if [ -f "$AGENTS_DIR/task-board.json" ] && [ -f "$SNAPSHOT" ]; then
      jq -c '.tasks[]' "$AGENTS_DIR/task-board.json" 2>/dev/null | while read -r TASK; do
        TASK_ID=$(echo "$TASK" | jq -r '.id')
        NEW_STATUS=$(echo "$TASK" | jq -r '.status')
        OLD_STATUS=$(jq -r --arg tid "$TASK_ID" '.tasks[] | select(.id == $tid) | .status' "$SNAPSHOT" 2>/dev/null || echo "")

        [ -z "$OLD_STATUS" ] && continue
        [ "$OLD_STATUS" = "$NEW_STATUS" ] && continue

        # Define legal transitions (from agent-fsm/SKILL.md)
        LEGAL=false

        # Read workflow mode for this task
        WORKFLOW_MODE=$(jq -r --arg tid "$TASK_ID" '.tasks[] | select(.id == $tid) | .workflow_mode // "simple"' "$AGENTS_DIR/task-board.json" 2>/dev/null || echo "simple")

        if [ "$WORKFLOW_MODE" = "3phase" ]; then
          # 3-Phase Engineering Closed Loop transitions
          case "${OLD_STATUS}→${NEW_STATUS}" in
            # Phase 1: Design
            "created→requirements")          LEGAL=true ;;
            "requirements→architecture")     LEGAL=true ;;
            "architecture→tdd_design")       LEGAL=true ;;
            "tdd_design→dfmea")              LEGAL=true ;;
            "dfmea→design_review")           LEGAL=true ;;
            "design_review→implementing")    LEGAL=true ;;
            "design_review→architecture")    LEGAL=true ;;

            # Phase 2: Implementation
            "implementing→code_reviewing")   LEGAL=true ;;
            "implementing→ci_monitoring")    LEGAL=true ;;
            "test_scripting→code_reviewing") LEGAL=true ;;
            "code_reviewing→implementing")   LEGAL=true ;;
            "code_reviewing→ci_monitoring")  LEGAL=true ;;
            "ci_monitoring→ci_fixing")       LEGAL=true ;;
            "ci_monitoring→device_baseline") LEGAL=true ;;
            "ci_fixing→ci_monitoring")       LEGAL=true ;;
            "device_baseline→deploying")     LEGAL=true ;;
            "device_baseline→implementing")  LEGAL=true ;;

            # Phase 3: Testing & Verification
            "deploying→regression_testing")       LEGAL=true ;;
            "regression_testing→feature_testing") LEGAL=true ;;
            "regression_testing→implementing")    LEGAL=true ;;
            "feature_testing→log_analysis")       LEGAL=true ;;
            "feature_testing→tdd_design")         LEGAL=true ;;
            "log_analysis→documentation")         LEGAL=true ;;
            "log_analysis→ci_fixing")             LEGAL=true ;;
            "documentation→accepted")             LEGAL=true ;;

            # Universal
            *→blocked)                            LEGAL=true ;;
            "blocked→"*)                          LEGAL=true ;;
          esac

          # Feedback loop safety check for 3-Phase
          if [ "$LEGAL" = true ]; then
            case "${OLD_STATUS}→${NEW_STATUS}" in
              "regression_testing→implementing"|"feature_testing→tdd_design"|\
              "log_analysis→ci_fixing"|"device_baseline→implementing"|\
              "design_review→architecture"|"code_reviewing→implementing")
                FEEDBACK_COUNT=$(jq -r --arg tid "$TASK_ID" '.tasks[] | select(.id == $tid) | .feedback_loops // 0' "$AGENTS_DIR/task-board.json" 2>/dev/null || echo 0)
                if [ "$FEEDBACK_COUNT" -ge 10 ]; then
                  echo "⛔ [FSM] FEEDBACK SAFETY LIMIT: Task $TASK_ID has reached 10 feedback loops. Transition $OLD_STATUS → $NEW_STATUS blocked. Manual intervention required."
                  sqlite3 "$EVENTS_DB" "INSERT INTO events (timestamp, event_type, agent, task_id, detail) VALUES ($TIMESTAMP, 'fsm_feedback_limit', '$ACTIVE_AGENT', '$TASK_ID', '{\"from\":\"$OLD_STATUS\",\"to\":\"$NEW_STATUS\",\"loops\":$FEEDBACK_COUNT}');" 2>/dev/null || true
                  LEGAL=false
                fi
                ;;
            esac
          fi

          # Convergence gate check for device_baseline
          if [ "$LEGAL" = true ] && [ "$NEW_STATUS" = "device_baseline" ]; then
            IMPL_STATUS=$(jq -r --arg tid "$TASK_ID" '.tasks[] | select(.id == $tid) | .parallel_tracks.implementing // "pending"' "$AGENTS_DIR/task-board.json" 2>/dev/null || echo "pending")
            TEST_STATUS=$(jq -r --arg tid "$TASK_ID" '.tasks[] | select(.id == $tid) | .parallel_tracks.test_scripting // "pending"' "$AGENTS_DIR/task-board.json" 2>/dev/null || echo "pending")
            REVIEW_STATUS=$(jq -r --arg tid "$TASK_ID" '.tasks[] | select(.id == $tid) | .parallel_tracks.code_reviewing // "pending"' "$AGENTS_DIR/task-board.json" 2>/dev/null || echo "pending")
            CI_STATUS=$(jq -r --arg tid "$TASK_ID" '.tasks[] | select(.id == $tid) | .parallel_tracks.ci_monitoring // "pending"' "$AGENTS_DIR/task-board.json" 2>/dev/null || echo "pending")
            if [ "$IMPL_STATUS" != "complete" ] || [ "$TEST_STATUS" != "complete" ] || [ "$REVIEW_STATUS" != "complete" ] || [ "$CI_STATUS" != "green" ]; then
              echo "⛔ [FSM] CONVERGENCE GATE: Task $TASK_ID cannot enter device_baseline. Parallel tracks not converged (impl=$IMPL_STATUS, test=$TEST_STATUS, review=$REVIEW_STATUS, ci=$CI_STATUS)."
              LEGAL=false
            fi
          fi
        else
          # Simple Linear FSM transitions
          case "${OLD_STATUS}→${NEW_STATUS}" in
            "created→designing")       LEGAL=true ;;
            "designing→implementing")  LEGAL=true ;;
            "implementing→reviewing")  LEGAL=true ;;
            "reviewing→implementing")  LEGAL=true ;;  # review rejection
            "reviewing→testing")       LEGAL=true ;;
            "testing→fixing")          LEGAL=true ;;
            "testing→accepting")       LEGAL=true ;;
            "fixing→testing")          LEGAL=true ;;  # fix retest
            "accepting→accepted")      LEGAL=true ;;
            "accept_fail→designing")   LEGAL=true ;;
            *→blocked)                 LEGAL=true ;;  # anything can be blocked
            "blocked→"*)               LEGAL=true ;;  # unblock to any
          esac
        fi

        if [ "$LEGAL" = false ]; then
          echo "⛔ [FSM] ILLEGAL transition detected: $TASK_ID ($OLD_STATUS → $NEW_STATUS). Legal transitions from '$OLD_STATUS' do not include '$NEW_STATUS'. Please use agent-fsm to make valid transitions."
          sqlite3 "$EVENTS_DB" "INSERT INTO events (timestamp, event_type, agent, task_id, detail) VALUES ($TIMESTAMP, 'fsm_violation', '$ACTIVE_AGENT', '$TASK_ID', '{\"from\":\"$OLD_STATUS\",\"to\":\"$NEW_STATUS\"}');" 2>/dev/null || true
        fi
      done
    fi

    # === Auto Memory Capture (T-008) ===
    # When task status changes, detect transition and trigger memory capture
    if [ -f "$AGENTS_DIR/task-board.json" ]; then
      # Compare with last known snapshot to detect status changes
      SNAPSHOT="$AGENTS_DIR/runtime/.task-board-snapshot.json"

      if [ -f "$SNAPSHOT" ]; then
        # Extract current and previous statuses, detect transitions
        jq -c '.tasks[]' "$AGENTS_DIR/task-board.json" 2>/dev/null | while read -r TASK; do
          TASK_ID=$(echo "$TASK" | jq -r '.id')
          NEW_STATUS=$(echo "$TASK" | jq -r '.status')
          OLD_STATUS=$(jq -r --arg tid "$TASK_ID" '.tasks[] | select(.id == $tid) | .status' "$SNAPSHOT" 2>/dev/null || echo "")

          # Only trigger on actual transitions
          if [ -n "$OLD_STATUS" ] && [ "$OLD_STATUS" != "$NEW_STATUS" ]; then
            # Record memory_capture_needed event
            sqlite3 "$EVENTS_DB" "INSERT INTO events (timestamp, event_type, agent, task_id, detail) VALUES ($TIMESTAMP, 'memory_capture_needed', '$ACTIVE_AGENT', '$TASK_ID', '{\"from_status\":\"$OLD_STATUS\",\"to_status\":\"$NEW_STATUS\"}');" 2>/dev/null || true

            # Create memory directory if needed
            MEMORY_DIR="$AGENTS_DIR/memory"
            mkdir -p "$MEMORY_DIR"

            # Initialize memory file if it doesn't exist
            MEMORY_FILE="$MEMORY_DIR/${TASK_ID}-memory.json"
            if [ ! -f "$MEMORY_FILE" ]; then
              TITLE=$(echo "$TASK" | jq -r '.title')
              NOW_ISO=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
              cat > "$MEMORY_FILE" << MEMEOF
{"task_id":"$TASK_ID","title":"$TITLE","version":1,"created_at":"$NOW_ISO","last_updated":"$NOW_ISO","stages":{}}
MEMEOF
            fi

            # Prompt agent via stdout (agent sees this as hook output)
            echo "🧠 [Auto-Capture] Task $TASK_ID status changed: $OLD_STATUS → $NEW_STATUS. Please save memory snapshot to .agents/memory/${TASK_ID}-memory.json (summary, decisions, files_modified, handoff_notes)."
          fi
        done
      fi

      # Update snapshot for next comparison
      cp "$AGENTS_DIR/task-board.json" "$SNAPSHOT" 2>/dev/null || true
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
