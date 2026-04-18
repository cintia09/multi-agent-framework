#!/usr/bin/env bats
# M5.6 — config-mutator: dispatched config writer with audit log

load helpers/load
load helpers/assertions

MUTATE_SH="$CORE_ROOT/skills/builtin/config-mutator/mutate.sh"

mk_ws() {
  local d; d="$(make_scratch)"
  mkdir -p "$d/.codenook/history" "$d/.codenook/plugins/development"
  echo "$d"
}

mk_task() {
  local ws="$1" tid="$2"
  mkdir -p "$ws/.codenook/tasks/$tid"
  cat >"$ws/.codenook/tasks/$tid/state.json" <<EOF
{"task_id":"$tid","phase":"start","iteration":0,"config_overrides":{}}
EOF
}

@test "m5-mutator: skill exists and is executable" {
  assert_file_exists "$MUTATE_SH"
  assert_file_executable "$MUTATE_SH"
}

@test "m5-mutator: workspace scope writes config.yaml + audit log" {
  ws="$(mk_ws)"
  run_with_stderr "\"$MUTATE_SH\" --plugin development --path models.reviewer --value tier_balanced --reason 'why' --actor distiller --workspace \"$ws\" --scope workspace"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.changed == true' >/dev/null
  # config.yaml updated
  grep -q "tier_balanced" "$ws/.codenook/config.yaml"
  # audit log appended
  [ -f "$ws/.codenook/history/config-changes.jsonl" ]
  last=$(tail -1 "$ws/.codenook/history/config-changes.jsonl")
  echo "$last" | jq -e '.actor == "distiller"' >/dev/null
  echo "$last" | jq -e '.scope == "workspace"' >/dev/null
  echo "$last" | jq -e '.path  == "models.reviewer"' >/dev/null
  echo "$last" | jq -e '.new   == "tier_balanced"' >/dev/null
}

@test "m5-mutator: subsequent config-resolve sees the new value" {
  ws="$(mk_ws)"
  run_with_stderr "\"$MUTATE_SH\" --plugin development --path models.reviewer --value tier_balanced --reason 'why' --actor distiller --workspace \"$ws\" --scope workspace"
  [ "$status" -eq 0 ]
  run_with_stderr "\"$RESOLVE_SH\" --plugin development --workspace \"$ws\" --catalog \"$FIXTURES_ROOT/catalog/full.json\""
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.models.reviewer == "sonnet-4.6"' >/dev/null
  echo "$output" | jq -e '._provenance["models.reviewer"].from_layer == 3' >/dev/null
}

@test "m5-mutator: task scope writes state.json.config_overrides + provenance from_layer 4" {
  ws="$(mk_ws)"
  mk_task "$ws" "T-001"
  run_with_stderr "\"$MUTATE_SH\" --plugin development --path models.reviewer --value tier_cheap --reason 'task local' --actor user --workspace \"$ws\" --scope task --task T-001"
  [ "$status" -eq 0 ]
  assert_jq "$ws/.codenook/tasks/T-001/state.json" '.config_overrides.models.reviewer == "tier_cheap"'
  last=$(tail -1 "$ws/.codenook/history/config-changes.jsonl")
  echo "$last" | jq -e '.scope == "task" and .task == "T-001"' >/dev/null
}

@test "m5-mutator: noop returns changed=false and writes no audit entry" {
  ws="$(mk_ws)"
  run_with_stderr "\"$MUTATE_SH\" --plugin development --path models.reviewer --value tier_balanced --reason 'first' --actor distiller --workspace \"$ws\" --scope workspace"
  [ "$status" -eq 0 ]
  before_lines=$(wc -l <"$ws/.codenook/history/config-changes.jsonl" | tr -d ' ')
  run_with_stderr "\"$MUTATE_SH\" --plugin development --path models.reviewer --value tier_balanced --reason 'second same' --actor distiller --workspace \"$ws\" --scope workspace"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.changed == false' >/dev/null
  after_lines=$(wc -l <"$ws/.codenook/history/config-changes.jsonl" | tr -d ' ')
  [ "$before_lines" = "$after_lines" ]
}

@test "m5-mutator: router invariant blocks plugin=__router__ + path=models.router" {
  ws="$(mk_ws)"
  run_with_stderr "\"$MUTATE_SH\" --plugin __router__ --path models.router --value tier_cheap --reason 'try' --actor user --workspace \"$ws\" --scope workspace"
  [ "$status" -ne 0 ]
  assert_contains "$STDERR" "router"
  assert_contains "$STDERR" "invariant"
}

@test "m5-mutator: unknown top-level path segment blocked" {
  ws="$(mk_ws)"
  run_with_stderr "\"$MUTATE_SH\" --plugin development --path bogus.x --value y --reason 'no' --actor user --workspace \"$ws\" --scope workspace"
  [ "$status" -ne 0 ]
  assert_contains "$STDERR" "bogus"
}

@test "m5-mutator: actor enum validated" {
  ws="$(mk_ws)"
  run_with_stderr "\"$MUTATE_SH\" --plugin development --path models.reviewer --value tier_cheap --reason 'x' --actor hacker --workspace \"$ws\" --scope workspace"
  [ "$status" -ne 0 ]
  assert_contains "$STDERR" "actor"
}

@test "m5-mutator: path starting with _ rejected" {
  ws="$(mk_ws)"
  run_with_stderr "\"$MUTATE_SH\" --plugin development --path _provenance.x --value y --reason 'x' --actor user --workspace \"$ws\" --scope workspace"
  [ "$status" -ne 0 ]
}

@test "m5-mutator: --value 5 round-trips as integer" {
  ws="$(mk_ws)"
  run_with_stderr "\"$MUTATE_SH\" --plugin development --path concurrency.workers --value 5 --reason 'int' --actor user --workspace \"$ws\" --scope workspace"
  [ "$status" -eq 0 ]
  type=$(python3 -c "import yaml; d=yaml.safe_load(open('$ws/.codenook/config.yaml')); v=d['plugins']['development']['overrides']['concurrency']['workers']; print(type(v).__name__,'=',repr(v))")
  [ "$type" = "int = 5" ]
}

@test "m5-mutator: --value true round-trips as boolean" {
  ws="$(mk_ws)"
  run_with_stderr "\"$MUTATE_SH\" --plugin development --path hitl.enabled --value true --reason 'bool' --actor user --workspace \"$ws\" --scope workspace"
  [ "$status" -eq 0 ]
  type=$(python3 -c "import yaml; d=yaml.safe_load(open('$ws/.codenook/config.yaml')); v=d['plugins']['development']['overrides']['hitl']['enabled']; print(type(v).__name__,'=',repr(v))")
  [ "$type" = "bool = True" ]
}

@test "m5-mutator: --value '\"5\"' (quoted JSON string) round-trips as string" {
  ws="$(mk_ws)"
  run_with_stderr "\"$MUTATE_SH\" --plugin development --path concurrency.workers --value '\"5\"' --reason 'str' --actor user --workspace \"$ws\" --scope workspace"
  [ "$status" -eq 0 ]
  type=$(python3 -c "import yaml; d=yaml.safe_load(open('$ws/.codenook/config.yaml')); v=d['plugins']['development']['overrides']['concurrency']['workers']; print(type(v).__name__,'=',repr(v))")
  [ "$type" = "str = '5'" ]
}

@test "m5-mutator: --value some-string round-trips as string" {
  ws="$(mk_ws)"
  run_with_stderr "\"$MUTATE_SH\" --plugin development --path models.reviewer --value some-string --reason 'fallback' --actor user --workspace \"$ws\" --scope workspace"
  [ "$status" -eq 0 ]
  val=$(python3 -c "import yaml; print(yaml.safe_load(open('$ws/.codenook/config.yaml'))['plugins']['development']['overrides']['models']['reviewer'])")
  [ "$val" = "some-string" ]
}

@test "m5-mutator: --value-json with invalid JSON exits 2" {
  ws="$(mk_ws)"
  run_with_stderr "\"$MUTATE_SH\" --plugin development --path models.reviewer --value-json 'not-json' --reason 'x' --actor user --workspace \"$ws\" --scope workspace"
  [ "$status" -eq 2 ]
}

@test "m5-mutator: write persists at target scope even when value matches deeper-layer default" {
  # Plugin baseline (L1) sets reviewer=tier_balanced (resolves to sonnet-4.6).
  # User explicitly pins workspace L3 reviewer=sonnet-4.6. Even though the
  # merged effective already resolves to sonnet-4.6, the override MUST land
  # in config.yaml and audit log MUST be appended.
  ws="$(mk_ws)"
  cat >"$ws/.codenook/plugins/development/config-defaults.yaml" <<'EOF'
models:
  reviewer: tier_balanced
EOF
  run_with_stderr "\"$MUTATE_SH\" --plugin development --path models.reviewer --value sonnet-4.6 --reason 'pin literal' --actor user --workspace \"$ws\" --scope workspace"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.changed == true' >/dev/null
  grep -q "sonnet-4.6" "$ws/.codenook/config.yaml"
  [ -f "$ws/.codenook/history/config-changes.jsonl" ]
}

@test "m5-mutator: noop true only when target-scope already has the exact value" {
  ws="$(mk_ws)"
  # First write — target layer is empty, so this lands.
  run_with_stderr "\"$MUTATE_SH\" --plugin development --path models.reviewer --value tier_balanced --reason 'first' --actor user --workspace \"$ws\" --scope workspace"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.changed == true' >/dev/null
  before_lines=$(wc -l <"$ws/.codenook/history/config-changes.jsonl" | tr -d ' ')
  # Second write of the *same* value at the same target layer → noop.
  run_with_stderr "\"$MUTATE_SH\" --plugin development --path models.reviewer --value tier_balanced --reason 'again' --actor user --workspace \"$ws\" --scope workspace"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.changed == false' >/dev/null
  after_lines=$(wc -l <"$ws/.codenook/history/config-changes.jsonl" | tr -d ' ')
  [ "$before_lines" = "$after_lines" ]
  # Third write: different value → changed:true again.
  run_with_stderr "\"$MUTATE_SH\" --plugin development --path models.reviewer --value tier_cheap --reason 'switch' --actor user --workspace \"$ws\" --scope workspace"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.changed == true' >/dev/null
}

@test "m5-mutator: _-prefixed segment at any depth is rejected" {
  ws="$(mk_ws)"
  run_with_stderr "\"$MUTATE_SH\" --plugin development --path models._magic --value y --reason 'x' --actor user --workspace \"$ws\" --scope workspace"
  [ "$status" -ne 0 ]
  assert_contains "$STDERR" "invalid path"
}
