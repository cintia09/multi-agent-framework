#!/usr/bin/env bash
# HITL Adapter: Confluence
# Creates/updates Confluence pages for HITL review, polls comments for approval
# Usage:
#   hitl-confluence.sh publish <task_id> <role> <content_md_file>
#   hitl-confluence.sh poll <task_id> <role>
#   hitl-confluence.sh get_feedback <task_id> <role>
#
# Requires: CONFLUENCE_BASE_URL, CONFLUENCE_SPACE_KEY, CONFLUENCE_PARENT_PAGE_ID, CONFLUENCE_TOKEN env vars
# Or configured in codenook/config.json under hitl.confluence

set -euo pipefail

# Dependency checks
if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 is required for HITL confluence adapter but not found" >&2
  exit 1
fi
if ! command -v curl >/dev/null 2>&1; then
  echo "ERROR: curl is required for HITL confluence adapter but not found" >&2
  exit 1
fi

PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
# Detect platform root: .github/codenook/ or .claude/codenook/
if [ -d "$PROJECT_ROOT/.github/codenook" ]; then
  CODENOOK_DIR="$PROJECT_ROOT/.github/codenook"
elif [ -d "$PROJECT_ROOT/.claude/codenook" ]; then
  CODENOOK_DIR="$PROJECT_ROOT/.claude/codenook"
else
  CODENOOK_DIR="$PROJECT_ROOT/.github/codenook"
fi
REVIEWS_DIR="$CODENOOK_DIR/reviews"
CONFIG_FILE="$CODENOOK_DIR/config.json"
mkdir -p "$REVIEWS_DIR"

# Load config
load_config() {
  if [ -f "$CONFIG_FILE" ]; then
    CONFLUENCE_BASE_URL="${CONFLUENCE_BASE_URL:-$(python3 -c "import json,sys; c=json.load(open(sys.argv[1])); print(c.get('hitl',{}).get('confluence',{}).get('base_url',''))" "$CONFIG_FILE" 2>/dev/null || echo "")}"
    CONFLUENCE_SPACE_KEY="${CONFLUENCE_SPACE_KEY:-$(python3 -c "import json,sys; c=json.load(open(sys.argv[1])); print(c.get('hitl',{}).get('confluence',{}).get('space_key',''))" "$CONFIG_FILE" 2>/dev/null || echo "")}"
    CONFLUENCE_PARENT_PAGE_ID="${CONFLUENCE_PARENT_PAGE_ID:-$(python3 -c "import json,sys; c=json.load(open(sys.argv[1])); print(c.get('hitl',{}).get('confluence',{}).get('parent_page_id',''))" "$CONFIG_FILE" 2>/dev/null || echo "")}"
    CONFLUENCE_TOKEN="${CONFLUENCE_TOKEN:-$(python3 -c "import json,sys; t=json.load(open(sys.argv[1])).get('hitl',{}).get('confluence',{}).get('auth',''); print(t.replace('env:',''))" "$CONFIG_FILE" 2>/dev/null || echo "")}"
    # Resolve env: prefix — only allow reading from whitelisted env var names
    ALLOWED_TOKEN_VARS="CONFLUENCE_TOKEN CONFLUENCE_API_KEY CONFLUENCE_PAT ATLASSIAN_TOKEN"
    if [ -n "$CONFLUENCE_TOKEN" ] && [ "$CONFLUENCE_TOKEN" != "CONFLUENCE_TOKEN" ]; then
      if echo " $ALLOWED_TOKEN_VARS " | grep -q " $CONFLUENCE_TOKEN "; then
        resolved=$(printenv "$CONFLUENCE_TOKEN" 2>/dev/null || echo "")
        [ -n "$resolved" ] && CONFLUENCE_TOKEN="$resolved"
      else
        echo "WARNING: env var '$CONFLUENCE_TOKEN' not in whitelist ($ALLOWED_TOKEN_VARS). Using literal value." >&2
      fi
    fi
  fi
}

load_config

cmd="${1:-help}"
task_id="${2:-}"
role="${3:-}"

case "$cmd" in
  publish)
    content_file="${4:-}"
    if [ -z "$task_id" ] || [ -z "$role" ] || [ -z "$content_file" ]; then
      echo "Usage: hitl-confluence.sh publish <task_id> <role> <content_md_file>"
      exit 1
    fi

    if [ -z "$CONFLUENCE_BASE_URL" ]; then
      echo "ERROR: CONFLUENCE_BASE_URL not set. Configure in codenook/config.json or env" >&2
      exit 1
    fi

    # H3 fix: validate inputs
    if ! echo "$task_id" | grep -qE '^T-[0-9]+$'; then
      echo "ERROR: Invalid task_id format" >&2; exit 1
    fi
    if ! echo "$role" | grep -qE '^(acceptor|designer|implementer|reviewer|tester)$'; then
      echo "ERROR: Invalid role" >&2; exit 1
    fi

    # Convert markdown to HTML (sanitize to prevent XSS)
    if command -v pandoc >/dev/null 2>&1; then
      # Use pandoc with sandbox to block raw HTML passthrough
      content_html=$(pandoc -f markdown-raw_html -t html "$content_file" 2>/dev/null)
    else
      content_html="<pre>$(cat "$content_file" | sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g')</pre>"
    fi

    title="HITL Review: ${task_id} - ${role}"

    # H1 fix: use jq to construct JSON safely (no injection)
    body_html="<h2>Status: ⏳ Pending Review</h2><p>Comment <b>approved</b> to approve, or add feedback comments.</p><hr/>${content_html}"
    page_data=$(python3 -c "
import json, sys
data = {
    'type': 'page',
    'title': sys.argv[1],
    'space': {'key': sys.argv[2]},
    'ancestors': [{'id': sys.argv[3]}],
    'body': {
        'storage': {
            'value': sys.argv[4],
            'representation': 'storage'
        }
    }
}
print(json.dumps(data))
" "$title" "$CONFLUENCE_SPACE_KEY" "$CONFLUENCE_PARENT_PAGE_ID" "$body_html")

    response=$(curl -sf -X POST \
      "${CONFLUENCE_BASE_URL}/rest/api/content" \
      -H "Authorization: Bearer ${CONFLUENCE_TOKEN}" \
      -H "Content-Type: application/json" \
      -d "$page_data" 2>/dev/null)
    
    if [ $? -ne 0 ] || [ -z "$response" ]; then
      echo "ERROR: Confluence API request failed. Check CONFLUENCE_BASE_URL and CONFLUENCE_TOKEN." >&2
      exit 1
    fi

    page_id=$(echo "$response" | python3 -c "import json,sys; print(json.load(sys.stdin).get('id',''))" 2>/dev/null || echo "")

    if [ -n "$page_id" ]; then
      echo "$page_id" > "$REVIEWS_DIR/${task_id}-${role}-confluence.txt"
      page_url="${CONFLUENCE_BASE_URL}/pages/viewpage.action?pageId=${page_id}"
      echo "$page_url"
    else
      echo "ERROR: Failed to create Confluence page" >&2
      echo "$response" >&2
      exit 1
    fi
    ;;

  poll)
    if [ -z "$task_id" ] || [ -z "$role" ]; then
      echo "Usage: hitl-confluence.sh poll <task_id> <role>"
      exit 1
    fi

    page_file="$REVIEWS_DIR/${task_id}-${role}-confluence.txt"
    if [ ! -f "$page_file" ]; then
      echo "pending_review"
      exit 0
    fi

    page_id=$(cat "$page_file")

    comments=$(curl -s \
      "${CONFLUENCE_BASE_URL}/rest/api/content/${page_id}/child/comment" \
      -H "Authorization: Bearer ${CONFLUENCE_TOKEN}" 2>/dev/null || echo '{"results":[]}')

    status=$(echo "$comments" | python3 -c "
import json, sys
data = json.load(sys.stdin)
for c in data.get('results', []):
    body = c.get('body', {}).get('storage', {}).get('value', '').strip().lower()
    if 'approved' in body or 'lgtm' in body:
        print('approved')
        sys.exit(0)
    elif body:
        print('feedback')
        sys.exit(0)
print('pending_review')
" 2>/dev/null || echo "pending_review")

    echo "$status"
    ;;

  get_feedback)
    if [ -z "$task_id" ] || [ -z "$role" ]; then
      echo "Usage: hitl-confluence.sh get_feedback <task_id> <role>"
      exit 1
    fi

    page_file="$REVIEWS_DIR/${task_id}-${role}-confluence.txt"
    if [ ! -f "$page_file" ]; then
      echo '{"status":"no_page"}'
      exit 0
    fi

    page_id=$(cat "$page_file")
    curl -s \
      "${CONFLUENCE_BASE_URL}/rest/api/content/${page_id}/child/comment?expand=body.storage" \
      -H "Authorization: Bearer ${CONFLUENCE_TOKEN}" 2>/dev/null || echo '{"results":[]}'
    ;;

  *)
    echo "HITL Confluence Adapter"
    echo "Commands: publish, poll, get_feedback"
    echo "Config: codenook/config.json → hitl.confluence.{base_url, space_key, parent_page_id, auth}"
    ;;
esac
