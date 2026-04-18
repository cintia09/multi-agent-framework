#!/usr/bin/env bats
# M2 Unit 5 — plugin-deps-check (G06)
#
# Contract:
#   deps-check.sh --src <dir> [--core-version <v>] [--json]
#
# Reads plugin.yaml.requires.core_version (a comma-separated
# comparator list, e.g. ">=0.2.0,<1.0.0") and verifies the current
# core VERSION satisfies it. If --core-version is not supplied, the
# core VERSION file (skills/codenook-core/VERSION) is used.

load helpers/load
load helpers/assertions

GATE_SH="$CORE_ROOT/skills/builtin/plugin-deps-check/deps-check.sh"

mk_src() {
  local body d
  d="$(make_scratch)/p"; mkdir -p "$d"
  body="$1"
  printf '%s' "$body" >"$d/plugin.yaml"
  echo "$d"
}

@test "deps-check.sh exists and executable" {
  assert_file_exists "$GATE_SH"
  assert_file_executable "$GATE_SH"
}

@test "no requires.core_version → exit 0 (treated as 'any')" {
  d="$(mk_src "id: foo
version: 0.1.0
")"
  run_with_stderr "\"$GATE_SH\" --src \"$d\" --core-version 0.2.0"
  [ "$status" -eq 0 ]
}

@test "satisfied >= constraint → exit 0" {
  d="$(mk_src "id: foo
version: 0.1.0
requires:
  core_version: '>=0.2.0'
")"
  run_with_stderr "\"$GATE_SH\" --src \"$d\" --core-version 0.2.0"
  [ "$status" -eq 0 ]
}

@test "unsatisfied >= constraint → exit 1" {
  d="$(mk_src "id: foo
version: 0.1.0
requires:
  core_version: '>=0.5.0'
")"
  run_with_stderr "\"$GATE_SH\" --src \"$d\" --core-version 0.2.0"
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" "core_version"
}

@test "compound range satisfied (>=0.2.0,<1.0.0)" {
  d="$(mk_src "id: foo
version: 0.1.0
requires:
  core_version: '>=0.2.0,<1.0.0'
")"
  run_with_stderr "\"$GATE_SH\" --src \"$d\" --core-version 0.5.0"
  [ "$status" -eq 0 ]
}

@test "compound range unsatisfied (upper bound) → exit 1" {
  d="$(mk_src "id: foo
version: 0.1.0
requires:
  core_version: '>=0.2.0,<1.0.0'
")"
  run_with_stderr "\"$GATE_SH\" --src \"$d\" --core-version 1.0.0"
  [ "$status" -eq 1 ]
}

@test "garbage in core_version constraint → exit 1" {
  d="$(mk_src "id: foo
version: 0.1.0
requires:
  core_version: 'foo bar'
")"
  run_with_stderr "\"$GATE_SH\" --src \"$d\" --core-version 0.2.0"
  [ "$status" -eq 1 ]
}
