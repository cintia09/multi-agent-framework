#!/usr/bin/env bash
# Module: FSM Validation — validates status transitions, goal guard, document gate
# Sourced by agent-post-tool-use.sh. Expects: TASK_BOARD_CACHE, SNAPSHOT, AGENTS_DIR, ACTIVE_AGENT, TIMESTAMP, EVENTS_DB, sql_escape()

run_fsm_validation() {
  [ -z "$TASK_BOARD_CACHE" ] || [ ! -f "$SNAPSHOT" ] && return 0

  echo "$TASK_BOARD_CACHE" | jq -c '.tasks[]' 2>/dev/null | while read -r TASK; do
    TASK_ID=$(echo "$TASK" | jq -r '.id // empty')
    NEW_STATUS=$(echo "$TASK" | jq -r '.status // empty')
    [ -z "$TASK_ID" ] || [ -z "$NEW_STATUS" ] && continue
    OLD_STATUS=$(jq -r --arg tid "$TASK_ID" '.tasks[] | select(.id == $tid) | .status' "$SNAPSHOT" 2>/dev/null || echo "")
    [ "$OLD_STATUS" = "$NEW_STATUS" ] && continue

    TASK_ID_SQL=$(sql_escape "$TASK_ID")
    OLD_STATUS_SQL=$(sql_escape "$OLD_STATUS")
    NEW_STATUS_SQL=$(sql_escape "$NEW_STATUS")

    LEGAL=false
    WORKFLOW_MODE=$(echo "$TASK_BOARD_CACHE" | jq -r --arg tid "$TASK_ID" '.tasks[] | select(.id == $tid) | .workflow_mode // "simple"' 2>/dev/null || echo "simple")

    if [ "$WORKFLOW_MODE" = "3phase" ]; then
      _validate_3phase
    else
      _validate_simple
    fi

    # === Goal Guard ===
    if [ "$LEGAL" = true ] && [ "$NEW_STATUS_SQL" = "accepted" ]; then
      UNVERIFIED=$(echo "$TASK_BOARD_CACHE" | jq -r --arg tid "$TASK_ID" \
        '.tasks[] | select(.id == $tid) | .goals // [] | map(select(.status != "verified")) | length' \
        2>/dev/null || echo "0")
      if [ "$UNVERIFIED" -gt 0 ]; then
        echo "⛔ [GOAL GUARD] Task $TASK_ID cannot be accepted: $UNVERIFIED goal(s) not yet verified."
        sqlite3 "$EVENTS_DB" "INSERT INTO events (timestamp, event_type, agent, task_id, detail) VALUES ($TIMESTAMP, 'goal_guard_block', '$ACTIVE_AGENT', '$TASK_ID_SQL', '{\"unverified_goals\":$UNVERIFIED}');" 2>/dev/null || true
        LEGAL=false
      fi
    fi

    # === Document Gate ===
    DOCS_DIR="$AGENTS_DIR/docs/$TASK_ID"
    DOC_MISSING=""
    case "$OLD_STATUS" in
      created)       [ ! -f "$DOCS_DIR/requirements.md" ] && DOC_MISSING="requirements.md" ;;
      designing)     [ ! -f "$DOCS_DIR/design.md" ] && DOC_MISSING="design.md" ;;
      implementing)  [ ! -f "$DOCS_DIR/implementation.md" ] && DOC_MISSING="implementation.md" ;;
      reviewing)     [ ! -f "$DOCS_DIR/review-report.md" ] && DOC_MISSING="review-report.md" ;;
      testing)       [ ! -f "$DOCS_DIR/test-report.md" ] && DOC_MISSING="test-report.md" ;;
    esac
    if [ -n "$DOC_MISSING" ]; then
      echo "⚠️ [DOC GATE] Task $TASK_ID: missing '$DOC_MISSING' in .agents/docs/$TASK_ID/. See agent-docs skill for template."
      sqlite3 "$EVENTS_DB" "INSERT INTO events (timestamp, event_type, agent, task_id, detail) VALUES ($TIMESTAMP, 'doc_gate_warning', '$ACTIVE_AGENT', '$TASK_ID_SQL', '{\"missing\":\"$DOC_MISSING\",\"from\":\"$OLD_STATUS_SQL\",\"to\":\"$NEW_STATUS_SQL\"}');" 2>/dev/null || true
    fi

    if [ "$LEGAL" = false ]; then
      echo "⛔ [FSM] ILLEGAL transition: $TASK_ID ($OLD_STATUS → $NEW_STATUS)."
      sqlite3 "$EVENTS_DB" "INSERT INTO events (timestamp, event_type, agent, task_id, detail) VALUES ($TIMESTAMP, 'fsm_violation', '$ACTIVE_AGENT', '$TASK_ID_SQL', '{\"from\":\"$OLD_STATUS_SQL\",\"to\":\"$NEW_STATUS_SQL\"}');" 2>/dev/null || true
    fi
  done
}

# --- 3-Phase FSM transitions ---
_validate_3phase() {
  case "${OLD_STATUS}→${NEW_STATUS}" in
    "created→requirements")          LEGAL=true ;;
    "requirements→architecture")     LEGAL=true ;;
    "architecture→tdd_design")       LEGAL=true ;;
    "tdd_design→dfmea")              LEGAL=true ;;
    "dfmea→design_review")           LEGAL=true ;;
    "design_review→implementing")    LEGAL=true ;;
    "design_review→architecture")    LEGAL=true ;;
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
    "deploying→regression_testing")       LEGAL=true ;;
    "regression_testing→feature_testing") LEGAL=true ;;
    "regression_testing→implementing")    LEGAL=true ;;
    "feature_testing→log_analysis")       LEGAL=true ;;
    "feature_testing→tdd_design")         LEGAL=true ;;
    "log_analysis→documentation")         LEGAL=true ;;
    "log_analysis→ci_fixing")             LEGAL=true ;;
    "documentation→accepted")             LEGAL=true ;;
    *→blocked)                            LEGAL=true ;;
    "blocked→"*)
      BLOCKED_FROM=$(echo "$TASK_BOARD_CACHE" | jq -r --arg tid "$TASK_ID" '.tasks[] | select(.id == $tid) | .blocked_from // ""' 2>/dev/null || echo "")
      if [ -n "$BLOCKED_FROM" ] && [ "$BLOCKED_FROM" != "null" ]; then
        [ "$NEW_STATUS_SQL" = "$BLOCKED_FROM" ] && LEGAL=true
      else
        echo "⚠️ [FSM] Task $TASK_ID unblocked without blocked_from record."
        LEGAL=true
      fi
      ;;
  esac

  # Feedback loop check
  if [ "$LEGAL" = true ]; then
    case "${OLD_STATUS}→${NEW_STATUS}" in
      "regression_testing→implementing"|"feature_testing→tdd_design"|\
      "log_analysis→ci_fixing"|"device_baseline→implementing"|\
      "design_review→architecture"|"code_reviewing→implementing")
        _check_feedback_limit
        ;;
    esac
  fi

  # Convergence gate
  if [ "$LEGAL" = true ] && [ "$NEW_STATUS_SQL" = "device_baseline" ]; then
    IMPL_STATUS=$(echo "$TASK_BOARD_CACHE" | jq -r --arg tid "$TASK_ID" '.tasks[] | select(.id == $tid) | .parallel_tracks.implementing // "pending"' 2>/dev/null || echo "pending")
    TEST_STATUS=$(echo "$TASK_BOARD_CACHE" | jq -r --arg tid "$TASK_ID" '.tasks[] | select(.id == $tid) | .parallel_tracks.test_scripting // "pending"' 2>/dev/null || echo "pending")
    REVIEW_STATUS=$(echo "$TASK_BOARD_CACHE" | jq -r --arg tid "$TASK_ID" '.tasks[] | select(.id == $tid) | .parallel_tracks.code_reviewing // "pending"' 2>/dev/null || echo "pending")
    CI_STATUS=$(echo "$TASK_BOARD_CACHE" | jq -r --arg tid "$TASK_ID" '.tasks[] | select(.id == $tid) | .parallel_tracks.ci_monitoring // "pending"' 2>/dev/null || echo "pending")
    if [ "$IMPL_STATUS" != "complete" ] || [ "$TEST_STATUS" != "complete" ] || [ "$REVIEW_STATUS" != "complete" ] || [ "$CI_STATUS" != "green" ]; then
      echo "⛔ [FSM] CONVERGENCE GATE: Task $TASK_ID — tracks not converged (impl=$IMPL_STATUS, test=$TEST_STATUS, review=$REVIEW_STATUS, ci=$CI_STATUS)."
      sqlite3 "$EVENTS_DB" "INSERT INTO events (timestamp, event_type, agent, task_id, detail) VALUES ($TIMESTAMP, 'convergence_gate_block', '$ACTIVE_AGENT', '$TASK_ID_SQL', '{\"impl\":\"$IMPL_STATUS\",\"test\":\"$TEST_STATUS\",\"review\":\"$REVIEW_STATUS\",\"ci\":\"$CI_STATUS\"}');" 2>/dev/null || true
      LEGAL=false
    fi
  fi
}

# --- Simple FSM transitions ---
_validate_simple() {
  case "${OLD_STATUS}→${NEW_STATUS}" in
    "created→designing")       LEGAL=true ;;
    "designing→implementing")  LEGAL=true ;;
    "implementing→reviewing")  LEGAL=true ;;
    "reviewing→implementing")  LEGAL=true ;;
    "reviewing→testing")       LEGAL=true ;;
    "testing→fixing")          LEGAL=true ;;
    "testing→accepting")       LEGAL=true ;;
    "fixing→testing")          LEGAL=true ;;
    "accepting→accepted")      LEGAL=true ;;
    "accepting→accept_fail")   LEGAL=true ;;
    "accept_fail→designing")   LEGAL=true ;;
    *→blocked)                 LEGAL=true ;;
    "blocked→"*)
      BLOCKED_FROM=$(echo "$TASK_BOARD_CACHE" | jq -r --arg tid "$TASK_ID" '.tasks[] | select(.id == $tid) | .blocked_from // ""' 2>/dev/null || echo "")
      if [ -n "$BLOCKED_FROM" ] && [ "$BLOCKED_FROM" != "null" ]; then
        [ "$NEW_STATUS_SQL" = "$BLOCKED_FROM" ] && LEGAL=true
      else
        echo "⚠️ [FSM] Task $TASK_ID unblocked without blocked_from record."
        LEGAL=true
      fi
      ;;
  esac

  # Feedback loop check for simple mode
  if [ "$LEGAL" = true ]; then
    case "${OLD_STATUS}→${NEW_STATUS}" in
      "reviewing→implementing"|"testing→fixing"|"accept_fail→designing")
        _check_feedback_limit
        ;;
    esac
  fi
}

# --- Shared: feedback loop limit ---
_check_feedback_limit() {
  FEEDBACK_COUNT=$(echo "$TASK_BOARD_CACHE" | jq -r --arg tid "$TASK_ID" '.tasks[] | select(.id == $tid) | .feedback_loops // 0' 2>/dev/null || echo 0)
  if [ "$FEEDBACK_COUNT" -ge 10 ]; then
    echo "⛔ [FSM] FEEDBACK LIMIT: Task $TASK_ID reached 10 loops. $OLD_STATUS → $NEW_STATUS blocked."
    sqlite3 "$EVENTS_DB" "INSERT INTO events (timestamp, event_type, agent, task_id, detail) VALUES ($TIMESTAMP, 'fsm_feedback_limit', '$ACTIVE_AGENT', '$TASK_ID_SQL', '{\"from\":\"$OLD_STATUS_SQL\",\"to\":\"$NEW_STATUS_SQL\",\"loops\":$FEEDBACK_COUNT}');" 2>/dev/null || true
    LEGAL=false
  fi
}
