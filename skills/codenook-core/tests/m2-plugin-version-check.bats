#!/usr/bin/env bats
# M2 Unit 4 — plugin-version-check (G04)
#
# Contract:
#   version-check.sh --src <dir> [--workspace <dir>] [--upgrade] [--json]
#
# Checks:
#   - plugin.yaml.version is valid SemVer (X.Y.Z[-pre][+build])
#   - if --upgrade && existing install at <ws>/.codenook/plugins/<id>/:
#       new version MUST be strictly > installed version

load helpers/load
load helpers/assertions

GATE_SH="$CORE_ROOT/skills/builtin/plugin-version-check/version-check.sh"

mk_src() {
  local d id ver; id="$1"; ver="$2"
  d="$(make_scratch)/p"; mkdir -p "$d"
  printf 'id: %s\nversion: %s\n' "$id" "$ver" >"$d/plugin.yaml"
  echo "$d"
}

mk_ws_with_installed() {
  local id ver d; id="$1"; ver="$2"
  d="$(make_scratch)/ws"
  mkdir -p "$d/.codenook/plugins/$id"
  printf 'id: %s\nversion: %s\n' "$id" "$ver" >"$d/.codenook/plugins/$id/plugin.yaml"
  echo "$d"
}

@test "version-check.sh exists and executable" {
  assert_file_exists "$GATE_SH"
  assert_file_executable "$GATE_SH"
}

@test "valid semver 1.2.3 → exit 0" {
  d="$(mk_src "foo" "1.2.3")"
  run_with_stderr "\"$GATE_SH\" --src \"$d\""
  [ "$status" -eq 0 ]
}

@test "valid semver with pre-release 1.0.0-rc.1 → exit 0" {
  d="$(mk_src "foo" "1.0.0-rc.1")"
  run_with_stderr "\"$GATE_SH\" --src \"$d\""
  [ "$status" -eq 0 ]
}

@test "invalid version 'v1.2' → exit 1" {
  d="$(mk_src "foo" "v1.2")"
  run_with_stderr "\"$GATE_SH\" --src \"$d\""
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" "semver"
}

@test "invalid version '1.2' (only 2 parts) → exit 1" {
  d="$(mk_src "foo" "1.2")"
  run_with_stderr "\"$GATE_SH\" --src \"$d\""
  [ "$status" -eq 1 ]
}

@test "--upgrade with new > installed → exit 0" {
  d="$(mk_src "foo" "1.2.0")"
  ws="$(mk_ws_with_installed "foo" "1.1.5")"
  run_with_stderr "\"$GATE_SH\" --src \"$d\" --workspace \"$ws\" --upgrade"
  [ "$status" -eq 0 ]
}

@test "--upgrade with new == installed and matching fingerprint → exit 1" {
  d="$(mk_src "foo" "1.1.5")"
  ws="$(mk_ws_with_installed "foo" "1.1.5")"
  # T-006: G04 only vetoes same-version when staged .fingerprint matches
  # source.  Compute and stamp the source fingerprint into the staged
  # tree to simulate the idempotent fast-path.
  fp="$(python3 - <<PY
import sys
sys.path.insert(0, "${CORE_ROOT}/_lib/install")
from stage_kernel import _compute_tree_fingerprint
from pathlib import Path
print(_compute_tree_fingerprint(Path("${d}")))
PY
)"
  printf '%s\n' "$fp" >"$ws/.codenook/plugins/foo/.fingerprint"
  run_with_stderr "\"$GATE_SH\" --src \"$d\" --workspace \"$ws\" --upgrade"
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" "downgrade"
}

@test "--upgrade with new == installed and missing fingerprint → exit 0 (restage)" {
  d="$(mk_src "foo" "1.1.5")"
  ws="$(mk_ws_with_installed "foo" "1.1.5")"
  # T-006: missing .fingerprint is treated as stale → allow restage so
  # dev-loop edits to plugin source land without a version bump.
  run_with_stderr "\"$GATE_SH\" --src \"$d\" --workspace \"$ws\" --upgrade"
  [ "$status" -eq 0 ]
}

@test "--upgrade with new < installed → exit 1 (downgrade)" {
  d="$(mk_src "foo" "1.0.0")"
  ws="$(mk_ws_with_installed "foo" "1.1.5")"
  run_with_stderr "\"$GATE_SH\" --src \"$d\" --workspace \"$ws\" --upgrade"
  [ "$status" -eq 1 ]
}

@test "--json envelope on success" {
  d="$(mk_src "foo" "1.2.3")"
  run "$GATE_SH" --src "$d" --json
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.gate == "plugin-version-check" and .ok == true' >/dev/null
}
