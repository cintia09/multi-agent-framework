#!/usr/bin/env bats
# M8.10 — orchestrator-tick honours state.role_constraints (skip excluded roles).

load helpers/load
load helpers/assertions

TICK_SH="$CORE_ROOT/skills/builtin/orchestrator-tick/tick.sh"

mk_ws_with_plugin() {
  local ws; ws="$(make_scratch)"
  mkdir -p "$ws/.codenook/tasks" "$ws/.codenook/queue" \
           "$ws/.codenook/hitl-queue" "$ws/.codenook/history" \
           "$ws/.codenook/memory/_pending" "$ws/.codenook/plugins"
  cp -R "$FIXTURES_ROOT/m4/plugins/generic" "$ws/.codenook/plugins/generic"
  echo "$ws"
}

mk_state() {
  local ws="$1" tid="$2" extra="${3:-}"
  local tdir="$ws/.codenook/tasks/$tid"
  mkdir -p "$tdir/outputs"
  python3 - "$tdir/state.json" "$tid" "$extra" <<'PY'
import json, sys
out, tid, extra = sys.argv[1], sys.argv[2], sys.argv[3]
state = {
  "schema_version": 1,
  "task_id": tid,
  "plugin": "generic",
  "phase": None,
  "iteration": 0,
  "max_iterations": 3,
  "dual_mode": "serial",
  "status": "in_progress",
  "config_overrides": {},
  "history": [],
}
if extra:
    state.update(json.loads(extra))
with open(out, "w") as f: json.dump(state, f, indent=2)
PY
}

@test "M8.10 missing role_constraints -> existing dispatch behaviour (no skip)" {
  ws="$(mk_ws_with_plugin)"
  mk_state "$ws" "T-810a"
  run bash -c "\"$TICK_SH\" --task T-810a --workspace \"$ws\""
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  # No skip events in history
  jq -e '[.history[] | select(.verdict=="skipped")] | length == 0' \
        "$ws/.codenook/tasks/T-810a/state.json" >/dev/null
  jq -e '.phase == "clarify"' "$ws/.codenook/tasks/T-810a/state.json" >/dev/null
  jq -e '.in_flight_agent.role == "clarifier"' \
        "$ws/.codenook/tasks/T-810a/state.json" >/dev/null
}

@test "M8.10 first-dispatch skips excluded role and advances to next allowed phase" {
  ws="$(mk_ws_with_plugin)"
  mk_state "$ws" "T-810b" \
    '{"role_constraints":{"excluded":[{"plugin":"generic","role":"clarifier"}]}}'
  run bash -c "\"$TICK_SH\" --task T-810b --workspace \"$ws\""
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  # clarify was skipped
  jq -e '[.history[] | select(.phase=="clarify" and .verdict=="skipped")] | length == 1' \
        "$ws/.codenook/tasks/T-810b/state.json" >/dev/null
  # analyzer (next phase) was dispatched
  jq -e '.phase == "analyze"' "$ws/.codenook/tasks/T-810b/state.json" >/dev/null
  jq -e '.in_flight_agent.role == "analyzer"' \
        "$ws/.codenook/tasks/T-810b/state.json" >/dev/null
  # warning text mentions role-skip
  jq -e '[.history[] | select(.phase=="clarify")][0]._warning | contains("role-skip")' \
        "$ws/.codenook/tasks/T-810b/state.json" >/dev/null
}

@test "M8.10 transition target excluded -> chained skip, downstream phase dispatched" {
  ws="$(mk_ws_with_plugin)"
  # We start at phase=clarify (already in flight); when its output arrives with
  # verdict=ok, transition would go to "analyze" — but analyzer is excluded.
  # Since "analyze -> complete" on ok, the only allowed downstream is complete.
  mk_state "$ws" "T-810c" \
    '{"phase":"clarify","status":"in_progress","role_constraints":{"excluded":[{"plugin":"generic","role":"analyzer"}]},"in_flight_agent":{"agent_id":"ag_x","role":"clarifier","dispatched_at":"2026-01-01T00:00:00Z","expected_output":"outputs/phase-1-clarifier.md"}}'
  # Drop clarifier output with verdict=ok so the tick moves the state forward.
  out="$ws/.codenook/tasks/T-810c/outputs/phase-1-clarifier.md"
  cat >"$out" <<EOF
---
verdict: ok
---
done
EOF
  run bash -c "\"$TICK_SH\" --task T-810c --workspace \"$ws\""
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  # analyze should be skipped, status=done (analyze->complete on ok)
  jq -e '[.history[] | select(.phase=="analyze" and .verdict=="skipped")] | length == 1' \
        "$ws/.codenook/tasks/T-810c/state.json" >/dev/null
  jq -e '.status == "done"' "$ws/.codenook/tasks/T-810c/state.json" >/dev/null
  jq -e '.phase == "complete"' "$ws/.codenook/tasks/T-810c/state.json" >/dev/null
}

@test "M8.10 included whitelist permits only listed role; others skipped" {
  ws="$(mk_ws_with_plugin)"
  mk_state "$ws" "T-810d" \
    '{"role_constraints":{"included":[{"plugin":"generic","role":"analyzer"}]}}'
  run bash -c "\"$TICK_SH\" --task T-810d --workspace \"$ws\""
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  jq -e '[.history[] | select(.phase=="clarify" and .verdict=="skipped")] | length == 1' \
        "$ws/.codenook/tasks/T-810d/state.json" >/dev/null
  jq -e '.in_flight_agent.role == "analyzer"' \
        "$ws/.codenook/tasks/T-810d/state.json" >/dev/null
}

@test "M8.10 schema accepts role_constraints in state.json" {
  ws="$(mk_ws_with_plugin)"
  mk_state "$ws" "T-810e" \
    '{"role_constraints":{"excluded":[{"plugin":"generic","role":"clarifier"}],"included":[{"plugin":"generic","role":"analyzer"}]}}'
  # tick runs the schema validator on every persist; if the schema rejected
  # role_constraints we would fail here.
  run bash -c "\"$TICK_SH\" --task T-810e --workspace \"$ws\""
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  jq -e '.role_constraints.excluded[0].role == "clarifier"' \
        "$ws/.codenook/tasks/T-810e/state.json" >/dev/null
}
