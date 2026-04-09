#!/usr/bin/env bash
# verify-init.sh — Verify Agent system initialization in a project
# Usage: bash scripts/verify-init.sh [project_dir]
set -euo pipefail

PROJECT_DIR="${1:-.}"
AGENTS_DIR="$PROJECT_DIR/.agents"

PASS=0
FAIL=0

check() {
  local label="$1" result="$2"
  if [ "$result" = "pass" ]; then
    echo "  ✅ $label"
    PASS=$((PASS + 1))
  else
    echo "  ❌ $label"
    FAIL=$((FAIL + 1))
  fi
}

echo "🔍 Agent System Init Verification"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Directory: $AGENTS_DIR"
echo ""

# Directory structure
echo "📁 Directory Structure:"
check ".agents/ exists" "$([ -d "$AGENTS_DIR" ] && echo pass || echo fail)"
check "skills/ exists" "$([ -d "$AGENTS_DIR/skills" ] && echo pass || echo fail)"
check "tasks/ exists" "$([ -d "$AGENTS_DIR/tasks" ] && echo pass || echo fail)"
check "runtime/ exists" "$([ -d "$AGENTS_DIR/runtime" ] && echo pass || echo fail)"

# Project skills
echo ""
echo "📄 Project Skills (expect 6):"
SKILL_COUNT=$(ls -d "$AGENTS_DIR"/skills/project-* 2>/dev/null | wc -l | tr -d ' ')
check "Project skill dirs: $SKILL_COUNT/6" "$([ "$SKILL_COUNT" -eq 6 ] && echo pass || echo fail)"

for name in project-agents-context project-acceptor project-designer project-implementer project-reviewer project-tester; do
  if [ -f "$AGENTS_DIR/skills/$name/SKILL.md" ]; then
    check "$name/SKILL.md" "pass"
  else
    check "$name/SKILL.md" "fail"
  fi
done

# Runtime agents
echo ""
echo "🤖 Runtime Agents (expect 5):"
for agent in acceptor designer implementer reviewer tester; do
  AGENT_DIR="$AGENTS_DIR/runtime/$agent"
  if [ -f "$AGENT_DIR/state.json" ]; then
    # Validate JSON
    if jq -e --arg agent "$agent" '.agent == $agent' "$AGENT_DIR/state.json" >/dev/null 2>&1; then
      check "$agent/state.json (valid)" "pass"
    else
      check "$agent/state.json (invalid format)" "fail"
    fi
  else
    check "$agent/state.json" "fail"
  fi

  check "$agent/inbox.json" "$([ -f "$AGENT_DIR/inbox.json" ] && echo pass || echo fail)"
  check "$agent/workspace/" "$([ -d "$AGENT_DIR/workspace" ] && echo pass || echo fail)"
done

# Task board
echo ""
echo "📋 Task Board:"
if [ -f "$AGENTS_DIR/task-board.json" ]; then
  if jq -e 'has("version") and has("tasks")' "$AGENTS_DIR/task-board.json" >/dev/null 2>&1; then
    TASK_COUNT=$(jq '.tasks | length' "$AGENTS_DIR/task-board.json")
    check "task-board.json (valid, $TASK_COUNT tasks)" "pass"
  else
    check "task-board.json (invalid schema)" "fail"
  fi
else
  check "task-board.json" "fail"
fi
check "task-board.md" "$([ -f "$AGENTS_DIR/task-board.md" ] && echo pass || echo fail)"

# Events DB
echo ""
echo "📊 Events DB:"
if [ -f "$AGENTS_DIR/events.db" ]; then
  TABLE_COUNT=$(sqlite3 "$AGENTS_DIR/events.db" "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='events';" 2>/dev/null || echo 0)
  check "events.db (events table: $TABLE_COUNT)" "$([ "$TABLE_COUNT" -eq 1 ] && echo pass || echo fail)"
else
  check "events.db" "fail"
fi

# Gitignore
echo ""
echo "📝 Configuration:"
check ".gitignore" "$([ -f "$AGENTS_DIR/.gitignore" ] && echo pass || echo fail)"

# Summary
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Results: $PASS passed, $FAIL failed"
if [ "$FAIL" -eq 0 ]; then
  echo "✅ Init verified successfully!"
else
  echo "❌ Init has $FAIL issue(s) — see above"
  exit 1
fi
