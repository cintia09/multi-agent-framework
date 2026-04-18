#!/usr/bin/env bats
# M4.U3 — session-resume FULL algorithm (impl-v6.md §3.4).
#
# The MVP output schema (M4) is what main session consumes:
#   {active_tasks: [...], current_focus, last_session_summary, suggested_next}
# The legacy M1 fields (active_task, summary, etc.) remain to keep
# the m1-session-resume bats suite green.

load helpers/load
load helpers/assertions

RESUME_SH="$CORE_ROOT/skills/builtin/session-resume/resume.sh"

mk_ws_m4() {
  local d; d="$(make_scratch)"
  mkdir -p "$d/.codenook/tasks" "$d/.codenook/history/sessions"
  echo "$d"
}

mk_ws_state() {
  local ws="$1"; shift
  python3 - "$ws/.codenook/state.json" "$@" <<'PY'
import json, sys
out, *args = sys.argv[1:]
state = {"active_tasks": [], "current_focus": None}
i = 0
while i < len(args):
    k, v = args[i].split("=", 1)
    if k == "active_tasks":
        state[k] = v.split(",") if v else []
    elif v == "null":
        state[k] = None
    else:
        state[k] = v
    i += 1
with open(out, "w") as f: json.dump(state, f)
PY
}

mk_task_m4() {
  local ws="$1" tid="$2" plugin="${3:-generic}" phase="${4:-clarify}" \
        status="${5:-in_progress}" title="${6:-task $tid}"
  local tdir="$ws/.codenook/tasks/$tid"
  mkdir -p "$tdir"
  python3 - "$tdir/state.json" "$tid" "$plugin" "$phase" "$status" "$title" <<'PY'
import json, sys
out, tid, plugin, phase, status, title = sys.argv[1:]
state = {
  "schema_version": 1, "task_id": tid, "title": title,
  "plugin": plugin, "phase": phase, "iteration": 0, "max_iterations": 3,
  "dual_mode": "serial", "status": status,
  "config_overrides": {}, "history": [],
  "created_at": "2026-04-18T09:00:00Z",
}
with open(out, "w") as f: json.dump(state, f)
PY
}

@test "0 active tasks → suggested_next == 'No active task, awaiting user input'" {
  ws="$(mk_ws_m4)"; mk_ws_state "$ws"
  run bash -c "\"$RESUME_SH\" --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.suggested_next | test("[Nn]o active|awaiting user input")' >/dev/null
  echo "$output" | jq -e '.active_tasks | length == 0' >/dev/null
}

@test "1 active in_progress + current_focus matches → 'Continue T-XXX (<phase>)?'" {
  ws="$(mk_ws_m4)"
  mk_task_m4 "$ws" "T-201" generic implement in_progress
  mk_ws_state "$ws" "active_tasks=T-201" "current_focus=T-201"
  run bash -c "\"$RESUME_SH\" --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.current_focus == "T-201"' >/dev/null
  echo "$output" | jq -e '.suggested_next | test("T-201") and test("implement")' >/dev/null
  echo "$output" | jq -e '.active_tasks[0].plugin == "generic"' >/dev/null
}

@test "Multiple active → 'N active tasks...'" {
  ws="$(mk_ws_m4)"
  mk_task_m4 "$ws" "T-202" generic clarify in_progress
  mk_task_m4 "$ws" "T-203" generic analyze in_progress
  mk_ws_state "$ws" "active_tasks=T-202,T-203"
  run bash -c "\"$RESUME_SH\" --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.active_tasks | length == 2' >/dev/null
  echo "$output" | jq -e '.suggested_next | test("2 active|2 个 active")' >/dev/null
}

@test "last_session_summary is tail of history/sessions/latest.md, ≤300 chars" {
  ws="$(mk_ws_m4)"
  python3 -c "open('$ws/.codenook/history/sessions/latest.md','w').write('A'*100 + 'TAIL_MARKER_' + 'B'*250)"
  mk_ws_state "$ws"
  run bash -c "\"$RESUME_SH\" --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  len=$(echo "$output" | jq -r '.last_session_summary | length')
  [ "$len" -le 300 ]
  echo "$output" | jq -e '.last_session_summary | test("TAIL_MARKER")' >/dev/null
}

@test "no latest.md → last_session_summary is empty string" {
  ws="$(mk_ws_m4)"; mk_ws_state "$ws"
  run bash -c "\"$RESUME_SH\" --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.last_session_summary == ""' >/dev/null
}

@test "total summary ≤500 bytes UTF-8 even with CJK active tasks" {
  ws="$(mk_ws_m4)"
  for i in 1 2 3; do
    mk_task_m4 "$ws" "T-30$i" generic clarify in_progress "中文标题包含一些较长的描述用于测试"
  done
  mk_ws_state "$ws" "active_tasks=T-301,T-302,T-303" "current_focus=T-301"
  run bash -c "\"$RESUME_SH\" --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  bytes=$(echo -n "$output" | wc -c | tr -d ' ')
  [ "$bytes" -le 500 ]
  echo "$output" | jq . >/dev/null
}

@test "active_tasks entries carry task_id, plugin, phase, status, last_event_ts, one_liner" {
  ws="$(mk_ws_m4)"
  mk_task_m4 "$ws" "T-401" mydomain implement in_progress "fix the bug"
  mk_ws_state "$ws" "active_tasks=T-401" "current_focus=T-401"
  run bash -c "\"$RESUME_SH\" --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.active_tasks[0] | .task_id and .plugin and .phase and .status and .last_event_ts' >/dev/null
}
