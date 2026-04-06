#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ERRORS=0

for agent_file in "${REPO_DIR}/agents/"*.agent.md; do
    agent_name=$(basename "$agent_file")
    
    # Check YAML frontmatter
    if ! head -1 "$agent_file" | grep -q "^---"; then
        echo "  ❌ ${agent_name}: Missing YAML frontmatter"
        ERRORS=$((ERRORS + 1))
        continue
    fi
    
    # Check name field
    if ! grep -q "^name:" "$agent_file"; then
        echo "  ❌ ${agent_name}: Missing 'name:' in frontmatter"
        ERRORS=$((ERRORS + 1))
        continue
    fi
done

# Check count
AGENT_COUNT=$(ls "${REPO_DIR}/agents/"*.agent.md 2>/dev/null | wc -l | tr -d ' ')
if [ "$AGENT_COUNT" -lt 5 ]; then
    echo "  ❌ Expected 5 agents, found ${AGENT_COUNT}"
    ERRORS=$((ERRORS + 1))
fi

exit $ERRORS
