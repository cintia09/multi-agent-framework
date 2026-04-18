#!/usr/bin/env bats
# M4.U5 — End-to-end DoD test mirroring impl-v6.md L1947-1970.
#
# Init workspace with the generic 2-phase plugin, create a task,
# run two ticks (the second after writing a verdict:ok output for
# clarify), then call session-resume and assert ≤500-byte summary
# containing the task id.

load helpers/load
load helpers/assertions

TICK_SH="$CORE_ROOT/skills/builtin/orchestrator-tick/tick.sh"
RESUME_SH="$CORE_ROOT/skills/builtin/session-resume/resume.sh"

init_ws_with_core_and_generic() {
  local ws; ws="$(make_scratch)"
  mkdir -p "$ws/.codenook/tasks" "$ws/.codenook/queue" \
           "$ws/.codenook/hitl-queue" "$ws/.codenook/history" \
           "$ws/.codenook/memory/_pending" "$ws/.codenook/plugins"
  cp -R "$FIXTURES_ROOT/m4/plugins/generic" "$ws/.codenook/plugins/generic"
  echo "$ws"
}

create_task() {
  local ws="$1" tid="$2" plugin="$3" title="$4"
  local tdir="$ws/.codenook/tasks/$tid"
  mkdir -p "$tdir/outputs"
  cat >"$tdir/state.json" <<EOF
{"schema_version":1,"task_id":"$tid","title":"$title","plugin":"$plugin",
 "phase":null,"iteration":0,"max_iterations":3,"dual_mode":"serial",
 "status":"in_progress","config_overrides":{},"history":[],
 "created_at":"2026-04-18T09:00:00Z"}
EOF
  cat >"$ws/.codenook/state.json" <<EOF
{"active_tasks":["$tid"],"current_focus":"$tid"}
EOF
}

write_clarifier_output() {
  local ws="$1" tid="$2"
  cat >"$ws/.codenook/tasks/$tid/outputs/phase-1-clarifier.md" <<'EOF'
---
verdict: ok
---
clarifier confirmed scope
EOF
}

@test "M4 DoD: tick boots from phase=null to clarify; ready output → analyze; resume ≤500 bytes" {
  ws="$(init_ws_with_core_and_generic)"
  create_task "$ws" "T-700" "generic" "test task"

  # Initial state: phase is null
  jq -e '.phase == null' "$ws/.codenook/tasks/T-700/state.json" >/dev/null

  # First tick → phase becomes "clarify"
  run bash -c "\"$TICK_SH\" --task T-700 --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  jq -e '.phase == "clarify"' "$ws/.codenook/tasks/T-700/state.json" >/dev/null
  jq -e '.in_flight_agent.role == "clarifier"' \
     "$ws/.codenook/tasks/T-700/state.json" >/dev/null

  # Simulate clarifier writing the expected output with verdict:ok
  write_clarifier_output "$ws" "T-700"

  # Second tick → phase becomes "analyze"
  run bash -c "\"$TICK_SH\" --task T-700 --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  jq -e '.phase == "analyze"' "$ws/.codenook/tasks/T-700/state.json" >/dev/null
  jq -e '.history | length == 1 and .[0].verdict == "ok"' \
     "$ws/.codenook/tasks/T-700/state.json" >/dev/null

  # session-resume: summary ≤500 bytes and contains the task id
  run bash -c "\"$RESUME_SH\" --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  bytes=$(echo -n "$output" | wc -c | tr -d ' ')
  [ "$bytes" -le 500 ]
  echo "$output" | jq -e '.active_tasks | map(.task_id) | index("T-700") != null' >/dev/null
  echo "$output" | jq -e '.suggested_next | test("T-700") and test("analyze")' >/dev/null
}

@test "M4 DoD bonus: dispatch.jsonl records every dispatched role" {
  ws="$(init_ws_with_core_and_generic)"
  create_task "$ws" "T-701" "generic" "audit log task"

  run bash -c "\"$TICK_SH\" --task T-701 --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  write_clarifier_output "$ws" "T-701"
  run bash -c "\"$TICK_SH\" --task T-701 --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]

  [ -f "$ws/.codenook/history/dispatch.jsonl" ]
  lines=$(wc -l <"$ws/.codenook/history/dispatch.jsonl" | tr -d ' ')
  [ "$lines" -ge 2 ]
  grep -q '"role"[[:space:]]*:[[:space:]]*"clarifier"' \
       "$ws/.codenook/history/dispatch.jsonl"
  grep -q '"role"[[:space:]]*:[[:space:]]*"analyzer"' \
       "$ws/.codenook/history/dispatch.jsonl"
}

@test "M4 DoD bonus: full pipeline → done + distiller pending marker" {
  ws="$(init_ws_with_core_and_generic)"
  create_task "$ws" "T-702" "generic" "full pipeline"

  run bash -c "\"$TICK_SH\" --task T-702 --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  write_clarifier_output "$ws" "T-702"

  run bash -c "\"$TICK_SH\" --task T-702 --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]

  # analyzer output → should advance to complete
  cat >"$ws/.codenook/tasks/T-702/outputs/phase-2-analyzer.md" <<'EOF'
---
verdict: ok
---
analyzed
EOF

  run bash -c "\"$TICK_SH\" --task T-702 --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  jq -e '.status == "done"' "$ws/.codenook/tasks/T-702/state.json" >/dev/null
  [ -f "$ws/.codenook/memory/_pending/T-702.json" ]
}
