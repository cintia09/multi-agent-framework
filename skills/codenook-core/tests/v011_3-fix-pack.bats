#!/usr/bin/env bats
# v0.11.3 — round-1 fix-pack tests covering 11 E2E findings.
#
# Coverage map:
#   E2E-001 wrapper        → bats below (`.codenook/bin/codenook --help`,
#                                          `codenook task new`, `codenook chain link`)
#   E2E-002 router driver  → pytest skills/codenook-core/tests/test_router_host_driver.py
#   E2E-003 schemas        → bats below
#   E2E-005 tick malformed → pytest skills/codenook-core/tests/test_tick_malformed_output.py
#   E2E-006 entry-q enum   → pytest skills/codenook-core/tests/test_tick_entry_questions_meta.py
#   E2E-008 chain link     → bats below
#   E2E-009 extractor FM   → pytest skills/codenook-core/tests/test_extractor_frontmatter.py
#   E2E-016 idempotent     → bats below
#   E2E-017 marker linter  → pytest skills/codenook-core/tests/test_linter_marker_modes.py
#   E2E-018 memory seed    → bats below
#   E2E-019 state schema   → pytest skills/codenook-core/tests/test_workspace_state_schema.py

load helpers/load
load helpers/assertions

REPO_ROOT="$(cd "$CORE_ROOT/../.." && pwd)"
INSTALL_SH="$REPO_ROOT/install.sh"

setup() {
  ws="$(make_scratch)"
  bash "$INSTALL_SH" --plugin development "$ws" >/dev/null 2>&1 || {
    bash "$INSTALL_SH" --plugin development "$ws"
    return 1
  }
}

# ── E2E-001 ──────────────────────────────────────────────────────────────────
@test "[v0.11.3] E2E-001 .codenook/bin/codenook is executable post-install" {
  [ -x "$ws/.codenook/bin/codenook" ]
}

@test "[v0.11.3] E2E-001 codenook --help lists canonical workflow commands" {
  run "$ws/.codenook/bin/codenook" --help
  [ "$status" -eq 0 ]
  for cmd in "task new" "router" "tick" "decide" "status" "chain"; do
    [[ "$output" == *"codenook $cmd"* ]] || { echo "missing: $cmd"; echo "$output"; return 1; }
  done
}

@test "[v0.11.3] E2E-001 codenook task new creates task and returns ID" {
  run "$ws/.codenook/bin/codenook" task new --title "Hello"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  tid="$(echo "$output" | tr -d '[:space:]')"
  [[ "$tid" =~ ^T-[0-9]+$ ]]
  [ -f "$ws/.codenook/tasks/$tid/state.json" ]
  python3 -c "
import json
d=json.load(open('$ws/.codenook/tasks/$tid/state.json'))
assert d['title']=='Hello'
assert d['plugin']=='development'
assert d['status']=='in_progress'
"
}

# ── E2E-003 ──────────────────────────────────────────────────────────────────
@test "[v0.11.3] E2E-003 install seeds .codenook/schemas/ + state.example.md" {
  for f in task-state.schema.json installed.schema.json hitl-entry.schema.json queue-entry.schema.json; do
    [ -f "$ws/.codenook/schemas/$f" ] || { echo "missing: $f"; return 1; }
  done
  [ -f "$ws/.codenook/state.example.md" ]
}

# ── E2E-008 ──────────────────────────────────────────────────────────────────
@test "[v0.11.3] E2E-008 codenook chain link round-trip sets parent_id + chain_root" {
  child="$("$ws/.codenook/bin/codenook" task new --title "Child")"
  parent="$("$ws/.codenook/bin/codenook" task new --title "Parent")"
  run "$ws/.codenook/bin/codenook" chain link --child "$child" --parent "$parent"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  python3 -c "
import json
d=json.load(open('$ws/.codenook/tasks/$child/state.json'))
assert d.get('parent_id')=='$parent', d
# chain_root populated lazily — must equal parent (root of chain)
assert d.get('chain_root') in ('$parent', None), d.get('chain_root')
"
  # Verify show works.
  run "$ws/.codenook/bin/codenook" chain show "$child"
  [ "$status" -eq 0 ]
}

# ── E2E-016 ──────────────────────────────────────────────────────────────────
@test "[v0.11.3] E2E-016 second install.sh on identical workspace exits 0 (idempotent)" {
  run bash "$INSTALL_SH" --plugin development "$ws"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  [[ "$output" == *"already installed (idempotent)"* ]] || \
    [[ "$output" == *"IDEMPOTENT"* ]]
}

@test "[v0.11.3] E2E-016 install at different version without --upgrade exits 3" {
  # Forge a state.json with an older version pin.
  python3 -c "
import json
sj='$ws/.codenook/state.json'
d=json.load(open(sj))
for r in d['installed_plugins']:
    if r['id']=='development': r['version']='0.0.1'
json.dump(d, open(sj,'w'))
"
  run bash "$INSTALL_SH" --plugin development "$ws"
  [ "$status" -eq 3 ]
  [[ "$output" == *"--upgrade"* ]]
}

# ── E2E-018 ──────────────────────────────────────────────────────────────────
@test "[v0.11.3] E2E-018 install seeds .codenook/memory/ skeleton" {
  for sub in knowledge skills history _pending; do
    [ -f "$ws/.codenook/memory/$sub/.gitkeep" ] || { echo "missing: $sub"; return 1; }
  done
  [ -f "$ws/.codenook/memory/config.yaml" ]
  grep -q "entries: \[\]" "$ws/.codenook/memory/config.yaml"
}

@test "[v0.11.3] E2E-018 memory skeleton is idempotent (does not overwrite)" {
  echo "entries: [{topic: keep}]" > "$ws/.codenook/memory/config.yaml"
  run bash "$INSTALL_SH" --plugin development "$ws"
  [ "$status" -eq 0 ]
  grep -q "keep" "$ws/.codenook/memory/config.yaml"
}

# ── E2E-019 (workspace state.json schema) ───────────────────────────────────
@test "[v0.11.3] E2E-019 workspace state.json carries kernel_version + bin + files_sha256" {
  python3 -c "
import json
d=json.load(open('$ws/.codenook/state.json'))
assert d.get('schema_version')=='v1', d
assert d.get('kernel_version'), d
assert d.get('installed_at')
assert d.get('kernel_dir')
assert d.get('bin')=='.codenook/bin/codenook', d
assert d['installed_plugins'][0].get('version'), d
assert d['installed_plugins'][0].get('files_sha256'), d
"
}
