#!/usr/bin/env bats
# Unit 12 — orchestrator-tick (advance one task one phase OR dispatch one sub-agent)

load helpers/load
load helpers/assertions

TICK_SH="$CORE_ROOT/skills/builtin/orchestrator-tick/tick.sh"

mk_ws() {
  local d; d="$(make_scratch)"
  mkdir -p "$d/.codenook/tasks" "$d/.codenook/queues" "$d/.codenook/history"
  echo "$d"
}

mk_task() {
  local ws="$1" tid="$2" phase="${3:-start}"
  local tdir="$ws/.codenook/tasks/$tid"
  mkdir -p "$tdir"
  cat >"$tdir/state.json" <<EOF
{
  "task_id": "$tid",
  "phase": "$phase",
  "iteration": 0,
  "total_iterations": 5,
  "dual_mode": "serial",
  "config_overrides": {},
  "tick_log": []
}
EOF
}

mk_dispatch_stub() {
  local stub="$1"
  cat >"$stub" <<'EOF'
#!/usr/bin/env bash
# Stub dispatch command - always succeeds
echo "dispatch stub called" >&2
mkdir -p "$(dirname "$CODENOOK_DISPATCH_SUMMARY")"
echo '{"success":true,"summary":"stub dispatch"}' >"$CODENOOK_DISPATCH_SUMMARY"
exit 0
EOF
  chmod +x "$stub"
}

@test "tick.sh exists and is executable" {
  assert_file_exists "$TICK_SH"
  assert_file_executable "$TICK_SH"
}

@test "missing args → exit 2" {
  ws="$(mk_ws)"
  run_with_stderr "\"$TICK_SH\" --workspace \"$ws\""
  [ "$status" -eq 2 ]
}

@test "start-of-phase task → preflight passes → dispatch invoked → state advances" {
  ws="$(mk_ws)"
  mk_task "$ws" "T-001" "start"
  stub="$ws/dispatch-stub.sh"
  mk_dispatch_stub "$stub"
  
  export CODENOOK_DISPATCH_CMD="$stub"
  run_with_stderr "\"$TICK_SH\" --task T-001 --workspace \"$ws\""
  [ "$status" -eq 0 ]
  
  # Check iteration incremented
  iter=$(jq -r '.iteration' "$ws/.codenook/tasks/T-001/state.json")
  [ "$iter" -eq 1 ]
  unset CODENOOK_DISPATCH_CMD
}

@test "preflight fail → exit 1 + reasons in state.json.tick_log" {
  ws="$(mk_ws)"
  # Create invalid task (missing dual_mode at first tick: total_iterations<=1)
  local tdir="$ws/.codenook/tasks/T-002"
  mkdir -p "$tdir"
  cat >"$tdir/state.json" <<EOF
{
  "task_id": "T-002",
  "phase": "start",
  "iteration": 0,
  "total_iterations": 1,
  "dual_mode": null,
  "tick_log": []
}
EOF
  
  run_with_stderr "\"$TICK_SH\" --task T-002 --workspace \"$ws\""
  [ "$status" -eq 1 ]
  # Check tick_log has entry
  log_len=$(jq '.tick_log | length' "$tdir/state.json")
  [ "$log_len" -ge 1 ]
}

@test "dispatch-audit invoked before each dispatch (assert via audit jsonl line)" {
  ws="$(mk_ws)"
  mk_task "$ws" "T-003" "start"
  stub="$ws/dispatch-stub.sh"
  mk_dispatch_stub "$stub"
  
  export CODENOOK_DISPATCH_CMD="$stub"
  run_with_stderr "\"$TICK_SH\" --task T-003 --workspace \"$ws\""
  unset CODENOOK_DISPATCH_CMD
  
  # Check dispatch audit log exists
  audit_file="$ws/.codenook/history/dispatch.jsonl"
  [ -f "$audit_file" ]
  # Should have at least one line
  lines=$(wc -l <"$audit_file" | tr -d ' ')
  [ "$lines" -ge 1 ]
}

@test "--dry-run: no state written, no dispatch" {
  ws="$(mk_ws)"
  mk_task "$ws" "T-004" "start"
  
  # Snapshot state before
  before=$(cat "$ws/.codenook/tasks/T-004/state.json")
  
  run_with_stderr "\"$TICK_SH\" --task T-004 --workspace \"$ws\" --dry-run"
  [ "$status" -eq 0 ]
  
  # State should be unchanged
  after=$(cat "$ws/.codenook/tasks/T-004/state.json")
  [ "$before" = "$after" ]
}

@test "phase with fanout:true → enqueues subtasks into queue" {
  skip "Fanout requires phase config - defer to integration tests"
}

@test "fan-out wait: subtasks pending → exit 3 idle" {
  skip "Fanout requires phase config - defer to integration tests"
}

@test "phase with hitl:confirm → enqueues into hitl-queue + exit 1 blocked" {
  skip "HITL requires phase config - defer to integration tests"
}

@test "iteration counter increments once per tick" {
  ws="$(mk_ws)"
  mk_task "$ws" "T-007" "start"
  stub="$ws/dispatch-stub.sh"
  mk_dispatch_stub "$stub"
  
  export CODENOOK_DISPATCH_CMD="$stub"
  
  # First tick
  run_with_stderr "\"$TICK_SH\" --task T-007 --workspace \"$ws\""
  [ "$status" -eq 0 ]
  iter=$(jq -r '.iteration' "$ws/.codenook/tasks/T-007/state.json")
  [ "$iter" -eq 1 ]
  
  # Second tick
  run_with_stderr "\"$TICK_SH\" --task T-007 --workspace \"$ws\""
  [ "$status" -eq 0 ]
  iter=$(jq -r '.iteration' "$ws/.codenook/tasks/T-007/state.json")
  [ "$iter" -eq 2 ]
  
  unset CODENOOK_DISPATCH_CMD
}

@test "total_iterations cap reached → exit 1 + reason" {
  ws="$(mk_ws)"
  # Create task at iteration limit
  local tdir="$ws/.codenook/tasks/T-008"
  mkdir -p "$tdir"
  cat >"$tdir/state.json" <<EOF
{
  "task_id": "T-008",
  "phase": "start",
  "iteration": 5,
  "total_iterations": 5,
  "dual_mode": "serial",
  "tick_log": []
}
EOF
  
  run_with_stderr "\"$TICK_SH\" --task T-008 --workspace \"$ws\""
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" "iteration limit"
}

@test "unknown task → exit 2" {
  ws="$(mk_ws)"
  run_with_stderr "\"$TICK_SH\" --task T-999 --workspace \"$ws\""
  [ "$status" -eq 2 ]
}

@test "terminal phase → exit 3" {
  ws="$(mk_ws)"
  mk_task "$ws" "T-010" "done"
  run_with_stderr "\"$TICK_SH\" --task T-010 --workspace \"$ws\""
  [ "$status" -eq 3 ]
}

@test "dispatch payload ≤500 chars" {
  ws="$(mk_ws)"
  mk_task "$ws" "T-011" "start"
  
  # Custom stub that captures payload
  stub="$ws/dispatch-stub.sh"
  cat >"$stub" <<'EOF'
#!/usr/bin/env bash
payload_len=${#CODENOOK_DISPATCH_PAYLOAD}
if [ "$payload_len" -gt 500 ]; then
  echo "payload too long: $payload_len" >&2
  exit 1
fi
mkdir -p "$(dirname "$CODENOOK_DISPATCH_SUMMARY")"
echo '{"success":true}' >"$CODENOOK_DISPATCH_SUMMARY"
exit 0
EOF
  chmod +x "$stub"
  
  export CODENOOK_DISPATCH_CMD="$stub"
  run_with_stderr "\"$TICK_SH\" --task T-011 --workspace \"$ws\""
  [ "$status" -eq 0 ]
  unset CODENOOK_DISPATCH_CMD
}

@test "tick_log[] appended with {ts, action, result}" {
  ws="$(mk_ws)"
  mk_task "$ws" "T-012" "start"
  stub="$ws/dispatch-stub.sh"
  mk_dispatch_stub "$stub"
  
  export CODENOOK_DISPATCH_CMD="$stub"
  run_with_stderr "\"$TICK_SH\" --task T-012 --workspace \"$ws\""
  [ "$status" -eq 0 ]
  unset CODENOOK_DISPATCH_CMD
  
  # Check tick_log has entry
  log=$(jq '.tick_log[-1]' "$ws/.codenook/tasks/T-012/state.json")
  echo "$log" | jq -e '.ts' >/dev/null
  echo "$log" | jq -e '.action' >/dev/null
  echo "$log" | jq -e '.result' >/dev/null
}

@test "dispatch cmd exits non-zero → state rolled back" {
  ws="$(mk_ws)"
  mk_task "$ws" "T-013" "start"
  
  # Failing stub
  stub="$ws/dispatch-fail.sh"
  cat >"$stub" <<'EOF'
#!/usr/bin/env bash
echo "dispatch failed" >&2
exit 1
EOF
  chmod +x "$stub"
  
  # Snapshot iteration before
  iter_before=$(jq -r '.iteration' "$ws/.codenook/tasks/T-013/state.json")
  
  export CODENOOK_DISPATCH_CMD="$stub"
  run_with_stderr "\"$TICK_SH\" --task T-013 --workspace \"$ws\""
  [ "$status" -ne 0 ]
  unset CODENOOK_DISPATCH_CMD
  
  # Iteration should not have incremented
  iter_after=$(jq -r '.iteration' "$ws/.codenook/tasks/T-013/state.json")
  [ "$iter_before" = "$iter_after" ]
}
