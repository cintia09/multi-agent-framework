#!/usr/bin/env bats
# Unit 3 — config-resolve (F-021..F-031, M-006..M-016)

load helpers/load
load helpers/assertions

# Build a minimal workspace skeleton under $1.
#   <ws>/.codenook/plugins/<plugin>/config-defaults.yaml   (optional, $2)
#   <ws>/.codenook/plugins/<plugin>/config-schema.yaml     (optional, $3)
#   <ws>/.codenook/config.yaml                             (optional, $4)
#   <ws>/.codenook/tasks/<task>/state.json                 (optional, $5,$6)
mk_ws() {
  local ws plugin defaults schema cfg task task_state
  ws="$1"; plugin="$2"; defaults="$3"; schema="$4"; cfg="$5"; task="$6"; task_state="$7"
  mkdir -p "$ws/.codenook/plugins/$plugin"
  [ -n "$defaults" ] && [ -f "$defaults" ] && cp "$defaults" "$ws/.codenook/plugins/$plugin/config-defaults.yaml"
  [ -n "$schema" ]   && [ -f "$schema" ]   && cp "$schema"   "$ws/.codenook/plugins/$plugin/config-schema.yaml"
  [ -n "$cfg" ]      && [ -f "$cfg" ]      && cp "$cfg"      "$ws/.codenook/config.yaml"
  if [ -n "$task" ] && [ -n "$task_state" ] && [ -f "$task_state" ]; then
    mkdir -p "$ws/.codenook/tasks/$task"
    cp "$task_state" "$ws/.codenook/tasks/$task/state.json"
  fi
}

run_resolve() {
  # $1=workspace, $2=plugin, $3=catalog (path), $4=optional task
  local ws="$1" plugin="$2" cat="$3" task="${4:-}"
  STDERR_FILE="${BATS_TEST_TMPDIR:-/tmp}/cn-stderr.$$"
  if [ -n "$task" ]; then
    run bash -c "\"$RESOLVE_SH\" --plugin \"$plugin\" --task \"$task\" --workspace \"$ws\" --catalog \"$cat\" 2>\"$STDERR_FILE\""
  else
    run bash -c "\"$RESOLVE_SH\" --plugin \"$plugin\" --workspace \"$ws\" --catalog \"$cat\" 2>\"$STDERR_FILE\""
  fi
  STDERR="$(cat "$STDERR_FILE" 2>/dev/null || echo)"
  export STDERR
}

@test "resolve.sh exists and is executable" {
  assert_file_exists "$RESOLVE_SH"
  assert_file_executable "$RESOLVE_SH"
}

@test "Layer 0 builtin fallback when no plugin/config files (F-025)" {
  ws="$(make_scratch)"
  mk_ws "$ws" "development" "" "" "" "" ""
  run_resolve "$ws" "development" "$FIXTURES_ROOT/catalog/full.json"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.models.default == "opus-4.7"' >/dev/null
  echo "$output" | jq -e '._provenance["models.default"].from_layer == 0' >/dev/null
}

@test "Layer 1 plugin baseline overrides Layer 0 (F-026 / M-012)" {
  ws="$(make_scratch)"
  mk_ws "$ws" "development" "$FIXTURES_ROOT/config/plugin-baseline.yaml" "" "" "" ""
  run_resolve "$ws" "development" "$FIXTURES_ROOT/catalog/full.json"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.models.reviewer == "sonnet-4.6"' >/dev/null
  echo "$output" | jq -e '._provenance["models.reviewer"].from_layer == 1' >/dev/null
}

@test "Layer 2 workspace defaults overrides Layer 1 (F-027 / M-013)" {
  ws="$(make_scratch)"
  cat >"$ws.cfg.yaml" <<'EOF'
defaults:
  models:
    reviewer: tier_cheap
EOF
  mk_ws "$ws" "development" "$FIXTURES_ROOT/config/plugin-baseline.yaml" "" "$ws.cfg.yaml" "" ""
  run_resolve "$ws" "development" "$FIXTURES_ROOT/catalog/full.json"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.models.reviewer == "haiku-4.5"' >/dev/null
  echo "$output" | jq -e '._provenance["models.reviewer"].from_layer == 2' >/dev/null
}

@test "Layer 3 plugin overrides overrides Layer 2 (F-028 / M-014)" {
  ws="$(make_scratch)"
  cat >"$ws.cfg.yaml" <<'EOF'
defaults:
  models:
    reviewer: tier_cheap
plugins:
  development:
    overrides:
      models:
        reviewer: tier_strong
EOF
  mk_ws "$ws" "development" "$FIXTURES_ROOT/config/plugin-baseline.yaml" "" "$ws.cfg.yaml" "" ""
  run_resolve "$ws" "development" "$FIXTURES_ROOT/catalog/full.json"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.models.reviewer == "opus-4.7"' >/dev/null
  echo "$output" | jq -e '._provenance["models.reviewer"].from_layer == 3' >/dev/null
}

@test "Layer 4 task overrides hits (F-029 / M-015)" {
  ws="$(make_scratch)"
  cat >"$ws.cfg.yaml" <<'EOF'
defaults:
  models:
    reviewer: tier_cheap
plugins:
  development:
    overrides:
      models:
        reviewer: tier_strong
EOF
  mk_ws "$ws" "development" "$FIXTURES_ROOT/config/plugin-baseline.yaml" "" "$ws.cfg.yaml" \
        "T-007" "$FIXTURES_ROOT/config/task-overrides.json"
  run_resolve "$ws" "development" "$FIXTURES_ROOT/catalog/full.json" "T-007"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.models.reviewer == "sonnet-4.6"' >/dev/null
  echo "$output" | jq -e '._provenance["models.reviewer"].from_layer == 4' >/dev/null
}

@test "Deep merge default — high layer adds, low layer keeps (F-030)" {
  ws="$(make_scratch)"
  cat >"$ws.cfg.yaml" <<'EOF'
defaults:
  models:
    extra_role: tier_balanced
EOF
  # plugin-baseline sets planner + reviewer; cfg adds extra_role; both should survive.
  mk_ws "$ws" "development" "$FIXTURES_ROOT/config/plugin-baseline.yaml" "" "$ws.cfg.yaml" "" ""
  run_resolve "$ws" "development" "$FIXTURES_ROOT/catalog/full.json"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.models.planner == "opus-4.7"' >/dev/null
  echo "$output" | jq -e '.models.extra_role == "sonnet-4.6"' >/dev/null
}

@test "merge: replace annotation on hitl.gates (F-031)" {
  ws="$(make_scratch)"
  cat >"$ws.schema.yaml" <<'EOF'
properties:
  hitl:
    properties:
      gates:
        x-merge: replace
EOF
  cat >"$ws.cfg.yaml" <<'EOF'
plugins:
  development:
    overrides:
      hitl:
        gates: [accept]
EOF
  mk_ws "$ws" "development" "$FIXTURES_ROOT/config/plugin-baseline.yaml" "$ws.schema.yaml" "$ws.cfg.yaml" "" ""
  run_resolve "$ws" "development" "$FIXTURES_ROOT/catalog/full.json"
  [ "$status" -eq 0 ]
  # Replace, not deep-merge / not append — should be exactly ["accept"], not ["design","accept"].
  echo "$output" | jq -e '.hitl.gates == ["accept"]' >/dev/null
}

@test "Unknown key emits stderr warning but does not fail (F-032 lite)" {
  ws="$(make_scratch)"
  cat >"$ws.cfg.yaml" <<'EOF'
plugins:
  development:
    overrides:
      models:
        reviewer: tier_strong
      weird_unknown_key: 1
EOF
  mk_ws "$ws" "development" "$FIXTURES_ROOT/config/plugin-baseline.yaml" "" "$ws.cfg.yaml" "" ""
  run_resolve "$ws" "development" "$FIXTURES_ROOT/catalog/full.json"
  [ "$status" -eq 0 ]
  assert_contains "$STDERR" "weird_unknown_key"
  assert_contains "$STDERR" "warning"
}

@test "Tier symbol expansion via catalog (M-006)" {
  ws="$(make_scratch)"
  mk_ws "$ws" "development" "$FIXTURES_ROOT/config/plugin-baseline.yaml" "" "" "" ""
  run_resolve "$ws" "development" "$FIXTURES_ROOT/catalog/full.json"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.models.planner == "opus-4.7"' >/dev/null
  echo "$output" | jq -e '._provenance["models.planner"].symbol == "tier_strong"' >/dev/null
  echo "$output" | jq -e '._provenance["models.planner"].resolved_via == "model_catalog.resolved_tiers.strong"' >/dev/null
}

@test "Literal value passthrough + symbol mixing (M-010)" {
  ws="$(make_scratch)"
  cat >"$ws.def.yaml" <<'EOF'
models:
  reviewer: gpt-5.4
  planner: tier_strong
  default: tier_strong
EOF
  mk_ws "$ws" "development" "$ws.def.yaml" "" "" "" ""
  run_resolve "$ws" "development" "$FIXTURES_ROOT/catalog/full.json"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.models.reviewer == "gpt-5.4"' >/dev/null
  echo "$output" | jq -e '._provenance["models.reviewer"].resolved_via == "literal"' >/dev/null
  echo "$output" | jq -e '._provenance["models.reviewer"].symbol == null' >/dev/null
  echo "$output" | jq -e '.models.planner == "opus-4.7"' >/dev/null
}

@test "Unknown tier symbol → warn + fallback to tier_strong" {
  ws="$(make_scratch)"
  cat >"$ws.def.yaml" <<'EOF'
models:
  reviewer: tier_xxx
  default: tier_strong
EOF
  mk_ws "$ws" "development" "$ws.def.yaml" "" "" "" ""
  run_resolve "$ws" "development" "$FIXTURES_ROOT/catalog/full.json"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.models.reviewer == "opus-4.7"' >/dev/null
  echo "$output" | jq -e '._provenance["models.reviewer"].resolved_via | startswith("fallback")' >/dev/null
  assert_contains "$STDERR" "tier_xxx"
}

@test "Catalog has no tier_strong candidates → ultimate hardcoded fallback (R-26)" {
  ws="$(make_scratch)"
  mk_ws "$ws" "development" "$FIXTURES_ROOT/config/plugin-baseline.yaml" "" "" "" ""
  run_resolve "$ws" "development" "$FIXTURES_ROOT/catalog/empty.json"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.models.planner == "opus-4.7"' >/dev/null
  echo "$output" | jq -e '._provenance["models.planner"].resolved_via | test("hardcoded|fallback")' >/dev/null
}

@test "Corrupt catalog → stderr 'catalog corrupt' + exit non-zero (R-27)" {
  ws="$(make_scratch)"
  mk_ws "$ws" "development" "$FIXTURES_ROOT/config/plugin-baseline.yaml" "" "" "" ""
  run_resolve "$ws" "development" "$FIXTURES_ROOT/catalog/corrupt.json"
  [ "$status" -ne 0 ]
  assert_contains "$STDERR" "catalog corrupt"
}

@test "_provenance fields present and well-formed (M-024)" {
  ws="$(make_scratch)"
  mk_ws "$ws" "development" "$FIXTURES_ROOT/config/plugin-baseline.yaml" "" "" "" ""
  run_resolve "$ws" "development" "$FIXTURES_ROOT/catalog/full.json"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '._provenance["models.planner"] | has("from_layer") and has("symbol") and has("resolved_via") and has("value")' >/dev/null
}

@test "Router sentinel plugin=__router__ reads only Layer 0/2 (M-016)" {
  ws="$(make_scratch)"
  cat >"$ws.def.yaml" <<'EOF'
models:
  router: tier_cheap
EOF
  cat >"$ws.cfg.yaml" <<'EOF'
plugins:
  __router__:
    overrides:
      models:
        router: tier_cheap
EOF
  # Layer 1 (plugin baseline) AND Layer 3 (plugin overrides) try to push router=cheap.
  # Both must be ignored for the router sentinel; only Layer 0 (default tier_strong) and
  # Layer 2 (none here) apply, so router resolves to opus-4.7.
  mk_ws "$ws" "__router__" "$ws.def.yaml" "" "$ws.cfg.yaml" "" ""
  run_resolve "$ws" "__router__" "$FIXTURES_ROOT/catalog/full.json"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.models.router == "opus-4.7"' >/dev/null
  echo "$output" | jq -e '._provenance["models.router"].from_layer == 0' >/dev/null
}
