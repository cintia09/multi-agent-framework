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

# ── Fix #9: HITL approve / reject / needs_changes round-trip (DoD G1) ───
HITL_SH_E2E="$CORE_ROOT/skills/builtin/hitl-adapter/terminal.sh"

init_ws_gated() {
  local ws; ws="$(init_ws_with_core_and_generic)"
  # Patch generic plugin so clarify has a HITL gate.
  python3 -c "
import yaml
p='$ws/.codenook/plugins/generic/phases.yaml'
d=yaml.safe_load(open(p))
d['phases'][0]['gate']='design_signoff'
open(p,'w').write(yaml.safe_dump(d, sort_keys=False))
"
  echo "$ws"
}

@test "M4 HITL DoD: approve → tick advances phase + status=in_progress" {
  ws="$(init_ws_gated)"
  create_task "$ws" "T-800" "generic" "hitl approve"

  # First tick: dispatch clarifier
  run bash -c "\"$TICK_SH\" --task T-800 --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]

  # Write clarifier output verdict:ok
  write_clarifier_output "$ws" "T-800"

  # Second tick: hits HITL gate → status=waiting + entry written (E2E-P-009: exit 3)
  run bash -c "\"$TICK_SH\" --task T-800 --workspace \"$ws\" --json"
  [ "$status" -eq 3 ]
  jq -e '.status=="waiting"' "$ws/.codenook/tasks/T-800/state.json" >/dev/null
  [ -f "$ws/.codenook/hitl-queue/T-800-design_signoff.json" ]
  jq -e '.verdict_at_gate=="ok"' \
     "$ws/.codenook/hitl-queue/T-800-design_signoff.json" >/dev/null

  # Approve via hitl-adapter
  run bash -c "\"$HITL_SH_E2E\" decide --id T-800-design_signoff --decision approve --reviewer alice --workspace \"$ws\""
  [ "$status" -eq 0 ]

  # Third tick: phase advances to analyze + status=in_progress
  run bash -c "\"$TICK_SH\" --task T-800 --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  jq -e '.phase=="analyze"' "$ws/.codenook/tasks/T-800/state.json" >/dev/null
  jq -e '.status=="in_progress"' "$ws/.codenook/tasks/T-800/state.json" >/dev/null
  # Entry consumed → moved to _consumed/
  [ ! -f "$ws/.codenook/hitl-queue/T-800-design_signoff.json" ]
  [ -f "$ws/.codenook/hitl-queue/_consumed/T-800-design_signoff.json" ]
}

@test "M4 HITL DoD: reject → status=blocked" {
  ws="$(init_ws_gated)"
  create_task "$ws" "T-801" "generic" "hitl reject"
  run bash -c "\"$TICK_SH\" --task T-801 --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  write_clarifier_output "$ws" "T-801"
  run bash -c "\"$TICK_SH\" --task T-801 --workspace \"$ws\" --json"
  [ "$status" -eq 3 ]

  run bash -c "\"$HITL_SH_E2E\" decide --id T-801-design_signoff --decision reject --reviewer bob --workspace \"$ws\""
  [ "$status" -eq 0 ]

  run bash -c "\"$TICK_SH\" --task T-801 --workspace \"$ws\" --json"
  [ "$status" -eq 1 ]
  jq -e '.status=="blocked"' "$ws/.codenook/tasks/T-801/state.json" >/dev/null
  jq -e '[.history[]._warning] | map(select(. != null)) | any(test("hitl_rejected"))' \
     "$ws/.codenook/tasks/T-801/state.json" >/dev/null
}

@test "M4 HITL DoD: needs_changes → iteration incremented, same phase" {
  ws="$(init_ws_gated)"
  create_task "$ws" "T-802" "generic" "hitl needs_changes"
  run bash -c "\"$TICK_SH\" --task T-802 --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  write_clarifier_output "$ws" "T-802"
  run bash -c "\"$TICK_SH\" --task T-802 --workspace \"$ws\" --json"
  [ "$status" -eq 3 ]
  iter_before=$(jq -r '.iteration' "$ws/.codenook/tasks/T-802/state.json")

  run bash -c "\"$HITL_SH_E2E\" decide --id T-802-design_signoff --decision needs_changes --reviewer carol --workspace \"$ws\""
  [ "$status" -eq 0 ]

  run bash -c "\"$TICK_SH\" --task T-802 --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  jq -e '.phase=="clarify"' "$ws/.codenook/tasks/T-802/state.json" >/dev/null
  iter_after=$(jq -r '.iteration' "$ws/.codenook/tasks/T-802/state.json")
  [ "$iter_after" -gt "$iter_before" ]
  [ ! -f "$ws/.codenook/hitl-queue/T-802-design_signoff.json" ]
}
