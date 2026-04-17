#!/usr/bin/env bash
# CodeNook v5.0 POC bootstrap script
# Generates a .codenook/ workspace in the current directory.
set -euo pipefail

TARGET_DIR="${1:-$(pwd)}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATES_DIR="$SCRIPT_DIR/templates"

if [[ ! -d "$TEMPLATES_DIR" ]]; then
  echo "Error: templates directory not found at $TEMPLATES_DIR" >&2
  exit 1
fi

cd "$TARGET_DIR"

if [[ -d ".codenook" ]]; then
  echo "Warning: .codenook/ already exists at $TARGET_DIR"
  read -p "Overwrite? (y/N) " -n 1 -r
  echo
  [[ ! $REPLY =~ ^[Yy]$ ]] && { echo "Aborted."; exit 0; }
  rm -rf .codenook
fi

echo "Bootstrapping CodeNook v5.0 POC at: $TARGET_DIR"

mkdir -p .codenook/{core,prompts-templates,prompts-criteria,agents,project,tasks,knowledge/by-role,knowledge/by-topic,history,hitl-queue/pending}

# Copy templates
cp "$TEMPLATES_DIR/core/codenook-core.md"              .codenook/core/
cp "$TEMPLATES_DIR/prompts-templates/clarifier.md"     .codenook/prompts-templates/
cp "$TEMPLATES_DIR/prompts-templates/implementer.md"   .codenook/prompts-templates/
cp "$TEMPLATES_DIR/prompts-templates/reviewer.md"      .codenook/prompts-templates/
cp "$TEMPLATES_DIR/prompts-templates/synthesizer.md"   .codenook/prompts-templates/
cp "$TEMPLATES_DIR/prompts-templates/validator.md"     .codenook/prompts-templates/
cp "$TEMPLATES_DIR/prompts-criteria/criteria-clarify.md"   .codenook/prompts-criteria/
cp "$TEMPLATES_DIR/prompts-criteria/criteria-implement.md" .codenook/prompts-criteria/
cp "$TEMPLATES_DIR/prompts-criteria/criteria-review.md"    .codenook/prompts-criteria/
cp "$TEMPLATES_DIR/agents/clarifier.agent.md"          .codenook/agents/
cp "$TEMPLATES_DIR/agents/implementer.agent.md"        .codenook/agents/
cp "$TEMPLATES_DIR/agents/reviewer.agent.md"           .codenook/agents/
cp "$TEMPLATES_DIR/agents/synthesizer.agent.md"        .codenook/agents/
cp "$TEMPLATES_DIR/agents/validator.agent.md"          .codenook/agents/
cp "$TEMPLATES_DIR/project/ENVIRONMENT.md"             .codenook/project/
cp "$TEMPLATES_DIR/project/CONVENTIONS.md"             .codenook/project/
cp "$TEMPLATES_DIR/project/ARCHITECTURE.md"            .codenook/project/
cp "$TEMPLATES_DIR/config.yaml"                        .codenook/
cp "$TEMPLATES_DIR/state.json"                         .codenook/

# Bootloader (`CLAUDE.md` — read by both Claude Code and Copilot CLI)
cp "$TEMPLATES_DIR/CLAUDE.md"                          ./CLAUDE.md

# History bootstrap
cat > .codenook/history/latest.md <<'EOF'
# Latest Session Summary

No prior session. This is a fresh CodeNook v5.0 POC workspace.

## Active Tasks
None. Awaiting first task.

## Next Action for Main Session
Greet user and ask what task to start.
EOF

echo ""
echo "✅ CodeNook v5.0 POC initialized."
echo ""
echo "Structure:"
echo "  .codenook/        (workspace)"
echo "  CLAUDE.md         (bootloader — Claude Code & Copilot CLI both read this)"
echo ""
echo "Next: start Claude Code (\`claude\`) or Copilot CLI (\`copilot\`) in this directory."
echo "The core.md will take over as orchestrator."
