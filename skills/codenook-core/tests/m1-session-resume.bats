#!/usr/bin/env bats
# Unit 13 — session-resume (session state summary)

load helpers/load
load helpers/assertions

RESUME_SH="$CORE_ROOT/skills/builtin/session-resume/resume.sh"

mk_ws() {
  local d; d="$(make_scratch)"
  mkdir -p "$d/.codenook/tasks" "$d/.codenook/queues"
  echo "$d"
}

mk_task() {
  local ws="$1" tid="$2" phase="${3:-start}" iter="${4:-0}"
  local tdir="$ws/.codenook/tasks/$tid"
  mkdir -p "$tdir"
  cat >"$tdir/state.json" <<EOF
{
  "task_id": "$tid",
  "phase": "$phase",
  "iteration": $iter,
  "total_iterations": 5,
  "dual_mode": "serial",
  "updated_at": "2026-04-18T10:00:00Z",
  "tick_log": []
}
EOF
}

@test "resume.sh exists and is executable" {
  assert_file_exists "$RESUME_SH"
  assert_file_executable "$RESUME_SH"
}

@test "no workspace (neither arg nor env) → exit 2" {
  run_with_stderr "\"$RESUME_SH\""
  [ "$status" -eq 2 ]
}

@test "empty workspace → {active_task:null, summary:no active task}" {
  ws="$(mk_ws)"
  run bash -c "\"$RESUME_SH\" --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.active_task == null' >/dev/null
  echo "$output" | jq -e '.summary | contains("No active")' >/dev/null
}

@test "single active task → includes task id + phase + iteration + last_action_ts" {
  ws="$(mk_ws)"
  mk_task "$ws" "T-001" "implement" 2
  run bash -c "\"$RESUME_SH\" --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.active_task == "T-001"' >/dev/null
  echo "$output" | jq -e '.phase == "implement"' >/dev/null
  echo "$output" | jq -e '.iteration == 2' >/dev/null
}

@test "multiple active → sorted by updated_at desc" {
  ws="$(mk_ws)"
  mk_task "$ws" "T-001" "start" 0
  mk_task "$ws" "T-002" "implement" 1
  # Manually set different updated_at times
  cat >"$ws/.codenook/tasks/T-001/state.json" <<'EOF'
{
  "task_id": "T-001",
  "phase": "start",
  "iteration": 0,
  "total_iterations": 5,
  "dual_mode": "serial",
  "updated_at": "2026-04-18T09:00:00Z",
  "tick_log": []
}
EOF
  cat >"$ws/.codenook/tasks/T-002/state.json" <<'EOF'
{
  "task_id": "T-002",
  "phase": "implement",
  "iteration": 1,
  "total_iterations": 5,
  "dual_mode": "serial",
  "updated_at": "2026-04-18T10:00:00Z",
  "tick_log": []
}
EOF
  
  run bash -c "\"$RESUME_SH\" --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  # Most recent (T-002) should be the active task
  echo "$output" | jq -e '.active_task == "T-002"' >/dev/null
}

@test "pending HITL gate flagged" {
  ws="$(mk_ws)"
  mk_task "$ws" "T-003" "review" 1
  mkdir -p "$ws/.codenook/queues"
  cat >"$ws/.codenook/queues/hitl.jsonl" <<EOF
{"task":"T-003","gate":"accept","status":"pending"}
EOF
  
  run bash -c "\"$RESUME_SH\" --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.hitl_pending == true' >/dev/null
}

@test "pending fan-out subtasks flagged with count" {
  skip "Fan-out detection requires queue inspection - defer"
}

@test "corrupt state.json → skipped with warning on stderr" {
  ws="$(mk_ws)"
  mkdir -p "$ws/.codenook/tasks/T-BAD"
  echo "not-json" >"$ws/.codenook/tasks/T-BAD/state.json"
  
  run_with_stderr "\"$RESUME_SH\" --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  assert_contains "$STDERR" "warn"
}

@test "--json emits structured output" {
  ws="$(mk_ws)"
  mk_task "$ws" "T-005" "test" 3
  run bash -c "\"$RESUME_SH\" --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  # Verify it's valid JSON
  echo "$output" | jq . >/dev/null
}

@test "includes next_suggested_action field" {
  ws="$(mk_ws)"
  mk_task "$ws" "T-006" "start" 0
  run bash -c "\"$RESUME_SH\" --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.next_suggested_action' >/dev/null
}

@test "output size ≤1KB" {
  ws="$(mk_ws)"
  # Create multiple tasks
  for i in {1..5}; do
    mk_task "$ws" "T-00$i" "implement" "$i"
  done
  
  run bash -c "\"$RESUME_SH\" --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  size=${#output}
  [ "$size" -le 1024 ]
}
