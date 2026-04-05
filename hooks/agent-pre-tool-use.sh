#!/bin/bash
# Multi-Agent Framework: Pre-Tool-Use Hook
# 1. Security: Scans staged files for secrets before git commit/push (ALWAYS active)
# 2. Boundaries: Enforces agent role boundaries (only when agent system is active)
# Can output {"permissionDecision":"deny","permissionDecisionReason":"..."} to block.

set -e
INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.toolName')
TOOL_ARGS=$(echo "$INPUT" | jq -r '.toolArgs')
CWD=$(echo "$INPUT" | jq -r '.cwd')

# === SECTION 1: Security Scan (always active, no agent system required) ===
case "$TOOL_NAME" in
  bash)
    CMD=$(echo "$TOOL_ARGS" | jq -r '.command // empty' 2>/dev/null)
    if echo "$CMD" | grep -qE '(git\s+(commit|push)|git\s+.*\s+(commit|push))'; then
      # Scan staged files for sensitive patterns
      STAGED_FILES=$(cd "$CWD" && git diff --cached --name-only 2>/dev/null)
      if [ -n "$STAGED_FILES" ]; then
        SECRETS_FOUND=""
        while IFS= read -r f; do
          [ -f "$CWD/$f" ] || continue
          # API keys
          if grep -qE '(AIza[0-9A-Za-z_-]{35}|sk-[a-zA-Z0-9]{20,}|ghp_[a-zA-Z0-9]{36}|ghr_[a-zA-Z0-9]{36}|AKIA[0-9A-Z]{16})' "$CWD/$f" 2>/dev/null; then
            SECRETS_FOUND="$SECRETS_FOUND\n  ⚠️ $f: possible API key"
          fi
          # Passwords in assignments
          if grep -qiE '(password|passwd|secret|token|api_key)\s*[:=]\s*["\x27][^\s"'\'']{8,}' "$CWD/$f" 2>/dev/null; then
            SECRETS_FOUND="$SECRETS_FOUND\n  ⚠️ $f: possible password/secret"
          fi
          # Private keys
          if grep -q 'BEGIN.*PRIVATE KEY' "$CWD/$f" 2>/dev/null; then
            SECRETS_FOUND="$SECRETS_FOUND\n  ⚠️ $f: private key detected"
          fi
          # .env file content
          if echo "$f" | grep -qE '\.env(\..+)?$'; then
            SECRETS_FOUND="$SECRETS_FOUND\n  ⚠️ $f: .env file should not be committed"
          fi
        done <<< "$STAGED_FILES"

        if [ -n "$SECRETS_FOUND" ]; then
          REASON="🔒 Pre-commit security scan found sensitive data:${SECRETS_FOUND}\nRemove secrets before committing. Use git reset HEAD <file> to unstage."
          echo "{\"permissionDecision\":\"deny\",\"permissionDecisionReason\":\"$(echo -e "$REASON" | head -c 500)\"}"
          exit 0
        fi
      fi
    fi
    ;;
esac

# === SECTION 2: Agent Boundary Rules (only when agent system is active) ===
AGENTS_DIR="$CWD/.agents"

# Only enforce boundaries if agent framework is initialized and an agent is active
[ -d "$AGENTS_DIR/runtime" ] || exit 0
ACTIVE_FILE="$AGENTS_DIR/runtime/active-agent"
[ -f "$ACTIVE_FILE" ] || exit 0

ACTIVE_AGENT=$(cat "$ACTIVE_FILE")
[ -n "$ACTIVE_AGENT" ] || exit 0

# Only enforce on file-modifying tools
case "$TOOL_NAME" in
  edit|create)
    FILE_PATH=$(echo "$TOOL_ARGS" | jq -r '.path // empty' 2>/dev/null)
    [ -n "$FILE_PATH" ] || exit 0

    # Normalize: remove CWD prefix for relative comparison
    REL_PATH="${FILE_PATH#$CWD/}"

    case "$ACTIVE_AGENT" in
      acceptor)
        # Acceptor can only edit: .agents/ files (requirements, acceptance reports, task board)
        # Cannot edit source code
        if [[ ! "$REL_PATH" =~ ^\.agents/ ]] && [[ ! "$REL_PATH" =~ ^\.github/ ]]; then
          echo '{"permissionDecision":"deny","permissionDecisionReason":"🎯 Acceptor cannot edit source code. Use task-board to create tasks or messaging to communicate."}'
          exit 0
        fi
        ;;
      reviewer)
        # Reviewer can only edit: .agents/runtime/reviewer/ (review reports)
        # Cannot edit source code or other agents' files
        if [[ ! "$REL_PATH" =~ ^\.agents/runtime/reviewer/ ]] && [[ ! "$REL_PATH" =~ ^\.agents/task-board ]]; then
          echo '{"permissionDecision":"deny","permissionDecisionReason":"🔍 Reviewer cannot edit source code. Write review reports in .agents/runtime/reviewer/workspace/."}'
          exit 0
        fi
        ;;
      designer)
        # Designer can edit: .agents/ (design docs, task board) but not source code
        if [[ ! "$REL_PATH" =~ ^\.agents/ ]]; then
          echo '{"permissionDecision":"deny","permissionDecisionReason":"🏗️ Designer cannot edit source code directly. Output design docs to .agents/runtime/designer/workspace/."}'
          exit 0
        fi
        ;;
      tester)
        # Tester can edit: .agents/runtime/tester/ and test files
        # Can also run tests (bash tool) but not edit source
        if [[ ! "$REL_PATH" =~ ^\.agents/ ]] && [[ ! "$REL_PATH" =~ ^tests?/ ]] && [[ ! "$REL_PATH" =~ \.test\. ]] && [[ ! "$REL_PATH" =~ \.spec\. ]]; then
          echo '{"permissionDecision":"deny","permissionDecisionReason":"🧪 Tester cannot edit source code. Write test cases in test directories or .agents/runtime/tester/workspace/."}'
          exit 0
        fi
        ;;
      implementer)
        # Implementer has the broadest access — can edit source code
        # But cannot edit other agents' workspaces
        if [[ "$REL_PATH" =~ ^\.agents/runtime/(acceptor|designer|reviewer|tester)/ ]]; then
          echo '{"permissionDecision":"deny","permissionDecisionReason":"💻 Implementer cannot edit other agents workspaces. Use messaging to communicate."}'
          exit 0
        fi
        ;;
    esac
    ;;
esac

# Allow by default
