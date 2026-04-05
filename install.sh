#!/bin/bash
# Install/update multi-agent framework to ~/.copilot/
# Idempotent: safe to run multiple times
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILLS_DIR="$HOME/.copilot/skills"
AGENTS_DIR="$HOME/.copilot/agents"
INSTRUCTIONS="$HOME/.copilot/copilot-instructions.md"

# Detect install vs update
if [ -f "$SKILLS_DIR/agent-fsm.md" ]; then
  MODE="update"
  echo "🔄 Updating Multi-Agent Framework..."
else
  MODE="install"
  echo "🚀 Installing Multi-Agent Framework..."
fi
echo ""

# 1. Copy skill files
mkdir -p "$SKILLS_DIR"
COPIED=0
for f in "$SCRIPT_DIR/skills"/agent-*.md; do
  name=$(basename "$f")
  cp "$f" "$SKILLS_DIR/$name"
  echo "  ✅ skill: $name"
  COPIED=$((COPIED + 1))
done
echo "  📄 $COPIED skills → $SKILLS_DIR"
echo ""

# 2. Copy agent templates
for agent in acceptor designer implementer reviewer tester; do
  mkdir -p "$AGENTS_DIR/$agent/skills"
  cp "$SCRIPT_DIR/agents/$agent/instructions.md" "$AGENTS_DIR/$agent/"
  echo "  ✅ agent: $agent/instructions.md"
done
echo "  📄 5 agent templates → $AGENTS_DIR"
echo ""

# 3. Copy global AGENTS.md (project init guide)
cp "$SCRIPT_DIR/docs/AGENTS-global.md" "$HOME/.copilot/AGENTS.md"
echo "  ✅ AGENTS.md → ~/.copilot/AGENTS.md"
echo ""

# 4. Handle copilot-instructions.md
if [ -f "$INSTRUCTIONS" ]; then
  if grep -q "Multi-Agent 协作规则" "$INSTRUCTIONS"; then
    echo "  ⚠️  Agent rules already present, skipping"
  else
    echo "" >> "$INSTRUCTIONS"
    cat "$SCRIPT_DIR/docs/agent-rules.md" >> "$INSTRUCTIONS"
    echo "  ✅ Agent rules appended"
  fi
else
  cp "$SCRIPT_DIR/docs/agent-rules.md" "$INSTRUCTIONS"
  echo "  ✅ Created copilot-instructions.md"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ "$MODE" = "update" ]; then
  echo "✅ Agent framework updated!"
else
  echo "✅ Agent framework installed!"
fi
echo ""
echo "  Skills: $COPIED → ~/.copilot/skills/"
echo "  Agents: 5 templates → ~/.copilot/agents/"
echo "  Guide:  AGENTS.md → ~/.copilot/"
echo ""
echo "Next steps:"
echo "  1. cd <your-project>"
echo "  2. Run /init (auto-creates project agent dirs)"
echo "  3. Say '切换到验收者'"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
