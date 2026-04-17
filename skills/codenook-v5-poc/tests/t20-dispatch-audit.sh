#!/usr/bin/env bash
# T20: Dispatch log + delegation audit
# Verifies §20 protocol:
#   - init.sh creates dispatch-log.jsonl (empty) and dispatch-audit.sh (+x)
#   - core.md §20 documents the protocol
#   - audit script: clean log + clean outputs ⇒ pass (0)
#   - audit script: ghost output (no log entry) ⇒ violation (1)
#   - audit script: dangling manifest ⇒ violation (1)
#   - audit script: duplicate invocation_id ⇒ violation (1)
#   - audit script: phase mismatch ⇒ violation (1)
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
POC_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
INIT_SH="$POC_DIR/init.sh"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

FAIL=0
pass() { echo "  ✅ $1"; }
fail() { echo "  ❌ $1"; FAIL=$((FAIL+1)); }

echo "=== T20: Dispatch log & delegation audit ==="

# ----------------------------------------------------------------------
# [1] init.sh wiring
# ----------------------------------------------------------------------
echo ""
echo "[1] init.sh creates dispatch infra:"
cd "$TMP" && bash "$INIT_SH" > /tmp/t20-init.log 2>&1

[[ -f .codenook/dispatch-audit.sh && -x .codenook/dispatch-audit.sh ]] \
  && pass "dispatch-audit.sh present + executable" \
  || fail "dispatch-audit.sh missing or not +x"

[[ -f .codenook/history/dispatch-log.jsonl ]] \
  && pass "dispatch-log.jsonl initialized" \
  || fail "dispatch-log.jsonl missing"

[[ ! -s .codenook/history/dispatch-log.jsonl ]] \
  && pass "dispatch-log.jsonl starts empty" \
  || fail "dispatch-log.jsonl not empty at init"

# ----------------------------------------------------------------------
# [2] core.md §20 documents protocol
# ----------------------------------------------------------------------
echo ""
echo "[2] core.md §20 protocol present:"
C=.codenook/core/codenook-core.md
s20=$(awk '/^## 20\. /,0' "$C")
echo "$s20" | grep -qi 'Dispatch Log'                     && pass "§20 titled Dispatch Log"          || fail "§20 missing"
echo "$s20" | grep -q  'dispatch-log.jsonl'               && pass "§20 names log file"              || fail "§20 no log path"
echo "$s20" | grep -qi 'JSON Lines\|JSONL'                && pass "§20 says JSONL"                  || fail "§20 no JSONL"
echo "$s20" | grep -q  'invocation_id'                    && pass "§20 schema includes invocation_id" || fail "§20 no invocation_id"
echo "$s20" | grep -qi 'BEFORE'                           && pass "§20 says log BEFORE invoke"      || fail "§20 no BEFORE rule"
echo "$s20" | grep -qi 'ghost'                            && pass "§20 explains ghost detection"     || fail "§20 no ghost concept"

# ----------------------------------------------------------------------
# [3] Empty workspace audit returns 0 (no outputs, no violations)
# ----------------------------------------------------------------------
echo ""
echo "[3] Empty workspace audit:"
out=$(bash .codenook/dispatch-audit.sh 2>&1); rc=$?
[[ $rc -eq 0 ]] && pass "exit 0 on empty workspace" || fail "expected 0, got $rc"
[[ "$out" == *"violations:  0"* ]] && pass "reports 0 violations" || fail "violation count missing"

# ----------------------------------------------------------------------
# [4] Healthy task: log entry + manifest + output → pass
# ----------------------------------------------------------------------
echo ""
echo "[4] Healthy task audit:"
mkdir -p .codenook/tasks/T-001/{prompts,outputs}
echo '# manifest' > .codenook/tasks/T-001/prompts/phase-1-clarifier.md
echo '# output'   > .codenook/tasks/T-001/outputs/phase-1-clarifier.md
cat > .codenook/history/dispatch-log.jsonl <<'JSONL'
{"ts":"2025-07-15T10:00:00Z","task_id":"T-001","phase":"phase-1-clarify","role":"clarifier","manifest":".codenook/tasks/T-001/prompts/phase-1-clarifier.md","output_expected":".codenook/tasks/T-001/outputs/phase-1-clarifier.md","invocation_id":"d-1-clarifier-T001-1"}
JSONL
out=$(bash .codenook/dispatch-audit.sh 2>&1); rc=$?
[[ $rc -eq 0 ]] && pass "exit 0 on healthy task" || { fail "expected 0, got $rc"; echo "$out"; }
[[ "$out" == *"all outputs trace back to a dispatch"* ]] && pass "output coverage clean" || fail "output coverage report missing"

# ----------------------------------------------------------------------
# [5] Ghost output (no dispatch entry) → violation
# ----------------------------------------------------------------------
echo ""
echo "[5] Ghost output detection:"
echo '# ghost' > .codenook/tasks/T-001/outputs/phase-2-designer.md
out=$(bash .codenook/dispatch-audit.sh 2>&1); rc=$?
[[ $rc -eq 1 ]] && pass "exit 1 when ghost output present" || fail "expected 1, got $rc"
[[ "$out" == *"ghost output"* ]] && pass "ghost output flagged by name" || fail "ghost not named"
[[ "$out" == *"phase-2-designer.md"* ]] && pass "specific ghost file named" || fail "ghost path missing"
rm .codenook/tasks/T-001/outputs/phase-2-designer.md

# ----------------------------------------------------------------------
# [6] Dangling manifest → violation
# ----------------------------------------------------------------------
echo ""
echo "[6] Dangling manifest detection:"
cat > .codenook/history/dispatch-log.jsonl <<'JSONL'
{"ts":"2025-07-15T10:00:00Z","task_id":"T-001","phase":"phase-1-clarify","role":"clarifier","manifest":".codenook/tasks/T-001/prompts/phase-1-clarifier.md","output_expected":".codenook/tasks/T-001/outputs/phase-1-clarifier.md","invocation_id":"d-1-clarifier-T001-1"}
{"ts":"2025-07-15T11:00:00Z","task_id":"T-001","phase":"phase-2-design","role":"designer","manifest":".codenook/tasks/T-001/prompts/MISSING.md","output_expected":".codenook/tasks/T-001/outputs/phase-2-designer.md","invocation_id":"d-2-designer-T001-2"}
JSONL
out=$(bash .codenook/dispatch-audit.sh 2>&1); rc=$?
[[ $rc -eq 1 ]] && pass "exit 1 on dangling manifest" || fail "expected 1, got $rc"
[[ "$out" == *"dangling manifest"* ]] && pass "dangling manifest flagged" || fail "dangling not reported"

# ----------------------------------------------------------------------
# [7] Duplicate invocation_id → violation
# ----------------------------------------------------------------------
echo ""
echo "[7] Duplicate invocation_id detection:"
cat > .codenook/history/dispatch-log.jsonl <<'JSONL'
{"ts":"2025-07-15T10:00:00Z","task_id":"T-001","phase":"phase-1-clarify","role":"clarifier","manifest":".codenook/tasks/T-001/prompts/phase-1-clarifier.md","output_expected":".codenook/tasks/T-001/outputs/phase-1-clarifier.md","invocation_id":"d-dup-1"}
{"ts":"2025-07-15T10:01:00Z","task_id":"T-001","phase":"phase-1-clarify","role":"clarifier","manifest":".codenook/tasks/T-001/prompts/phase-1-clarifier.md","output_expected":".codenook/tasks/T-001/outputs/phase-1-clarifier.md","invocation_id":"d-dup-1"}
JSONL
out=$(bash .codenook/dispatch-audit.sh 2>&1); rc=$?
[[ $rc -eq 1 ]] && pass "exit 1 on duplicate invocation_id" || fail "expected 1, got $rc"
[[ "$out" == *"duplicate invocation_id"* ]] && pass "duplicate flagged by name" || fail "dup label missing"

# ----------------------------------------------------------------------
# [8] Filter by task argument
# ----------------------------------------------------------------------
echo ""
echo "[8] Task filter:"
mkdir -p .codenook/tasks/T-002/{prompts,outputs}
echo '# m' > .codenook/tasks/T-002/prompts/phase-1-clarifier.md
echo '# o' > .codenook/tasks/T-002/outputs/phase-1-clarifier.md
cat > .codenook/history/dispatch-log.jsonl <<'JSONL'
{"ts":"2025-07-15T10:00:00Z","task_id":"T-001","phase":"phase-1-clarify","role":"clarifier","manifest":".codenook/tasks/T-001/prompts/phase-1-clarifier.md","output_expected":".codenook/tasks/T-001/outputs/phase-1-clarifier.md","invocation_id":"d-1"}
{"ts":"2025-07-15T11:00:00Z","task_id":"T-002","phase":"phase-1-clarify","role":"clarifier","manifest":".codenook/tasks/T-002/prompts/phase-1-clarifier.md","output_expected":".codenook/tasks/T-002/outputs/phase-1-clarifier.md","invocation_id":"d-2"}
JSONL
mkdir -p .codenook/tasks/T-001/outputs
echo '# o' > .codenook/tasks/T-001/outputs/phase-1-clarifier.md
out=$(bash .codenook/dispatch-audit.sh T-002 2>&1); rc=$?
[[ $rc -eq 0 ]] && pass "filter T-002 exits 0" || fail "expected 0, got $rc"
out=$(bash .codenook/dispatch-audit.sh T-001 2>&1); rc=$?
[[ $rc -eq 0 ]] && pass "filter T-001 exits 0" || fail "expected 0, got $rc"

echo ""
if [[ $FAIL -eq 0 ]]; then
  echo "=== T20 PASSED ==="
  exit 0
else
  echo "=== T20 FAILED ($FAIL issues) ==="
  exit 1
fi
