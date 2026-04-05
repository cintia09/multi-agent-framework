#!/bin/bash
# Install/update multi-agent framework skills to ~/.copilot/skills/
# Idempotent: safe to run multiple times
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILLS_DIR="$HOME/.copilot/skills"
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

# Ensure target directory exists
mkdir -p "$SKILLS_DIR"

# Copy skill files (always overwrite for updates)
COPIED=0
for f in "$SCRIPT_DIR/skills"/agent-*.md; do
  name=$(basename "$f")
  cp "$f" "$SKILLS_DIR/$name"
  echo "  ✅ $name"
  COPIED=$((COPIED + 1))
done

echo ""
echo "📄 Copied $COPIED skill files to $SKILLS_DIR"

# Handle copilot-instructions.md (idempotent: skip if already contains rules)
if [ -f "$INSTRUCTIONS" ]; then
  if grep -q "Multi-Agent 协作规则" "$INSTRUCTIONS"; then
    echo "⚠️  Agent rules already in copilot-instructions.md, skipping"
  else
    echo ""
    echo "📝 Appending agent rules to $INSTRUCTIONS"
    echo "" >> "$INSTRUCTIONS"
    cat "$SCRIPT_DIR/docs/agent-rules.md" >> "$INSTRUCTIONS"
    echo "  ✅ Agent rules appended"
  fi
else
  echo ""
  echo "📝 Creating $INSTRUCTIONS"
  cp "$SCRIPT_DIR/docs/agent-rules.md" "$INSTRUCTIONS"
  echo "  ✅ Created"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ "$MODE" = "update" ]; then
  echo "✅ Agent framework updated!"
else
  echo "✅ Agent framework installed!"
fi
echo ""
echo "Next steps:"
echo "  1. cd <your-project>"
echo "  2. Tell Copilot: '初始化 Agent 系统'"
echo "  3. Tell Copilot: '切换到验收者'"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
