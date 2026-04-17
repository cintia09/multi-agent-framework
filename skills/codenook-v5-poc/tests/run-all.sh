#!/usr/bin/env bash
# Run all automated tests for CodeNook v5 POC
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PASS=0
FAIL=0

run_test() {
  local name="$1"
  local script="$2"
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "▶ Running $name"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  if bash "$script"; then
    PASS=$((PASS+1))
  else
    FAIL=$((FAIL+1))
  fi
}

run_test "T1 init smoke"          "$SCRIPT_DIR/t1-init-smoke.sh"
run_test "T8 manifest lint"       "$SCRIPT_DIR/t8-manifest-lint.sh"
run_test "T9 dual-agent serial"   "$SCRIPT_DIR/t9-dual-agent-static.sh"
run_test "T10 dual-agent parallel" "$SCRIPT_DIR/t10-dual-agent-parallel.sh"
run_test "T11 clarifier role"     "$SCRIPT_DIR/t11-clarifier-role.sh"
run_test "T12 full pipeline"      "$SCRIPT_DIR/t12-full-pipeline.sh"
run_test "T13 planner + subtasks" "$SCRIPT_DIR/t13-planner-subtasks.sh"
run_test "T14 skill trigger"      "$SCRIPT_DIR/t14-skill-trigger.sh"

echo ""
echo "════════════════════════════════════════════"
echo "Summary: $PASS passed, $FAIL failed"
echo "════════════════════════════════════════════"

[[ $FAIL -eq 0 ]]
