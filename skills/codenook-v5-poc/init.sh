#!/usr/bin/env bash
# CodeNook v5.0 POC bootstrap script
# Generates a .codenook/ workspace in the current directory.
#
# Platform support:
#   - Linux, macOS, WSL2: run directly.
#   - Windows Git Bash / MSYS2: supported. Requires `python3` on PATH
#     (the helper runners parse plan.md and dispatch-log.jsonl with
#     python3 to stay dependency-free).
#   - Native cmd.exe / PowerShell: NOT supported (scripts are bash).
set -euo pipefail

# ---- Platform prerequisites -------------------------------------------------
if ! command -v python3 >/dev/null 2>&1; then
  if command -v py >/dev/null 2>&1 && py -3 --version >/dev/null 2>&1; then
    echo "warn: 'python3' not on PATH but 'py -3' works. Create a python3 shim:" >&2
    echo "      echo 'py -3 \"\$@\"' > /usr/bin/python3 && chmod +x /usr/bin/python3" >&2
    exit 3
  fi
  echo "error: python3 is required (used by subtask-runner / queue-runner / dispatch-audit)." >&2
  echo "       On Windows Git Bash, install Python for Windows and ensure python3 is on PATH." >&2
  exit 3
fi

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
  echo ""
  echo "Choose action:"
  echo "  [u] Upgrade  — refresh templates/scripts only, KEEP your tasks/history/knowledge/state"
  echo "  [o] Overwrite — DELETE everything and start clean (DESTRUCTIVE)"
  echo "  [N] Abort"
  read -p "Action? (u/o/N) " -n 1 -r
  echo
  if [[ $REPLY =~ ^[Uu]$ ]]; then
    UPGRADE_MODE=1
    echo "Upgrade mode: preserving tasks/, history/, knowledge/, hitl-queue/, state.json, config.yaml, .secretignore"
  elif [[ $REPLY =~ ^[Oo]$ ]]; then
    UPGRADE_MODE=0
    echo "Overwrite mode: removing existing .codenook/ ..."
    rm -rf .codenook
  else
    echo "Aborted."; exit 0
  fi
else
  UPGRADE_MODE=0
fi

echo "Bootstrapping CodeNook v5.0 POC at: $TARGET_DIR"

mkdir -p .codenook/{core,prompts-templates,prompts-criteria,agents,project,tasks,knowledge/by-role,knowledge/by-topic,history,history/sessions,hitl-queue/pending,hitl-queue/answered,hitl-adapters,queue,locks}

# Copy templates
cp "$TEMPLATES_DIR/core/codenook-core.md"              .codenook/core/
cp "$TEMPLATES_DIR/prompts-templates/clarifier.md"     .codenook/prompts-templates/
cp "$TEMPLATES_DIR/prompts-templates/designer.md"      .codenook/prompts-templates/
cp "$TEMPLATES_DIR/prompts-templates/planner.md"       .codenook/prompts-templates/
cp "$TEMPLATES_DIR/prompts-templates/implementer.md"   .codenook/prompts-templates/
cp "$TEMPLATES_DIR/prompts-templates/reviewer.md"      .codenook/prompts-templates/
cp "$TEMPLATES_DIR/prompts-templates/synthesizer.md"   .codenook/prompts-templates/
cp "$TEMPLATES_DIR/prompts-templates/tester.md"        .codenook/prompts-templates/
cp "$TEMPLATES_DIR/prompts-templates/acceptor.md"      .codenook/prompts-templates/
cp "$TEMPLATES_DIR/prompts-templates/validator.md"     .codenook/prompts-templates/
cp "$TEMPLATES_DIR/prompts-templates/session-distiller.md" .codenook/prompts-templates/
cp "$TEMPLATES_DIR/prompts-criteria/criteria-clarify.md"   .codenook/prompts-criteria/
cp "$TEMPLATES_DIR/prompts-criteria/criteria-design.md"    .codenook/prompts-criteria/
cp "$TEMPLATES_DIR/prompts-criteria/criteria-plan.md"      .codenook/prompts-criteria/
cp "$TEMPLATES_DIR/prompts-criteria/criteria-implement.md" .codenook/prompts-criteria/
cp "$TEMPLATES_DIR/prompts-criteria/criteria-review.md"    .codenook/prompts-criteria/
cp "$TEMPLATES_DIR/prompts-criteria/criteria-test.md"      .codenook/prompts-criteria/
cp "$TEMPLATES_DIR/prompts-criteria/criteria-accept.md"    .codenook/prompts-criteria/
cp "$TEMPLATES_DIR/agents/clarifier.agent.md"          .codenook/agents/
cp "$TEMPLATES_DIR/agents/designer.agent.md"           .codenook/agents/
cp "$TEMPLATES_DIR/agents/planner.agent.md"            .codenook/agents/
cp "$TEMPLATES_DIR/agents/implementer.agent.md"        .codenook/agents/
cp "$TEMPLATES_DIR/agents/reviewer.agent.md"           .codenook/agents/
cp "$TEMPLATES_DIR/agents/synthesizer.agent.md"        .codenook/agents/
cp "$TEMPLATES_DIR/agents/tester.agent.md"             .codenook/agents/
cp "$TEMPLATES_DIR/agents/acceptor.agent.md"           .codenook/agents/
cp "$TEMPLATES_DIR/agents/validator.agent.md"          .codenook/agents/
cp "$TEMPLATES_DIR/agents/session-distiller.agent.md"  .codenook/agents/
cp "$TEMPLATES_DIR/agents/security-auditor.agent.md"   .codenook/agents/
cp "$TEMPLATES_DIR/project/ENVIRONMENT.md"             .codenook/project/
cp "$TEMPLATES_DIR/project/CONVENTIONS.md"             .codenook/project/
cp "$TEMPLATES_DIR/project/ARCHITECTURE.md"            .codenook/project/
cp "$TEMPLATES_DIR/config.yaml"                        .codenook/config.yaml.new
if [[ $UPGRADE_MODE -eq 1 && -f .codenook/config.yaml ]]; then
  rm .codenook/config.yaml.new
  echo "  kept existing config.yaml (template available at .codenook/config.yaml.template)"
  cp "$TEMPLATES_DIR/config.yaml"                      .codenook/config.yaml.template
else
  mv .codenook/config.yaml.new .codenook/config.yaml
  # Prompt once for default model (fresh install only). Non-TTY → accept default.
  DEFAULT_MODEL="${CODENOOK_DEFAULT_MODEL:-claude-opus-4.7}"
  if [[ -t 0 && -z "${CODENOOK_DEFAULT_MODEL:-}" ]]; then
    echo ""
    echo "Default model for all sub-agent roles?"
    echo "  Common choices: claude-opus-4.7, claude-sonnet-4.6, claude-haiku-4.5,"
    echo "                  gpt-5.4, gpt-5.3-codex, platform-default"
    echo "  ('platform-default' = dispatch without --model; platform picks)"
    read -p "Default model [claude-opus-4.7]: " -r REPLY_MODEL
    [[ -n "$REPLY_MODEL" ]] && DEFAULT_MODEL="$REPLY_MODEL"
  fi
  if [[ "$DEFAULT_MODEL" != "claude-opus-4.7" ]]; then
    # Replace every `: claude-opus-4.7` line in the models: block with the chosen model.
    python3 - "$DEFAULT_MODEL" <<'PY'
import sys, re
m = sys.argv[1]
p = ".codenook/config.yaml"
src = open(p).read()
out, in_models = [], False
for line in src.splitlines():
    if re.match(r'^models:\s*$', line):
        in_models = True; out.append(line); continue
    if in_models and line and not line.startswith((' ', '\t')) and not line.startswith('#'):
        in_models = False
    if in_models:
        line = re.sub(r'(:\s*)claude-opus-4\.7\s*$', r'\1' + m, line)
    out.append(line)
open(p, 'w').write('\n'.join(out) + '\n')
PY
  fi
  echo "  default model: $DEFAULT_MODEL"
fi
if [[ $UPGRADE_MODE -eq 1 && -f .codenook/state.json ]]; then
  echo "  kept existing state.json"
else
  cp "$TEMPLATES_DIR/state.json"                       .codenook/
fi
cp "$TEMPLATES_DIR/hitl-item-schema.md"                .codenook/
cp "$TEMPLATES_DIR/hitl-adapters/terminal.sh"          .codenook/hitl-adapters/
chmod +x .codenook/hitl-adapters/terminal.sh
# Initialize empty current.md (will be populated by queue_hitl)
if [[ ! -f .codenook/hitl-queue/current.md ]]; then
  : > .codenook/hitl-queue/current.md
fi

# Queue Runtime (core §19)
cp "$TEMPLATES_DIR/dependency-graph-schema.md"         .codenook/
cp "$TEMPLATES_DIR/queue-runner.sh"                    .codenook/
chmod +x .codenook/queue-runner.sh
cp "$TEMPLATES_DIR/subtask-runner.sh"                  .codenook/
chmod +x .codenook/subtask-runner.sh
cp "$TEMPLATES_DIR/dispatch-audit.sh"                  .codenook/
chmod +x .codenook/dispatch-audit.sh
cp "$TEMPLATES_DIR/preflight.sh"                       .codenook/
chmod +x .codenook/preflight.sh
cp "$TEMPLATES_DIR/rebuild-task-board.sh"              .codenook/
chmod +x .codenook/rebuild-task-board.sh
cp "$TEMPLATES_DIR/secret-scan.sh"                     .codenook/
chmod +x .codenook/secret-scan.sh
cp "$TEMPLATES_DIR/keyring-helper.sh"                  .codenook/
chmod +x .codenook/keyring-helper.sh
cp "$TEMPLATES_DIR/session-runner.sh"                  .codenook/
chmod +x .codenook/session-runner.sh
cp "$TEMPLATES_DIR/model-config.sh"                    .codenook/
chmod +x .codenook/model-config.sh
cp "$TEMPLATES_DIR/security-audit.sh"                  .codenook/
chmod +x .codenook/security-audit.sh
mkdir -p .codenook/history/security
if [[ ! -f .codenook/.secretignore ]]; then
cat > .codenook/.secretignore <<'EOF'
# Add file-name globs (one per line, '#' for comments) the secret-scan.sh
# should skip. Match is plain --exclude= passed to grep.
EOF
fi
if [[ ! -f .codenook/history/dispatch-log.jsonl ]]; then
  : > .codenook/history/dispatch-log.jsonl
fi
[[ -f .codenook/queue/pending.json ]]     || printf '{"items":[]}\n' > .codenook/queue/pending.json
[[ -f .codenook/queue/dispatching.json ]] || printf '{"items":[]}\n' > .codenook/queue/dispatching.json
[[ -f .codenook/queue/completed.json ]]   || printf '{"items":[]}\n' > .codenook/queue/completed.json

# Bootloader (`CLAUDE.md` — read by both Claude Code and Copilot CLI)
cp "$TEMPLATES_DIR/CLAUDE.md"                          ./CLAUDE.md

# History bootstrap (only on fresh install; preserve user history)
if [[ ! -f .codenook/history/latest.md ]]; then
cat > .codenook/history/latest.md <<'EOF'
# Latest Session Summary
_Last updated: fresh-workspace_
_Trigger: init_

## Workspace State
- Active tasks: none
- Current focus: none

## Current Task Snapshot
(no current focus)

## Next Action for the Next Session
Greet the user and ask what task to start. No prior session to resume.
EOF
fi

echo ""
echo "✅ CodeNook v5.0 POC initialized."
echo ""
echo "Structure:"
echo "  .codenook/        (workspace)"
echo "  CLAUDE.md         (bootloader — Claude Code & Copilot CLI both read this)"
echo ""
echo "Next: start Claude Code (\`claude\`) or Copilot CLI (\`copilot\`) in this directory."
echo "The core.md will take over as orchestrator."
