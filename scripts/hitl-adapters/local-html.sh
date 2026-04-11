#!/usr/bin/env bash
# HITL Adapter: Local HTML
# Generates a local HTML review page from markdown content
# Usage:
#   hitl-local-html.sh publish <task_id> <role> <content_md_file>
#   hitl-local-html.sh poll <task_id> <role>
#   hitl-local-html.sh get_feedback <task_id> <role>

set -euo pipefail

# Dependency check
if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 is required for HITL local-html adapter but not found" >&2
  exit 1
fi

AGENTS_DIR="$(git rev-parse --show-toplevel 2>/dev/null)/.agents"
[ -d "$AGENTS_DIR" ] || AGENTS_DIR="./.agents"
REVIEWS_DIR="$AGENTS_DIR/reviews"
TEMPLATE="$AGENTS_DIR/templates/review-page.html"

ROLE_EMOJI_MAP='{"acceptor":"🎯","designer":"🏗️","implementer":"💻","reviewer":"🔍","tester":"🧪"}'

mkdir -p "$REVIEWS_DIR"

cmd="${1:-help}"
task_id="${2:-}"
role="${3:-}"

case "$cmd" in
  publish)
    content_file="${4:-}"
    if [ -z "$task_id" ] || [ -z "$role" ] || [ -z "$content_file" ]; then
      echo "Usage: hitl-local-html.sh publish <task_id> <role> <content_md_file>"
      exit 1
    fi

    # H3 fix: validate task_id and role to prevent path traversal
    if ! echo "$task_id" | grep -qE '^T-[0-9]+$'; then
      echo "ERROR: Invalid task_id format (expected T-NNN)" >&2
      exit 1
    fi
    if ! echo "$role" | grep -qE '^(acceptor|designer|implementer|reviewer|tester)$'; then
      echo "ERROR: Invalid role" >&2
      exit 1
    fi

    # Find available port (8900-8999 range)
    HITL_PORT=""
    for p in $(seq 8900 8999); do
      if ! lsof -i ":$p" >/dev/null 2>&1; then
        HITL_PORT=$p
        break
      fi
    done
    if [ -z "$HITL_PORT" ]; then
      echo "ERROR: No available port in range 8900-8999. Close some HITL servers first." >&2
      echo "  To list: lsof -i :8900-8999" >&2
      exit 1
    fi

    # Start HITL review server in background
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

    # Detect headless environment (Docker, SSH, no DISPLAY)
    BIND_HOST="127.0.0.1"
    HEADLESS=false
    if [ -f /.dockerenv ] || grep -q docker /proc/1/cgroup 2>/dev/null; then
      BIND_HOST="0.0.0.0"
      HEADLESS=true
    elif [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] && [ "$(uname)" != "Darwin" ]; then
      HEADLESS=true
    fi

    python3 "$SCRIPT_DIR/hitl-server.py" "$HITL_PORT" "$task_id" "$role" "$content_file" "$REVIEWS_DIR" "$BIND_HOST" &
    SERVER_PID=$!
    echo "$SERVER_PID" > "$REVIEWS_DIR/${task_id}-${role}-server.pid"

    # Wait briefly and verify server started
    sleep 1
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
      echo "ERROR: HITL server failed to start (PID $SERVER_PID exited). Check python3 and port $HITL_PORT." >&2
      rm -f "$REVIEWS_DIR/${task_id}-${role}-server.pid"
      exit 1
    fi

    # Build review URL
    if [ "$BIND_HOST" = "0.0.0.0" ]; then
      HOSTNAME_DISPLAY=$(hostname -I 2>/dev/null | awk '{print $1}')
      [ -z "$HOSTNAME_DISPLAY" ] && HOSTNAME_DISPLAY=$(hostname)
      review_url="http://${HOSTNAME_DISPLAY}:${HITL_PORT}"
    else
      review_url="http://127.0.0.1:${HITL_PORT}"
    fi

    # Open in browser (skip in headless)
    if [ "$HEADLESS" = "false" ]; then
      if [ "$(uname)" = "Darwin" ]; then
        open "$review_url" 2>/dev/null || true
      elif command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$review_url" 2>/dev/null || true
      fi
    fi

    echo "$review_url"
    ;;

  poll)
    if [ -z "$task_id" ] || [ -z "$role" ]; then
      echo "Usage: hitl-local-html.sh poll <task_id> <role>"
      exit 1
    fi

    feedback_file="$REVIEWS_DIR/${task_id}-${role}-feedback.json"
    if [ -f "$feedback_file" ]; then
      decision=$(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(d.get('decision','pending'))" "$feedback_file" 2>/dev/null || echo "pending")
      echo "$decision"
    else
      echo "pending_review"
    fi
    ;;

  get_feedback)
    if [ -z "$task_id" ] || [ -z "$role" ]; then
      echo "Usage: hitl-local-html.sh get_feedback <task_id> <role>"
      exit 1
    fi

    feedback_file="$REVIEWS_DIR/${task_id}-${role}-feedback.json"
    if [ -f "$feedback_file" ]; then
      cat "$feedback_file"
    else
      echo '{"status":"no_feedback"}'
    fi
    ;;

  stop)
    if [ -z "$task_id" ] || [ -z "$role" ]; then
      echo "Usage: hitl-local-html.sh stop <task_id> <role>"
      exit 1
    fi

    pid_file="$REVIEWS_DIR/${task_id}-${role}-server.pid"
    if [ -f "$pid_file" ]; then
      pid=$(cat "$pid_file")
      kill "$pid" 2>/dev/null && echo "Server stopped (PID: $pid)" || echo "Server already stopped"
      rm -f "$pid_file"
    else
      echo "No running server found"
    fi
    ;;

  *)
    echo "HITL Local HTML Adapter"
    echo "Commands: publish, poll, get_feedback, stop"
    ;;
esac
