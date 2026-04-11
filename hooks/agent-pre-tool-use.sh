#!/usr/bin/env bash
# Multi-Agent Framework: Pre-Tool-Use Hook
# Enforces agent boundaries — prevents agents from doing things outside their role.
# Can output {"permissionDecision":"deny","permissionDecisionReason":"..."} to block.

set -euo pipefail
INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.toolName')
TOOL_ARGS=$(echo "$INPUT" | jq -r '.toolArgs')
CWD=$(echo "$INPUT" | jq -r '.cwd')

# --- Locate project root (walk up from cwd, then try file path) ---
find_agents_dir() {
  local dir="$1"
  while [ "$dir" != "/" ] && [ -n "$dir" ]; do
    [ -d "$dir/.agents/runtime" ] && echo "$dir" && return 0
    dir=$(dirname "$dir")
  done
  return 1
}

PROJECT_ROOT=""
# Strategy 1: walk up from cwd
PROJECT_ROOT=$(find_agents_dir "$CWD" 2>/dev/null) || true

# Strategy 2: if not found, try the file path from tool args (edit/create targets)
if [ -z "$PROJECT_ROOT" ]; then
  FILE_HINT=$(echo "$TOOL_ARGS" | jq -r '.path // empty' 2>/dev/null)
  if [ -n "$FILE_HINT" ]; then
    PROJECT_ROOT=$(find_agents_dir "$(dirname "$FILE_HINT")" 2>/dev/null) || true
  fi
fi

# Strategy 3: try bash command's cd target or common project paths
if [ -z "$PROJECT_ROOT" ]; then
  BASH_CMD_HINT=$(echo "$TOOL_ARGS" | jq -r '.command // empty' 2>/dev/null)
  if echo "$BASH_CMD_HINT" | grep -qo 'cd [^ ;|&]*' 2>/dev/null; then
    CD_TARGET=$(echo "$BASH_CMD_HINT" | grep -o 'cd [^ ;|&]*' | head -1 | sed 's/^cd //')
    # Expand ~ to HOME
    CD_TARGET="${CD_TARGET/#\~/$HOME}"
    [ -d "$CD_TARGET" ] && PROJECT_ROOT=$(find_agents_dir "$CD_TARGET" 2>/dev/null) || true
  fi
fi

# Strategy 4: extract absolute paths from bash command arguments
# Catches: rm /path/to/project/file, echo >> /path/to/project/file
if [ -z "$PROJECT_ROOT" ]; then
  BASH_CMD_HINT=$(echo "$TOOL_ARGS" | jq -r '.command // empty' 2>/dev/null)
  if [ -n "$BASH_CMD_HINT" ]; then
    ABS_PATHS=$(echo "$BASH_CMD_HINT" | grep -oE '/[a-zA-Z0-9_./~-]+' | head -5) || true
    for apath in $ABS_PATHS; do
      ADIR=$(dirname "$apath" 2>/dev/null) || true
      if [ -n "$ADIR" ] && [ -d "$ADIR" ]; then
        PROJECT_ROOT=$(find_agents_dir "$ADIR" 2>/dev/null) || true
        [ -n "$PROJECT_ROOT" ] && break
      fi
    done
  fi
fi

[ -n "$PROJECT_ROOT" ] || exit 0
AGENTS_DIR="$PROJECT_ROOT/.agents"

# Read active agent — default to most restrictive role if missing/empty
# This prevents bypass via `rm .agents/runtime/active-agent`
ACTIVE_FILE="$AGENTS_DIR/runtime/active-agent"
if [ -f "$ACTIVE_FILE" ] && [ -s "$ACTIVE_FILE" ]; then
  ACTIVE_AGENT=$(cat "$ACTIVE_FILE" | tr -d '[:space:]')
else
  # No active agent or empty file → check if framework was ever initialized
  # (presence of task-board.json or any agent state indicates active framework)
  if [ -f "$AGENTS_DIR/task-board.json" ] || ls "$AGENTS_DIR/runtime"/*/state.json >/dev/null 2>&1; then
    ACTIVE_AGENT="acceptor"  # default to most restrictive role
  else
    exit 0  # framework not initialized, skip enforcement
  fi
fi
[ -n "$ACTIVE_AGENT" ] || exit 0

# --- Virtual Event Validation (emulate custom hook events via preToolUse) ---
# Copilot CLI only supports 6 events; these checks emulate agentSwitch, memoryWrite,
# taskCreate, and taskStatusChange using file-path detection in preToolUse.

case "$TOOL_NAME" in
  edit|create)
    VE_PATH=$(echo "$TOOL_ARGS" | jq -r '.path // empty' 2>/dev/null)
    VE_REL="${VE_PATH#"$PROJECT_ROOT"/}"

    # V-EVENT 1: agentSwitch — validate role name when writing active-agent
    if [[ "$VE_REL" == ".agents/runtime/active-agent" ]]; then
      NEW_CONTENT=$(echo "$TOOL_ARGS" | jq -r '.file_text // .new_str // empty' 2>/dev/null)
      NEW_ROLE=$(echo "$NEW_CONTENT" | tr -d '[:space:]')
      if [ -z "$NEW_ROLE" ]; then
        echo '{"permissionDecision":"deny","permissionDecisionReason":"🔄 Cannot clear agent role. Switch to a valid role: acceptor, designer, implementer, reviewer, tester."}'
        exit 0
      fi
      case "$NEW_ROLE" in
        acceptor|designer|implementer|reviewer|tester) ;; # valid
        *)
          echo "{\"permissionDecision\":\"deny\",\"permissionDecisionReason\":\"🔄 Invalid agent role: '$NEW_ROLE'. Valid: acceptor, designer, implementer, reviewer, tester.\"}"
          exit 0 ;;
      esac
      exit 0  # valid switch — allow (bypass role-based file restrictions)
    fi

    # V-EVENT 2: memoryWrite — namespace isolation
    if [[ "$VE_REL" =~ ^\.agents/memory/ ]]; then
      MEMFILE=$(basename "$VE_REL")
      # Task memory (T-NNN-*) is shared across all roles
      if [[ ! "$MEMFILE" =~ ^T- ]] && [[ ! "$MEMFILE" =~ $ACTIVE_AGENT ]]; then
        echo "{\"permissionDecision\":\"deny\",\"permissionDecisionReason\":\"🧠 ${ACTIVE_AGENT} cannot write to other agents' memory files. File: $MEMFILE\"}"
        exit 0
      fi
      exit 0  # own memory or task memory — allow
    fi

    # V-EVENT 3: taskCreate/StatusChange — validate task-board.json format
    if [[ "$VE_REL" == ".agents/task-board.json" ]]; then
      NEW_CONTENT=$(echo "$TOOL_ARGS" | jq -r '.file_text // .new_str // empty' 2>/dev/null)
      # Validate JSON syntax if writing complete file
      if [ -n "$NEW_CONTENT" ] && echo "$TOOL_ARGS" | jq -e '.file_text' >/dev/null 2>&1; then
        if ! echo "$NEW_CONTENT" | jq empty 2>/dev/null; then
          echo '{"permissionDecision":"deny","permissionDecisionReason":"📋 task-board.json must be valid JSON. Check syntax before writing."}'
          exit 0
        fi
      fi
      # All roles can update task-board (FSM validation is in agent-switch skill)
    fi
    ;;
  bash)
    VE_CMD=$(echo "$TOOL_ARGS" | jq -r '.command // empty' 2>/dev/null)
    # Strip quoted strings for virtual event checks (collapse newlines first for multi-line strings)
    # Then strip harmless /dev/null redirects (e.g., 2>/dev/null) to avoid false positives
    VE_CMD_CHECK=$(echo "$VE_CMD" | tr '\n' ' ' | sed "s/'[^']*'/_Q_/g" | sed 's/"[^"]*"/_Q_/g' | sed -E 's/[0-9]*>&?\/dev\/null//g; s/&>\/dev\/null//g')

    # PROTECT: block deletion of active-agent file (prevents enforcement bypass)
    if echo "$VE_CMD_CHECK" | grep -qE '(rm|mv)\s+.*active-agent'; then
      echo '{"permissionDecision":"deny","permissionDecisionReason":"🛡️ Cannot delete active-agent file. Switch to a valid role instead: acceptor, designer, implementer, reviewer, tester."}'
      exit 0
    fi

    # V-EVENT 1b: agentSwitch via bash — validate role in echo/printf to active-agent
    # NOTE: do NOT early-exit on valid switch — chained commands must still be checked
    if echo "$VE_CMD_CHECK" | grep -qE '(>|>>)\s*.*active-agent'; then
      SWITCH_ROLE=$(echo "$VE_CMD" | grep -oE '(echo|printf)\s+["\x27]?(acceptor|designer|implementer|reviewer|tester)["\x27]?' | head -1 | grep -oE '(acceptor|designer|implementer|reviewer|tester)' || true)
      if [ -z "$SWITCH_ROLE" ]; then
        WRITTEN_VAL=$(echo "$VE_CMD" | sed -n "s/.*echo[[:space:]]*[\"']*\([^\"'>]*\)[\"']*[[:space:]]*>.*/\1/p" | tr -d '[:space:]')
        if [ -n "$WRITTEN_VAL" ]; then
          case "$WRITTEN_VAL" in
            acceptor|designer|implementer|reviewer|tester) ;; # valid
            *)
              echo "{\"permissionDecision\":\"deny\",\"permissionDecisionReason\":\"🔄 Invalid agent role: '$WRITTEN_VAL'. Valid: acceptor, designer, implementer, reviewer, tester.\"}"
              exit 0 ;;
          esac
        fi
      fi
      # Don't exit 0 — let the rest of bash checks run for chained commands
    fi

    # V-EVENT 2b: memoryWrite via bash — block redirects to other agents' memory
    if echo "$VE_CMD_CHECK" | grep -qE '(>|>>)\s*.*\.agents/memory/' || \
       echo "$VE_CMD_CHECK" | grep -qE 'tee\s+.*\.agents/memory/'; then
      MEM_TARGET=$(echo "$VE_CMD_CHECK" | grep -oE '\.agents/memory/[^ ]+' | head -1 || true)
      if [ -n "$MEM_TARGET" ]; then
        MEM_BASENAME=$(basename "$MEM_TARGET")
        if [[ ! "$MEM_BASENAME" =~ ^T- ]] && [[ ! "$MEM_BASENAME" =~ $ACTIVE_AGENT ]]; then
          echo "{\"permissionDecision\":\"deny\",\"permissionDecisionReason\":\"🧠 ${ACTIVE_AGENT} cannot write to other agents' memory via bash. File: $MEM_BASENAME\"}"
          exit 0
        fi
      fi
    fi
    ;;
esac

# --- Boundary Rules ---
case "$TOOL_NAME" in
  edit|create)
    FILE_PATH=$(echo "$TOOL_ARGS" | jq -r '.path // empty' 2>/dev/null)
    [ -n "$FILE_PATH" ] || exit 0

    # Normalize: remove project root prefix for relative comparison
    REL_PATH="${FILE_PATH#"$PROJECT_ROOT"/}"

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
        # Reviewer can edit: .agents/runtime/reviewer/ (review reports), .agents/docs/ (review-report.md)
        # Cannot edit source code or other agents' files
        if [[ ! "$REL_PATH" =~ ^\.agents/runtime/reviewer/ ]] && [[ ! "$REL_PATH" =~ ^\.agents/task-board ]] && [[ ! "$REL_PATH" =~ ^\.agents/docs/ ]]; then
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
  bash)
    # Enforce bash command boundaries for non-implementer roles
    BASH_CMD=$(echo "$TOOL_ARGS" | jq -r '.command // empty' 2>/dev/null)
    [ -n "$BASH_CMD" ] || exit 0

    # Strip quoted strings to avoid false positives from argument content
    # e.g., gh release --notes "mentions npm publish" should NOT trigger npm publish check
    # Direct commands like `npm publish` (unquoted) are still caught
    # Also strip harmless /dev/null redirects (2>/dev/null, &>/dev/null)
    BASH_CMD_CHECK=$(echo "$BASH_CMD" | tr '\n' ' ' | sed "s/'[^']*'/_Q_/g" | sed 's/"[^"]*"/_Q_/g' | sed -E 's/[0-9]*>&?\/dev\/null//g; s/&>\/dev\/null//g')

    # Helper: check if ANY segment of a chained command has a dangerous pattern
    # without matching a whitelist. Splits on &&, ||, ; for per-segment analysis.
    has_dangerous_segment() {
      local cmd="$1" pattern="$2" whitelist="$3"
      echo "$cmd" | sed 's/&&/\n/g; s/||/\n/g; s/;/\n/g' | while IFS= read -r seg; do
        seg=$(echo "$seg" | sed 's/^[[:space:]]*//')
        [ -z "$seg" ] && continue
        if echo "$seg" | grep -qE "$pattern"; then
          if [ -z "$whitelist" ] || ! echo "$seg" | grep -qE "$whitelist"; then
            echo "DENY"
            break
          fi
        fi
      done
    }

    case "$ACTIVE_AGENT" in
      acceptor|designer)
        # Read-only roles: block destructive commands and file writes
        if echo "$BASH_CMD_CHECK" | grep -qE '(^|\s)(rm|mv|cp|git\s+push|git\s+commit|npm\s+publish|docker\s+run|chmod|chown)(\s|$)'; then
          AGENT_JSON_ESC=$(echo "$ACTIVE_AGENT" | sed 's/"/\\"/g')
          echo "{\"permissionDecision\":\"deny\",\"permissionDecisionReason\":\"${AGENT_JSON_ESC} cannot run write/destructive commands via bash.\"}"
          exit 0
        fi
        # Block bash file-write patterns (redirects, in-place edits) outside .agents/
        if [ -n "$(has_dangerous_segment "$BASH_CMD_CHECK" '(>[^&]|>>|tee\s|sed\s+-i|patch\s|dd\s)' '\.agents/')" ]; then
          AGENT_JSON_ESC=$(echo "$ACTIVE_AGENT" | sed 's/"/\\"/g')
          echo "{\"permissionDecision\":\"deny\",\"permissionDecisionReason\":\"${AGENT_JSON_ESC} cannot write to files via bash redirects. Use task-board or messaging instead.\"}"
          exit 0
        fi
        ;;
      reviewer)
        # Reviewer: read + git diff/log allowed, no writes
        if echo "$BASH_CMD_CHECK" | grep -qE '(^|\s)(rm|mv|cp|git\s+push|git\s+commit|npm\s+publish|docker\s+run|chmod|chown)(\s|$)'; then
          echo '{"permissionDecision":"deny","permissionDecisionReason":"🔍 Reviewer cannot run write/destructive commands via bash."}'
          exit 0
        fi
        # Block bash file-write patterns outside .agents/
        if [ -n "$(has_dangerous_segment "$BASH_CMD_CHECK" '(>[^&]|>>|tee\s|sed\s+-i|patch\s|dd\s)' '\.agents/')" ]; then
          echo '{"permissionDecision":"deny","permissionDecisionReason":"🔍 Reviewer cannot write to files via bash redirects."}'
          exit 0
        fi
        ;;
      tester)
        # Tester: can run tests, read code, but not modify source or deploy
        if echo "$BASH_CMD_CHECK" | grep -qE '(^|\s)(git\s+push|git\s+commit|npm\s+publish|docker\s+run|chmod|chown)(\s|$)'; then
          echo '{"permissionDecision":"deny","permissionDecisionReason":"🧪 Tester cannot run commit/publish/deploy commands. Use test runners only."}'
          exit 0
        fi
        # Block destructive commands on non-test files (per-segment to prevent chain bypass)
        if [ -n "$(has_dangerous_segment "$BASH_CMD_CHECK" '(^|\s)(rm|mv|cp)(\s)' '(tests?/|\.test\.|\.spec\.|\.agents/|/tmp/)')" ]; then
          echo '{"permissionDecision":"deny","permissionDecisionReason":"🧪 Tester cannot modify non-test files via rm/mv/cp."}'
          exit 0
        fi
        # Block bash file-write patterns outside .agents/ and test dirs (per-segment)
        if [ -n "$(has_dangerous_segment "$BASH_CMD_CHECK" '(>[^&]|>>|tee\s|sed\s+-i|patch\s|dd\s)' '(\.agents/|tests?/|\.test\.|\.spec\.)')" ]; then
          echo '{"permissionDecision":"deny","permissionDecisionReason":"🧪 Tester cannot write to non-test files via bash redirects."}'
          exit 0
        fi
        ;;
      implementer)
        # Implementer: broadest access but cannot touch other agents' workspaces or deploy
        # Block editing other agents' runtime directories via redirects (per-segment)
        if [ -n "$(has_dangerous_segment "$BASH_CMD_CHECK" '(>[^&]|>>|tee\s|sed\s+-i)' '')" ] && \
           echo "$BASH_CMD_CHECK" | grep -qE '\.agents/runtime/(acceptor|designer|reviewer|tester)/'; then
          echo '{"permissionDecision":"deny","permissionDecisionReason":"💻 Implementer cannot write to other agents workspaces via bash. Use messaging."}'
          exit 0
        fi
        # Block direct deploy without going through review pipeline
        if echo "$BASH_CMD_CHECK" | grep -qE '(^|\s)(npm\s+publish|docker\s+push)(\s|$)'; then
          echo '{"permissionDecision":"deny","permissionDecisionReason":"💻 Implementer cannot publish/deploy directly. Code must go through review first."}'
          exit 0
        fi
        ;;
    esac
    ;;
esac

# Allow by default
