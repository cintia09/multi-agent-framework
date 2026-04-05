#!/bin/bash
# verify-install.sh — Verify Multi-Agent Framework installation
# Usage: bash scripts/verify-install.sh
set -e

PASS=0
FAIL=0
WARN=0

check() {
  local label="$1" result="$2"
  if [ "$result" = "pass" ]; then
    echo "  ✅ $label"
    PASS=$((PASS + 1))
  elif [ "$result" = "warn" ]; then
    echo "  ⚠️  $label"
    WARN=$((WARN + 1))
  else
    echo "  ❌ $label"
    FAIL=$((FAIL + 1))
  fi
}

echo "🔍 Multi-Agent Framework Install Verification"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Skills
echo ""
echo "📦 Skills (expect 12):"
SKILL_COUNT=$(ls -d ~/.copilot/skills/agent-*/ 2>/dev/null | wc -l | tr -d ' ')
check "Skill directories: $SKILL_COUNT/12" "$([ "$SKILL_COUNT" -eq 12 ] && echo pass || echo fail)"

for name in agent-acceptor agent-designer agent-events agent-fsm agent-implementer agent-init agent-memory agent-messaging agent-reviewer agent-switch agent-task-board agent-tester; do
  if [ -f ~/.copilot/skills/$name/SKILL.md ]; then
    # Check YAML frontmatter
    if head -1 ~/.copilot/skills/$name/SKILL.md | grep -q "^---"; then
      HAS_NAME=$(grep -c "^name:" ~/.copilot/skills/$name/SKILL.md)
      HAS_DESC=$(grep -c "^description:" ~/.copilot/skills/$name/SKILL.md)
      if [ "$HAS_NAME" -gt 0 ] && [ "$HAS_DESC" -gt 0 ]; then
        check "$name/SKILL.md (frontmatter OK)" "pass"
      else
        check "$name/SKILL.md (missing name or description)" "fail"
      fi
    else
      check "$name/SKILL.md (no YAML frontmatter)" "fail"
    fi
  else
    check "$name/SKILL.md" "fail"
  fi
done

# Agents
echo ""
echo "🤖 Agents (expect 5):"
AGENT_COUNT=$(ls ~/.copilot/agents/*.agent.md 2>/dev/null | wc -l | tr -d ' ')
check "Agent profiles: $AGENT_COUNT/5" "$([ "$AGENT_COUNT" -eq 5 ] && echo pass || echo fail)"

for name in acceptor designer implementer reviewer tester; do
  if [ -f ~/.copilot/agents/$name.agent.md ]; then
    if head -1 ~/.copilot/agents/$name.agent.md | grep -q "^---"; then
      check "$name.agent.md (frontmatter OK)" "pass"
    else
      check "$name.agent.md (no YAML frontmatter)" "fail"
    fi
  else
    check "$name.agent.md" "fail"
  fi
done

# Hooks
echo ""
echo "🪝 Hooks (expect 5 scripts + hooks.json):"
for script in security-scan.sh agent-session-start.sh agent-pre-tool-use.sh agent-post-tool-use.sh agent-staleness-check.sh; do
  if [ -f ~/.copilot/hooks/$script ]; then
    if [ -x ~/.copilot/hooks/$script ]; then
      check "$script (executable)" "pass"
    else
      check "$script (NOT executable)" "fail"
    fi
  else
    check "$script" "fail"
  fi
done

if [ -f ~/.copilot/hooks/hooks.json ]; then
  if python3 -c "import json; json.load(open('$HOME/.copilot/hooks/hooks.json'))" 2>/dev/null; then
    check "hooks.json (valid JSON)" "pass"
  else
    check "hooks.json (invalid JSON)" "fail"
  fi
else
  check "hooks.json" "fail"
fi

# Rules
echo ""
echo "📋 Collaboration Rules:"
if grep -q "## Agent Collaboration Rules" ~/.copilot/copilot-instructions.md 2>/dev/null; then
  check "Rules in copilot-instructions.md" "pass"
else
  check "Rules in copilot-instructions.md" "warn"
fi

# Summary
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Results: $PASS passed, $FAIL failed, $WARN warnings"
if [ "$FAIL" -eq 0 ]; then
  echo "✅ Installation verified successfully!"
else
  echo "❌ Installation has $FAIL issue(s) — see above"
  exit 1
fi
