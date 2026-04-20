#!/usr/bin/env bats
# M10.6 — snapshot v2 schema + audit 6+4 + perf budgets (TC-M10.6-01..05).
# Spec: docs/task-chains.md §8 §9
# Cases: docs/m10-test-cases.md §M10.6
#
# Perf cases (TC-M10.6-02, TC-M10.6-03) honour CN_SKIP_PERF=1 to allow
# CI lanes to opt out without code changes. Default behaviour is to run
# them and assert the spec budgets verbatim.

load helpers/load
load helpers/assertions
load helpers/m10_chain

# ---------------------------------------------------------------- TC-M10.6-01

@test "[m10.6] TC-M10.6-01 6 chain outcomes flow through extraction-log" {
  ws=$(m10_seed_workspace)
  mock="$ws/_mock"
  make_task "$ws" T-001
  make_task "$ws" T-002
  make_task "$ws" T-003

  log="$ws/$M10_AUDIT_LOG_REL"
  mkdir -p "$(dirname "$log")"
  : >"$log"

  # Outcome 1: chain_attached  (T-002.parent = T-001)
  PYTHONPATH="$M10_LIB_DIR" WS="$ws" python3 -c \
    'import os, task_chain as tc; tc.set_parent(os.environ["WS"], "T-002", "T-001")'

  # Outcome 2: chain_attach_failed  (T-001.parent = T-002 → cycle)
  PYTHONPATH="$M10_LIB_DIR" WS="$ws" python3 - <<'PY' || true
import os, task_chain as tc
try:
    tc.set_parent(os.environ["WS"], "T-001", "T-002")
except Exception:
    pass
PY

  # Outcome 6 (out of order on purpose): set up T-003 attached to T-002
  # so we can later corrupt T-002 mid-chain to force chain_walk_truncated.
  PYTHONPATH="$M10_LIB_DIR" WS="$ws" python3 -c \
    'import os, task_chain as tc; tc.set_parent(os.environ["WS"], "T-003", "T-002")'

  # Outcome 4: chain_summarized  (mock LLM ok)
  seed_mock_llm "$mock" chain_summarize "summary OK"
  PYTHONPATH="$M10_LIB_DIR" CN_LLM_MOCK_DIR="$mock" WS="$ws" python3 -c \
    'import os, chain_summarize as cs; cs.summarize(os.environ["WS"], "T-003")' >/dev/null

  # Outcome 5: chain_summarize_failed  (mock LLM error)
  PYTHONPATH="$M10_LIB_DIR" CN_LLM_MOCK_ERROR="boom" WS="$ws" python3 -c \
    'import os, chain_summarize as cs; cs.summarize(os.environ["WS"], "T-003")' >/dev/null

  # Outcome 3: chain_walk_truncated  (corrupt T-002 mid-chain)
  printf '%s' '{ this is not json' >"$ws/.codenook/tasks/T-002/state.json"
  PYTHONPATH="$M10_LIB_DIR" WS="$ws" python3 -c \
    'import os, task_chain as tc; tc.walk_ancestors(os.environ["WS"], "T-003")' >/dev/null

  # Repair T-002 then detach for outcome 6.
  cat >"$ws/.codenook/tasks/T-002/state.json" <<'JSON'
{
  "schema_version": 1,
  "task_id": "T-002",
  "plugin": "development",
  "phase": "design",
  "iteration": 0,
  "max_iterations": 5,
  "status": "in_progress",
  "history": [],
  "parent_id": "T-001",
  "chain_root": "T-001"
}
JSON

  # Outcome 6: chain_detached  (T-002 → no parent)
  PYTHONPATH="$M10_LIB_DIR" WS="$ws" python3 -c \
    'import os, task_chain as tc; tc.detach(os.environ["WS"], "T-002")'

  # Verify all 6 outcomes appear at least once.
  for oc in chain_attached chain_attach_failed chain_walk_truncated \
            chain_summarized chain_summarize_failed chain_detached; do
    n=$(jq -c --arg o "$oc" 'select(.outcome==$o)' "$log" | wc -l | tr -d ' ')
    [ "$n" -ge 1 ] || { echo "missing outcome=$oc"; cat "$log"; return 1; }
  done

  # Verify schema for each chain-asset_type canonical record (≥8 keys,
  # asset_type==chain). Diagnostic side-records may carry extra keys.
  bad=$(jq -c 'select(.asset_type=="chain" and .outcome!="diagnostic")
               | select((. | keys | length) < 8)' "$log" | wc -l | tr -d ' ')
  [ "$bad" -eq 0 ] || { echo "schema-violating chain rows: $bad"; cat "$log"; return 1; }
  notchain=$(jq -rc 'select(.outcome | startswith("chain_"))
                     | select(.asset_type != "chain") | .outcome' "$log" | wc -l | tr -d ' ')
  [ "$notchain" -eq 0 ] || { echo "chain_* rows with asset_type != chain"; cat "$log"; return 1; }
}

# ---------------------------------------------------------------- TC-M10.6-02

@test "[m10.6] TC-M10.6-02 walk_ancestors depth=10 wall avg <= 100ms" {
  if [ "${CN_SKIP_PERF:-0}" = "1" ]; then skip "perf-only"; fi
  ws=$(m10_seed_workspace)
  leaf=$(make_chain_depth "$ws" T-root 10)
  # Prime snapshot.
  PYTHONPATH="$M10_LIB_DIR" WS="$ws" LEAF="$leaf" python3 -c \
    'import os, task_chain as tc; tc.chain_root(os.environ["WS"], os.environ["LEAF"])' >/dev/null

  avg_ms=$(PYTHONPATH="$M10_LIB_DIR" WS="$ws" LEAF="$leaf" python3 - <<'PY'
import os, time, task_chain as tc
ws  = os.environ["WS"]
lf  = os.environ["LEAF"]
N   = 100
t0 = time.perf_counter_ns()
for _ in range(N):
    tc.walk_ancestors(ws, lf)
t1 = time.perf_counter_ns()
avg_ms = (t1 - t0) / N / 1_000_000.0
print(f"{avg_ms:.3f}")
PY
)
  echo "avg_ms=$avg_ms"
  ok=$(python3 -c "import sys; sys.exit(0 if float(sys.argv[1]) <= 100.0 else 1)" "$avg_ms" \
       && echo 1 || echo 0)
  [ "$ok" -eq 1 ] || { echo "avg ${avg_ms}ms > 100ms budget"; return 1; }
}

# ---------------------------------------------------------------- TC-M10.6-03

@test "[m10.6] TC-M10.6-03 cold rebuild <=1s, warm cache <=5ms (N=200)" {
  if [ "${CN_SKIP_PERF:-0}" = "1" ]; then skip "perf-only"; fi
  ws=$(m10_seed_workspace)
  leaf=$(make_chain_depth "$ws" T-root 200)
  # Cold start: remove snapshot file.
  rm -f "$ws/.codenook/tasks/.chain-snapshot.json"

  read first_ms second_ms <<<"$(PYTHONPATH=$M10_LIB_DIR WS=$ws LEAF=$leaf python3 - <<'PY'
import os, time, task_chain as tc
ws = os.environ["WS"]
lf = os.environ["LEAF"]
t0 = time.perf_counter_ns()
tc.chain_root(ws, lf)
t1 = time.perf_counter_ns()
tc.chain_root(ws, lf)
t2 = time.perf_counter_ns()
print(f"{(t1-t0)/1e6:.3f} {(t2-t1)/1e6:.3f}")
PY
)"
  echo "first=${first_ms}ms second=${second_ms}ms"
  ok=$(python3 -c "import sys; a,b=float(sys.argv[1]),float(sys.argv[2]); sys.exit(0 if a<=1000.0 and b<=5.0 else 1)" \
       "$first_ms" "$second_ms" && echo 1 || echo 0)
  [ "$ok" -eq 1 ] || { echo "cold=${first_ms}ms (<=1000) warm=${second_ms}ms (<=5)"; return 1; }
}

# ---------------------------------------------------------------- TC-M10.6-04

@test "[m10.6] TC-M10.6-04 set_parent bumps snapshot generation + entries refreshed" {
  ws=$(m10_seed_workspace)
  make_task "$ws" T-X
  make_task "$ws" T-Y
  # Seed a baseline snapshot so we can observe a strict bump.
  PYTHONPATH="$M10_LIB_DIR" WS="$ws" python3 -c \
    'import os, task_chain as tc; tc._build_snapshot(os.environ["WS"])' >/dev/null
  snap="$ws/.codenook/tasks/.chain-snapshot.json"
  [ -f "$snap" ] || { echo "no snapshot"; return 1; }
  gen0=$(jq -r '.generation' "$snap")

  PYTHONPATH="$M10_LIB_DIR" WS="$ws" python3 -c \
    'import os, task_chain as tc; tc.set_parent(os.environ["WS"], "T-X", "T-Y")'

  gen1=$(jq -r '.generation' "$snap")
  [ "$gen1" -gt "$gen0" ] || { echo "gen $gen0 -> $gen1 (no bump)"; return 1; }

  # entries[T-X] reflects the new parent + chain_root.
  pid=$(jq -r '.entries["T-X"].parent_id' "$snap")
  rt=$(jq -r '.entries["T-X"].chain_root'  "$snap")
  [ "$pid" = "T-Y" ] || { echo "entries[T-X].parent_id=$pid"; cat "$snap"; return 1; }
  [ "$rt"  = "T-Y" ] || { echo "entries[T-X].chain_root=$rt"; cat "$snap"; return 1; }

  mt=$(jq -r '.entries["T-X"].state_mtime' "$snap")
  [ -n "$mt" ] && [ "$mt" != "null" ] || { echo "missing state_mtime"; return 1; }
}

# ---------------------------------------------------------------- TC-M10.6-05

@test "[m10.6] TC-M10.6-05 detach bumps once; no-op detach does not re-bump" {
  ws=$(m10_seed_workspace)
  make_chain "$ws" T-Y T-X   # T-X.parent = T-Y
  snap="$ws/.codenook/tasks/.chain-snapshot.json"
  [ -f "$snap" ] || { echo "no snapshot"; return 1; }
  has_entries=$(jq -r 'has("entries")' "$snap")
  [ "$has_entries" = "true" ] || { echo "snapshot missing 'entries' (schema v2)"; cat "$snap"; return 1; }
  gen_g=$(jq -r '.generation' "$snap")

  PYTHONPATH="$M10_LIB_DIR" WS="$ws" python3 -c \
    'import os, task_chain as tc; tc.detach(os.environ["WS"], "T-X")'
  gen_after_detach=$(jq -r '.generation' "$snap")
  [ "$gen_after_detach" -gt "$gen_g" ] || { echo "gen $gen_g -> $gen_after_detach (no bump)"; return 1; }

  PYTHONPATH="$M10_LIB_DIR" WS="$ws" python3 -c \
    'import os, task_chain as tc; tc.detach(os.environ["WS"], "T-X")'
  gen_after_noop=$(jq -r '.generation' "$snap")
  [ "$gen_after_noop" -eq "$gen_after_detach" ] \
    || { echo "no-op detach bumped: $gen_after_detach -> $gen_after_noop"; return 1; }

  # entries[T-X] now has parent_id=null and chain_root=null.
  pid=$(jq -r '.entries["T-X"].parent_id' "$snap")
  rt=$(jq -r '.entries["T-X"].chain_root' "$snap")
  [ "$pid" = "null" ] || { echo "entries[T-X].parent_id=$pid"; cat "$snap"; return 1; }
  [ "$rt"  = "null" ] || { echo "entries[T-X].chain_root=$rt"; cat "$snap"; return 1; }
}
