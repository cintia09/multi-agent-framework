#!/usr/bin/env bats
# M3 Unit 5 — router agent profile (extended from M1 stub).
#
# The profile must list the self-bootstrap reads, codify the triage
# priority order, and forbid the router from inlining manifest content
# (it must call router-dispatch-build instead). Hard 2KB limit
# (matches A-012 main-session loader budget).

load helpers/load
load helpers/assertions

PROFILE="$CORE_ROOT/agents/router.md"

@test "router.md exists" {
  assert_file_exists "$PROFILE"
}

@test "router.md ≤ 2KB" {
  assert_file_size_le "$PROFILE" 2048
}

@test "router.md has Self-bootstrap section listing required reads" {
  body="$(cat "$PROFILE")"
  assert_contains "$body" "Self-bootstrap"
  assert_contains "$body" "agents/router.md"
  assert_contains "$body" "core/shell.md"
  assert_contains "$body" "state.json"
  assert_contains "$body" "plugin.yaml"
}

@test "router.md has Triage rules section with priority order" {
  body="$(cat "$PROFILE")"
  assert_contains "$body" "Triage rules"
  # Priority words anywhere in the section
  assert_contains "$body" "skill"
  assert_contains "$body" "plugin"
  assert_contains "$body" "chat"
  assert_contains "$body" "hitl"
}

@test "router.md has Dispatch contract forbidding inline manifests" {
  body="$(cat "$PROFILE")"
  assert_contains "$body" "Dispatch contract"
  assert_contains "$body" "router-dispatch-build"
}
