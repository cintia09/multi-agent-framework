#!/usr/bin/env bats
# M8.10 — _lib/role_index.py: role enumeration + constraint filtering.

load helpers/load
load helpers/assertions

LIB_DIR="$CORE_ROOT/skills/builtin/_lib"

py_helper() {
  PYTHONPATH="$LIB_DIR" python3 -c "$1"
}

# Build a tiny synthetic plugins tree under $1.
mk_plugin() {
  local root="$1" plugin="$2" role="$3" phase="$4" job="$5"
  local d="$root/plugins/$plugin/roles"
  mkdir -p "$d"
  cat >"$d/$role.md" <<EOF
---
name: $role
plugin: $plugin
phase: $phase
manifest: phase-x-$role.md
one_line_job: "$job"
---

# $role

**One-line job:** $job

body
EOF
}

# Role file missing the frontmatter one_line_job (legacy).
mk_legacy_role() {
  local root="$1" plugin="$2" role="$3" phase="$4" job="$5"
  local d="$root/plugins/$plugin/roles"
  mkdir -p "$d"
  cat >"$d/$role.md" <<EOF
---
name: $role
plugin: $plugin
phase: $phase
manifest: phase-x-$role.md
---

# $role

**One-line job:** $job

body
EOF
}

@test "M8.10 role_index module imports cleanly" {
  run py_helper "import role_index as ri; print('OK')"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "M8.10 discover_roles parses frontmatter one_line_job" {
  d=$(make_scratch)
  mk_plugin "$d" "demo" "implementer" "implement" "Write code."
  mk_plugin "$d" "demo" "reviewer"    "review"    "Critique it."
  run py_helper "
from pathlib import Path
import role_index as ri
got = ri.discover_roles(Path('$d/plugins/demo'))
got_sorted = sorted(got, key=lambda r: r['role'])
assert len(got_sorted) == 2, got_sorted
assert got_sorted[0]['role'] == 'implementer'
assert got_sorted[0]['plugin'] == 'demo'
assert got_sorted[0]['phase'] == 'implement'
assert got_sorted[0]['manifest'] == 'phase-x-implementer.md'
assert got_sorted[0]['one_line_job'] == 'Write code.'
assert got_sorted[1]['one_line_job'] == 'Critique it.'
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "M8.10 discover_roles falls back to body One-line job line" {
  d=$(make_scratch)
  mk_legacy_role "$d" "demo" "implementer" "implement" "Body fallback wins."
  run py_helper "
from pathlib import Path
import role_index as ri
got = ri.discover_roles(Path('$d/plugins/demo'))
assert len(got) == 1, got
assert got[0]['one_line_job'] == 'Body fallback wins.', got[0]
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "M8.10 discover_roles tolerates missing one_line_job entirely" {
  d=$(make_scratch)
  mkdir -p "$d/plugins/demo/roles"
  cat >"$d/plugins/demo/roles/orphan.md" <<'EOF'
---
name: orphan
plugin: demo
phase: orphan
manifest: phase-x-orphan.md
---

no one-line job here at all
EOF
  run py_helper "
from pathlib import Path
import role_index as ri
got = ri.discover_roles(Path('$d/plugins/demo'))
assert len(got) == 1
assert got[0]['one_line_job'] == ''
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "M8.10 discover_roles returns [] when roles dir missing" {
  d=$(make_scratch)
  mkdir -p "$d/plugins/demo"
  run py_helper "
from pathlib import Path
import role_index as ri
assert ri.discover_roles(Path('$d/plugins/demo')) == []
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "M8.10 aggregate_roles groups by plugin name" {
  d=$(make_scratch)
  mk_plugin "$d" "alpha" "impl" "implement" "Alpha impl."
  mk_plugin "$d" "alpha" "rev"  "review"    "Alpha review."
  mk_plugin "$d" "beta"  "exec" "execute"   "Beta exec."
  run py_helper "
from pathlib import Path
import role_index as ri
got = ri.aggregate_roles(Path('$d'))
assert sorted(got.keys()) == ['alpha', 'beta'], got.keys()
assert len(got['alpha']) == 2
assert len(got['beta']) == 1
assert got['beta'][0]['one_line_job'] == 'Beta exec.'
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "M8.10 aggregate_roles returns empty dict when no plugins/ dir" {
  d=$(make_scratch)
  run py_helper "
from pathlib import Path
import role_index as ri
assert ri.aggregate_roles(Path('$d')) == {}
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "M8.10 filter_roles excluded-only acts as blacklist" {
  run py_helper "
import role_index as ri
roles = [
  {'plugin':'dev','role':'impl','phase':'i','manifest':'','one_line_job':''},
  {'plugin':'dev','role':'val', 'phase':'v','manifest':'','one_line_job':''},
]
out = ri.filter_roles(roles, {'excluded':[{'plugin':'dev','role':'val'}]})
assert [r['role'] for r in out] == ['impl'], out
# no mutation
assert len(roles) == 2
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "M8.10 filter_roles included-only acts as whitelist" {
  run py_helper "
import role_index as ri
roles = [
  {'plugin':'dev','role':'impl','phase':'i','manifest':'','one_line_job':''},
  {'plugin':'dev','role':'val', 'phase':'v','manifest':'','one_line_job':''},
  {'plugin':'dev','role':'rev', 'phase':'r','manifest':'','one_line_job':''},
]
out = ri.filter_roles(roles, {'included':[{'plugin':'dev','role':'impl'},{'plugin':'dev','role':'rev'}]})
assert sorted(r['role'] for r in out) == ['impl','rev'], out
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "M8.10 filter_roles included + excluded -> excluded subtracted from whitelist" {
  run py_helper "
import role_index as ri
roles = [
  {'plugin':'dev','role':'impl','phase':'i','manifest':'','one_line_job':''},
  {'plugin':'dev','role':'val', 'phase':'v','manifest':'','one_line_job':''},
  {'plugin':'dev','role':'rev', 'phase':'r','manifest':'','one_line_job':''},
]
out = ri.filter_roles(roles, {
    'included':[{'plugin':'dev','role':'impl'},{'plugin':'dev','role':'val'}],
    'excluded':[{'plugin':'dev','role':'val'}],
})
assert [r['role'] for r in out] == ['impl'], out
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "M8.10 filter_roles empty constraints is identity" {
  run py_helper "
import role_index as ri
roles = [{'plugin':'dev','role':'impl','phase':'i','manifest':'','one_line_job':''}]
assert ri.filter_roles(roles, {}) == roles
assert ri.filter_roles(roles, {'included':[],'excluded':[]}) == roles
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "M8.10 is_role_allowed truth table" {
  run py_helper "
import role_index as ri
assert ri.is_role_allowed('dev','impl', {}) is True
assert ri.is_role_allowed('dev','impl', {'included':[],'excluded':[]}) is True
# excluded only
assert ri.is_role_allowed('dev','val', {'excluded':[{'plugin':'dev','role':'val'}]}) is False
assert ri.is_role_allowed('dev','impl',{'excluded':[{'plugin':'dev','role':'val'}]}) is True
# included only (whitelist)
assert ri.is_role_allowed('dev','impl',{'included':[{'plugin':'dev','role':'impl'}]}) is True
assert ri.is_role_allowed('dev','val', {'included':[{'plugin':'dev','role':'impl'}]}) is False
# both: excluded wins for overlap
assert ri.is_role_allowed('dev','impl',{
    'included':[{'plugin':'dev','role':'impl'}],
    'excluded':[{'plugin':'dev','role':'impl'}],
}) is False
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}
