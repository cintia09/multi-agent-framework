#!/usr/bin/env bash
# HITL Adapter: GitHub Issues
# Creates GitHub Issues for HITL review, polls for approval via comments/reactions
# Usage:
#   hitl-github-issue.sh publish <task_id> <role> <content_md_file>
#   hitl-github-issue.sh poll <task_id> <role>
#   hitl-github-issue.sh get_feedback <task_id> <role>
#
# Requires: gh CLI authenticated

set -euo pipefail

# Dependency checks
if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 is required for HITL github-issue adapter but not found" >&2
  exit 1
fi
if ! command -v gh >/dev/null 2>&1; then
  echo "ERROR: gh CLI is required for HITL github-issue adapter but not found" >&2
  exit 1
fi

AGENTS_DIR="$(git rev-parse --show-toplevel 2>/dev/null)/.agents"
[ -d "$AGENTS_DIR" ] || AGENTS_DIR="./.agents"
REVIEWS_DIR="$AGENTS_DIR/reviews"
mkdir -p "$REVIEWS_DIR"

# Get repo info
REPO_OWNER=$(git remote get-url origin 2>/dev/null | sed -E 's|.*[:/]([^/]+)/([^/]+)(\.git)?$|\1|')
REPO_NAME=$(git remote get-url origin 2>/dev/null | sed -E 's|.*[:/]([^/]+)/([^/]+)(\.git)?$|\2|' | sed 's/\.git$//')

cmd="${1:-help}"
task_id="${2:-}"
role="${3:-}"

case "$cmd" in
  publish)
    content_file="${4:-}"
    if [ -z "$task_id" ] || [ -z "$role" ] || [ -z "$content_file" ]; then
      echo "Usage: hitl-github-issue.sh publish <task_id> <role> <content_md_file>"
      exit 1
    fi

    # H3 fix: validate inputs
    if ! echo "$task_id" | grep -qE '^T-[0-9]+$'; then
      echo "ERROR: Invalid task_id format" >&2; exit 1
    fi
    if ! echo "$role" | grep -qE '^(acceptor|designer|implementer|reviewer|tester)$'; then
      echo "ERROR: Invalid role" >&2; exit 1
    fi

    content=$(cat "$content_file")
    title="🚪 HITL Review: ${task_id} — ${role}"
    body="## Human-in-the-Loop Review

**Task**: ${task_id}
**Role**: ${role}
**Status**: ⏳ Pending Review

---

${content}

---

### How to review:
- Comment **\`approved\`** or **\`LGTM\`** to approve
- Comment with feedback to request changes
- Add 👍 reaction to approve"

    # Create issue
    issue_url=$(GH_TOKEN="" gh issue create \
      --repo "${REPO_OWNER}/${REPO_NAME}" \
      --title "$title" \
      --body "$body" \
      --label "hitl-review" 2>/dev/null || echo "")

    if [ -n "$issue_url" ]; then
      # Extract issue number
      issue_number=$(echo "$issue_url" | grep -oE '[0-9]+$')
      echo "$issue_number" > "$REVIEWS_DIR/${task_id}-${role}-issue.txt"
      echo "$issue_url"
    else
      echo "ERROR: Failed to create GitHub issue" >&2
      exit 1
    fi
    ;;

  poll)
    if [ -z "$task_id" ] || [ -z "$role" ]; then
      echo "Usage: hitl-github-issue.sh poll <task_id> <role>"
      exit 1
    fi

    issue_file="$REVIEWS_DIR/${task_id}-${role}-issue.txt"
    if [ ! -f "$issue_file" ]; then
      echo "pending_review"
      exit 0
    fi

    issue_number=$(cat "$issue_file")

    # Check comments for approval keywords
    comments=$(GH_TOKEN="" gh issue view "$issue_number" \
      --repo "${REPO_OWNER}/${REPO_NAME}" \
      --comments --json comments 2>/dev/null || echo '{"comments":[]}')

    approved=$(echo "$comments" | python3 -c "
import json, sys
data = json.load(sys.stdin)
for c in data.get('comments', []):
    body = c.get('body', '').strip().lower()
    if body in ('approved', 'lgtm', '✅', 'approve'):
        print('approved')
        sys.exit(0)
    elif body not in ('', 'pending'):
        print('feedback')
        sys.exit(0)
print('pending_review')
" 2>/dev/null || echo "pending_review")

    echo "$approved"
    ;;

  get_feedback)
    if [ -z "$task_id" ] || [ -z "$role" ]; then
      echo "Usage: hitl-github-issue.sh get_feedback <task_id> <role>"
      exit 1
    fi

    issue_file="$REVIEWS_DIR/${task_id}-${role}-issue.txt"
    if [ ! -f "$issue_file" ]; then
      echo '{"status":"no_issue"}'
      exit 0
    fi

    issue_number=$(cat "$issue_file")
    GH_TOKEN="" gh issue view "$issue_number" \
      --repo "${REPO_OWNER}/${REPO_NAME}" \
      --comments --json comments 2>/dev/null || echo '{"comments":[]}'
    ;;

  *)
    echo "HITL GitHub Issue Adapter"
    echo "Commands: publish, poll, get_feedback"
    ;;
esac
