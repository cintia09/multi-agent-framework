#!/usr/bin/env bats
# M5 — task-config-set: clear mode + audit log to history/config-changes.jsonl

load helpers/load
load helpers/assertions

SET_SH="$CORE_ROOT/skills/builtin/task-config-set/set.sh"

mk_ws_with_task() {
  local d; d="$(make_scratch)"
  mkdir -p "$d/.codenook/tasks/T-001" "$d/.codenook/history"
  cat >"$d/.codenook/tasks/T-001/state.json" <<'EOF'
{"task_id":"T-001","phase":"start","iteration":0,"config_overrides":{"models":{"reviewer":"tier_balanced"}}}
EOF
  echo "$d"
}

@test "m5-task-config-set: set mode (existing CLI) appends audit log" {
  ws="$(mk_ws_with_task)"
  run_with_stderr "\"$SET_SH\" --task T-001 --key models.default --value tier_strong --workspace \"$ws\""
  [ "$status" -eq 0 ]
  [ -f "$ws/.codenook/history/config-changes.jsonl" ]
  last=$(tail -1 "$ws/.codenook/history/config-changes.jsonl")
  echo "$last" | jq -e '.actor == "user"' >/dev/null
  echo "$last" | jq -e '.scope == "task"' >/dev/null
  echo "$last" | jq -e '.task  == "T-001"' >/dev/null
  echo "$last" | jq -e '.path  == "models.default"' >/dev/null
  echo "$last" | jq -e '.new   == "tier_strong"' >/dev/null
}

@test "m5-task-config-set: --mode clear --role reviewer removes single key" {
  ws="$(mk_ws_with_task)"
  run_with_stderr "\"$SET_SH\" --mode clear --task T-001 --plugin development --role reviewer --workspace \"$ws\""
  [ "$status" -eq 0 ]
  # The reviewer key was removed; models obj may or may not be empty/dropped.
  assert_jq "$ws/.codenook/tasks/T-001/state.json" '.config_overrides.models.reviewer == null'
  last=$(tail -1 "$ws/.codenook/history/config-changes.jsonl")
  echo "$last" | jq -e '.actor == "user"' >/dev/null
  echo "$last" | jq -e '.path  == "models.reviewer"' >/dev/null
}

@test "m5-task-config-set: clear of non-existent key is no-op (exit 0, no audit)" {
  ws="$(mk_ws_with_task)"
  before=0
  [ -f "$ws/.codenook/history/config-changes.jsonl" ] && before=$(wc -l <"$ws/.codenook/history/config-changes.jsonl" | tr -d ' ')
  run_with_stderr "\"$SET_SH\" --mode clear --task T-001 --plugin development --role distiller --workspace \"$ws\""
  [ "$status" -eq 0 ]
  after=0
  [ -f "$ws/.codenook/history/config-changes.jsonl" ] && after=$(wc -l <"$ws/.codenook/history/config-changes.jsonl" | tr -d ' ')
  [ "$before" = "$after" ]
}

@test "m5-task-config-set: --role still routed through models.* whitelist" {
  ws="$(mk_ws_with_task)"
  run_with_stderr "\"$SET_SH\" --mode set --task T-001 --plugin development --role reviewer --value tier_cheap --workspace \"$ws\""
  [ "$status" -eq 0 ]
  assert_jq "$ws/.codenook/tasks/T-001/state.json" '.config_overrides.models.reviewer == "tier_cheap"'
}
