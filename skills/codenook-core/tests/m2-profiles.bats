#!/usr/bin/env bats
# m2-profiles.bats — v0.2.0 development plugin: end-to-end smoke for
# every profile other than `feature` (the default `feature` profile is
# covered by m6-development-e2e.bats).
#
# For each non-feature profile we:
#   1. Install the plugin, seed a task with `task_type` matching the
#      profile (via the clarifier output frontmatter on the very first
#      tick).
#   2. Drive ticks, mock every role output as `verdict: ok`, and
#      auto-approve every HITL gate.
#   3. Assert the task ends in `status=done`, `state.profile==<name>`,
#      and that every phase from the profile's chain appears in
#      `history` with `verdict=ok`.

load helpers/load
load helpers/assertions

PLUGIN_SRC="$CORE_ROOT/../../plugins/development"
INSTALL_SH="$CORE_ROOT/skills/builtin/install-orchestrator/orchestrator.sh"
TICK_SH="$CORE_ROOT/skills/builtin/orchestrator-tick/tick.sh"
HITL_SH="$CORE_ROOT/skills/builtin/hitl-adapter/terminal.sh"

setup_ws_with_plugin() {
  local ws; ws="$(make_scratch)"
  mkdir -p "$ws/.codenook"
  local dist; dist="$(make_scratch)/dist"
  mkdir -p "$dist"
  ( cd "$PLUGIN_SRC/.." && tar -czf "$dist/dev.tar.gz" development )
  "$INSTALL_SH" --src "$dist/dev.tar.gz" --workspace "$ws" --json >/dev/null
  echo "$ws"
}

create_task_for_profile() {
  local ws="$1" tid="$2" profile="$3"
  local d="$ws/.codenook/tasks/$tid"
  mkdir -p "$d/outputs" "$d/prompts"
  mkdir -p "$ws/work"
  python3 -c "
import json
state = {
  'schema_version': 1,
  'task_id': '$tid',
  'title': 'profile-test $profile',
  'plugin': 'development',
  'phase': None,
  'iteration': 0,
  'max_iterations': 3,
  'dual_mode': 'serial',
  'target_dir': '$ws/work',
  'status': 'in_progress',
  'config_overrides': {},
  'history': [],
  'task_type': '$profile',
}
open('$d/state.json', 'w').write(json.dumps(state, indent=2))
"
}

# Mock role output. Clarifier always declares its profile via task_type
# in the frontmatter — that's what the orchestrator's profile resolver
# reads (with state.task_type as a fallback).
write_role_output() {
  local ws="$1" tid="$2" expected="$3" profile="$4"
  local out="$ws/.codenook/tasks/$tid/$expected"
  mkdir -p "$(dirname "$out")"
  if [[ "$expected" == *clarifier* ]]; then
    cat >"$out" <<EOF
---
verdict: ok
task_type: $profile
summary: mock clarifier ($profile)
---
mocked clarifier body
EOF
  else
    cat >"$out" <<'EOF'
---
verdict: ok
summary: mock verdict
---
mocked role body
EOF
  fi
}

drive_to_done() {
  local ws="$1" tid="$2" profile="$3" max="$4"
  local i status_code out tick_status expected out_file
  for i in $(seq 1 "$max"); do
    out=""
    status_code=0
    if ! out=$("$TICK_SH" --task "$tid" --workspace "$ws" --json 2>/dev/null); then
      status_code=$?
    fi
    [ -n "$out" ] || { echo "no JSON (i=$i rc=$status_code)" >&2; return 1; }

    tick_status=$(echo "$out" | python3 -c 'import sys,json;print(json.load(sys.stdin)["status"])')
    if [ "$tick_status" = "done" ]; then return 0; fi
    if [ "$tick_status" = "blocked" ] || [ "$tick_status" = "error" ]; then
      echo "tick $tick_status at i=$i: $out" >&2
      cat "$ws/.codenook/tasks/$tid/state.json" >&2
      return 1
    fi

    expected=$(jq -r '.in_flight_agent.expected_output // empty' \
               "$ws/.codenook/tasks/$tid/state.json")
    if [ -n "$expected" ]; then
      out_file="$ws/.codenook/tasks/$tid/$expected"
      if [ ! -f "$out_file" ]; then
        write_role_output "$ws" "$tid" "$expected" "$profile"
        continue
      fi
    fi

    if [ "$tick_status" = "waiting" ]; then
      cur_phase=$(jq -r '.phase' "$ws/.codenook/tasks/$tid/state.json")
      gate=$(python3 - "$ws" "$cur_phase" <<'PY'
import sys, yaml
ws, phase = sys.argv[1], sys.argv[2]
phases = yaml.safe_load(open(f"{ws}/.codenook/plugins/development/phases.yaml"))["phases"]
ph = phases.get(phase) if isinstance(phases, dict) else next((p for p in phases if p["id"] == phase), None)
print((ph or {}).get("gate", ""))
PY
)
      if [ -n "$gate" ]; then
        eid="$tid-$gate"
        if [ -f "$ws/.codenook/hitl-queue/$eid.json" ]; then
          "$HITL_SH" decide --workspace "$ws" --id "$eid" \
            --decision approve --reviewer human \
            --comment "m2-profiles auto-approve" >/dev/null
        fi
      fi
    fi
  done
  echo "did not finish in $max ticks (profile=$profile)" >&2
  cat "$ws/.codenook/tasks/$tid/state.json" >&2
  return 1
}

assert_done_with_chain() {
  local ws="$1" tid="$2" profile="$3"
  python3 - "$ws/.codenook/tasks/$tid/state.json" \
           "$ws/.codenook/plugins/development/phases.yaml" \
           "$profile" <<'PY'
import json, sys, yaml
state = json.load(open(sys.argv[1]))
profs = yaml.safe_load(open(sys.argv[2]))["profiles"]
profile = sys.argv[3]
assert state["status"] == "done", state["status"]
assert state.get("profile") == profile, (state.get("profile"), profile)
chain_spec = profs[profile]
chain = chain_spec["phases"] if isinstance(chain_spec, dict) else chain_spec
seen = {h["phase"] for h in state["history"] if h.get("verdict") == "ok"}
missing = set(chain) - seen
assert not missing, f"profile={profile} missing verdict=ok phases: {missing}"
print("ok")
PY
}

@test "profile=hotfix drives to done with the hotfix chain" {
  ws="$(setup_ws_with_plugin)"
  create_task_for_profile "$ws" "T-HOT" "hotfix"
  drive_to_done "$ws" "T-HOT" "hotfix" 60
  assert_done_with_chain "$ws" "T-HOT" "hotfix"
}

@test "profile=refactor drives to done with the refactor chain" {
  ws="$(setup_ws_with_plugin)"
  create_task_for_profile "$ws" "T-REF" "refactor"
  drive_to_done "$ws" "T-REF" "refactor" 80
  assert_done_with_chain "$ws" "T-REF" "refactor"
}

@test "profile=test-only drives to done with the test-only chain" {
  ws="$(setup_ws_with_plugin)"
  create_task_for_profile "$ws" "T-TST" "test-only"
  drive_to_done "$ws" "T-TST" "test-only" 60
  assert_done_with_chain "$ws" "T-TST" "test-only"
}

@test "profile=docs drives to done with the docs chain" {
  ws="$(setup_ws_with_plugin)"
  create_task_for_profile "$ws" "T-DOC" "docs"
  drive_to_done "$ws" "T-DOC" "docs" 50
  assert_done_with_chain "$ws" "T-DOC" "docs"
}

@test "profile=review drives to done with the review chain" {
  ws="$(setup_ws_with_plugin)"
  create_task_for_profile "$ws" "T-REV" "review"
  drive_to_done "$ws" "T-REV" "review" 40
  assert_done_with_chain "$ws" "T-REV" "review"
}

@test "profile=design drives to done with the design chain" {
  ws="$(setup_ws_with_plugin)"
  create_task_for_profile "$ws" "T-DSG" "design"
  drive_to_done "$ws" "T-DSG" "design" 40
  assert_done_with_chain "$ws" "T-DSG" "design"
}

@test "clarifier task_type frontmatter overrides state.task_type" {
  # Even when state.task_type is unset, the clarifier's frontmatter
  # `task_type` is what the orchestrator must use to resolve the profile.
  ws="$(setup_ws_with_plugin)"
  local tid=T-OVR
  local d="$ws/.codenook/tasks/$tid"
  mkdir -p "$d/outputs" "$ws/work"
  python3 -c "
import json
state = {
  'schema_version': 1, 'task_id': '$tid',
  'title': 'profile-from-clarifier',
  'plugin': 'development', 'phase': None, 'iteration': 0,
  'max_iterations': 3, 'dual_mode': 'serial',
  'target_dir': '$ws/work', 'status': 'in_progress',
  'config_overrides': {}, 'history': [],
}
open('$d/state.json','w').write(json.dumps(state, indent=2))
"
  drive_to_done "$ws" "$tid" "docs" 40
  jq -e '.profile == "docs"' "$d/state.json" >/dev/null
}
