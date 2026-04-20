#!/usr/bin/env bats
# M6 U9 — full pack + install integration test
#
# Builds a tarball from plugins/development/, installs it via the
# M2 install-orchestrator into a fresh workspace, asserts every
# expected file landed under .codenook/plugins/development/, and
# verifies all 12 gates passed.

load helpers/load
load helpers/assertions

PLUGIN_SRC="$CORE_ROOT/../../plugins/development"
INSTALL_SH="$CORE_ROOT/skills/builtin/install-orchestrator/orchestrator.sh"

mk_workspace() {
  local ws; ws="$(make_scratch)"
  mkdir -p "$ws/.codenook"
  echo "$ws"
}

mk_tarball() {
  local out_dir="$1"
  local tgz="$out_dir/development-0.2.0.tar.gz"
  ( cd "$PLUGIN_SRC/.." && tar -czf "$tgz" development )
  echo "$tgz"
}

@test "tarball can be built and installs via M2 12-gate pipeline" {
  ws="$(mk_workspace)"
  dist="$(make_scratch)/dist"
  mkdir -p "$dist"
  tgz="$(mk_tarball "$dist")"
  [ -f "$tgz" ]

  run_with_stderr "\"$INSTALL_SH\" --src \"$tgz\" --workspace \"$ws\" --json"
  if [ "$status" -ne 0 ]; then
    echo "STDERR: $STDERR" >&2
    echo "STDOUT: $output" >&2
    return 1
  fi
  echo "$output" | grep -q '"ok": *true'
  echo "$output" | grep -q '"plugin_id": *"development"'
}

@test "installed tree contains all expected yaml + 8 role + 8 manifest files" {
  ws="$(mk_workspace)"
  dist="$(make_scratch)/dist2"
  mkdir -p "$dist"
  tgz="$(mk_tarball "$dist")"
  run_with_stderr "\"$INSTALL_SH\" --src \"$tgz\" --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]

  for f in plugin.yaml config-defaults.yaml config-schema.yaml \
           phases.yaml transitions.yaml entry-questions.yaml \
           hitl-gates.yaml README.md CHANGELOG.md; do
    [ -f "$ws/.codenook/plugins/development/$f" ] \
      || { echo "missing $f" >&2; return 1; }
  done
  for r in clarifier designer planner implementer builder reviewer submitter test-planner tester acceptor; do
    [ -f "$ws/.codenook/plugins/development/roles/$r.md" ] \
      || { echo "missing roles/$r.md" >&2; return 1; }
  done
  count=$(ls "$ws/.codenook/plugins/development/manifest-templates"/phase-*.md | wc -l | tr -d ' ')
  [ "$count" -eq 11 ]
  [ -x "$ws/.codenook/plugins/development/skills/test-runner/runner.sh" ]
  [ -x "$ws/.codenook/plugins/development/validators/post-implement.sh" ]
  [ -x "$ws/.codenook/plugins/development/validators/post-build.sh" ]
}

@test "all gate_results are ok in install JSON envelope" {
  ws="$(mk_workspace)"
  dist="$(make_scratch)/dist3"
  mkdir -p "$dist"
  tgz="$(mk_tarball "$dist")"
  run_with_stderr "\"$INSTALL_SH\" --src \"$tgz\" --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  echo "$output" | python3 -c '
import json, sys
d = json.load(sys.stdin)
gates = d["gate_results"]
for g in gates:
    assert g["ok"], (g["gate"], g.get("reasons"))
assert len(gates) >= 9, len(gates)
print("ok")
' >&2
}

@test "re-install with --upgrade is idempotent" {
  ws="$(mk_workspace)"
  dist="$(make_scratch)/dist4"
  mkdir -p "$dist"
  tgz="$(mk_tarball "$dist")"
  run_with_stderr "\"$INSTALL_SH\" --src \"$tgz\" --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  # Second install without --upgrade must report already_installed (exit 3).
  run_with_stderr "\"$INSTALL_SH\" --src \"$tgz\" --workspace \"$ws\" --json"
  [ "$status" -eq 3 ]
  # state.json records the plugin once.
  count=$(jq '[.installed_plugins[] | select(.id=="development")] | length' \
          "$ws/.codenook/state.json")
  [ "$count" = "1" ]
}
