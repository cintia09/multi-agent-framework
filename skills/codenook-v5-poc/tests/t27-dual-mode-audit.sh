#!/usr/bin/env bash
# T27: dispatch-audit check [6] — dual-mode iteration consistency
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
POC_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
INIT_SH="$POC_DIR/init.sh"

TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
FAIL=0
pass() { echo "  ✅ $1"; }
fail() { echo "  ❌ $1"; FAIL=$((FAIL+1)); }

echo "=== T27: dispatch-audit dual-mode check [6] ==="
cd "$TMP" && bash "$INIT_SH" > /tmp/t27-init.log 2>&1

# ----------------------------------------------------------------------
# [1] Empty workspace -> check [6] passes (no dual-mode tasks)
# ----------------------------------------------------------------------
echo ""
echo "[1] Empty workspace:"
out=$(bash .codenook/dispatch-audit.sh 2>&1 || true)
echo "$out" | grep -q '\[6\] Dual-agent iteration consistency' && pass "check [6] runs" || fail "no [6]"
echo "$out" | grep -q 'iteration scoping' && pass "passes on empty" || fail "did not pass on empty"

# ----------------------------------------------------------------------
# [2] Plant dual_mode=serial task with implement dispatches but NO
#     iterations/ dir -> check [6] flags violation
# ----------------------------------------------------------------------
echo ""
echo "[2] dual_mode=serial without iterations/ dir:"
mkdir -p .codenook/tasks/T-001
cat > .codenook/tasks/T-001/state.json <<'JSON'
{"task_id":"T-001","status":"in_progress","phase":"implement","dual_mode":"serial","total_iterations":2}
JSON
# Add implement dispatch entries to the log.
ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
cat >> .codenook/history/dispatch-log.jsonl <<EOF
{"ts":"$ts","task_id":"T-001","phase":"implement","role":"implementer","manifest":".codenook/tasks/T-001/prompts/phase-3.md","output_expected":".codenook/tasks/T-001/outputs/phase-3-implementer.md","invocation_id":"T-001-impl-1"}
{"ts":"$ts","task_id":"T-001","phase":"review","role":"reviewer","manifest":".codenook/tasks/T-001/prompts/phase-4.md","output_expected":".codenook/tasks/T-001/outputs/phase-4-reviewer.md","invocation_id":"T-001-rev-1"}
EOF
out=$(bash .codenook/dispatch-audit.sh 2>&1 || true)
echo "$out" | grep -q 'no iterations/ dir' && pass "flags missing iterations/" || fail "did not flag missing dir: $out"

# ----------------------------------------------------------------------
# [3] Add iterations/ dir but outputs not in iterations/ -> warns
# ----------------------------------------------------------------------
echo ""
echo "[3] iterations/ exists but outputs flat:"
mkdir -p .codenook/tasks/T-001/iterations/iter-1
out=$(bash .codenook/dispatch-audit.sh 2>&1 || true)
echo "$out" | grep -qE 'output not in iterations/' && pass "warns on flat output path" || fail "no flat-output warning: $out"

# ----------------------------------------------------------------------
# [4] dual_mode=off (or null) + non-iteration outputs -> no [6] complaints
# ----------------------------------------------------------------------
echo ""
echo "[4] dual_mode=off (no complaints):"
mkdir -p .codenook/tasks/T-002
cat > .codenook/tasks/T-002/state.json <<'JSON'
{"task_id":"T-002","status":"in_progress","phase":"implement","dual_mode":"off","total_iterations":1}
JSON
# Make T-001 also clean for this test.
rm -rf .codenook/tasks/T-001
: > .codenook/history/dispatch-log.jsonl
ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
echo "{\"ts\":\"$ts\",\"task_id\":\"T-002\",\"phase\":\"implement\",\"role\":\"implementer\",\"manifest\":\".codenook/tasks/T-002/prompts/phase-3.md\",\"output_expected\":\".codenook/tasks/T-002/outputs/phase-3.md\",\"invocation_id\":\"T-002-impl-1\"}" >> .codenook/history/dispatch-log.jsonl
out=$(bash .codenook/dispatch-audit.sh 2>&1 || true)
echo "$out" | grep -q 'iteration scoping' && pass "no dual-mode complaints when off" || fail "false positive on dual_mode=off: $out"

# ----------------------------------------------------------------------
# [5] dual_mode=invalid_value -> warning
# ----------------------------------------------------------------------
echo ""
echo "[5] dual_mode=bogus:"
cat > .codenook/tasks/T-002/state.json <<'JSON'
{"task_id":"T-002","status":"in_progress","phase":"implement","dual_mode":"weirdmode","total_iterations":1}
JSON
out=$(bash .codenook/dispatch-audit.sh 2>&1 || true)
echo "$out" | grep -q "unknown dual_mode value" && pass "warns on unknown dual_mode" || fail "no unknown-value warning: $out"

# ----------------------------------------------------------------------
# [6] --filter limits scope
# ----------------------------------------------------------------------
echo ""
echo "[6] filter T-002:"
out=$(bash .codenook/dispatch-audit.sh T-002 2>&1 || true)
echo "$out" | grep -q 'unknown dual_mode' && pass "filter still finds T-002 issue" || fail "filter dropped result"

echo ""
if [[ $FAIL -eq 0 ]]; then echo "=== T27 PASSED ==="; exit 0; else echo "=== T27 FAILED ($FAIL) ==="; exit 1; fi
