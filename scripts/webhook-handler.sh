#!/usr/bin/env bash
set -euo pipefail
# Webhook Handler - processes external triggers
# Usage: bash scripts/webhook-handler.sh <event_type> [payload_json]
# Designed to be called from a lightweight HTTP server or git hook

EVENT="${1:?Usage: webhook-handler.sh <event_type> [payload_json]}"
PAYLOAD="${2:-{}}"

# Validate CWD has agent framework
[ -d ".agents/runtime" ] || { echo "Error: .agents/runtime not found in $(pwd). Run from project root."; exit 1; }

log_event() {
  if [ -f ".agents/events.db" ]; then
    local detail_esc
    detail_esc=$(echo "$1" | sed "s/'/''/g")
    sqlite3 .agents/events.db "INSERT INTO events(timestamp,event_type,detail) VALUES(strftime('%s','now'),'webhook','$detail_esc')" 2>/dev/null || true
  fi
}

case "$EVENT" in
  github-push)
    echo "🔔 GitHub push detected"
    log_event "github-push: $PAYLOAD"
    PREV_AGENT=$(cat .agents/runtime/active-agent 2>/dev/null || echo "none")
    echo "reviewer" > .agents/runtime/active-agent
    echo "→ Switched to Reviewer for push review (was: $PREV_AGENT)"
    ;;
  github-pr)
    echo "🔔 GitHub PR detected"
    log_event "github-pr: $PAYLOAD"
    PREV_AGENT=$(cat .agents/runtime/active-agent 2>/dev/null || echo "none")
    echo "reviewer" > .agents/runtime/active-agent
    echo "→ Switched to Reviewer for PR review (was: $PREV_AGENT)"
    ;;
  ci-success)
    echo "✅ CI passed"
    log_event "ci-success: $PAYLOAD"
    PREV_AGENT=$(cat .agents/runtime/active-agent 2>/dev/null || echo "none")
    echo "tester" > .agents/runtime/active-agent
    echo "→ Switched to Tester for verification (was: $PREV_AGENT)"
    ;;
  ci-failure)
    echo "❌ CI failed"
    log_event "ci-failure: $PAYLOAD"
    PREV_AGENT=$(cat .agents/runtime/active-agent 2>/dev/null || echo "none")
    echo "implementer" > .agents/runtime/active-agent
    echo "→ Switched to Implementer for fix (was: $PREV_AGENT)"
    ;;
  wake)
    echo "🔔 Wake signal received"
    log_event "wake: $PAYLOAD"
    ;;
  *)
    echo "Unknown event: $EVENT"
    exit 1
    ;;
esac
