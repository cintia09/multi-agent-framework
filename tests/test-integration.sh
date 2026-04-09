#!/usr/bin/env bash
# Integration test: actual hook execution with simulated inputs
set -euo pipefail
cd "$(dirname "$0")/.."
HOOK_DIR="$(pwd)/hooks"
PASS=0; FAIL=0; TOTAL=0

check() {
  TOTAL=$((TOTAL + 1))
  if [ "$2" = "pass" ]; then
    echo "  ✅ $1"
    PASS=$((PASS + 1))
  else
    echo "  ❌ $1"
    FAIL=$((FAIL + 1))
  fi
}

echo "🔬 Integration Tests — Hook Execution"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Setup test project
TEST_DIR=$(mktemp -d)
trap "rm -rf '$TEST_DIR'" EXIT
mkdir -p "$TEST_DIR/.agents/runtime"/{acceptor,designer,implementer,reviewer,tester}
sqlite3 "$TEST_DIR/.agents/events.db" "CREATE TABLE events (id INTEGER PRIMARY KEY, timestamp INTEGER, event_type TEXT, agent TEXT, tool_name TEXT, task_id TEXT, detail TEXT);"
echo "designer" > "$TEST_DIR/.agents/runtime/active-agent"
for a in acceptor designer implementer reviewer tester; do
  echo '{"messages":[]}' > "$TEST_DIR/.agents/runtime/$a/inbox.json"
done

# === Test 1: Post-tool-use logs tool_use event ===
echo '{"toolName":"read","toolArgs":"{}","toolResult":{"resultType":"success"},"cwd":"'"$TEST_DIR"'","timestamp":"1744200000"}' \
  | bash "$HOOK_DIR/agent-post-tool-use.sh" 2>/dev/null
EVENTS=$(sqlite3 "$TEST_DIR/.agents/events.db" "SELECT count(*) FROM events WHERE event_type='tool_use';")
check "Post-tool-use: logs tool_use event" "$([ "$EVENTS" -ge 1 ] && echo pass || echo fail)"

# === Test 2: Auto-dispatch sends message on status change ===
cat > "$TEST_DIR/.agents/runtime/.task-board-snapshot.json" << 'EOF'
{"version":1,"tasks":[{"id":"T-INT-001","title":"Integration Test","status":"created","workflow_mode":"simple","goals":[]}]}
EOF
cat > "$TEST_DIR/.agents/task-board.json" << 'EOF'
{"version":1,"tasks":[{"id":"T-INT-001","title":"Integration Test","status":"designing","workflow_mode":"simple","goals":[]}]}
EOF
echo '{"toolName":"edit","toolArgs":"{\"path\":\"'"$TEST_DIR"'/.agents/task-board.json\"}","toolResult":{"resultType":"success"},"cwd":"'"$TEST_DIR"'","timestamp":"1744200100"}' \
  | bash "$HOOK_DIR/agent-post-tool-use.sh" 2>/dev/null
MSG_COUNT=$(jq '.messages | length' "$TEST_DIR/.agents/runtime/designer/inbox.json" 2>/dev/null || echo 0)
check "Auto-dispatch: designer inbox has message" "$([ "$MSG_COUNT" -ge 1 ] && echo pass || echo fail)"

# === Test 3: FSM violation detected ===
cp "$TEST_DIR/.agents/task-board.json" "$TEST_DIR/.agents/runtime/.task-board-snapshot.json"
cat > "$TEST_DIR/.agents/task-board.json" << 'EOF'
{"version":1,"tasks":[{"id":"T-INT-001","title":"Integration Test","status":"accepted","workflow_mode":"simple","goals":[]}]}
EOF
OUTPUT=$(echo '{"toolName":"edit","toolArgs":"{\"path\":\"'"$TEST_DIR"'/.agents/task-board.json\"}","toolResult":{"resultType":"success"},"cwd":"'"$TEST_DIR"'","timestamp":"1744200200"}' \
  | bash "$HOOK_DIR/agent-post-tool-use.sh" 2>&1)
check "FSM validation: illegal transition detected" "$(echo "$OUTPUT" | grep -q 'ILLEGAL' && echo pass || echo fail)"

# === Test 4: Document gate warning ===
cp "$TEST_DIR/.agents/task-board.json" "$TEST_DIR/.agents/runtime/.task-board-snapshot.json"
cat > "$TEST_DIR/.agents/runtime/.task-board-snapshot.json" << 'EOF'
{"version":1,"tasks":[{"id":"T-INT-002","title":"Doc Test","status":"designing","workflow_mode":"simple","goals":[]}]}
EOF
cat > "$TEST_DIR/.agents/task-board.json" << 'EOF'
{"version":1,"tasks":[{"id":"T-INT-002","title":"Doc Test","status":"implementing","workflow_mode":"simple","goals":[]}]}
EOF
OUTPUT=$(echo '{"toolName":"edit","toolArgs":"{\"path\":\"'"$TEST_DIR"'/.agents/task-board.json\"}","toolResult":{"resultType":"success"},"cwd":"'"$TEST_DIR"'","timestamp":"1744200300"}' \
  | bash "$HOOK_DIR/agent-post-tool-use.sh" 2>&1)
check "Document gate: warns about missing design.md" "$(echo "$OUTPUT" | grep -q 'DOC GATE' && echo pass || echo fail)"

# === Test 5: Memory capture triggered ===
check "Memory capture: auto-capture message shown" "$(echo "$OUTPUT" | grep -q 'Auto-Capture' && echo pass || echo fail)"

# === Test 6: After-switch hook outputs JSON ===
OUTPUT=$(echo '{"agent":"implementer","cwd":"'"$TEST_DIR"'"}' | bash "$HOOK_DIR/agent-after-switch.sh" 2>&1)
check "After-switch: returns valid JSON" "$(echo "$OUTPUT" | jq -e '.status' >/dev/null 2>&1 && echo pass || echo fail)"

# === Test 7: Before-compaction flushes diary ===
OUTPUT=$(echo '{"cwd":"'"$TEST_DIR"'"}' | bash "$HOOK_DIR/agent-before-compaction.sh" 2>&1)
check "Before-compaction: returns status" "$(echo "$OUTPUT" | grep -q 'status' && echo pass || echo fail)"

# === Test 8: Security scan allows non-git commands ===
OUTPUT=$(echo '{"toolName":"bash","toolArgs":"{\"command\":\"ls\"}","cwd":"'"$TEST_DIR"'"}' | bash "$HOOK_DIR/security-scan.sh" 2>&1)
check "Security scan: allows non-git commands" "$([ -z "$OUTPUT" ] && echo pass || echo fail)"

# === Test 9: Before-task-create blocks empty title ===
OUTPUT=$(echo '{"task_id":"T-999","title":"","cwd":"'"$TEST_DIR"'"}' | bash "$HOOK_DIR/agent-before-task-create.sh" 2>&1)
check "Before-task-create: blocks empty title" "$(echo "$OUTPUT" | grep -q 'block.*true' && echo pass || echo fail)"

# === Test 10: Before-task-create allows valid task ===
OUTPUT=$(echo '{"task_id":"T-NEW","title":"Valid task","cwd":"'"$TEST_DIR"'"}' | bash "$HOOK_DIR/agent-before-task-create.sh" 2>&1)
check "Before-task-create: allows valid task" "$(echo "$OUTPUT" | grep -q 'allow.*true' && echo pass || echo fail)"

# === Test 11: Events logged to DB ===
DB_EVENTS=$(sqlite3 "$TEST_DIR/.agents/events.db" "SELECT count(*) FROM events;")
check "Events DB: has logged events ($DB_EVENTS total)" "$([ "$DB_EVENTS" -ge 3 ] && echo pass || echo fail)"

# === Test 12: Doc gate logged to events DB ===
DOC_EVENTS=$(sqlite3 "$TEST_DIR/.agents/events.db" "SELECT count(*) FROM events WHERE event_type='doc_gate_warning';")
check "Events DB: doc_gate_warning recorded" "$([ "$DOC_EVENTS" -ge 1 ] && echo pass || echo fail)"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Results: $PASS/$TOTAL passed, $FAIL failed"
[ "$FAIL" -eq 0 ] && echo "✅ All integration tests passed!" || echo "❌ Some tests failed"
exit $FAIL
