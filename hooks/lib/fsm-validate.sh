#!/usr/bin/env bash
# Module: FSM Validation — validates status transitions, goal guard, document gate
# Sourced by agent-post-tool-use.sh. Expects: TASK_BOARD_CACHE, SNAPSHOT, AGENTS_DIR, ACTIVE_AGENT, TIMESTAMP, EVENTS_DB, sql_escape()

run_fsm_validation() {
  if [ -z "$TASK_BOARD_CACHE" ] || [ ! -f "$SNAPSHOT" ]; then
    return 0
  fi

  # Track tasks with FSM violations so downstream modules can skip them
  FSM_VIOLATED_TASKS=""

  # Pre-load old statuses from snapshot (1 jq call instead of N)
  local SNAPSHOT_STATUSES
  SNAPSHOT_STATUSES=$(jq -r '.tasks[] | "\(.id)\t\(.status)"' "$SNAPSHOT" 2>/dev/null || true)

  # Extract ALL fields per task in ONE jq call (replaces ~10 per-task jq calls)
  while IFS=$'\t' read -r TASK_ID NEW_STATUS WORKFLOW_MODE FEEDBACK_LOOPS BLOCKED_FROM UNVERIFIED_GOALS PT_IMPL PT_TEST PT_REVIEW PT_CI; do
    [ -z "$TASK_ID" ] || [ -z "$NEW_STATUS" ] && continue
    OLD_STATUS=$(echo "$SNAPSHOT_STATUSES" | awk -F'\t' -v tid="$TASK_ID" '$1==tid{print $2; exit}')
    [ "$OLD_STATUS" = "$NEW_STATUS" ] && continue

    TASK_ID_SQL=$(sql_escape "$TASK_ID")
    OLD_STATUS_SQL=$(sql_escape "$OLD_STATUS")
    NEW_STATUS_SQL=$(sql_escape "$NEW_STATUS")
    # Use ACTIVE_AGENT_ESC from parent (post-tool-use.sh) for SQL

    LEGAL=false

    if [ "$WORKFLOW_MODE" = "3phase" ]; then
      _validate_3phase
    else
      _validate_simple
    fi

    # === Goal Guard ===
    if [ "$LEGAL" = true ] && [ "$NEW_STATUS" = "accepted" ]; then
      if [ "$UNVERIFIED_GOALS" -gt 0 ] 2>/dev/null; then
        echo "⛔ [GOAL GUARD] Task $TASK_ID cannot be accepted: $UNVERIFIED_GOALS goal(s) not yet verified."
        sqlite3 "$EVENTS_DB" "INSERT INTO events (timestamp, event_type, agent, task_id, detail) VALUES ($TIMESTAMP, 'goal_guard_block', '$ACTIVE_AGENT_ESC', '$TASK_ID_SQL', '{\"unverified_goals\":$UNVERIFIED_GOALS}');" 2>/dev/null || true
        LEGAL=false
      fi
    fi

    # === Document Gate ===
    DOCS_DIR="$AGENTS_DIR/docs/$TASK_ID"
    DOC_MISSING=""
    case "$OLD_STATUS" in
      created)
        [ ! -f "$DOCS_DIR/requirements.md" ] && DOC_MISSING="requirements.md"
        [ ! -f "$DOCS_DIR/acceptance-criteria.md" ] && DOC_MISSING="${DOC_MISSING:+$DOC_MISSING, }acceptance-criteria.md"
        ;;
      designing|architecture|tdd_design|dfmea)
        [ ! -f "$DOCS_DIR/design.md" ] && DOC_MISSING="design.md" ;;
      implementing)
        [ ! -f "$DOCS_DIR/implementation.md" ] && DOC_MISSING="implementation.md" ;;
      reviewing|design_review|code_reviewing)
        [ ! -f "$DOCS_DIR/review-report.md" ] && DOC_MISSING="review-report.md" ;;
      testing|test_scripting|regression_testing)
        [ ! -f "$DOCS_DIR/test-report.md" ] && DOC_MISSING="test-report.md" ;;
    esac
    if [ -n "$DOC_MISSING" ]; then
      echo "⚠️ [DOC GATE] Task $TASK_ID: missing '$DOC_MISSING' in .agents/docs/$TASK_ID/. See agent-docs skill for template."
      sqlite3 "$EVENTS_DB" "INSERT INTO events (timestamp, event_type, agent, task_id, detail) VALUES ($TIMESTAMP, 'doc_gate_warning', '$ACTIVE_AGENT_ESC', '$TASK_ID_SQL', '{\"missing\":\"$DOC_MISSING\",\"from\":\"$OLD_STATUS_SQL\",\"to\":\"$NEW_STATUS_SQL\"}');" 2>/dev/null || true
    fi

    if [ "$LEGAL" = false ]; then
      echo "⛔ [FSM] ILLEGAL transition: $TASK_ID ($OLD_STATUS → $NEW_STATUS)."
      sqlite3 "$EVENTS_DB" "INSERT INTO events (timestamp, event_type, agent, task_id, detail) VALUES ($TIMESTAMP, 'fsm_violation', '$ACTIVE_AGENT_ESC', '$TASK_ID_SQL', '{\"from\":\"$OLD_STATUS_SQL\",\"to\":\"$NEW_STATUS_SQL\"}');" 2>/dev/null || true
      FSM_VIOLATED_TASKS="${FSM_VIOLATED_TASKS:+$FSM_VIOLATED_TASKS }$TASK_ID"
    fi
  done < <(echo "$TASK_BOARD_CACHE" | jq -r '.tasks[] | [
    .id // "",
    .status // "",
    .workflow_mode // "simple",
    (.feedback_loops // 0),
    .blocked_from // "",
    (.goals // [] | map(select(.status != "verified")) | length),
    .parallel_tracks.implementing // "pending",
    .parallel_tracks.test_scripting // "pending",
    .parallel_tracks.code_reviewing // "pending",
    .parallel_tracks.ci_monitoring // "pending"
  ] | @tsv' 2>/dev/null)
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
    "design_review→test_scripting")   LEGAL=true ;;
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
    # Hypothesis exploration (both simple and 3-phase)
    "designing→hypothesizing")             LEGAL=true ;;
    "implementing→hypothesizing")          LEGAL=true ;;
    "hypothesizing→designing")             LEGAL=true ;;
    "hypothesizing→implementing")          LEGAL=true ;;
    *→blocked)                            LEGAL=true ;;
    "blocked→"*)
      if [ -n "$BLOCKED_FROM" ] && [ "$BLOCKED_FROM" != "null" ]; then
        [ "$NEW_STATUS" = "$BLOCKED_FROM" ] && LEGAL=true
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

  # Convergence gate (uses pre-extracted parallel_tracks fields)
  if [ "$LEGAL" = true ] && [ "$NEW_STATUS" = "device_baseline" ]; then
    if [ "$PT_IMPL" != "complete" ] || [ "$PT_TEST" != "complete" ] || [ "$PT_REVIEW" != "complete" ] || [ "$PT_CI" != "green" ]; then
      echo "⛔ [FSM] CONVERGENCE GATE: Task $TASK_ID — tracks not converged (impl=$PT_IMPL, test=$PT_TEST, review=$PT_REVIEW, ci=$PT_CI)."
      local PT_IMPL_ESC PT_TEST_ESC PT_REVIEW_ESC PT_CI_ESC
      PT_IMPL_ESC=$(sql_escape "$PT_IMPL"); PT_TEST_ESC=$(sql_escape "$PT_TEST")
      PT_REVIEW_ESC=$(sql_escape "$PT_REVIEW"); PT_CI_ESC=$(sql_escape "$PT_CI")
      sqlite3 "$EVENTS_DB" "INSERT INTO events (timestamp, event_type, agent, task_id, detail) VALUES ($TIMESTAMP, 'convergence_gate_block', '$ACTIVE_AGENT_ESC', '$TASK_ID_SQL', '{\"impl\":\"$PT_IMPL_ESC\",\"test\":\"$PT_TEST_ESC\",\"review\":\"$PT_REVIEW_ESC\",\"ci\":\"$PT_CI_ESC\"}');" 2>/dev/null || true
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
    # Hypothesis exploration
    "designing→hypothesizing")    LEGAL=true ;;
    "implementing→hypothesizing") LEGAL=true ;;
    "hypothesizing→designing")    LEGAL=true ;;
    "hypothesizing→implementing") LEGAL=true ;;
    *→blocked)                 LEGAL=true ;;
    "blocked→"*)
      if [ -n "$BLOCKED_FROM" ] && [ "$BLOCKED_FROM" != "null" ]; then
        [ "$NEW_STATUS" = "$BLOCKED_FROM" ] && LEGAL=true
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

# --- Shared: feedback loop limit (uses pre-extracted FEEDBACK_LOOPS) ---
_check_feedback_limit() {
  if [ "$FEEDBACK_LOOPS" -ge 10 ] 2>/dev/null; then
    echo "⛔ [FSM] FEEDBACK LIMIT: Task $TASK_ID reached 10 loops. $OLD_STATUS → $NEW_STATUS blocked."
    sqlite3 "$EVENTS_DB" "INSERT INTO events (timestamp, event_type, agent, task_id, detail) VALUES ($TIMESTAMP, 'fsm_feedback_limit', '$ACTIVE_AGENT_ESC', '$TASK_ID_SQL', '{\"from\":\"$OLD_STATUS_SQL\",\"to\":\"$NEW_STATUS_SQL\",\"loops\":$FEEDBACK_LOOPS}');" 2>/dev/null || true
    LEGAL=false
  fi
}
