#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
PASS=0
FAIL=0
TOTAL=0

run_test() {
    local name="$1"
    local script="$2"
    TOTAL=$((TOTAL + 1))
    echo -n "  Testing ${name}... "
    if bash "$script" >/dev/null 2>&1; then
        echo "✅"
        PASS=$((PASS + 1))
    else
        echo "❌"
        FAIL=$((FAIL + 1))
    fi
}

echo "🧪 Multi-Agent Framework Test Suite"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

run_test "Skills format" "${SCRIPT_DIR}/test-skills.sh"
run_test "Agents format" "${SCRIPT_DIR}/test-agents.sh"
run_test "Hooks format"  "${SCRIPT_DIR}/test-hooks.sh"
run_test "3-Phase FSM"   "${SCRIPT_DIR}/test-3phase-fsm.sh"
run_test "Integration"   "${SCRIPT_DIR}/test-integration.sh"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Results: ${PASS}/${TOTAL} passed, ${FAIL} failed"

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
echo "✅ All tests passed!"
