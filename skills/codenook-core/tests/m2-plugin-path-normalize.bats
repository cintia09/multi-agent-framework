#!/usr/bin/env bats
# M2 Unit 7 — plugin-path-normalize (G11)
#
# Contract:
#   path-normalize.sh --src <dir> [--json]
#
# Rejects:
#   - any symlink anywhere under <src> (G11 is stricter than G01)
#   - any path-shaped string in any *.yaml under <src> that:
#       * starts with '/'  (absolute)
#       * starts with '~'
#       * contains '..' as a path segment
#
# A "path-shaped string" = a YAML scalar string that contains '/' or
# ends in a known source extension (.sh .py .md .yaml .yml .json).

load helpers/load
load helpers/assertions

GATE_SH="$CORE_ROOT/skills/builtin/plugin-path-normalize/path-normalize.sh"

mk_src() {
  local d
  d="$(make_scratch)/p"; mkdir -p "$d"
  printf 'id: foo\nversion: 0.1.0\n' >"$d/plugin.yaml"
  echo "$d"
}

@test "path-normalize.sh exists and executable" {
  assert_file_exists "$GATE_SH"
  assert_file_executable "$GATE_SH"
}

@test "clean tree → exit 0" {
  d="$(mk_src)"
  mkdir -p "$d/skills/test-runner"
  printf 'echo hi\n' >"$d/skills/test-runner/run.sh"
  printf 'entry_points:\n  install: skills/test-runner/run.sh\n' >>"$d/plugin.yaml"
  run_with_stderr "\"$GATE_SH\" --src \"$d\""
  [ "$status" -eq 0 ]
}

@test "yaml value with .. traversal → exit 1" {
  d="$(mk_src)"
  printf 'entry_points:\n  install: ../escape.sh\n' >>"$d/plugin.yaml"
  run_with_stderr "\"$GATE_SH\" --src \"$d\""
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" ".."
}

@test "yaml value with absolute path → exit 1" {
  d="$(mk_src)"
  printf 'entry_points:\n  install: /etc/passwd\n' >>"$d/plugin.yaml"
  run_with_stderr "\"$GATE_SH\" --src \"$d\""
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" "absolute"
}

@test "yaml value with ~/ home expansion → exit 1" {
  d="$(mk_src)"
  printf 'entry_points:\n  install: ~/scripts/x.sh\n' >>"$d/plugin.yaml"
  run_with_stderr "\"$GATE_SH\" --src \"$d\""
  [ "$status" -eq 1 ]
}

@test "any symlink under src → exit 1" {
  d="$(mk_src)"
  printf 'real\n' >"$d/real"
  ( cd "$d" && ln -s real link )
  run_with_stderr "\"$GATE_SH\" --src \"$d\""
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" "symlink"
}

@test "embedded .. in middle of yaml path (a/b/../c) → exit 1" {
  d="$(mk_src)"
  printf 'entry_points:\n  install: skills/foo/../bar.sh\n' >>"$d/plugin.yaml"
  run_with_stderr "\"$GATE_SH\" --src \"$d\""
  [ "$status" -eq 1 ]
}

@test "--json envelope on success" {
  d="$(mk_src)"
  run "$GATE_SH" --src "$d" --json
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.gate == "plugin-path-normalize" and .ok == true' >/dev/null
}
