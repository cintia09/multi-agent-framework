#!/usr/bin/env bats
# F-029 e2e — task-config-set then config-resolve sees the override (Layer 4).

load helpers/load
load helpers/assertions

SET_SH="$CORE_ROOT/skills/builtin/task-config-set/set.sh"

mk_ws() {
  local d; d="$(make_scratch)"
  mkdir -p "$d/.codenook/plugins/development" "$d/.codenook/tasks/T-029"
  cat >"$d/.codenook/tasks/T-029/state.json" <<'EOF'
{
  "task_id": "T-029",
  "phase": "start",
  "iteration": 0,
  "config_overrides": {}
}
EOF
  echo "$d"
}

@test "F-029 roundtrip: task-config-set tier_balanced flows through to resolve.models.reviewer" {
  ws="$(mk_ws)"
  # Set Layer-4 override.
  run_with_stderr "\"$SET_SH\" --task T-029 --key models.reviewer --value tier_balanced --workspace \"$ws\""
  [ "$status" -eq 0 ]
  # Sanity: it landed as a nested dict under config_overrides.
  assert_jq "$ws/.codenook/tasks/T-029/state.json" '.config_overrides.models.reviewer == "tier_balanced"'
  # Now resolve and confirm Layer-4 wins + tier_balanced expands to the catalog literal.
  run_with_stderr "\"$RESOLVE_SH\" --plugin development --task T-029 --workspace \"$ws\" --catalog \"$FIXTURES_ROOT/catalog/full.json\""
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.models.reviewer == "sonnet-4.6"' >/dev/null
  echo "$output" | jq -e '._provenance["models.reviewer"].from_layer == 4' >/dev/null
  echo "$output" | jq -e '._provenance["models.reviewer"].symbol == "tier_balanced"' >/dev/null
}
