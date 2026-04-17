#!/usr/bin/env bash
# T22: Helper-script security invariants
# Verifies the three helper scripts (subtask-runner, queue-runner,
# dispatch-audit, terminal HITL adapter) reject malicious IDs/paths and
# that workspace-escape attempts recorded in the dispatch log get flagged.
#
# Threat model: the orchestrator (an LLM) or a prompt-author controls the
# task_id / path / agent_id arguments and the content of manifest files
# (plan.md, dependency-graph.md, hitl pending items). The scripts must
# refuse to construct filesystem paths from untrusted values that contain
# '..', '/', or control characters, and must not write or read outside
# .codenook/.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
POC_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
INIT_SH="$POC_DIR/init.sh"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

FAIL=0
pass() { echo "  ✅ $1"; }
fail() { echo "  ❌ $1"; FAIL=$((FAIL+1)); }

# Helper: run a command, expect it to fail with rc=2 (usage/validation error)
# and emit no files under the victim directory.
expect_rejected() {
  local desc="$1"; shift
  local rc=0
  "$@" >/dev/null 2>&1 || rc=$?
  if [[ $rc -eq 2 ]]; then
    pass "$desc (rc=2 as expected)"
  else
    fail "$desc (expected rc=2, got $rc)"
  fi
}

echo "=== T22: Helper-script security ==="

cd "$TMP" && bash "$INIT_SH" > /tmp/t22-init.log 2>&1
SR=".codenook/subtask-runner.sh"
QR=".codenook/queue-runner.sh"
DA=".codenook/dispatch-audit.sh"
HI=".codenook/hitl-adapters/terminal.sh"

# Create a "victim" directory we will check stays untouched.
VICTIM="$TMP/victim"
mkdir -p "$VICTIM"

# ----------------------------------------------------------------------
# [1] subtask-runner: task_id validation on seed/status/mark/ready/deps
# ----------------------------------------------------------------------
echo ""
echo "[1] subtask-runner rejects malicious task_id:"

# Set up a legit task so "path exists" errors don't confuse us.
mkdir -p .codenook/tasks/T-003
echo '{"task_id":"T-003","phase":"decomp","subtasks":[]}' > .codenook/tasks/T-003/state.json

expect_rejected "traversal in seed"        bash "$SR" seed "T-003/../victim"
expect_rejected "absolute path in seed"    bash "$SR" seed "/etc/passwd"
expect_rejected "shell meta in seed"       bash "$SR" seed 'T-003;rm -rf /'
expect_rejected "dotdot in status"         bash "$SR" status "../../etc"
expect_rejected "slash in deps"            bash "$SR" deps "T-003/sub"
expect_rejected "empty task"               bash "$SR" status ""

# Integration-ready uses task_id too.
expect_rejected "traversal in integration-ready" bash "$SR" integration-ready "T-003/.."

# Valid ID still works (regression).
out=$(bash "$SR" status T-003 2>&1) && [[ "$out" == *"status:"* || "$out" == *"T-003"* ]] \
  && pass "valid task_id T-003 still accepted" || fail "regression: T-003 rejected ($out)"

# ----------------------------------------------------------------------
# [2] subtask-runner: subtask_id validation on mark
# ----------------------------------------------------------------------
echo ""
echo "[2] subtask-runner rejects malicious subtask_id:"
expect_rejected "mark traversal sid"      bash "$SR" mark "T-003/../../x" done
expect_rejected "mark missing .N"         bash "$SR" mark "T-003" done
expect_rejected "mark shell-meta sid"     bash "$SR" mark 'T-003.1; echo hi' done
expect_rejected "mark bad status"         bash "$SR" mark "T-003.1" "; rm -rf"

# ----------------------------------------------------------------------
# [3] subtask-runner: seed refuses to create files outside workspace
# ----------------------------------------------------------------------
echo ""
echo "[3] subtask-runner does not create files outside .codenook/:"
# Victim dir should be empty before and after.
before=$(find "$VICTIM" -type f 2>/dev/null | wc -l | tr -d ' ')
bash "$SR" seed "T-003/../../victim/evil" >/dev/null 2>&1 || true
bash "$SR" seed "/../../victim" >/dev/null 2>&1 || true
after=$(find "$VICTIM" -type f 2>/dev/null | wc -l | tr -d ' ')
[[ "$before" == "$after" ]] && pass "victim dir untouched ($after files)" || fail "files leaked outside workspace"

# ----------------------------------------------------------------------
# [4] subtask-runner: graph parser ignores bad-shaped node/edge IDs
# ----------------------------------------------------------------------
echo ""
echo "[4] subtask-runner graph parser refuses bad IDs silently:"
# Seed a real subtask structure with one legit node + one malicious one.
mkdir -p .codenook/tasks/T-200/decomposition
cat > .codenook/tasks/T-200/decomposition/plan.md <<'PLAN'
# Subtask plan

## Subtask List

| id | title | acceptance | est |
|----|-------|------------|-----|
| T-200.1 | real | works | S |
| T-200/../evil | escape | nope | S |
PLAN
cat > .codenook/tasks/T-200/decomposition/dependency-graph.md <<'GRAPH'
# Deps

## Nodes
- T-200.1: real
- T-200/../evil: bad

## Edges
- T-200.1 depends_on T-200/../evil
GRAPH
echo '{"task_id":"T-200","phase":"decomp","subtasks":[]}' > .codenook/tasks/T-200/state.json

bash "$SR" seed T-200 >/tmp/t22-seed.log 2>&1 || true
[[ -d .codenook/tasks/T-200/subtasks/T-200.1 ]] && pass "legit subtask T-200.1 seeded" || fail "legit subtask not created"
# The evil id should not have produced a directory anywhere.
! find .codenook/tasks/T-200/subtasks -type d -name '*evil*' | grep -q . \
  && pass "evil subtask id rejected by parser" || fail "evil id produced a directory"
# Nothing should have been written outside .codenook/.
! find "$TMP" -path '*/.codenook' -prune -o -name evil -print 2>/dev/null | grep -v '^$' | grep -q . \
  && pass "no 'evil' paths outside workspace" || fail "evil path leaked"

# ----------------------------------------------------------------------
# [5] queue-runner: lock path + agent_id validation
# ----------------------------------------------------------------------
echo ""
echo "[5] queue-runner lock rejects unsafe inputs:"
expect_rejected "lock absolute path"   bash "$QR" lock "/etc/passwd" agent-1
expect_rejected "lock traversal path"  bash "$QR" lock "../../etc/passwd" agent-1
expect_rejected "lock with newline"    bash "$QR" lock $'src/foo\ninjected' agent-1
expect_rejected "lock agent injection" bash "$QR" lock "src/foo" $'a1\nholder: evil'
expect_rejected "unlock traversal"     bash "$QR" unlock "../../x"

# Valid lock still works.
bash "$QR" lock "src/module.py" agent-1 >/dev/null 2>&1 \
  && pass "legit lock still works" || fail "regression: legit lock rejected"
[[ -f .codenook/locks/src-module.py.lock ]] && pass "lock file created in workspace" || fail "lock file missing"

# ----------------------------------------------------------------------
# [6] queue-runner: ready/deps/cycles reject bad task_id
# ----------------------------------------------------------------------
echo ""
echo "[6] queue-runner task-id commands validate:"
expect_rejected "ready traversal"   bash "$QR" ready "T-003/../x"
expect_rejected "deps absolute"     bash "$QR" deps "/etc"
expect_rejected "cycles shell meta" bash "$QR" cycles 'T-003;ls'

# ----------------------------------------------------------------------
# [7] dispatch-audit flags traversal / absolute paths in log
# ----------------------------------------------------------------------
echo ""
echo "[7] dispatch-audit flags workspace-escape in log:"
LOG=.codenook/history/dispatch-log.jsonl
cat > "$LOG" <<'JSONL'
{"ts":"2025-01-01T00:00:00Z","task_id":"T-900","phase":"phase-1-clarify","role":"clarifier","manifest":"../../etc/passwd","output_expected":".codenook/tasks/T-900/outputs/phase-1-clarifier.md","invocation_id":"d-1-clarifier-T900-1"}
{"ts":"2025-01-01T00:00:01Z","task_id":"T-900","phase":"phase-2-design","role":"designer","manifest":".codenook/tasks/T-900/prompts/phase-2.md","output_expected":"/tmp/absolute.md","invocation_id":"d-2-designer-T900-2"}
JSONL
mkdir -p .codenook/tasks/T-900/outputs
audit_out=$(bash "$DA" T-900 2>&1 || true)
echo "$audit_out" | grep -q "traversal segment '..'" && pass "flags '..' in manifest"   || fail "did not flag traversal"
echo "$audit_out" | grep -q "absolute path in log"    && pass "flags absolute in output" || fail "did not flag absolute path"
echo "$audit_out" | grep -q "Workspace containment"   && pass "audit has check [5]"       || fail "check [5] missing"

# ----------------------------------------------------------------------
# [8] hitl terminal: rejects unsafe pending ids and yaml-embedded task ids
# ----------------------------------------------------------------------
echo ""
echo "[8] hitl terminal.sh validates inputs:"
Q=.codenook/hitl-queue/pending
mkdir -p "$Q"
# Legit pending item exists so our "not found" path isn't the one hit first.
cat > "$Q/hitl-001.md" <<'EOF'
---
task_id: T-003
phase: design
---
Please choose.
EOF
# 8a: malicious pending id (path traversal). Note: different scripts implement
# this check at different layers; at minimum we require that no file is
# created under victim/, and rc is nonzero.
rc=0
bash "$HI" answer "../../etc/passwd" opt-a note >/dev/null 2>&1 || rc=$?
[[ $rc -ne 0 ]] && pass "traversal pending id rejected (rc=$rc)" || fail "traversal pending id accepted"

# 8b: YAML with malicious task_id inside a legit-named pending item.
cat > "$Q/hitl-evil.md" <<'EOF'
---
task_id: T-003/../../etc
phase: design
---
Please choose.
EOF
rc=0
bash "$HI" answer "hitl-evil" opt-a >/dev/null 2>&1 || rc=$?
[[ $rc -ne 0 ]] && pass "malicious yaml task_id rejected (rc=$rc)" || fail "yaml task_id accepted"

# 8c: legit answer still works.
rc=0
bash "$HI" answer "hitl-001" opt-a "looks good" >/dev/null 2>&1 || rc=$?
[[ $rc -eq 0 ]] && pass "legit answer still works" || fail "regression: legit answer rejected"

# ----------------------------------------------------------------------
# [9] Nothing leaked outside .codenook/ at the end
# ----------------------------------------------------------------------
echo ""
echo "[9] Workspace containment (final sweep):"
# Exclude expected init artifacts: CLAUDE.md bootloader at workspace root,
# and the /tmp/*.log files we wrote explicitly.
leaked_list=$(find "$TMP" -not -path "*/.codenook*" -not -path "$TMP" -not -path "$VICTIM" -not -path "$VICTIM/*" -type f 2>/dev/null \
  | grep -v '/CLAUDE\.md$' || true)
leaked=$(echo -n "$leaked_list" | grep -c . || true)
if [[ "$leaked" == "0" ]]; then
  pass "no stray files outside .codenook/ (CLAUDE.md bootloader excluded)"
else
  fail "$leaked stray files leaked: $leaked_list"
fi

echo ""
if [[ $FAIL -eq 0 ]]; then
  echo "=== T22 PASSED ==="
  exit 0
else
  echo "=== T22 FAILED ($FAIL) ==="
  exit 1
fi
