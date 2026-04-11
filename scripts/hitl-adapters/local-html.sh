#!/usr/bin/env bash
# HITL Adapter: Local HTML
# Generates a local HTML review page from markdown content
# Usage:
#   hitl-local-html.sh publish <task_id> <role> <content_md_file>
#   hitl-local-html.sh poll <task_id> <role>
#   hitl-local-html.sh get_feedback <task_id> <role>

set -euo pipefail

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

    # Convert markdown to HTML (basic conversion)
    content_html=""
    if command -v pandoc >/dev/null 2>&1; then
      content_html=$(pandoc -f markdown -t html "$content_file" 2>/dev/null)
    else
      # Fallback: wrap in <pre> tag
      content_html="<pre>$(cat "$content_file" | sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g')</pre>"
    fi

    # C1 fix: pass role as argument, not embedded in string
    role_emoji=$(echo "$ROLE_EMOJI_MAP" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get(sys.argv[1],'📋'))" "$role" 2>/dev/null || echo "📋")

    # Generate HTML from template
    output_file="$REVIEWS_DIR/${task_id}-${role}.html"
    feedback_path="$REVIEWS_DIR/${task_id}-${role}-feedback.json"

    sed \
      -e "s|{{TASK_ID}}|${task_id}|g" \
      -e "s|{{ROLE}}|${role}|g" \
      -e "s|{{ROLE_EMOJI}}|${role_emoji}|g" \
      -e "s|{{FEEDBACK_PATH}}|${feedback_path}|g" \
      "$TEMPLATE" > "$output_file.tmp"

    # C2 fix: write content to temp file, read in Python (no string embedding)
    CONTENT_TMP=$(mktemp)
    echo "$content_html" > "$CONTENT_TMP"
    # Find available port (8900-8999 range)
    HITL_PORT=""
    for p in $(seq 8900 8999); do
      if ! lsof -i ":$p" >/dev/null 2>&1; then
        HITL_PORT=$p
        break
      fi
    done
    if [ -z "$HITL_PORT" ]; then
      HITL_PORT=8900
    fi

    # Start HITL review server in background
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    python3 "$SCRIPT_DIR/hitl-server.py" "$HITL_PORT" "$task_id" "$role" "$content_file" "$REVIEWS_DIR" &
    SERVER_PID=$!
    echo "$SERVER_PID" > "$REVIEWS_DIR/${task_id}-${role}-server.pid"

    # Wait briefly for server to start
    sleep 1

    # Open in browser
    review_url="http://127.0.0.1:${HITL_PORT}"
    if [ "$(uname)" = "Darwin" ]; then
      open "$review_url" 2>/dev/null || true
    elif command -v xdg-open >/dev/null 2>&1; then
      xdg-open "$review_url" 2>/dev/null || true
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
