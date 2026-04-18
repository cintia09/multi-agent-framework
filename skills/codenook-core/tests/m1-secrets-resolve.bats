#!/usr/bin/env bats
# Unit 6 — secrets-resolve (${env:...} / ${file:...} placeholder resolution)

load helpers/load
load helpers/assertions

RESOLVE_SECRETS_SH="$CORE_ROOT/skills/builtin/secrets-resolve/resolve.sh"

write_json() {
  local path="$1"; shift
  printf '%s' "$*" >"$path"
}

@test "resolve.sh exists and is executable" {
  assert_file_exists "$RESOLVE_SECRETS_SH"
  assert_file_executable "$RESOLVE_SECRETS_SH"
}

@test "missing --config → exit 2" {
  run_with_stderr "\"$RESOLVE_SECRETS_SH\""
  [ "$status" -eq 2 ]
  assert_contains "$STDERR" "--config"
}

@test "non-existent config → exit 2" {
  run_with_stderr "\"$RESOLVE_SECRETS_SH\" --config /nope.json"
  [ "$status" -eq 2 ]
}

@test "no placeholders → passthrough unchanged" {
  ws="$(make_scratch)"
  write_json "$ws/c.json" '{"a":1,"b":"hello"}'
  run_with_stderr "\"$RESOLVE_SECRETS_SH\" --config \"$ws/c.json\""
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.a == 1 and .b == "hello"' >/dev/null
}

@test "\${env:FOO} resolved when FOO set" {
  ws="$(make_scratch)"
  write_json "$ws/c.json" '{"token":"${env:CN_TEST_FOO}"}'
  CN_TEST_FOO="abc123" run_with_stderr "\"$RESOLVE_SECRETS_SH\" --config \"$ws/c.json\""
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.token == "abc123"' >/dev/null
}

@test "\${env:MISSING} without --allow-missing → exit 1 + key name in stderr" {
  ws="$(make_scratch)"
  unset CN_TEST_ABSENT || true
  write_json "$ws/c.json" '{"token":"${env:CN_TEST_ABSENT}"}'
  run_with_stderr "\"$RESOLVE_SECRETS_SH\" --config \"$ws/c.json\""
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" "CN_TEST_ABSENT"
}

@test "\${env:MISSING} with --allow-missing → empty string + warn" {
  ws="$(make_scratch)"
  unset CN_TEST_ABSENT2 || true
  write_json "$ws/c.json" '{"token":"${env:CN_TEST_ABSENT2}"}'
  run_with_stderr "\"$RESOLVE_SECRETS_SH\" --config \"$ws/c.json\" --allow-missing"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.token == ""' >/dev/null
  assert_contains "$STDERR" "CN_TEST_ABSENT2"
}

@test "\${file:path} reads and trims file content" {
  ws="$(make_scratch)"
  printf '   my-secret-value  \n\n' >"$ws/secret.txt"
  write_json "$ws/c.json" "{\"k\":\"\${file:$ws/secret.txt}\"}"
  run_with_stderr "\"$RESOLVE_SECRETS_SH\" --config \"$ws/c.json\""
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.k == "my-secret-value"' >/dev/null
}

@test "\${file:...} with non-existent path → exit 1" {
  ws="$(make_scratch)"
  write_json "$ws/c.json" "{\"k\":\"\${file:$ws/nope.txt}\"}"
  run_with_stderr "\"$RESOLVE_SECRETS_SH\" --config \"$ws/c.json\""
  [ "$status" -eq 1 ]
}

@test "nested placeholders disallowed → exit 1 with message" {
  ws="$(make_scratch)"
  write_json "$ws/c.json" '{"k":"${env:${env:VAR_NAME}}"}'
  run_with_stderr "\"$RESOLVE_SECRETS_SH\" --config \"$ws/c.json\""
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" "nested"
}

@test "multiple placeholders in same string all resolved" {
  ws="$(make_scratch)"
  write_json "$ws/c.json" '{"auth":"Bearer ${env:CN_T_A}:${env:CN_T_B}"}'
  CN_T_A="aa" CN_T_B="bb" run_with_stderr "\"$RESOLVE_SECRETS_SH\" --config \"$ws/c.json\""
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.auth == "Bearer aa:bb"' >/dev/null
}

@test "placeholders in array elements and nested objects resolved" {
  ws="$(make_scratch)"
  write_json "$ws/c.json" '{"list":["${env:CN_T_X}","literal"],"nest":{"k":"${env:CN_T_Y}"}}'
  CN_T_X="xx" CN_T_Y="yy" run_with_stderr "\"$RESOLVE_SECRETS_SH\" --config \"$ws/c.json\""
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.list[0] == "xx"' >/dev/null
  echo "$output" | jq -e '.list[1] == "literal"' >/dev/null
  echo "$output" | jq -e '.nest.k == "yy"' >/dev/null
}

@test "SECURITY: resolved value NOT leaked in stderr on success" {
  ws="$(make_scratch)"
  write_json "$ws/c.json" '{"token":"${env:CN_T_SECRET}"}'
  CN_T_SECRET="super-sensitive-XYZ" run_with_stderr "\"$RESOLVE_SECRETS_SH\" --config \"$ws/c.json\""
  [ "$status" -eq 0 ]
  assert_not_contains "$STDERR" "super-sensitive-XYZ"
}

@test "JSON output is valid" {
  ws="$(make_scratch)"
  write_json "$ws/c.json" '{"a":1}'
  run_with_stderr "\"$RESOLVE_SECRETS_SH\" --config \"$ws/c.json\""
  [ "$status" -eq 0 ]
  echo "$output" | jq -e . >/dev/null
}

@test "\${file:/abs/path} absolute path works" {
  ws="$(make_scratch)"
  abs="$ws/abs-secret.txt"
  printf 'absval' >"$abs"
  write_json "$ws/c.json" "{\"k\":\"\${file:$abs}\"}"
  run_with_stderr "\"$RESOLVE_SECRETS_SH\" --config \"$ws/c.json\""
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.k == "absval"' >/dev/null
}
