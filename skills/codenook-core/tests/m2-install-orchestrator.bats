#!/usr/bin/env bats
# M2 Unit 10 — install-orchestrator + install.sh
#
# CLI:
#   install.sh --src <tarball|dir> [--upgrade] [--dry-run]
#              [--workspace <dir>] [--json]
#
# Exit codes:
#   0  installed (or dry-run pass)
#   1  gate failure (any of G01..G11 + sec-audit + size)
#   2  usage error
#   3  already installed (without --upgrade) — distinct so wrappers
#      can ask "did you mean --upgrade?"

load helpers/load
load helpers/assertions

INSTALL_SH="$CORE_ROOT/install.sh"

# ---------- fixture builders ----------

mk_minimal_good() {
  local d
  d="$(make_scratch)/good-minimal"
  mkdir -p "$d/skills/x"
  cat >"$d/plugin.yaml" <<'YAML'
id: foo-plugin
version: 0.2.0
type: domain
entry_points:
  install: skills/x/run.sh
declared_subsystems:
  - skills/foo-runner
requires:
  core_version: '>=0.2.0-m2'
YAML
  cat >"$d/skills/x/run.sh" <<'SH'
#!/usr/bin/env bash
echo "hello"
SH
  chmod +x "$d/skills/x/run.sh"
  echo "$d"
}

mk_ws() {
  local d; d="$(make_scratch)/ws"
  mkdir -p "$d/.codenook"
  echo "$d"
}

mutate_yaml() {
  # mutate_yaml <plugin-dir> <python-snippet operating on `d` (dict)>
  local d="$1"; local snippet="$2"
  python3 - "$d" <<PY
import sys, yaml
from pathlib import Path
p = Path(sys.argv[1]) / "plugin.yaml"
d = yaml.safe_load(p.read_text())
${snippet}
p.write_text(yaml.safe_dump(d, sort_keys=False))
PY
}

# ---------- tests ----------

@test "install.sh exists and executable" {
  assert_file_exists "$INSTALL_SH"
  assert_file_executable "$INSTALL_SH"
}

@test "missing --src → exit 2" {
  run_with_stderr "\"$INSTALL_SH\""
  [ "$status" -eq 2 ]
}

@test "happy path: dir source → exit 0, plugin installed" {
  src="$(mk_minimal_good)"; ws="$(mk_ws)"
  run_with_stderr "\"$INSTALL_SH\" --src \"$src\" --workspace \"$ws\""
  [ "$status" -eq 0 ]
  assert_file_exists "$ws/.codenook/plugins/foo-plugin/plugin.yaml"
}

@test "happy path: tarball source → exit 0" {
  src="$(mk_minimal_good)"; ws="$(mk_ws)"
  tar -C "$(dirname "$src")" -czf "$src.tar.gz" "$(basename "$src")"
  run_with_stderr "\"$INSTALL_SH\" --src \"$src.tar.gz\" --workspace \"$ws\""
  [ "$status" -eq 0 ]
  assert_file_exists "$ws/.codenook/plugins/foo-plugin/plugin.yaml"
}

@test "--dry-run: passes gates but does NOT install" {
  src="$(mk_minimal_good)"; ws="$(mk_ws)"
  run_with_stderr "\"$INSTALL_SH\" --src \"$src\" --workspace \"$ws\" --dry-run"
  [ "$status" -eq 0 ]
  [ ! -e "$ws/.codenook/plugins/foo-plugin" ]
}

@test "G01 fail — no plugin.yaml" {
  src="$(make_scratch)/no-yaml"; mkdir -p "$src"
  echo readme >"$src/README.md"
  ws="$(mk_ws)"
  run_with_stderr "\"$INSTALL_SH\" --src \"$src\" --workspace \"$ws\""
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" "G01"
}

@test "G02 fail — yaml missing required field" {
  src="$(mk_minimal_good)"
  mutate_yaml "$src" "del d['type']"
  ws="$(mk_ws)"
  run_with_stderr "\"$INSTALL_SH\" --src \"$src\" --workspace \"$ws\""
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" "G02"
}

@test "G03 fail — uppercase id" {
  src="$(mk_minimal_good)"
  mutate_yaml "$src" "d['id'] = 'BadID'"
  ws="$(mk_ws)"
  run_with_stderr "\"$INSTALL_SH\" --src \"$src\" --workspace \"$ws\""
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" "G03"
}

@test "G04 fail — bad semver" {
  src="$(mk_minimal_good)"
  mutate_yaml "$src" "d['version'] = 'v1'"
  ws="$(mk_ws)"
  run_with_stderr "\"$INSTALL_SH\" --src \"$src\" --workspace \"$ws\""
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" "G04"
}

@test "G05 fail — REQUIRE_SIG=1 but no sig" {
  src="$(mk_minimal_good)"; ws="$(mk_ws)"
  CODENOOK_REQUIRE_SIG=1 run_with_stderr "\"$INSTALL_SH\" --src \"$src\" --workspace \"$ws\""
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" "G05"
}

@test "G06 fail — deps too old" {
  src="$(mk_minimal_good)"
  mutate_yaml "$src" "d['requires'] = {'core_version': '>=99.0.0'}"
  ws="$(mk_ws)"
  run_with_stderr "\"$INSTALL_SH\" --src \"$src\" --workspace \"$ws\""
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" "G06"
}

@test "G07 fail — subsystem collision" {
  src="$(mk_minimal_good)"; ws="$(mk_ws)"
  # pre-install another plugin claiming the same subsystem
  mkdir -p "$ws/.codenook/plugins/peer"
  cat >"$ws/.codenook/plugins/peer/plugin.yaml" <<'YAML'
id: peer
version: 0.1.0
type: domain
entry_points: {install: x.sh}
declared_subsystems: [skills/foo-runner]
YAML
  run_with_stderr "\"$INSTALL_SH\" --src \"$src\" --workspace \"$ws\""
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" "G07"
}

@test "G08 fail — embedded secret (sec-audit)" {
  src="$(mk_minimal_good)"
  printf 'API=sk-proj-abcdefghij0123456789ABCDEFGHIJklmnopqr\n' >"$src/leak.txt"
  ws="$(mk_ws)"
  run_with_stderr "\"$INSTALL_SH\" --src \"$src\" --workspace \"$ws\""
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" "G08"
}

@test "G09 fail — file >1MB" {
  src="$(mk_minimal_good)"
  python3 -c "open('$src/big.bin','wb').write(b'x'*1500000)"
  ws="$(mk_ws)"
  run_with_stderr "\"$INSTALL_SH\" --src \"$src\" --workspace \"$ws\""
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" "G09"
}

@test "G10 fail — perl shebang" {
  src="$(mk_minimal_good)"
  printf '#!/usr/bin/perl\nprint "x";\n' >"$src/skills/x/run.sh"
  chmod +x "$src/skills/x/run.sh"
  ws="$(mk_ws)"
  run_with_stderr "\"$INSTALL_SH\" --src \"$src\" --workspace \"$ws\""
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" "G10"
}

@test "G11 fail — yaml has .. traversal" {
  src="$(mk_minimal_good)"
  mutate_yaml "$src" "d['entry_points']['install'] = '../escape.sh'"
  ws="$(mk_ws)"
  run_with_stderr "\"$INSTALL_SH\" --src \"$src\" --workspace \"$ws\""
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" "G11"
}

@test "--upgrade: install over existing → exit 0" {
  src1="$(mk_minimal_good)"
  ws="$(mk_ws)"
  run_with_stderr "\"$INSTALL_SH\" --src \"$src1\" --workspace \"$ws\""
  [ "$status" -eq 0 ]
  src2="$(mk_minimal_good)"
  mutate_yaml "$src2" "d['version'] = '0.3.0'"
  run_with_stderr "\"$INSTALL_SH\" --src \"$src2\" --workspace \"$ws\" --upgrade"
  [ "$status" -eq 0 ]
  grep -q '0.3.0' "$ws/.codenook/plugins/foo-plugin/plugin.yaml"
}

@test "--upgrade refuses downgrade" {
  src1="$(mk_minimal_good)"
  mutate_yaml "$src1" "d['version'] = '0.5.0'"
  ws="$(mk_ws)"
  run_with_stderr "\"$INSTALL_SH\" --src \"$src1\" --workspace \"$ws\""
  [ "$status" -eq 0 ]
  src2="$(mk_minimal_good)"  # version 0.2.0
  run_with_stderr "\"$INSTALL_SH\" --src \"$src2\" --workspace \"$ws\" --upgrade"
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" "G04"
}

@test "already installed without --upgrade → exit 3" {
  src1="$(mk_minimal_good)"
  ws="$(mk_ws)"
  run_with_stderr "\"$INSTALL_SH\" --src \"$src1\" --workspace \"$ws\""
  [ "$status" -eq 0 ]
  src2="$(mk_minimal_good)"
  run_with_stderr "\"$INSTALL_SH\" --src \"$src2\" --workspace \"$ws\""
  [ "$status" -eq 3 ]
  assert_contains "$STDERR" "already installed"
}

@test "happy path records to state.json.installed_plugins" {
  src="$(mk_minimal_good)"; ws="$(mk_ws)"
  run_with_stderr "\"$INSTALL_SH\" --src \"$src\" --workspace \"$ws\""
  [ "$status" -eq 0 ]
  assert_file_exists "$ws/.codenook/state.json"
  jq -e '.installed_plugins[] | select(.id=="foo-plugin" and .version=="0.2.0")' \
    "$ws/.codenook/state.json" >/dev/null
}

@test "--json mode emits machine-readable summary on success" {
  src="$(mk_minimal_good)"; ws="$(mk_ws)"
  run "$INSTALL_SH" --src "$src" --workspace "$ws" --json
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.ok == true and .plugin_id == "foo-plugin"' >/dev/null
}

@test "--json mode emits failure summary listing failed gate(s)" {
  src="$(mk_minimal_good)"
  mutate_yaml "$src" "d['version'] = 'v1'"
  ws="$(mk_ws)"
  run "$INSTALL_SH" --src "$src" --workspace "$ws" --json
  [ "$status" -eq 1 ]
  echo "$output" | jq -e '.ok == false and ([.gate_results[] | select(.ok==false)] | length) >= 1' >/dev/null
}

@test "staging area is cleaned up on success" {
  src="$(mk_minimal_good)"; ws="$(mk_ws)"
  run_with_stderr "\"$INSTALL_SH\" --src \"$src\" --workspace \"$ws\""
  [ "$status" -eq 0 ]
  if [ -d "$ws/.codenook/staging" ]; then
    n=$(find "$ws/.codenook/staging" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')
    [ "$n" -eq 0 ]
  fi
}
