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

@test "m5-resolve: missing catalog file substitutes hardcoded literal with warn" {
  ws="$(mk_ws_bare)"
  mkdir -p "$ws/.codenook/plugins/development"
  cat >"$ws/.codenook/plugins/development/config-defaults.yaml" <<'EOF'
models:
  reviewer: tier_balanced
EOF
  run_with_stderr "\"$RESOLVE_SH\" --plugin development --workspace \"$ws\" --catalog \"$ws/.codenook/state.json\""
  [ "$status" -eq 0 ]
  # Catalog file missing → tier symbol replaced with HARDCODED_FALLBACK
  echo "$output" | jq -e '.models.reviewer == "opus-4.7"' >/dev/null
  echo "$output" | jq -e '._provenance["models.reviewer"].resolved_via == "fallback:catalog_missing"' >/dev/null
  assert_contains "$STDERR" "catalog missing"
}

@test "m5-resolve: catalog missing + tier_strong substitutes literal not symbol" {
  ws="$(mk_ws_bare)"
  mkdir -p "$ws/.codenook/plugins/development"
  cat >"$ws/.codenook/plugins/development/config-defaults.yaml" <<'EOF'
models:
  default: tier_strong
EOF
  run_with_stderr "\"$RESOLVE_SH\" --plugin development --workspace \"$ws\" --catalog \"$ws/.codenook/state.json\""
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.models.default == "opus-4.7"' >/dev/null
  echo "$output" | jq -e '.models.default != "tier_strong"' >/dev/null
  echo "$output" | jq -e '._provenance["models.default"].resolved_via == "fallback:catalog_missing"' >/dev/null
}

@test "m5-resolve: literal model not in catalog.available emits warn" {
  ws="$(mk_ws_bare)"
  cat >"$ws/.codenook/state.json" <<'EOF'
{"model_catalog": {"refreshed_at": "2099-01-01T00:00:00Z", "available": [{"id": "opus-4.7"}], "resolved_tiers": {"strong": "opus-4.7", "balanced": "opus-4.7", "cheap": "opus-4.7"}}}
EOF
  cat >"$ws/.codenook/config.yaml" <<'EOF'
plugins:
  development:
    overrides:
      models:
        reviewer: gpt-4
EOF
  run_with_stderr "\"$RESOLVE_SH\" --plugin development --workspace \"$ws\" --catalog \"$ws/.codenook/state.json\""
  [ "$status" -eq 0 ]
  # value retained — only a warning fires
  echo "$output" | jq -e '.models.reviewer == "gpt-4"' >/dev/null
  assert_contains "$STDERR" "literal model gpt-4"
  assert_contains "$STDERR" "not in catalog.available"
}

@test "m5-resolve: router invariant strip emits stderr warning per layer" {
  ws="$(mk_ws_bare)"
  cat >"$ws/.codenook/config.yaml" <<'YAML'
plugins:
  __router__:
    overrides:
      models:
        router: tier_cheap
YAML
  run_with_stderr "\"$RESOLVE_SH\" --plugin __router__ --workspace \"$ws\" --catalog \"$FIXTURES_ROOT/catalog/full.json\""
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.models.router == "opus-4.7"' >/dev/null
  assert_contains "$STDERR" "router invariant: dropped"
  assert_contains "$STDERR" "layer 3"
}
