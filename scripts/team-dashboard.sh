#!/usr/bin/env bash
set -euo pipefail
# Team Dashboard — shows agent team status (designed for watch -n10)

AGENTS_DIR=".agents"
[ -d "$AGENTS_DIR" ] || { echo "⚠️ No .agents directory found"; exit 0; }

# Colors
BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${BOLD}📊 Agent Team Dashboard${NC}  $(date '+%H:%M:%S')"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Active agent
ACTIVE="none"
[ -f "$AGENTS_DIR/runtime/active-agent" ] && ACTIVE=$(cat "$AGENTS_DIR/runtime/active-agent")

# Agent status table
printf "${BOLD}%-14s %-8s %-6s %-30s${NC}\n" "AGENT" "STATUS" "INBOX" "CURRENT TASK"
echo "──────────────────────────────────────────────────────────────"

for agent in acceptor designer implementer reviewer tester; do
  # Status
  if [ "$agent" = "$ACTIVE" ]; then
    STATUS="${GREEN}ACTIVE${NC}"
  elif [ -f "$AGENTS_DIR/runtime/$agent/state.json" ]; then
    STATUS="${YELLOW}IDLE${NC}"
  else
    STATUS="—"
  fi

  # Inbox count
  INBOX_COUNT=0
  INBOX_FILE="$AGENTS_DIR/runtime/$agent/inbox.json"
  if [ -f "$INBOX_FILE" ]; then
    INBOX_COUNT=$(jq '[.messages[] | select(.read == false)] | length' "$INBOX_FILE" 2>/dev/null || echo 0)
  fi
  if [ "$INBOX_COUNT" -gt 0 ]; then
    INBOX="${RED}${INBOX_COUNT}${NC}"
  else
    INBOX="0"
  fi

  # Current task (from state.json)
  CURRENT_TASK="—"
  if [ -f "$AGENTS_DIR/runtime/$agent/state.json" ]; then
    CURRENT_TASK=$(jq -r '.current_task // "—"' "$AGENTS_DIR/runtime/$agent/state.json" 2>/dev/null || echo "—")
  fi

  printf "%-14s %-18b %-16b %-30s\n" "$agent" "$STATUS" "$INBOX" "$CURRENT_TASK"
done

echo ""

# Task pipeline progress
if [ -f "$AGENTS_DIR/task-board.json" ]; then
  TOTAL=$(jq '.tasks | length' "$AGENTS_DIR/task-board.json" 2>/dev/null || echo 0)
  ACCEPTED=$(jq '[.tasks[] | select(.status == "accepted")] | length' "$AGENTS_DIR/task-board.json" 2>/dev/null || echo 0)
  IN_PROGRESS=$(jq '[.tasks[] | select(.status | IN("implementing","designing","reviewing","testing","hypothesizing"))] | length' "$AGENTS_DIR/task-board.json" 2>/dev/null || echo 0)
  BLOCKED=$(jq '[.tasks[] | select(.blocked_from != null and .blocked_from != "")] | length' "$AGENTS_DIR/task-board.json" 2>/dev/null || echo 0)

  echo -e "${BOLD}Pipeline:${NC} ${GREEN}${ACCEPTED}${NC} accepted | ${CYAN}${IN_PROGRESS}${NC} active | ${RED}${BLOCKED}${NC} blocked | ${TOTAL} total"

  # Progress bar
  if [ "$TOTAL" -gt 0 ]; then
    PCT=$((ACCEPTED * 100 / TOTAL))
    BAR_LEN=40
    FILLED=$((PCT * BAR_LEN / 100))
    EMPTY=$((BAR_LEN - FILLED))
    printf "  ["
    [ "$FILLED" -gt 0 ] && printf "${GREEN}%0.s█${NC}" $(seq 1 "$FILLED") || true
    [ "$EMPTY" -gt 0 ] && printf "%0.s░" $(seq 1 "$EMPTY") || true
    printf "] %d%%\n" "$PCT"
  fi
fi

# Recent events (last 5)
if [ -f "$AGENTS_DIR/events.db" ]; then
  echo ""
  echo -e "${BOLD}Recent Events:${NC}"
  sqlite3 "$AGENTS_DIR/events.db" \
    "SELECT datetime(timestamp, 'unixepoch', 'localtime') || ' | ' || event_type || ' | ' || COALESCE(agent,'?') || ' | ' || COALESCE(task_id,'') FROM events ORDER BY timestamp DESC LIMIT 5;" 2>/dev/null | while read -r line; do
    echo "  $line"
  done
fi

# Hypothesis tracker
if [ -d "$AGENTS_DIR/hypotheses" ]; then
  H_COUNT=$(find "$AGENTS_DIR/hypotheses" -name manifest.json 2>/dev/null | wc -l | tr -d ' ')
  if [ "$H_COUNT" -gt 0 ]; then
    echo ""
    echo -e "${BOLD}Active Hypotheses:${NC} $H_COUNT"
    find "$AGENTS_DIR/hypotheses" -name manifest.json -exec jq -r '.task_id + ": " + .challenge + " (" + (.hypotheses | length | tostring) + " approaches)"' {} \; 2>/dev/null | head -3 | while read -r line; do
      echo "  🔬 $line"
    done
  fi
fi
