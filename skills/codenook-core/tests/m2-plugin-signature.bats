#!/usr/bin/env bats
# M2 Unit 8 — plugin-signature (G05)
#
# Contract:
#   signature-check.sh --src <dir> [--json]
#
# Detached signature file: <src>/plugin.yaml.sig
#   - Format: hex sha256 digest of plugin.yaml on first non-blank line.
#   - If file missing & CODENOOK_REQUIRE_SIG=1 → fail
#   - If file missing & CODENOOK_REQUIRE_SIG=0 → pass (signatures opt-in)
#   - If file present → digest must match plugin.yaml's sha256
#
# Real cryptographic signing is deferred to M5; M2 ships the hook so
# downstream gates and packaging tools can wire it in.

load helpers/load
load helpers/assertions

GATE_SH="$CORE_ROOT/skills/builtin/plugin-signature/signature-check.sh"

mk_src() {
  local d
  d="$(make_scratch)/p"; mkdir -p "$d"
  printf 'id: foo\nversion: 0.1.0\n' >"$d/plugin.yaml"
  echo "$d"
}

sig_for() {
  shasum -a 256 "$1" | awk '{print $1}'
}

@test "signature-check.sh exists and executable" {
  assert_file_exists "$GATE_SH"
  assert_file_executable "$GATE_SH"
}

@test "no sig file & require unset → exit 0" {
  d="$(mk_src)"
  unset CODENOOK_REQUIRE_SIG
  run_with_stderr "\"$GATE_SH\" --src \"$d\""
  [ "$status" -eq 0 ]
}

@test "no sig file & CODENOOK_REQUIRE_SIG=1 → exit 1" {
  d="$(mk_src)"
  CODENOOK_REQUIRE_SIG=1 run_with_stderr "\"$GATE_SH\" --src \"$d\""
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" "signature"
}

@test "valid sig file → exit 0" {
  d="$(mk_src)"
  sig_for "$d/plugin.yaml" >"$d/plugin.yaml.sig"
  run_with_stderr "\"$GATE_SH\" --src \"$d\""
  [ "$status" -eq 0 ]
}

@test "valid sig file even when REQUIRE_SIG=1 → exit 0" {
  d="$(mk_src)"
  sig_for "$d/plugin.yaml" >"$d/plugin.yaml.sig"
  CODENOOK_REQUIRE_SIG=1 run_with_stderr "\"$GATE_SH\" --src \"$d\""
  [ "$status" -eq 0 ]
}

@test "tampered sig (wrong digest) → exit 1" {
  d="$(mk_src)"
  printf 'deadbeef\n' >"$d/plugin.yaml.sig"
  run_with_stderr "\"$GATE_SH\" --src \"$d\""
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" "mismatch"
}

@test "sig present but plugin.yaml missing → exit 1" {
  d="$(make_scratch)/p"; mkdir -p "$d"
  printf 'deadbeef\n' >"$d/plugin.yaml.sig"
  run_with_stderr "\"$GATE_SH\" --src \"$d\""
  [ "$status" -eq 1 ]
}

@test "--json envelope on tamper" {
  d="$(mk_src)"
  printf 'deadbeef\n' >"$d/plugin.yaml.sig"
  run "$GATE_SH" --src "$d" --json
  [ "$status" -eq 1 ]
  echo "$output" | jq -e '.gate == "plugin-signature" and .ok == false' >/dev/null
}

@test "happy path: fixtures/plugins/good-with-sig verifies → exit 0" {
  d="$FIXTURES_ROOT/plugins/good-with-sig"
  assert_file_exists "$d/plugin.yaml.sig"
  run_with_stderr "\"$GATE_SH\" --src \"$d\""
  [ "$status" -eq 0 ]
}
