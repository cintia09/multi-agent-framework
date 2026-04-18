#!/usr/bin/env bats
# M5 — config-resolve full 4-layer + provenance + #44 router invariant + #45 whitelist

load helpers/load
load helpers/assertions

mk_ws_bare() {
  local d; d="$(make_scratch)"
  mkdir -p "$d/.codenook"
  echo "$d"
}

# Bare workspace, no config files at all -> only Layer 0 contributes.
@test "m5-resolve: empty workspace returns Layer 0 builtin defaults" {
  ws="$(mk_ws_bare)"
  run_with_stderr "\"$RESOLVE_SH\" --plugin development --workspace \"$ws\" --catalog \"$FIXTURES_ROOT/catalog/full.json\""
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.models.default == "opus-4.7"' >/dev/null
  echo "$output" | jq -e '.models.router  == "opus-4.7"' >/dev/null
  echo "$output" | jq -e '._provenance["models.default"].from_layer == 0' >/dev/null
  echo "$output" | jq -e '._provenance["models.router"].from_layer  == 0' >/dev/null
}

@test "m5-resolve: unknown top-key in config.yaml exits 1 with unknown_top_key" {
  ws="$(mk_ws_bare)"
  cat >"$ws/.codenook/config.yaml" <<'EOF'
defaults:
  models:
    default: tier_strong
weird_unknown_top: 1
EOF
  run_with_stderr "\"$RESOLVE_SH\" --plugin development --workspace \"$ws\" --catalog \"$FIXTURES_ROOT/catalog/full.json\""
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" "unknown_top_key"
  assert_contains "$STDERR" "weird_unknown_top"
}

@test "m5-resolve: 10-key whitelist permits all decision-45 keys" {
  ws="$(mk_ws_bare)"
  cat >"$ws/.codenook/config.yaml" <<'EOF'
models: {}
hitl: {}
knowledge: {}
concurrency: {}
skills: {}
memory: {}
router: {}
plugins: {}
defaults: {}
secrets: {}
EOF
  run_with_stderr "\"$RESOLVE_SH\" --plugin development --workspace \"$ws\" --catalog \"$FIXTURES_ROOT/catalog/full.json\""
  [ "$status" -eq 0 ]
}

@test "m5-resolve: __router__ Layer 1 cannot override models.router" {
  ws="$(mk_ws_bare)"
  mkdir -p "$ws/.codenook/plugins/__router__"
  cat >"$ws/.codenook/plugins/__router__/config-defaults.yaml" <<'EOF'
models:
  router: tier_cheap
EOF
  run_with_stderr "\"$RESOLVE_SH\" --plugin __router__ --workspace \"$ws\" --catalog \"$FIXTURES_ROOT/catalog/full.json\""
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.models.router == "opus-4.7"' >/dev/null
  echo "$output" | jq -e '._provenance["models.router"].from_layer == 0' >/dev/null
  echo "$output" | jq -e '._provenance["models.router"].router_invariant_enforced == true' >/dev/null
}

@test "m5-resolve: __router__ Layer 3 attempt is reverted with router_invariant_enforced" {
  ws="$(mk_ws_bare)"
  cat >"$ws/.codenook/config.yaml" <<'EOF'
plugins:
  __router__:
    overrides:
      models:
        router: tier_balanced
EOF
  run_with_stderr "\"$RESOLVE_SH\" --plugin __router__ --workspace \"$ws\" --catalog \"$FIXTURES_ROOT/catalog/full.json\""
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.models.router == "opus-4.7"' >/dev/null
  echo "$output" | jq -e '._provenance["models.router"].router_invariant_enforced == true' >/dev/null
}

@test "m5-resolve: __router__ Layer 2 defaults may set models.router" {
  ws="$(mk_ws_bare)"
  cat >"$ws/.codenook/config.yaml" <<'EOF'
defaults:
  models:
    router: tier_balanced
EOF
  run_with_stderr "\"$RESOLVE_SH\" --plugin __router__ --workspace \"$ws\" --catalog \"$FIXTURES_ROOT/catalog/full.json\""
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.models.router == "sonnet-4.6"' >/dev/null
  echo "$output" | jq -e '._provenance["models.router"].from_layer == 2' >/dev/null
}

@test "m5-resolve: missing catalog file leaves tier symbol unresolved with warn" {
  ws="$(mk_ws_bare)"
  mkdir -p "$ws/.codenook/plugins/development"
  cat >"$ws/.codenook/plugins/development/config-defaults.yaml" <<'EOF'
models:
  reviewer: tier_balanced
EOF
  run_with_stderr "\"$RESOLVE_SH\" --plugin development --workspace \"$ws\" --catalog \"$ws/.codenook/state.json\""
  [ "$status" -eq 0 ]
  # When catalog file is missing entirely, leave symbol unresolved (deferred)
  echo "$output" | jq -e '.models.reviewer == "tier_balanced"' >/dev/null
  echo "$output" | jq -e '._provenance["models.reviewer"].resolved_via == "deferred:catalog_missing"' >/dev/null
  assert_contains "$STDERR" "catalog"
}
