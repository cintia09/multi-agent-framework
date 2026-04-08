#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ERRORS=0

EXPECTED_HOOKS=(
    "agent-session-start.sh"
    "agent-pre-tool-use.sh"
    "agent-post-tool-use.sh"
    "agent-staleness-check.sh"
    "agent-before-switch.sh"
    "agent-after-switch.sh"
    "agent-before-task-create.sh"
    "agent-after-task-status.sh"
    "agent-before-memory-write.sh"
    "agent-after-memory-write.sh"
    "agent-before-compaction.sh"
    "agent-on-goal-verified.sh"
    "security-scan.sh"
)

for hook in "${EXPECTED_HOOKS[@]}"; do
    hook_file="${REPO_DIR}/hooks/${hook}"
    
    if [ ! -f "$hook_file" ]; then
        echo "  ❌ ${hook}: not found"
        ERRORS=$((ERRORS + 1))
        continue
    fi
    
    # Check executable
    if [ ! -x "$hook_file" ]; then
        echo "  ❌ ${hook}: not executable"
        ERRORS=$((ERRORS + 1))
        continue
    fi
    
    # Check shebang
    if ! head -1 "$hook_file" | grep -q "^#!/"; then
        echo "  ❌ ${hook}: missing shebang"
        ERRORS=$((ERRORS + 1))
        continue
    fi
done

# Check hooks.json
if [ ! -f "${REPO_DIR}/hooks/hooks.json" ]; then
    echo "  ❌ hooks.json: not found"
    ERRORS=$((ERRORS + 1))
fi

exit $ERRORS
