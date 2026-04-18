#!/usr/bin/env bats
# Unit 10 — task-config-set (writes Layer-4 override into tasks/T-NNN/state.json)

load helpers/load
load helpers/assertions

SET_SH="$CORE_ROOT/skills/builtin/task-config-set/set.sh"

mk_ws() {
  local d; d="$(make_scratch)"
  mkdir -p "$d/.codenook/tasks" "$d/.codenook/history"
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
  "config_overrides": {}
}
EOF
}

@test "set.sh exists and is executable" {
  assert_file_exists "$SET_SH"
  assert_file_executable "$SET_SH"
}

@test "missing args → exit 2" {
  ws="$(mk_ws)"
  run_with_stderr "\"$SET_SH\" --workspace \"$ws\""
  [ "$status" -eq 2 ]
}

@test "key models.default accepted" {
  ws="$(mk_ws)"
  mk_task "$ws" "T-001"
  run_with_stderr "\"$SET_SH\" --task T-001 --key models.default --value tier_strong --workspace \"$ws\""
  [ "$status" -eq 0 ]
  # Verify written to state.json
  assert_jq "$ws/.codenook/tasks/T-001/state.json" '.config_overrides.models.default == "tier_strong"'
}

@test "key models.reviewer accepted (role variants)" {
  ws="$(mk_ws)"
  mk_task "$ws" "T-002"
  run_with_stderr "\"$SET_SH\" --task T-002 --key models.reviewer --value tier_cheap --workspace \"$ws\""
  [ "$status" -eq 0 ]
  assert_jq "$ws/.codenook/tasks/T-002/state.json" '.config_overrides.models.reviewer == "tier_cheap"'
}

@test "key outside allow-list → exit 1" {
  ws="$(mk_ws)"
  mk_task "$ws" "T-003"
  run_with_stderr "\"$SET_SH\" --task T-003 --key bad.key --value foo --workspace \"$ws\""
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" "allow"
}

@test "value with tier symbol accepted" {
  ws="$(mk_ws)"
  mk_task "$ws" "T-004"
  for tier in tier_strong tier_balanced tier_cheap; do
    run_with_stderr "\"$SET_SH\" --task T-004 --key models.default --value $tier --workspace \"$ws\""
    [ "$status" -eq 0 ]
  done
}

@test "value literal model id accepted (warn on unknown)" {
  ws="$(mk_ws)"
  mk_task "$ws" "T-005"
  run_with_stderr "\"$SET_SH\" --task T-005 --key models.executor --value unknown-model-xyz --workspace \"$ws\""
  [ "$status" -eq 0 ]
  # Should warn on stderr but still exit 0
  assert_contains "$STDERR" "warn"
  assert_jq "$ws/.codenook/tasks/T-005/state.json" '.config_overrides.models.executor == "unknown-model-xyz"'
}

@test "writes under state.json .config_overrides.models.<role>" {
  ws="$(mk_ws)"
  mk_task "$ws" "T-006"
  run_with_stderr "\"$SET_SH\" --task T-006 --key models.planner --value tier_balanced --workspace \"$ws\""
  [ "$status" -eq 0 ]
  # Verify exact path in JSON
  val=$(jq -r '.config_overrides.models.planner' "$ws/.codenook/tasks/T-006/state.json")
  [ "$val" = "tier_balanced" ]
}

@test "idempotent re-set" {
  ws="$(mk_ws)"
  mk_task "$ws" "T-007"
  run_with_stderr "\"$SET_SH\" --task T-007 --key models.default --value tier_strong --workspace \"$ws\""
  [ "$status" -eq 0 ]
  run_with_stderr "\"$SET_SH\" --task T-007 --key models.default --value tier_strong --workspace \"$ws\""
  [ "$status" -eq 0 ]
  # Should still have the same value
  assert_jq "$ws/.codenook/tasks/T-007/state.json" '.config_overrides.models.default == "tier_strong"'
}

@test "--unset flag removes the key" {
  ws="$(mk_ws)"
  mk_task "$ws" "T-008"
  # Set then unset
  run_with_stderr "\"$SET_SH\" --task T-008 --key models.reviewer --value tier_cheap --workspace \"$ws\""
  [ "$status" -eq 0 ]
  run_with_stderr "\"$SET_SH\" --task T-008 --key models.reviewer --unset --workspace \"$ws\""
  [ "$status" -eq 0 ]
  # Should be gone
  val=$(jq -r '.config_overrides.models.reviewer' "$ws/.codenook/tasks/T-008/state.json")
  [ "$val" = "null" ]
}

@test "writes nested dict under config_overrides (not dotted key)" {
  ws="$(mk_ws)"
  mk_task "$ws" "T-100"
  run_with_stderr "\"$SET_SH\" --task T-100 --key models.reviewer --value tier_balanced --workspace \"$ws\""
  [ "$status" -eq 0 ]
  # The dotted-key form must NOT exist; nested form must.
  has_dotted=$(jq '.config_overrides | has("models.reviewer")' "$ws/.codenook/tasks/T-100/state.json")
  [ "$has_dotted" = "false" ]
  assert_jq "$ws/.codenook/tasks/T-100/state.json" '.config_overrides.models.reviewer == "tier_balanced"'
}
