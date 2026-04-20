#!/usr/bin/env bats
# M10.1 — _lib/task_chain.py primitives (TC-M10.1-01..12).
# Spec: docs/task-chains.md §2 §3 §4 §8 §9
# Cases: docs/m10-test-cases.md §M10.1

load helpers/load
load helpers/assertions
load helpers/m10_chain

# ------------------------------------------------------------------ TC-M10.1-01

@test "[m10.1] TC-M10.1-01 get_parent on fresh task returns None" {
  ws=$(m10_seed_workspace)
  make_task "$ws" T-001
  run env PYTHONPATH="$M10_LIB_DIR" WS="$ws" python3 -c \
    'import os, task_chain as tc; print(tc.get_parent(os.environ["WS"], "T-001"))'
  [ "$status" -eq 0 ] || { echo "out=$output"; return 1; }
  [ "$output" = "None" ] || { echo "got=$output"; return 1; }
}

# ------------------------------------------------------------------ TC-M10.1-02

@test "[m10.1] TC-M10.1-02 get_parent on missing task returns None" {
  ws=$(m10_seed_workspace)
  run env PYTHONPATH="$M10_LIB_DIR" WS="$ws" python3 -c \
    'import os, task_chain as tc; print(tc.get_parent(os.environ["WS"], "T-404"))'
  [ "$status" -eq 0 ] || { echo "out=$output"; return 1; }
  [ "$output" = "None" ] || { echo "got=$output"; return 1; }
}

# ------------------------------------------------------------------ TC-M10.1-03

@test "[m10.1] TC-M10.1-03 set_parent happy path writes parent_id + chain_root" {
  ws=$(m10_seed_workspace)
  make_task "$ws" T-005
  make_task "$ws" T-007
  make_task "$ws" T-012
  PYTHONPATH="$M10_LIB_DIR" WS="$ws" python3 - <<'PY'
import os, task_chain as tc
ws = os.environ["WS"]
tc.set_parent(ws, "T-007", "T-005")
tc.set_parent(ws, "T-012", "T-007")
PY
  [ "$(tc_state_field "$ws" T-012 parent_id)"  = "T-007" ]
  [ "$(tc_state_field "$ws" T-012 chain_root)" = "T-005" ]
  [ "$(tc_state_field "$ws" T-007 parent_id)"  = "T-005" ]
  [ "$(tc_state_field "$ws" T-007 chain_root)" = "T-005" ]
  assert_audit "$ws" chain_attached
}

# ------------------------------------------------------------------ TC-M10.1-04

@test "[m10.1] TC-M10.1-04 set_parent self-loop raises CycleError" {
  ws=$(m10_seed_workspace)
  make_task "$ws" T-001
  run_with_stderr "PYTHONPATH=\"$M10_LIB_DIR\" WS=\"$ws\" python3 -c '
import os, task_chain as tc
tc.set_parent(os.environ[\"WS\"], \"T-001\", \"T-001\")
'"
  [ "$status" -ne 0 ]
  assert_contains "$STDERR" "CycleError"
  assert_audit "$ws" chain_attach_failed
  jq -e 'select(.outcome=="chain_attach_failed") | .reason | test("cycle";"i")' \
    "$ws/$M10_AUDIT_LOG_REL" >/dev/null \
    || { cat "$ws/$M10_AUDIT_LOG_REL"; return 1; }
  [ "$(tc_state_field "$ws" T-001 parent_id)" = "null" ]
}

# ------------------------------------------------------------------ TC-M10.1-05

@test "[m10.1] TC-M10.1-05 set_parent indirect cycle raises CycleError" {
  ws=$(m10_seed_workspace)
  # chain T-003 → T-002 → T-001 (child → parent)
  make_chain "$ws" T-001 T-002 T-003
  run_with_stderr "PYTHONPATH=\"$M10_LIB_DIR\" WS=\"$ws\" python3 -c '
import os, task_chain as tc
tc.set_parent(os.environ[\"WS\"], \"T-001\", \"T-003\")
'"
  [ "$status" -ne 0 ]
  assert_contains "$STDERR" "CycleError"
  [ "$(tc_state_field "$ws" T-001 parent_id)" = "null" ]
  assert_audit "$ws" chain_attach_failed
}

# ------------------------------------------------------------------ TC-M10.1-06

@test "[m10.1] TC-M10.1-06 walk_ancestors returns child→root order including self" {
  ws=$(m10_seed_workspace)
  make_chain "$ws" T-005 T-007 T-012
  run env PYTHONPATH="$M10_LIB_DIR" WS="$ws" python3 -c \
    'import os, task_chain as tc; print(",".join(tc.walk_ancestors(os.environ["WS"], "T-012")))'
  [ "$status" -eq 0 ] || { echo "out=$output"; return 1; }
  [ "$output" = "T-012,T-007,T-005" ] || { echo "got=$output"; return 1; }
}

# ------------------------------------------------------------------ TC-M10.1-07

@test "[m10.1] TC-M10.1-07 walk_ancestors mid-chain corruption truncates without raising" {
  ws=$(m10_seed_workspace)
  make_chain "$ws" T-005 T-007 T-012
  echo "{ broken json" > "$ws/.codenook/tasks/T-007/state.json"
  run env PYTHONPATH="$M10_LIB_DIR" WS="$ws" python3 -c \
    'import os, task_chain as tc; print(",".join(tc.walk_ancestors(os.environ["WS"], "T-012")))'
  [ "$status" -eq 0 ] || { echo "out=$output"; return 1; }
  [ "$output" = "T-012" ] || { echo "got=$output"; return 1; }
  assert_audit "$ws" chain_walk_truncated
}

# ------------------------------------------------------------------ TC-M10.1-08

@test "[m10.1] TC-M10.1-08 chain_root cache hit avoids walk" {
  ws=$(m10_seed_workspace)
  make_chain "$ws" T-005 T-007 T-012
  # state.json.chain_root is already populated by make_chain.
  PYTHONPATH="$M10_LIB_DIR" WS="$ws" python3 - <<'PY'
import os, task_chain as tc
ws = os.environ["WS"]
calls = {"n": 0}
orig = tc._read_state_json
def spy(w, t):
    calls["n"] += 1
    return orig(w, t)
tc._read_state_json = spy
assert tc.chain_root(ws, "T-012") == "T-005", "first call wrong"
assert calls["n"] == 1, f"first call read {calls['n']} times, want 1"
assert tc.chain_root(ws, "T-012") == "T-005", "second call wrong"
assert calls["n"] <= 2, f"second call total {calls['n']}, want <=2"
PY
}

# ------------------------------------------------------------------ TC-M10.1-09

@test "[m10.1] TC-M10.1-09 CLI attach exit 0 + state updated" {
  ws=$(m10_seed_workspace)
  make_task "$ws" T-005
  make_task "$ws" T-007
  run env PYTHONPATH="$M10_LIB_DIR" python3 -m task_chain attach T-007 T-005 --workspace "$ws"
  [ "$status" -eq 0 ] || { echo "out=$output"; return 1; }
  [ "$(tc_state_field "$ws" T-007 parent_id)"  = "T-005" ]
  [ "$(tc_state_field "$ws" T-007 chain_root)" = "T-005" ]
  [ -f "$ws/.codenook/tasks/.chain-snapshot.json" ]
  gen=$(jq -r '.generation' "$ws/.codenook/tasks/.chain-snapshot.json")
  [ "$gen" -ge 1 ] || { echo "generation=$gen"; return 1; }
}

# ------------------------------------------------------------------ TC-M10.1-10

@test "[m10.1] TC-M10.1-10 CLI detach is idempotent" {
  ws=$(m10_seed_workspace)
  make_chain "$ws" T-005 T-007
  run env PYTHONPATH="$M10_LIB_DIR" python3 -m task_chain detach T-007 --workspace "$ws"
  [ "$status" -eq 0 ] || { echo "out=$output"; return 1; }
  before=$(tc_audit_count "$ws" chain_detached)
  run env PYTHONPATH="$M10_LIB_DIR" python3 -m task_chain detach T-007 --workspace "$ws"
  [ "$status" -eq 0 ] || { echo "out=$output"; return 1; }
  [ "$(tc_state_field "$ws" T-007 parent_id)"  = "null" ]
  [ "$(tc_state_field "$ws" T-007 chain_root)" = "null" ]
  after=$(tc_audit_count "$ws" chain_detached)
  [ "$before" -eq "$after" ] || { echo "audit grew: $before -> $after"; return 1; }
}

# ------------------------------------------------------------------ TC-M10.1-11

@test "[m10.1] TC-M10.1-11 CLI show outputs child→root order" {
  ws=$(m10_seed_workspace)
  make_chain "$ws" T-005 T-007 T-012
  run env PYTHONPATH="$M10_LIB_DIR" python3 -m task_chain show T-012 --workspace "$ws" --format=text
  [ "$status" -eq 0 ] || { echo "out=$output"; return 1; }
  first=$(echo "$output" | sed -n '1p')
  last=$(echo "$output" | sed -n '$p')
  assert_contains "$first" "T-012"
  assert_contains "$last"  "T-005"

  run env PYTHONPATH="$M10_LIB_DIR" bash -c \
    "python3 -m task_chain show T-012 --workspace '$ws' --format=json | jq -r '.ancestors | join(\",\")'"
  [ "$status" -eq 0 ] || { echo "out=$output"; return 1; }
  [ "$output" = "T-012,T-007,T-005" ] || { echo "got=$output"; return 1; }
}

# ------------------------------------------------------------------ TC-M10.1-12

@test "[m10.1] TC-M10.1-12 CLI attach on already-attached task exits 3 without --force" {
  ws=$(m10_seed_workspace)
  make_chain "$ws" T-005 T-007
  make_task "$ws" T-099
  run_with_stderr "PYTHONPATH=\"$M10_LIB_DIR\" python3 -m task_chain attach T-007 T-099 --workspace \"$ws\""
  [ "$status" -eq 3 ] || { echo "exit=$status stderr=$STDERR out=$output"; return 1; }
  assert_contains "$STDERR" "AlreadyAttachedError"
  [ "$(tc_state_field "$ws" T-007 parent_id)" = "T-005" ]

  gen_before=$(jq -r '.generation' "$ws/.codenook/tasks/.chain-snapshot.json")
  run env PYTHONPATH="$M10_LIB_DIR" python3 -m task_chain attach T-007 T-099 --workspace "$ws" --force
  [ "$status" -eq 0 ] || { echo "out=$output"; return 1; }
  [ "$(tc_state_field "$ws" T-007 parent_id)" = "T-099" ]
  gen_after=$(jq -r '.generation' "$ws/.codenook/tasks/.chain-snapshot.json")
  [ "$gen_after" -gt "$gen_before" ] || { echo "gen $gen_before -> $gen_after"; return 1; }
}

# ------------------------------------------------------------------ TC-M10.7-01 (MINOR-01 lock-in)

@test "[m10.7] TC-M10.7-01 CLI usage error exits 64 (spec §4.3)" {
  ws=$(m10_seed_workspace)
  # Unknown subcommand → argparse error → must exit 64.
  run env PYTHONPATH="$M10_LIB_DIR" python3 -m task_chain bogus --workspace "$ws"
  [ "$status" -eq 64 ] || { echo "unknown-subcmd exit=$status out=$output"; return 1; }

  # Missing required positional → argparse error → must exit 64.
  run env PYTHONPATH="$M10_LIB_DIR" python3 -m task_chain attach --workspace "$ws"
  [ "$status" -eq 64 ] || { echo "missing-arg exit=$status out=$output"; return 1; }

  # Unknown flag → argparse error → must exit 64.
  run env PYTHONPATH="$M10_LIB_DIR" python3 -m task_chain show --no-such-flag --workspace "$ws"
  [ "$status" -eq 64 ] || { echo "bad-flag exit=$status out=$output"; return 1; }
}

# ------------------------------------------------------------------ TC-M10.7-02 (MINOR-02 lock-in)

@test "[m10.7] TC-M10.7-02 set_parent under truncated parent walk emits warn + chain_root_uncertain" {
  ws=$(m10_seed_workspace)
  # Build a chain T-001 ← T-002 ← T-003, then hand-corrupt T-001 to
  # point back at T-003 — a self-contained cycle in the parent's
  # ancestry (does NOT include the new child T-NEW).
  make_chain "$ws" T-001 T-002 T-003
  PYTHONPATH="$M10_LIB_DIR" WS="$ws" python3 - <<'PY'
import json, os
p = os.path.join(os.environ["WS"], ".codenook/tasks/T-001/state.json")
s = json.load(open(p))
s["parent_id"] = "T-003"
json.dump(s, open(p, "w"))
PY
  make_task "$ws" T-NEW

  PYTHONPATH="$M10_LIB_DIR" WS="$ws" python3 - <<'PY'
import os, task_chain as tc
tc.set_parent(os.environ["WS"], "T-NEW", "T-003")
PY

  log="$ws/$M10_AUDIT_LOG_REL"
  # chain_attached recorded with verdict=warn
  jq -e 'select(.outcome=="chain_attached" and .verdict=="warn" and .source_task=="T-NEW")' \
    "$log" >/dev/null \
    || { echo "expected warn chain_attached"; cat "$log"; return 1; }
  # diagnostic side-record carries chain_root_uncertain=true
  jq -e 'select(.outcome=="diagnostic" and .source_task=="T-NEW" and .chain_root_uncertain==true)' \
    "$log" >/dev/null \
    || { echo "expected chain_root_uncertain=true diagnostic"; cat "$log"; return 1; }
  # Attachment still applied (best-effort).
  [ "$(tc_state_field "$ws" T-NEW parent_id)" = "T-003" ]
}

# ------------------------------------------------------------------ TC-M10.7-04 (MINOR-08 lock-in)

@test "[m10.7] TC-M10.7-04 set_parent refuses corrupt parent ancestry (CorruptChainError)" {
  ws=$(m10_seed_workspace)
  # Build T-001 ← T-002 then hand-corrupt T-002 to point at a phantom
  # task that has no state.json on disk.
  make_chain "$ws" T-001 T-002
  PYTHONPATH="$M10_LIB_DIR" WS="$ws" python3 - <<'PY'
import json, os
p = os.path.join(os.environ["WS"], ".codenook/tasks/T-002/state.json")
s = json.load(open(p))
s["parent_id"] = "T-PHANTOM"
json.dump(s, open(p, "w"))
PY
  make_task "$ws" T-NEW

  # Library API: must raise CorruptChainError.
  run_with_stderr "PYTHONPATH=\"$M10_LIB_DIR\" WS=\"$ws\" python3 -c '
import os, task_chain as tc
try:
    tc.set_parent(os.environ[\"WS\"], \"T-NEW\", \"T-002\")
except tc.CorruptChainError as e:
    print(\"CORRUPT:\" + str(e))
'"
  [ "$status" -eq 0 ] || { echo "exit=$status stderr=$STDERR out=$output"; return 1; }
  echo "$output" | grep -q '^CORRUPT:' \
    || { echo "expected CorruptChainError, out=$output stderr=$STDERR"; return 1; }

  # State NOT mutated.
  pid=$(tc_state_field "$ws" T-NEW parent_id)
  [ "$pid" = "null" ] || { echo "parent_id leaked: $pid"; return 1; }
  # Audit recorded as chain_attach_failed.
  assert_audit "$ws" chain_attach_failed

  # CLI surface: must exit 2 (cycle/corrupt class).
  run env PYTHONPATH="$M10_LIB_DIR" python3 -m task_chain attach T-NEW T-002 --workspace "$ws"
  [ "$status" -eq 2 ] || { echo "CLI exit=$status out=$output"; return 1; }
}
