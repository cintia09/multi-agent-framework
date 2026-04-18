#!/usr/bin/env bats
# M5 — End-to-end DoD (impl-v6.md L1972-2028)
#
# Mirrors the seven assertions (a)-(g):
#   (a) model-probe + state.json catalog
#   (b) tier_balanced resolves through Layer 3, provenance.from_layer == 3
#   (c) __router__ defaults to tier_strong
#   (d) distiller routes to memory by default
#   (e) config-validate reports unknown nested key
#   (f) config-mutator with actor=distiller appends audit log
#   (g) task-config-set writes Layer 4, effective config reflects, audit logs

load helpers/load
load helpers/assertions

VALIDATE_SH="$CORE_ROOT/skills/builtin/config-validate/validate.sh"
MUTATE_SH="$CORE_ROOT/skills/builtin/config-mutator/mutate.sh"
DISTILL_SH="$CORE_ROOT/skills/builtin/distiller/distill.sh"
SET_SH="$CORE_ROOT/skills/builtin/task-config-set/set.sh"
M5_FIX="$FIXTURES_ROOT/m5"

# Build a fully-furnished workspace with the development-mock plugin
# installed under .codenook/plugins/development.
mk_e2e_ws() {
  local d; d="$(make_scratch)"
  mkdir -p "$d/.codenook/plugins/development" \
           "$d/.codenook/tasks" \
           "$d/.codenook/history" \
           "$d/.codenook/memory" \
           "$d/.codenook/knowledge"
  cp "$M5_FIX/plugins/development-mock/plugin.yaml"          "$d/.codenook/plugins/development/"
  cp "$M5_FIX/plugins/development-mock/config-defaults.yaml" "$d/.codenook/plugins/development/"
  cp "$M5_FIX/plugins/development-mock/config-schema.yaml"   "$d/.codenook/plugins/development/"
  echo "$d"
}

# --- (a) ---
@test "m5-e2e (a): init.sh --refresh-models writes model_catalog into state.json" {
  ws="$(mk_e2e_ws)"
  CODENOOK_AVAILABLE_MODELS="opus-4.7,sonnet-4.6,haiku-4.5" \
    run_with_stderr "cd \"$ws\" && \"$INIT_SH\" --refresh-models"
  [ "$status" -eq 0 ]
  assert_jq "$ws/.codenook/state.json" '.model_catalog.refreshed_at | length > 0'
  assert_jq "$ws/.codenook/state.json" '.model_catalog.resolved_tiers.strong   == "opus-4.7"'
  assert_jq "$ws/.codenook/state.json" '.model_catalog.resolved_tiers.balanced == "sonnet-4.6"'
  assert_jq "$ws/.codenook/state.json" '.model_catalog.resolved_tiers.cheap    == "haiku-4.5"'
}

# --- (b) ---
@test "m5-e2e (b): tier_balanced override at Layer 3 resolves + provenance.from_layer == 3" {
  ws="$(mk_e2e_ws)"
  CODENOOK_AVAILABLE_MODELS="opus-4.7,sonnet-4.6,haiku-4.5" \
    bash -c "cd \"$ws\" && \"$INIT_SH\" --refresh-models" >/dev/null 2>&1
  cat >"$ws/.codenook/config.yaml" <<'EOF'
plugins:
  development:
    overrides:
      models:
        reviewer: tier_balanced
EOF
  run_with_stderr "\"$RESOLVE_SH\" --plugin development --workspace \"$ws\" --catalog \"$ws/.codenook/state.json\""
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.models.reviewer == "sonnet-4.6"' >/dev/null
  echo "$output" | jq -e '._provenance["models.reviewer"].symbol == "tier_balanced"' >/dev/null
  echo "$output" | jq -e '._provenance["models.reviewer"].from_layer == 3' >/dev/null
}

# --- (c) ---
@test "m5-e2e (c): __router__ resolves to tier_strong literal" {
  ws="$(mk_e2e_ws)"
  CODENOOK_AVAILABLE_MODELS="opus-4.7,sonnet-4.6,haiku-4.5" \
    bash -c "cd \"$ws\" && \"$INIT_SH\" --refresh-models" >/dev/null 2>&1
  run_with_stderr "\"$RESOLVE_SH\" --plugin __router__ --workspace \"$ws\" --catalog \"$ws/.codenook/state.json\""
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.models.router == "opus-4.7"' >/dev/null
}

# --- (d) ---
@test "m5-e2e (d): distiller routes pytest-style to memory by default" {
  ws="$(mk_e2e_ws)"
  c="${BATS_TEST_TMPDIR}/c.md"; printf 'body\n' > "$c"
  run_with_stderr "\"$DISTILL_SH\" --plugin development --topic pytest-style --content \"$c\" --workspace \"$ws\""
  [ "$status" -eq 0 ]
  [ -f "$ws/.codenook/memory/development/by-topic/pytest-style.md" ]
  [ ! -f "$ws/.codenook/knowledge/by-topic/pytest-style.md" ]
}

# --- (e) ---
@test "m5-e2e (e): config-validate flags unknown nested key with did-you-mean" {
  ws="$(mk_e2e_ws)"
  cfg="${BATS_TEST_TMPDIR}/cfg.json"
  cat >"$cfg" <<'EOF'
{ "models": { "default": "opus-4.7", "reviever": "x" } }
EOF
  run_with_stderr "\"$VALIDATE_SH\" --config \"$cfg\""
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" "unknown key"
  assert_contains "$STDERR" "reviewer"
}

# --- (f) ---
@test "m5-e2e (f): config-mutator (actor=distiller) appends audit log" {
  ws="$(mk_e2e_ws)"
  CODENOOK_AVAILABLE_MODELS="opus-4.7,sonnet-4.6,haiku-4.5" \
    bash -c "cd \"$ws\" && \"$INIT_SH\" --refresh-models" >/dev/null 2>&1
  run_with_stderr "\"$MUTATE_SH\" --plugin development --path models.reviewer --value tier_strong --reason 'observed' --actor distiller --workspace \"$ws\" --scope workspace"
  [ "$status" -eq 0 ]
  last=$(tail -1 "$ws/.codenook/history/config-changes.jsonl")
  echo "$last" | jq -e '.actor == "distiller"' >/dev/null
  echo "$last" | jq -e '.path  == "models.reviewer"' >/dev/null
}

# --- (g) ---
@test "m5-e2e (g): task-config-set writes L4, effective sees it, audit log records actor=user" {
  ws="$(mk_e2e_ws)"
  CODENOOK_AVAILABLE_MODELS="opus-4.7,sonnet-4.6,haiku-4.5" \
    bash -c "cd \"$ws\" && \"$INIT_SH\" --refresh-models" >/dev/null 2>&1
  TID="T-007"
  mkdir -p "$ws/.codenook/tasks/$TID"
  echo '{"task_id":"'$TID'","phase":"start","iteration":0,"config_overrides":{}}' > "$ws/.codenook/tasks/$TID/state.json"

  run_with_stderr "\"$SET_SH\" --mode set --task $TID --plugin development --role reviewer --value tier_cheap --workspace \"$ws\""
  [ "$status" -eq 0 ]
  assert_jq "$ws/.codenook/tasks/$TID/state.json" '.config_overrides.models.reviewer == "tier_cheap"'

  run_with_stderr "\"$RESOLVE_SH\" --plugin development --task $TID --workspace \"$ws\" --catalog \"$ws/.codenook/state.json\""
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.models.reviewer == "haiku-4.5"' >/dev/null
  echo "$output" | jq -e '._provenance["models.reviewer"].from_layer == 4' >/dev/null
  echo "$output" | jq -e '._provenance["models.reviewer"].symbol == "tier_cheap"' >/dev/null

  last=$(tail -1 "$ws/.codenook/history/config-changes.jsonl")
  echo "$last" | jq -e '.actor == "user"' >/dev/null
  echo "$last" | jq -e '.scope == "task"' >/dev/null
  echo "$last" | jq -e '.path  == "models.reviewer"' >/dev/null
}
