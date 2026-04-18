#!/usr/bin/env bats
# M2 Unit 1 — plugin-format gate (G01)
#
# Contract:
#   format-check.sh --src <dir> [--json]
#   exit 0 = ok, 1 = fail (reasons → stderr), 2 = usage
#   --json: emit {"ok":bool,"gate":"plugin-format","reasons":[...]} on stdout
#
# Checks:
#   - <src>/plugin.yaml exists at root
#   - no symlinks anywhere under <src> that escape the src tree

load helpers/load
load helpers/assertions

GATE_SH="$CORE_ROOT/skills/builtin/plugin-format/format-check.sh"

mk_good() {
  local d; d="$(make_scratch)/good"
  mkdir -p "$d"
  printf 'id: foo\nversion: 0.1.0\n' >"$d/plugin.yaml"
  echo "$d"
}

@test "format-check.sh exists and is executable" {
  assert_file_exists "$GATE_SH"
  assert_file_executable "$GATE_SH"
}

@test "missing --src → exit 2" {
  run_with_stderr "\"$GATE_SH\""
  [ "$status" -eq 2 ]
  assert_contains "$STDERR" "--src"
}

@test "non-existent --src dir → exit 2" {
  run_with_stderr "\"$GATE_SH\" --src /no/such/dir"
  [ "$status" -eq 2 ]
}

@test "src with plugin.yaml at root → exit 0" {
  d="$(mk_good)"
  run_with_stderr "\"$GATE_SH\" --src \"$d\""
  [ "$status" -eq 0 ]
}

@test "src missing plugin.yaml → exit 1" {
  d="$(make_scratch)/bad"
  mkdir -p "$d"
  printf 'hi\n' >"$d/README.md"
  run_with_stderr "\"$GATE_SH\" --src \"$d\""
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" "plugin.yaml"
}

@test "symlink escaping src → exit 1" {
  d="$(make_scratch)/symlink-escape"
  mkdir -p "$d"
  printf 'id: foo\nversion: 0.1.0\n' >"$d/plugin.yaml"
  ln -s /etc/passwd "$d/leak"
  run_with_stderr "\"$GATE_SH\" --src \"$d\""
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" "symlink"
}

@test "internal relative symlink (within src) → exit 0" {
  d="$(make_scratch)/symlink-internal"
  mkdir -p "$d/sub"
  printf 'id: foo\nversion: 0.1.0\n' >"$d/plugin.yaml"
  printf 'x\n' >"$d/sub/real"
  ( cd "$d/sub" && ln -s real link )
  run_with_stderr "\"$GATE_SH\" --src \"$d\""
  [ "$status" -eq 0 ]
}

@test "--json on success emits ok=true" {
  d="$(mk_good)"
  run "$GATE_SH" --src "$d" --json
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.ok == true and .gate == "plugin-format"' >/dev/null
}

@test "--json on failure emits ok=false with reasons" {
  d="$(make_scratch)/bad2"; mkdir -p "$d"
  run "$GATE_SH" --src "$d" --json
  [ "$status" -eq 1 ]
  echo "$output" | jq -e '.ok == false and (.reasons | length) >= 1' >/dev/null
}
