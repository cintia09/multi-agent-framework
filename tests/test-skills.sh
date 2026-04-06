#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ERRORS=0

for skill_dir in "${REPO_DIR}/skills/agent-"*/; do
    skill_name=$(basename "$skill_dir")
    skill_file="${skill_dir}SKILL.md"
    
    # Check SKILL.md exists
    if [ ! -f "$skill_file" ]; then
        echo "  ❌ ${skill_name}: SKILL.md not found"
        ERRORS=$((ERRORS + 1))
        continue
    fi
    
    # Check YAML frontmatter
    if ! head -1 "$skill_file" | grep -q "^---"; then
        echo "  ❌ ${skill_name}: Missing YAML frontmatter"
        ERRORS=$((ERRORS + 1))
        continue
    fi
    
    # Check name field
    if ! grep -q "^name:" "$skill_file"; then
        echo "  ❌ ${skill_name}: Missing 'name:' in frontmatter"
        ERRORS=$((ERRORS + 1))
        continue
    fi
    
    # Check description field
    if ! grep -q "^description:" "$skill_file"; then
        echo "  ❌ ${skill_name}: Missing 'description:' in frontmatter"
        ERRORS=$((ERRORS + 1))
        continue
    fi
done

exit $ERRORS
