#!/usr/bin/env bash
# Module: Auto-Dispatch — sends messages to target agents on task status changes
# Sourced by agent-post-tool-use.sh. Expects: TASK_BOARD_CACHE, AGENTS_DIR, ACTIVE_AGENT, TIMESTAMP, EVENTS_DB, sql_escape()

run_auto_dispatch() {
  [ -z "$TASK_BOARD_CACHE" ] && return 0

  while IFS=$'\t' read -r TASK_ID STATUS TITLE WORKFLOW_MODE; do
    # Map status to target agent
    case "$STATUS" in
      created)
        # In 3-phase mode, 'created' goes to acceptor (requirements phase); simple goes to designer
        if [ "$WORKFLOW_MODE" = "3phase" ]; then
          TARGET="acceptor"
        else
          TARGET="designer"
        fi
        ;;
      designing)      TARGET="designer" ;;
      implementing)   TARGET="implementer" ;;
      reviewing)      TARGET="reviewer" ;;
      testing)        TARGET="tester" ;;
      fixing)         TARGET="implementer" ;;
      accepting)      TARGET="acceptor" ;;
      accept_fail)    TARGET="designer" ;;
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
      hypothesizing)       TARGET="" ;;  # No auto-dispatch; coordinator manages hypotheses
      *)              TARGET="" ;;
    esac

    [ -z "$TARGET" ] && continue

    TARGET_INBOX="$AGENTS_DIR/runtime/$TARGET/inbox.json"
    [ -f "$TARGET_INBOX" ] || continue

    # Duplicate prevention
    MSG_ID="MSG-auto-${TASK_ID}-${STATUS}"
    EXISTING=$(jq --arg mid "$MSG_ID" \
      '[.messages[] | select(.id == $mid)] | length' \
      "$TARGET_INBOX" 2>/dev/null || echo 0)
    [ "$EXISTING" -gt 0 ] && continue

    NOW_ISO=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

    # Atomic write with portable directory-based locking
    LOCK_DIR="${TARGET_INBOX}.lock"
    LOCK_WAIT=0
    while ! mkdir "$LOCK_DIR" 2>/dev/null; do
      sleep 0.1
      LOCK_WAIT=$((LOCK_WAIT + 1))
      if [ "$LOCK_WAIT" -ge 50 ]; then
        echo "⚠️ [Auto-Dispatch] Lock timeout for $TARGET inbox, skipping" >&2
        continue 2
      fi
    done
    if jq --arg id "$MSG_ID" --arg from "$ACTIVE_AGENT" --arg to "$TARGET" \
       --arg tid "$TASK_ID" --arg status "$STATUS" --arg title "$TITLE" \
       --arg ts "$NOW_ISO" \
       '.messages += [{"id":$id,"from":$from,"to":$to,"type":"task_update","task_id":$tid,"content":"Task \($tid) [\($title)] status changed to \($status). Please process.","timestamp":$ts,"read":false}]' \
       "$TARGET_INBOX" > "${TARGET_INBOX}.tmp" && mv "${TARGET_INBOX}.tmp" "$TARGET_INBOX"; then
      : # success
    else
      rm -f "${TARGET_INBOX}.tmp"
    fi
    rmdir "$LOCK_DIR" 2>/dev/null || true

    TARGET_ESC=$(sql_escape "$TARGET")
    TASK_ID_ESC=$(sql_escape "$TASK_ID")
    STATUS_ESC=$(sql_escape "$STATUS")
    sqlite3 "$EVENTS_DB" "INSERT INTO events (timestamp, event_type, agent, task_id, detail) VALUES ($TIMESTAMP, 'auto_dispatch', '$TARGET_ESC', '$TASK_ID_ESC', '{\"from_status\":\"$STATUS_ESC\",\"from_agent\":\"$ACTIVE_AGENT_ESC\"}');" 2>/dev/null || true
  done < <(echo "$TASK_BOARD_CACHE" | jq -r '.tasks[] | [.id // "", .status // "", .title // "", .workflow_mode // "simple"] | @tsv' 2>/dev/null)
}
