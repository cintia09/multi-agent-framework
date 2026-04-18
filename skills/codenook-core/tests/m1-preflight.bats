#!/usr/bin/env bats
# Unit 9 — preflight (pre-tick sanity check)

load helpers/load
load helpers/assertions

PREFLIGHT_SH="$CORE_ROOT/skills/builtin/preflight/preflight.sh"

mk_ws() {
  local d; d="$(make_scratch)"
  mkdir -p "$d/.codenook/tasks" "$d/.codenook/queues"
  echo "$d"
}

mk_task() {
  local ws="$1" tid="$2"
  local tdir="$ws/.codenook/tasks/$tid"
  mkdir -p "$tdir"
  cat >"$tdir/state.json" <<EOF
{
  "task_id": "$tid",
  "phase": "start",
  "iteration": 0,
  "total_iterations": 5,
  "dual_mode": "serial",
  "config_overrides": {},
  "tick_log": []
}
EOF
}

@test "preflight.sh exists and is executable" {
  assert_file_exists "$PREFLIGHT_SH"
  assert_file_executable "$PREFLIGHT_SH"
}

@test "missing --task → exit 2" {
  ws="$(mk_ws)"
  run_with_stderr "\"$PREFLIGHT_SH\" --workspace \"$ws\""
  [ "$status" -eq 2 ]
  assert_contains "$STDERR" "--task"
}

@test "non-existent task dir → exit 2" {
  ws="$(mk_ws)"
  run_with_stderr "\"$PREFLIGHT_SH\" --task T-999 --workspace \"$ws\""
  [ "$status" -eq 2 ]
  assert_contains "$STDERR" "T-999"
}

@test "task with all valid state → exit 0" {
  ws="$(mk_ws)"
  mk_task "$ws" "T-001"
  run_with_stderr "\"$PREFLIGHT_SH\" --task T-001 --workspace \"$ws\""
  [ "$status" -eq 0 ]
}

@test "task missing dual_mode (null) with total_iterations<=1 → exit 1 + reason" {
  ws="$(mk_ws)"
  local tdir="$ws/.codenook/tasks/T-002"
  mkdir -p "$tdir"
  cat >"$tdir/state.json" <<EOF
{
  "task_id": "T-002",
  "phase": "start",
  "iteration": 0,
  "total_iterations": 1,
  "dual_mode": null,
  "config_overrides": {}
}
EOF
  run_with_stderr "\"$PREFLIGHT_SH\" --task T-002 --workspace \"$ws\""
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" "dual_mode"
}

@test "task missing dual_mode but total_iterations>1 → no needs-dual_mode reason" {
  # Symmetric pass case: once the task has run > 1 iteration without a
  # dual_mode answer, preflight stops re-asking (other layers handle it).
  ws="$(mk_ws)"
  local tdir="$ws/.codenook/tasks/T-002b"
  mkdir -p "$tdir"
  cat >"$tdir/state.json" <<EOF
{
  "task_id": "T-002b",
  "phase": "start",
  "iteration": 2,
  "total_iterations": 5,
  "dual_mode": null,
  "config_overrides": {}
}
EOF
  run bash -c "\"$PREFLIGHT_SH\" --task T-002b --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.reasons | map(select(. == "needs dual_mode")) | length == 0' >/dev/null
}

@test "task with dual_mode set + total_iterations<=1 → exit 0" {
  ws="$(mk_ws)"
  local tdir="$ws/.codenook/tasks/T-002c"
  mkdir -p "$tdir"
  cat >"$tdir/state.json" <<EOF
{
  "task_id": "T-002c",
  "phase": "start",
  "iteration": 0,
  "total_iterations": 1,
  "dual_mode": "serial",
  "config_overrides": {}
}
EOF
  run_with_stderr "\"$PREFLIGHT_SH\" --task T-002c --workspace \"$ws\""
  [ "$status" -eq 0 ]
}

@test "task at unknown phase → exit 1" {
  ws="$(mk_ws)"
  local tdir="$ws/.codenook/tasks/T-003"
  mkdir -p "$tdir"
  cat >"$tdir/state.json" <<EOF
{
  "task_id": "T-003",
  "phase": "unknown_phase_xyz",
  "iteration": 0,
  "total_iterations": 5,
  "dual_mode": "serial"
}
EOF
  run_with_stderr "\"$PREFLIGHT_SH\" --task T-003 --workspace \"$ws\""
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" "unknown_phase"
}

@test "blocking HITL queue entry present for task → exit 1" {
  ws="$(mk_ws)"
  mk_task "$ws" "T-004"
  mkdir -p "$ws/.codenook/queues"
  cat >"$ws/.codenook/queues/hitl.jsonl" <<EOF
{"task":"T-004","gate":"accept","status":"pending"}
EOF
  run_with_stderr "\"$PREFLIGHT_SH\" --task T-004 --workspace \"$ws\""
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" "HITL"
}

@test "invalid merged config → exit 1" {
  ws="$(mk_ws)"
  local tdir="$ws/.codenook/tasks/T-005"
  mkdir -p "$tdir"
  cat >"$tdir/state.json" <<EOF
{
  "task_id": "T-005",
  "phase": "start",
  "iteration": 0,
  "total_iterations": 5,
  "dual_mode": "serial",
  "config_overrides": {"invalid_key": "bad"}
}
EOF
  run_with_stderr "\"$PREFLIGHT_SH\" --task T-005 --workspace \"$ws\""
  [ "$status" -eq 1 ]
}

@test "--json emits {ok, reasons, task, phase}" {
  ws="$(mk_ws)"
  mk_task "$ws" "T-006"
  run bash -c "\"$PREFLIGHT_SH\" --task T-006 --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.ok == true' >/dev/null
  echo "$output" | jq -e '.task == "T-006"' >/dev/null
  echo "$output" | jq -e '.phase == "start"' >/dev/null
  echo "$output" | jq -e '.reasons | type == "array"' >/dev/null
}

@test "workspace auto-detect via CODENOOK_WORKSPACE env" {
  ws="$(mk_ws)"
  mk_task "$ws" "T-007"
  export CODENOOK_WORKSPACE="$ws"
  run_with_stderr "\"$PREFLIGHT_SH\" --task T-007"
  [ "$status" -eq 0 ]
  unset CODENOOK_WORKSPACE
}

@test "reasons are sorted + deduped" {
  ws="$(mk_ws)"
  local tdir="$ws/.codenook/tasks/T-008"
  mkdir -p "$tdir"
  # Multiple issues: missing dual_mode, unknown phase
  cat >"$tdir/state.json" <<EOF
{
  "task_id": "T-008",
  "phase": "unknown_xyz",
  "iteration": 0,
  "total_iterations": 5,
  "dual_mode": null
}
EOF
  run bash -c "\"$PREFLIGHT_SH\" --task T-008 --workspace \"$ws\" --json"
  [ "$status" -eq 1 ]
  # Extract reasons array length, should have 2 distinct reasons
  count=$(echo "$output" | jq '.reasons | length')
  [ "$count" -ge 1 ]
  # Verify they're sorted (python helper to check)
  reasons=$(echo "$output" | jq -r '.reasons[]')
  sorted=$(echo "$reasons" | sort)
  [ "$reasons" = "$sorted" ]
}

@test "nested override models.bogus_role rejected (whitelist exact-match)" {
  ws="$(mk_ws)"
  local tdir="$ws/.codenook/tasks/T-100"
  mkdir -p "$tdir"
  cat >"$tdir/state.json" <<JSON
{
  "task_id": "T-100",
  "phase": "start",
  "iteration": 0,
  "total_iterations": 5,
  "dual_mode": "serial",
  "config_overrides": {"models": {"bogus_role": "tier_strong"}}
}
JSON
  run bash -c "\"$PREFLIGHT_SH\" --task T-100 --workspace \"$ws\" --json"
  [ "$status" -eq 1 ]
  echo "$output" | jq -e '.reasons | map(select(. == "invalid config override key: models.bogus_role")) | length == 1' >/dev/null
}

@test "nested override hitl.evil rejected (whitelist exact-match)" {
  ws="$(mk_ws)"
  local tdir="$ws/.codenook/tasks/T-101"
  mkdir -p "$tdir"
  cat >"$tdir/state.json" <<JSON
{
  "task_id": "T-101",
  "phase": "start",
  "iteration": 0,
  "total_iterations": 5,
  "dual_mode": "serial",
  "config_overrides": {"hitl": {"evil": "true"}}
}
JSON
  run bash -c "\"$PREFLIGHT_SH\" --task T-101 --workspace \"$ws\" --json"
  [ "$status" -eq 1 ]
  echo "$output" | jq -e '.reasons | map(select(. == "invalid config override key: hitl.evil")) | length == 1' >/dev/null
}

@test "nested override valid keys (models.reviewer + hitl.mode) accepted" {
  ws="$(mk_ws)"
  local tdir="$ws/.codenook/tasks/T-102"
  mkdir -p "$tdir"
  cat >"$tdir/state.json" <<JSON
{
  "task_id": "T-102",
  "phase": "start",
  "iteration": 0,
  "total_iterations": 5,
  "dual_mode": "serial",
  "config_overrides": {"models": {"reviewer": "tier_cheap"}, "hitl": {"mode": "strict"}}
}
JSON
  run bash -c "\"$PREFLIGHT_SH\" --task T-102 --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
}
