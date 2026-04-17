#!/usr/bin/env bash
# T21: Subtask Runner — end-to-end fan-out lifecycle
# Verifies §17.6: subtask-runner.sh seeds dirs from plan + graph,
# computes ready set, marks status, and reports integration-ready.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
POC_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
INIT_SH="$POC_DIR/init.sh"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

FAIL=0
pass() { echo "  ✅ $1"; }
fail() { echo "  ❌ $1"; FAIL=$((FAIL+1)); }

echo "=== T21: Subtask Runner ==="

cd "$TMP" && bash "$INIT_SH" > /tmp/t21-init.log 2>&1
R=".codenook/subtask-runner.sh"

# ----------------------------------------------------------------------
# [1] Init places runner + makes it executable
# ----------------------------------------------------------------------
echo ""
echo "[1] Runner installed:"
[[ -x "$R" ]] && pass "subtask-runner.sh present + executable" || fail "runner missing/not +x"

# ----------------------------------------------------------------------
# [2] core.md §17.6 documents the runner
# ----------------------------------------------------------------------
echo ""
echo "[2] core.md §17.6 documentation:"
C=.codenook/core/codenook-core.md
s176=$(awk '/^### 17\.6/{p=1; print; next} p; /^## 18\./{p=0}' "$C")
echo "$s176" | grep -qi 'subtask-runner.sh'                  && pass "§17.6 names runner script"        || fail "§17.6 missing"
echo "$s176" | grep -q  'seed.*<T-XXX>'                      && pass "§17.6 documents seed cmd"          || fail "no seed doc"
echo "$s176" | grep -q  'integration-ready'                  && pass "§17.6 documents integration-ready" || fail "no integration-ready doc"
echo "$s176" | grep -qi 'idempotent'                         && pass "§17.6 declares idempotency"        || fail "no idempotency note"
echo "$s176" | grep -qi 'authoritative'                      && pass "§17.6 declares state authority"    || fail "no state-authority note"

# ----------------------------------------------------------------------
# [3] Seed from synthetic plan + graph
# ----------------------------------------------------------------------
echo ""
echo "[3] Seed lifecycle:"
T="T-100"
mkdir -p ".codenook/tasks/$T/decomposition" ".codenook/tasks/$T/outputs"
echo "demo" > ".codenook/tasks/$T/task.md"
echo "{}"   > ".codenook/tasks/$T/state.json"

cat > ".codenook/tasks/$T/decomposition/plan.md" <<'PLAN'
# Decomposition Plan — T-100

## 1. Decomposition Rationale
Fake.

## 2. Subtask List

| id      | title       | scope                      | primary_outputs    | size | parent_section |
|---------|-------------|----------------------------|--------------------|------|----------------|
| T-100.1 | Schema      | Define DB schema           | db/schema.sql      | S    | data           |
| T-100.2 | API         | REST handlers              | api/handlers.py    | M    | api            |
| T-100.3 | Integration | Wire schema + API together | tests/e2e_test.py  | S    | integration    |
PLAN

cat > ".codenook/tasks/$T/decomposition/dependency-graph.md" <<'GRAPH'
# Dependency Graph — T-100

## Nodes

- T-100.1: Schema
- T-100.2: API
- T-100.3: Integration

## Edges

- T-100.2 depends_on T-100.1
- T-100.3 depends_on T-100.1
- T-100.3 depends_on T-100.2
GRAPH

bash "$R" seed "$T" > /tmp/t21-seed.log 2>&1
rc=$?
[[ $rc -eq 0 ]] && pass "seed exited 0" || { fail "seed rc=$rc"; cat /tmp/t21-seed.log; }
[[ -d ".codenook/tasks/$T/subtasks/T-100.1" ]] && pass "T-100.1 dir created" || fail "T-100.1 missing"
[[ -d ".codenook/tasks/$T/subtasks/T-100.2" ]] && pass "T-100.2 dir created" || fail "T-100.2 missing"
[[ -d ".codenook/tasks/$T/subtasks/T-100.3" ]] && pass "T-100.3 dir created" || fail "T-100.3 missing"
[[ -f ".codenook/tasks/$T/subtasks/T-100.1/task.md"    ]] && pass "T-100.1 task.md"    || fail "T-100.1 task.md"
[[ -f ".codenook/tasks/$T/subtasks/T-100.1/state.json" ]] && pass "T-100.1 state.json" || fail "T-100.1 state.json"
[[ -d ".codenook/tasks/$T/subtasks/T-100.1/prompts"    ]] && pass "T-100.1 prompts/"   || fail "T-100.1 prompts/"

# Verify state.json shape
python3 - "$T" <<'PY' && pass "T-100.2 deps == [T-100.1]" || fail "T-100.2 deps wrong"
import json, sys
T = sys.argv[1]
with open(f".codenook/tasks/{T}/subtasks/T-100.2/state.json") as f:
    s = json.load(f)
assert s["depends_on"] == ["T-100.1"], s
assert s["status"] == "pending"
assert s["parent_id"] == "T-100"
PY

python3 - "$T" <<'PY' && pass "T-100.3 deps == [T-100.1,T-100.2]" || fail "T-100.3 deps wrong"
import json, sys
T = sys.argv[1]
with open(f".codenook/tasks/{T}/subtasks/T-100.3/state.json") as f:
    s = json.load(f)
assert sorted(s["depends_on"]) == ["T-100.1","T-100.2"], s
PY

# Parent state.json subtasks array
python3 - "$T" <<'PY' && pass "parent state.json mirrors 3 subtasks" || fail "parent state wrong"
import json, sys
T = sys.argv[1]
with open(f".codenook/tasks/{T}/state.json") as f:
    s = json.load(f)
assert len(s["subtasks"]) == 3, s
ids = [x["id"] for x in s["subtasks"]]
assert ids == ["T-100.1","T-100.2","T-100.3"], ids
assert s["phase"] == "subtasks_in_flight", s
PY

# ----------------------------------------------------------------------
# [4] Idempotent seed
# ----------------------------------------------------------------------
echo ""
echo "[4] Idempotent seed:"
out=$(bash "$R" seed "$T" 2>&1); rc=$?
[[ $rc -eq 0 ]] && pass "second seed rc=0" || fail "second seed failed"
[[ "$out" == *"skip T-100.1"* ]] && pass "second seed skips existing" || fail "no skip message"

# ----------------------------------------------------------------------
# [5] Ready set computation
# ----------------------------------------------------------------------
echo ""
echo "[5] Ready set:"
ready=$(bash "$R" ready "$T" 2>&1); rc=$?
[[ $rc -eq 0 ]] && pass "ready exit 0 (T-100.1 ready)" || fail "ready exit $rc"
[[ "$ready" == "T-100.1" ]] && pass "only T-100.1 ready initially" || { fail "expected T-100.1 only, got: $ready"; }

# ----------------------------------------------------------------------
# [6] Mark + ready propagation
# ----------------------------------------------------------------------
echo ""
echo "[6] Mark T-100.1 done → T-100.2 becomes ready:"
bash "$R" mark T-100.1 done > /dev/null
ready=$(bash "$R" ready "$T")
[[ "$ready" == "T-100.2" ]] && pass "T-100.2 ready after T-100.1 done" || fail "expected T-100.2, got: $ready"

bash "$R" mark T-100.2 done > /dev/null
ready=$(bash "$R" ready "$T")
[[ "$ready" == "T-100.3" ]] && pass "T-100.3 ready after T-100.2 done" || fail "expected T-100.3, got: $ready"

# ----------------------------------------------------------------------
# [7] Integration-ready gating
# ----------------------------------------------------------------------
echo ""
echo "[7] integration-ready gating:"
out=$(bash "$R" integration-ready "$T" 2>&1); rc=$?
[[ $rc -eq 1 ]] && pass "rc=1 while T-100.3 still pending" || fail "expected 1, got $rc"
[[ "$out" == *"T-100.3"* ]] && pass "names blocking subtask" || fail "didn't name blocker"

bash "$R" mark T-100.3 done > /dev/null
out=$(bash "$R" integration-ready "$T" 2>&1); rc=$?
[[ $rc -eq 0 ]] && pass "rc=0 when all subtasks done" || fail "expected 0, got $rc"
[[ "$out" == *"integration-ready"* ]] && pass "integration-ready message" || fail "no integration-ready msg"

# Empty ready set returns 1 (nothing pending)
bash "$R" ready "$T" > /dev/null 2>&1; rc=$?
[[ $rc -eq 1 ]] && pass "ready exit 1 when none pending" || fail "expected 1, got $rc"

# ----------------------------------------------------------------------
# [8] Status command
# ----------------------------------------------------------------------
echo ""
echo "[8] status command:"
out=$(bash "$R" status "$T" 2>&1)
[[ "$out" == *"T-100.1"*"done"* ]] && pass "status shows T-100.1 done" || fail "status missing T-100.1"
[[ "$out" == *"subtasks_in_flight"* ]] && pass "status shows phase" || fail "status missing phase"

# ----------------------------------------------------------------------
# [9] Bad arg handling
# ----------------------------------------------------------------------
echo ""
echo "[9] error handling:"
bash "$R" mark T-100.1 nonsense > /dev/null 2>&1; rc=$?
[[ $rc -eq 2 ]] && pass "invalid status → rc 2" || fail "expected 2, got $rc"
bash "$R" seed T-DOES-NOT-EXIST > /dev/null 2>&1; rc=$?
[[ $rc -eq 2 ]] && pass "missing task → rc 2" || fail "expected 2, got $rc"

# ----------------------------------------------------------------------
# [10] Planner template aligns with schema (Nodes/Edges format)
# ----------------------------------------------------------------------
echo ""
echo "[10] Planner template emits schema-compliant graph:"
PT=".codenook/prompts-templates/planner.md"
grep -q '## Nodes'                     "$PT" && pass "planner template names ## Nodes" || fail "no Nodes in template"
grep -q '## Edges'                     "$PT" && pass "planner template names ## Edges" || fail "no Edges in template"
grep -q 'depends_on'                   "$PT" && pass "uses depends_on vocab"           || fail "no depends_on"
grep -q 'dependency-graph-schema.md'   "$PT" && pass "references schema doc"           || fail "no schema ref"

echo ""
if [[ $FAIL -eq 0 ]]; then
  echo "=== T21 PASSED ==="
  exit 0
else
  echo "=== T21 FAILED ($FAIL issues) ==="
  exit 1
fi
