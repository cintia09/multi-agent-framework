#!/bin/bash
# Install multi-agent framework skills to ~/.copilot/skills/
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILLS_DIR="$HOME/.copilot/skills"
INSTRUCTIONS="$HOME/.copilot/instructions.md"

echo "🚀 Installing Multi-Agent Framework..."
echo ""

# Ensure target directory exists
mkdir -p "$SKILLS_DIR"

# Copy skill files
COPIED=0
for f in "$SCRIPT_DIR/skills"/agent-*.md; do
  name=$(basename "$f")
  cp "$f" "$SKILLS_DIR/$name"
  echo "  ✅ $name"
  COPIED=$((COPIED + 1))
done

echo ""
echo "📄 Copied $COPIED skill files to $SKILLS_DIR"

# Handle instructions.md
if [ -f "$INSTRUCTIONS" ]; then
  if grep -q "Multi-Agent 协作规则" "$INSTRUCTIONS"; then
    echo "⚠️  instructions.md already contains agent rules, skipping"
  else
    echo ""
    echo "📝 Appending agent rules to $INSTRUCTIONS"
    echo "" >> "$INSTRUCTIONS"
    cat "$SCRIPT_DIR/docs/global-instructions.md" >> "$INSTRUCTIONS"
    echo "  ✅ Agent rules appended"
  fi
else
  echo ""
  echo "📝 Creating $INSTRUCTIONS"
  cp "$SCRIPT_DIR/docs/global-instructions.md" "$INSTRUCTIONS"
  echo "  ✅ Created"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Installation complete!"
echo ""
echo "Next steps:"
echo "  1. cd <your-project>"
echo "  2. Tell Copilot: '/init agents'"
echo "  3. Tell Copilot: '/agent acceptor'"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
