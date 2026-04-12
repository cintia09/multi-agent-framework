#!/usr/bin/env bash
# HITL Terminal Adapter — Pure CLI review for headless/Docker environments
# No browser needed. Agent writes feedback JSON, user reviews in terminal.
#
# Usage:
#   bash scripts/hitl-adapters/terminal.sh publish <task_id> <role> <content_file>
#   bash scripts/hitl-adapters/terminal.sh poll    <task_id> <role>
#   bash scripts/hitl-adapters/terminal.sh get_feedback <task_id> <role>
#
# The agent calls publish → user reviews document → agent polls for decision.
# In terminal mode, the human interacts via the Agent's own ask_user mechanism.

set -euo pipefail

# Dependency check
if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 is required for HITL terminal adapter but not found" >&2
  exit 1
fi

PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
REVIEWS_DIR="$PROJECT_ROOT/.agents/reviews"
mkdir -p "$REVIEWS_DIR"

command="${1:-}"
task_id="${2:-}"
role="${3:-}"
content_file="${4:-}"

# Validate task_id and role (path traversal protection)
if [ -n "$task_id" ] && ! echo "$task_id" | grep -qE '^T-[0-9]+$'; then
  echo "ERROR: Invalid task_id format. Expected T-NNN" >&2
  exit 1
fi
if [ -n "$role" ] && ! echo "$role" | grep -qE '^(acceptor|designer|implementer|reviewer|tester)$'; then
  echo "ERROR: Invalid role. Expected one of: acceptor designer implementer reviewer tester" >&2
  exit 1
fi

case "$command" in
  publish)
    if [ -z "$task_id" ] || [ -z "$role" ] || [ -z "$content_file" ]; then
      echo "Usage: terminal.sh publish <task_id> <role> <content_file>"
      exit 1
    fi

    if [ ! -f "$content_file" ]; then
      echo "ERROR: Content file not found: $content_file" >&2
      exit 1
    fi

    # Clear any previous feedback
    rm -f "$REVIEWS_DIR/${task_id}-${role}-feedback.json"

    # Copy content for reference
    cp "$content_file" "$REVIEWS_DIR/${task_id}-${role}-content.md"

    # Write status
    cat > "$REVIEWS_DIR/${task_id}-${role}-terminal-status.json" <<EOF
{
  "task_id": "$task_id",
  "role": "$role",
  "status": "pending_review",
  "content_file": "$content_file",
  "published_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📋 HITL Review: $task_id ($role)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "📄 Document: $content_file"
    echo ""
    echo "--- Document Content ---"
    cat "$content_file"
    echo ""
    echo "--- End of Document ---"
    echo ""
    echo "📌 To approve/reject, the Agent will ask you directly."
    echo "   Respond with 'approve' or provide feedback text."
    echo ""
    echo "terminal://${task_id}/${role}"
    ;;

  poll)
    if [ -z "$task_id" ] || [ -z "$role" ]; then
      echo "Usage: terminal.sh poll <task_id> <role>"
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
      echo "Usage: terminal.sh get_feedback <task_id> <role>"
      exit 1
    fi

    feedback_file="$REVIEWS_DIR/${task_id}-${role}-feedback.json"
    if [ -f "$feedback_file" ]; then
      cat "$feedback_file"
    else
      echo '{"decision":"pending_review","feedback":""}'
    fi
    ;;

  *)
    echo "Usage: terminal.sh <publish|poll|get_feedback> <task_id> <role> [content_file]"
    exit 1
    ;;
esac
