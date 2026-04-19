#!/usr/bin/env bats
# Unit 7 — sec-audit (workspace security scanner)

load helpers/load
load helpers/assertions

AUDIT_SH="$CORE_ROOT/skills/builtin/sec-audit/audit.sh"

mk_clean_ws() {
  local d; d="$(make_scratch)"
  mkdir -p "$d/.codenook"
  ( cd "$d" && git init -q 2>/dev/null || true )
  echo "$d"
}

@test "audit.sh exists and is executable" {
  assert_file_exists "$AUDIT_SH"
  assert_file_executable "$AUDIT_SH"
}

@test "missing --workspace → exit 2" {
  run_with_stderr "\"$AUDIT_SH\""
  [ "$status" -eq 2 ]
  assert_contains "$STDERR" "--workspace"
}

@test "non-existent workspace → exit 2" {
  run_with_stderr "\"$AUDIT_SH\" --workspace /no/such/dir"
  [ "$status" -eq 2 ]
}

@test "clean workspace → exit 0, no findings" {
  ws="$(mk_clean_ws)"
  printf 'hello world\n' >"$ws/readme.md"
  run_with_stderr "\"$AUDIT_SH\" --workspace \"$ws\""
  [ "$status" -eq 0 ]
}

@test "file containing sk-XXXX-style OpenAI-like key → exit 1 + file+line" {
  ws="$(mk_clean_ws)"
  # M9.8 fix-r2: build sk- key at runtime so this fixture file does not
  # itself trip the pre-commit secret scanner.
  sk_key="sk""-abcdefghij0123456789ABCDEFGHIJklmnopqr"
  printf 'line1\napi: %s\nline3\n' "$sk_key" >"$ws/leak.txt"
  run_with_stderr "\"$AUDIT_SH\" --workspace \"$ws\""
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" "leak.txt"
  assert_contains "$STDERR" "2"
}

@test "AWS-key-like AKIA[A-Z0-9]{16} detected" {
  ws="$(mk_clean_ws)"
  # M9.8 fix-r2: split AKIA token so the bats source itself does not
  # trip the pre-commit secret scanner; concatenated at runtime so the
  # detector still sees a valid AWS-key-shaped string.
  aws_key="AKIA""IOSFODNN7EXAMPLE"
  printf 'key=%s\n' "$aws_key" >"$ws/aws.txt"
  run_with_stderr "\"$AUDIT_SH\" --workspace \"$ws\""
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" "aws.txt"
}

@test ".codenook/secrets.yaml with mode 644 → exit 1 + perm warning" {
  ws="$(mk_clean_ws)"
  printf 'x: y\n' >"$ws/.codenook/secrets.yaml"
  chmod 644 "$ws/.codenook/secrets.yaml"
  run_with_stderr "\"$AUDIT_SH\" --workspace \"$ws\""
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" "secrets.yaml"
  assert_contains "$STDERR" "600"
}

@test ".codenook/secrets.yaml with mode 600 → pass" {
  ws="$(mk_clean_ws)"
  printf 'x: y\n' >"$ws/.codenook/secrets.yaml"
  chmod 600 "$ws/.codenook/secrets.yaml"
  run_with_stderr "\"$AUDIT_SH\" --workspace \"$ws\""
  [ "$status" -eq 0 ]
}

@test "--json outputs structured findings list" {
  ws="$(mk_clean_ws)"
  sk_key="sk""-abcdefghij0123456789ABCDEFGHIJklmnopqr"
  printf '%s\n' "$sk_key" >"$ws/bad.txt"
  run_with_stderr "\"$AUDIT_SH\" --workspace \"$ws\" --json"
  [ "$status" -eq 1 ]
  echo "$output" | jq -e '.ok == false' >/dev/null
  echo "$output" | jq -e '.findings | length >= 1' >/dev/null
  echo "$output" | jq -e '.findings[0].type' >/dev/null
  echo "$output" | jq -e '.findings[0].path' >/dev/null
  echo "$output" | jq -e '.findings[0].severity' >/dev/null
}

@test "respects .gitignore (skip ignored paths)" {
  ws="$(mk_clean_ws)"
  printf 'ignored/\n' >"$ws/.gitignore"
  mkdir -p "$ws/ignored"
  sk_key="sk""-abcdefghij0123456789ABCDEFGHIJklmnopqr"
  printf '%s\n' "$sk_key" >"$ws/ignored/leak.txt"
  run_with_stderr "\"$AUDIT_SH\" --workspace \"$ws\""
  [ "$status" -eq 0 ]
}

@test ".git/ directory always skipped" {
  ws="$(mk_clean_ws)"
  mkdir -p "$ws/.git/objects"
  sk_key="sk""-abcdefghij0123456789ABCDEFGHIJklmnopqr"
  printf '%s\n' "$sk_key" >"$ws/.git/objects/leak.txt"
  run_with_stderr "\"$AUDIT_SH\" --workspace \"$ws\""
  [ "$status" -eq 0 ]
}

@test "only scans workspace subtree (not HOME)" {
  ws="$(mk_clean_ws)"
  printf 'clean\n' >"$ws/ok.txt"
  # HOME may contain secrets; audit must not walk it.
  run_with_stderr "\"$AUDIT_SH\" --workspace \"$ws\""
  [ "$status" -eq 0 ]
}

@test "modern sk-proj-* OpenAI project key detected" {
  ws="$(mk_clean_ws)"
  sk_proj="sk""-proj-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
  printf 'token: %s\n' "$sk_proj" >"$ws/proj.txt"
  run_with_stderr "\"$AUDIT_SH\" --workspace \"$ws\""
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" "proj.txt"
}

@test "modern sk-ant-api03-* Anthropic key detected" {
  ws="$(mk_clean_ws)"
  sk_ant="sk""-ant-api03-AAAAAAAAAAAAAAAAAAAA_BBBBBBBBBBBBBBBBBBBB"
  printf 'token: %s\n' "$sk_ant" >"$ws/ant.txt"
  run_with_stderr "\"$AUDIT_SH\" --workspace \"$ws\""
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" "ant.txt"
}
