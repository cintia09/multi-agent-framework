#!/usr/bin/env bash
set -euo pipefail
# Team Session — launch multi-agent tmux session
# Usage: bash scripts/team-session.sh [--agents <roles>] [--task <T-XXX>] [--layout <layout>]

SESSION_NAME="agent-team"
AGENTS="acceptor,designer,implementer,reviewer,tester"
TASK_FILTER=""
LAYOUT="tiled"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Parse args
while [[ $# -gt 0 ]]; do
  case "$1" in
    --agents) AGENTS="$2"; shift 2 ;;
    --task)   TASK_FILTER="$2"; shift 2 ;;
    --layout) LAYOUT="$2"; shift 2 ;;
    --help)
      echo "Usage: team-session.sh [--agents roles] [--task T-XXX] [--layout tiled|even-horizontal]"
      echo "  --agents  Comma-separated agent roles (default: all 5)"
      echo "  --task    Focus agents on a specific task"
      echo "  --layout  tmux layout (default: tiled)"
      exit 0
      ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

# Check tmux
if ! command -v tmux &>/dev/null; then
  echo "❌ tmux is required. Install with: brew install tmux (macOS) or apt install tmux (Linux)"
  exit 1
fi

# Kill existing session if running
tmux kill-session -t "$SESSION_NAME" 2>/dev/null || true

IFS=',' read -ra AGENT_LIST <<< "$AGENTS"
AGENT_COUNT=${#AGENT_LIST[@]}

if [ "$AGENT_COUNT" -lt 1 ]; then
  echo "❌ At least one agent role is required"
  exit 1
fi

echo "🚀 Launching Agent Team Session"
echo "   Agents: ${AGENTS}"
echo "   Layout: ${LAYOUT}"
[ -n "$TASK_FILTER" ] && echo "   Task: ${TASK_FILTER}"
echo ""

# Create first pane with first agent (escape single quotes for tmux)
FIRST_AGENT="${AGENT_LIST[0]}"
SAFE_PROJECT=$(printf '%s' "$PROJECT_DIR" | sed "s/'/'\\\\''/g")
SAFE_FILTER=$(printf '%s' "${TASK_FILTER:-all}" | sed "s/'/'\\\\''/g")
AGENT_CMD="cd '${SAFE_PROJECT}' && echo '🤖 Agent: $FIRST_AGENT' && echo 'Task: ${SAFE_FILTER}' && echo '---'"
tmux new-session -d -s "$SESSION_NAME" -x 200 -y 50 "$AGENT_CMD; bash"

# Create additional panes for remaining agents
for ((i=1; i<AGENT_COUNT; i++)); do
  AGENT="${AGENT_LIST[$i]}"
  AGENT_CMD="cd '${SAFE_PROJECT}' && echo '🤖 Agent: $AGENT' && echo 'Task: ${SAFE_FILTER}' && echo '---'"
  tmux split-window -t "$SESSION_NAME" "$AGENT_CMD; bash"
  tmux select-layout -t "$SESSION_NAME" "$LAYOUT"
done

# Add dashboard pane
SAFE_SCRIPT_DIR=$(printf '%s' "$SCRIPT_DIR" | sed "s/'/'\\\\''/g")
DASHBOARD_CMD="cd '${SAFE_PROJECT}' && watch -n 10 'bash \"${SAFE_SCRIPT_DIR}/team-dashboard.sh\" 2>/dev/null || echo \"Dashboard loading...\"'"
tmux split-window -t "$SESSION_NAME" -l 8 "$DASHBOARD_CMD"

# Final layout
tmux select-layout -t "$SESSION_NAME" "$LAYOUT" 2>/dev/null || true

# Set pane titles
for ((i=0; i<AGENT_COUNT; i++)); do
  tmux select-pane -t "$SESSION_NAME:0.$i" -T "${AGENT_LIST[$i]}"
done
tmux select-pane -t "$SESSION_NAME:0.$AGENT_COUNT" -T "dashboard"

# Enable pane borders with titles
tmux set-option -t "$SESSION_NAME" pane-border-status top 2>/dev/null || true
tmux set-option -t "$SESSION_NAME" pane-border-format " #{pane_title} " 2>/dev/null || true

# Select first pane
tmux select-pane -t "$SESSION_NAME:0.0"

echo "✅ Team session created: $SESSION_NAME"
echo ""
echo "  Attach:     tmux attach -t $SESSION_NAME"
echo "  Navigate:   Ctrl+B → arrow keys"
echo "  Zoom pane:  Ctrl+B → z"
echo "  Kill:       tmux kill-session -t $SESSION_NAME"
echo ""

# Attach
tmux attach -t "$SESSION_NAME"
