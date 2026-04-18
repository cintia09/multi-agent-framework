#!/usr/bin/env bats
# M2 Unit 2 — plugin-schema gate (G02)
#
# Contract:
#   schema-check.sh --src <dir> [--json]
#   exit 0 = pass, 1 = fail, 2 = usage
#
# Required top-level keys in plugin.yaml (per M2 spec):
#   id, version, type, entry_points, declared_subsystems
# Validated against plugin-schema.yaml shipped with this skill.

load helpers/load
load helpers/assertions

GATE_SH="$CORE_ROOT/skills/builtin/plugin-schema/schema-check.sh"
SCHEMA="$CORE_ROOT/skills/builtin/plugin-schema/plugin-schema.yaml"

mk_with_yaml() {
  local d body
  d="$(make_scratch)/p"
  mkdir -p "$d"
  body="$1"
  printf '%s' "$body" >"$d/plugin.yaml"
  echo "$d"
}

GOOD_YAML='id: foo
version: 0.1.0
type: domain
entry_points:
  install: install.sh
declared_subsystems:
  - skills
'

@test "schema-check.sh exists and is executable" {
  assert_file_exists "$GATE_SH"
  assert_file_executable "$GATE_SH"
  assert_file_exists "$SCHEMA"
}

@test "missing --src → exit 2" {
  run_with_stderr "\"$GATE_SH\""
  [ "$status" -eq 2 ]
}

@test "fully valid plugin.yaml → exit 0" {
  d="$(mk_with_yaml "$GOOD_YAML")"
  run_with_stderr "\"$GATE_SH\" --src \"$d\""
  [ "$status" -eq 0 ]
}

@test "missing id → exit 1, reason mentions id" {
  d="$(mk_with_yaml "version: 0.1.0
type: domain
entry_points: {install: install.sh}
declared_subsystems: [skills]
")"
  run_with_stderr "\"$GATE_SH\" --src \"$d\""
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" "id"
}

@test "missing version → exit 1" {
  d="$(mk_with_yaml "id: foo
type: domain
entry_points: {install: install.sh}
declared_subsystems: [skills]
")"
  run_with_stderr "\"$GATE_SH\" --src \"$d\""
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" "version"
}

@test "missing type → exit 1" {
  d="$(mk_with_yaml "id: foo
version: 0.1.0
entry_points: {install: install.sh}
declared_subsystems: [skills]
")"
  run_with_stderr "\"$GATE_SH\" --src \"$d\""
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" "type"
}

@test "missing entry_points → exit 1" {
  d="$(mk_with_yaml "id: foo
version: 0.1.0
type: domain
declared_subsystems: [skills]
")"
  run_with_stderr "\"$GATE_SH\" --src \"$d\""
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" "entry_points"
}

@test "missing declared_subsystems → exit 1" {
  d="$(mk_with_yaml "id: foo
version: 0.1.0
type: domain
entry_points: {install: install.sh}
")"
  run_with_stderr "\"$GATE_SH\" --src \"$d\""
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" "declared_subsystems"
}

@test "malformed YAML → exit 1" {
  d="$(mk_with_yaml "id: foo
version: 0.1.0
type: [unterminated
")"
  run_with_stderr "\"$GATE_SH\" --src \"$d\""
  [ "$status" -eq 1 ]
}

@test "wrong type for declared_subsystems (string instead of list) → exit 1" {
  d="$(mk_with_yaml "id: foo
version: 0.1.0
type: domain
entry_points: {install: install.sh}
declared_subsystems: skills
")"
  run_with_stderr "\"$GATE_SH\" --src \"$d\""
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" "declared_subsystems"
}

@test "--json envelope on success" {
  d="$(mk_with_yaml "$GOOD_YAML")"
  run "$GATE_SH" --src "$d" --json
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.ok == true and .gate == "plugin-schema"' >/dev/null
}
