#!/usr/bin/env bash
# Multi-Agent Framework: Post-Tool-Use Hook
# Logs tool execution results to events.db for audit trail.
# Detects task-board changes and logs state transitions.

set -euo pipefail
INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.toolName')
TOOL_ARGS=$(echo "$INPUT" | jq -r '.toolArgs')
RESULT_TYPE=$(echo "$INPUT" | jq -r '.toolResult.resultType')
CWD=$(echo "$INPUT" | jq -r '.cwd')
TIMESTAMP=$(echo "$INPUT" | jq -r '.timestamp')

AGENTS_DIR="$CWD/.agents"
EVENTS_DB="$AGENTS_DIR/events.db"
SNAPSHOT="$AGENTS_DIR/runtime/.task-board-snapshot.json"

# Only log if agent framework is initialized and events.db exists
[ -f "$EVENTS_DB" ] || exit 0

# Read active agent
# Escape single quotes for SQL safety
sql_escape() { echo "$1" | sed "s/'/''/g"; }

ACTIVE_AGENT="none"
ACTIVE_FILE="$AGENTS_DIR/runtime/active-agent"
[ -f "$ACTIVE_FILE" ] && ACTIVE_AGENT=$(sql_escape "$(cat "$ACTIVE_FILE")")

# Escape all input variables
TOOL_NAME_ESC=$(sql_escape "$TOOL_NAME")
RESULT_TYPE_ESC=$(sql_escape "$RESULT_TYPE")
TOOL_ARGS_ESC=$(echo "$TOOL_ARGS" | sed "s/'/''/g" | head -c 500)

# Log every tool use to events.db
sqlite3 "$EVENTS_DB" "INSERT INTO events (timestamp, event_type, agent, tool_name, detail) VALUES ($TIMESTAMP, 'tool_use', '$ACTIVE_AGENT', '$TOOL_NAME_ESC', '{\"result\":\"$RESULT_TYPE_ESC\",\"args\":\"$TOOL_ARGS_ESC\"}');"

# Detect task-board writes
if [ "$TOOL_NAME" = "edit" ] || [ "$TOOL_NAME" = "create" ]; then
  FILE_PATH=$(echo "$TOOL_ARGS" | jq -r '.path // empty' 2>/dev/null)
  if [[ "$FILE_PATH" =~ task-board\.json ]]; then
    sqlite3 "$EVENTS_DB" "INSERT INTO events (timestamp, event_type, agent, detail) VALUES ($TIMESTAMP, 'task_board_write', '$ACTIVE_AGENT', '{\"tool\":\"$TOOL_NAME_ESC\"}');"

    # --- AUTO-DISPATCH (G2) ---
    # When task-board.json changes, send messages to the next agent in FSM
    if [ -f "$AGENTS_DIR/task-board.json" ]; then
      jq -r '.tasks[] | "\(.id)|\(.status)|\(.title // "")"' "$AGENTS_DIR/task-board.json" 2>/dev/null | while IFS='|' read -r TASK_ID STATUS TITLE; do

        # Map status to target agent (dispatch on all FSM "arrival" statuses)
        case "$STATUS" in
          # Simple mode statuses
          created)        TARGET="designer" ;;
          designing)      TARGET="designer" ;;
          implementing)   TARGET="implementer" ;;
          reviewing)      TARGET="reviewer" ;;
          testing)        TARGET="tester" ;;
          fixing)         TARGET="implementer" ;;
          accepting)      TARGET="acceptor" ;;
          accept_fail)    TARGET="designer" ;;
          # 3-Phase mode statuses
          requirements)        TARGET="acceptor" ;;
          architecture)        TARGET="designer" ;;
          tdd_design)          TARGET="designer" ;;
          dfmea)               TARGET="designer" ;;
          design_review)       TARGET="reviewer" ;;
          test_scripting)      TARGET="tester" ;;
          code_reviewing)      TARGET="reviewer" ;;
          ci_monitoring)       TARGET="tester" ;;
          ci_fixing)           TARGET="implementer" ;;
          device_baseline)     TARGET="tester" ;;
          deploying)           TARGET="implementer" ;;
          regression_testing)  TARGET="tester" ;;
          feature_testing)     TARGET="tester" ;;
          log_analysis)        TARGET="tester" ;;
          documentation)       TARGET="designer" ;;
          *)              TARGET="" ;;
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

        # Atomic write with file locking to prevent race conditions
        (
          flock -x -w 5 200 2>/dev/null || true
          jq --arg id "$MSG_ID" --arg from "$ACTIVE_AGENT" --arg to "$TARGET" \
             --arg tid "$TASK_ID" --arg status "$STATUS" --arg title "$TITLE" \
             --arg ts "$NOW_ISO" \
             '.messages += [{"id":$id,"from":$from,"to":$to,"type":"task_update","task_id":$tid,"content":"Task \($tid) [\($title)] status changed to \($status). Please process.","timestamp":$ts,"read":false}]' \
             "$TARGET_INBOX" > "${TARGET_INBOX}.tmp" && mv "${TARGET_INBOX}.tmp" "$TARGET_INBOX"
        ) 200>"${TARGET_INBOX}.lock"

        TARGET_ESC=$(sql_escape "$TARGET")
        TASK_ID_ESC=$(sql_escape "$TASK_ID")
        STATUS_ESC=$(sql_escape "$STATUS")
        sqlite3 "$EVENTS_DB" "INSERT INTO events (timestamp, event_type, agent, task_id, detail) VALUES ($TIMESTAMP, 'auto_dispatch', '$TARGET_ESC', '$TASK_ID_ESC', '{\"from_status\":\"$STATUS_ESC\",\"from_agent\":\"$ACTIVE_AGENT\"}');" 2>/dev/null || true
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

        # SQL-safe versions for event logging
        TASK_ID_SQL=$(sql_escape "$TASK_ID")
        OLD_STATUS_SQL=$(sql_escape "$OLD_STATUS")
        NEW_STATUS_SQL=$(sql_escape "$NEW_STATUS")

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
            "blocked→"*)
              # Validate unblock: only allow return to blocked_from state
              BLOCKED_FROM=$(jq -r --arg tid "$TASK_ID" '.tasks[] | select(.id == $tid) | .blocked_from // ""' "$AGENTS_DIR/task-board.json" 2>/dev/null || echo "")
              if [ -n "$BLOCKED_FROM" ] && [ "$BLOCKED_FROM" != "null" ]; then
                [ "$NEW_STATUS_SQL" = "$BLOCKED_FROM" ] && LEGAL=true
              else
                LEGAL=true  # no blocked_from recorded, allow any unblock
              fi
              ;;
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
                  sqlite3 "$EVENTS_DB" "INSERT INTO events (timestamp, event_type, agent, task_id, detail) VALUES ($TIMESTAMP, 'fsm_feedback_limit', '$ACTIVE_AGENT', '$TASK_ID_SQL', '{\"from\":\"$OLD_STATUS_SQL\",\"to\":\"$NEW_STATUS_SQL\",\"loops\":$FEEDBACK_COUNT}');" 2>/dev/null || true
                  LEGAL=false
                fi
                ;;
            esac
          fi

          # Convergence gate check for device_baseline
          if [ "$LEGAL" = true ] && [ "$NEW_STATUS_SQL" = "device_baseline" ]; then
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
            "accepting→accept_fail")   LEGAL=true ;;  # acceptance failure
            "accept_fail→designing")   LEGAL=true ;;
            *→blocked)                 LEGAL=true ;;  # anything can be blocked
            "blocked→"*)
              # Validate unblock: only allow return to blocked_from state
              BLOCKED_FROM=$(jq -r --arg tid "$TASK_ID" '.tasks[] | select(.id == $tid) | .blocked_from // ""' "$AGENTS_DIR/task-board.json" 2>/dev/null || echo "")
              if [ -n "$BLOCKED_FROM" ] && [ "$BLOCKED_FROM" != "null" ]; then
                [ "$NEW_STATUS_SQL" = "$BLOCKED_FROM" ] && LEGAL=true
              else
                LEGAL=true  # no blocked_from recorded, allow any unblock
              fi
              ;;
          esac
        fi

        # === Goal Guard: block acceptance if goals not all verified ===
        if [ "$LEGAL" = true ] && [ "$NEW_STATUS_SQL" = "accepted" ]; then
          UNVERIFIED=$(jq -r --arg tid "$TASK_ID" \
            '.tasks[] | select(.id == $tid) | .goals // [] | map(select(.status != "verified")) | length' \
            "$AGENTS_DIR/task-board.json" 2>/dev/null || echo "0")
          if [ "$UNVERIFIED" -gt 0 ]; then
            echo "⛔ [GOAL GUARD] Task $TASK_ID cannot be accepted: $UNVERIFIED goal(s) not yet verified. All goals must have status=verified before acceptance."
            sqlite3 "$EVENTS_DB" "INSERT INTO events (timestamp, event_type, agent, task_id, detail) VALUES ($TIMESTAMP, 'goal_guard_block', '$ACTIVE_AGENT', '$TASK_ID_SQL', '{\"unverified_goals\":$UNVERIFIED}');" 2>/dev/null || true
            LEGAL=false
          fi
        fi

        if [ "$LEGAL" = false ]; then
          echo "⛔ [FSM] ILLEGAL transition detected: $TASK_ID ($OLD_STATUS → $NEW_STATUS). Legal transitions from '$OLD_STATUS' do not include '$NEW_STATUS'. Please use agent-fsm to make valid transitions."
          sqlite3 "$EVENTS_DB" "INSERT INTO events (timestamp, event_type, agent, task_id, detail) VALUES ($TIMESTAMP, 'fsm_violation', '$ACTIVE_AGENT', '$TASK_ID_SQL', '{\"from\":\"$OLD_STATUS_SQL\",\"to\":\"$NEW_STATUS_SQL\"}');" 2>/dev/null || true
        fi
      done
    fi

    # === Auto Memory Capture (T-008) ===
    # When task status changes, detect transition and trigger memory capture
    if [ -f "$AGENTS_DIR/task-board.json" ]; then
      # Compare with last known snapshot to detect status changes

      if [ -f "$SNAPSHOT" ]; then
        # Extract current and previous statuses, detect transitions
        jq -c '.tasks[]' "$AGENTS_DIR/task-board.json" 2>/dev/null | while read -r TASK; do
          TASK_ID=$(echo "$TASK" | jq -r '.id')
          NEW_STATUS=$(echo "$TASK" | jq -r '.status')
          OLD_STATUS=$(jq -r --arg tid "$TASK_ID" '.tasks[] | select(.id == $tid) | .status' "$SNAPSHOT" 2>/dev/null || echo "")

          # Only trigger on actual transitions
          if [ -n "$OLD_STATUS_SQL" ] && [ "$OLD_STATUS_SQL" != "$NEW_STATUS_SQL" ]; then
            # Record memory_capture_needed event
            sqlite3 "$EVENTS_DB" "INSERT INTO events (timestamp, event_type, agent, task_id, detail) VALUES ($TIMESTAMP, 'memory_capture_needed', '$ACTIVE_AGENT', '$TASK_ID_SQL', '{\"from_status\":\"$OLD_STATUS_SQL\",\"to_status\":\"$NEW_STATUS_SQL\"}');" 2>/dev/null || true

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

            # Trigger memory index rebuild on acceptance
            if [ "$NEW_STATUS_SQL" = "accepted" ]; then
              SCRIPT_PATH=""
              [ -f "$AGENTS_DIR/scripts/memory-index.sh" ] && SCRIPT_PATH="$AGENTS_DIR/scripts/memory-index.sh"
              [ -z "$SCRIPT_PATH" ] && [ -f "$CWD/scripts/memory-index.sh" ] && SCRIPT_PATH="$CWD/scripts/memory-index.sh"
              [ -n "$SCRIPT_PATH" ] && bash "$SCRIPT_PATH" 2>/dev/null || true
            fi
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
    AGENT_FROM_PATH=$(echo "$FILE_PATH" | sed -n 's|.*runtime/\([^/]*\).*|\1|p')
    AGENT_PATH_ESC=$(sql_escape "${AGENT_FROM_PATH:-unknown}")
    sqlite3 "$EVENTS_DB" "INSERT INTO events (timestamp, event_type, agent, detail) VALUES ($TIMESTAMP, 'state_change', '$AGENT_PATH_ESC', '{\"tool\":\"$TOOL_NAME_ESC\"}');"
  fi
fi
