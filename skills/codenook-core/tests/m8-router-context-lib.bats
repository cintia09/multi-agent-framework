#!/usr/bin/env bats
# M8.1 Unit 2 — _lib/router_context.py read/write/append helpers.

load helpers/load
load helpers/assertions

LIB_DIR="$CORE_ROOT/skills/builtin/_lib"
FX="$FIXTURES_ROOT/m8"

# Run the helper from a scratch dir; capture stdout for assertions.
py_helper() {
  local script="$1"
  PYTHONPATH="$LIB_DIR" python3 -c "$script"
}

@test "M8.1 router_context module imports cleanly" {
  run py_helper "import router_context as rc; print('OK', rc.CONTEXT_FILENAME)"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK router-context.md"
}

@test "M8.1 initial_context produces valid frontmatter and one user turn" {
  run py_helper "
import router_context as rc, json
fm, turns = rc.initial_context('T-042', 'hello world', now='2026-05-12T10:00:00Z')
assert fm['task_id'] == 'T-042'
assert fm['state'] == 'drafting'
assert fm['turn_count'] == 1
assert fm['draft_config_path'] is None
assert fm['selected_plugin'] is None
assert fm['decisions'] == []
assert len(turns) == 1
assert turns[0] == {'role':'user','timestamp':'2026-05-12T10:00:00Z','content':'hello world'}
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "M8.1 read_context round-trips the canonical fixture file" {
  d=$(make_scratch)
  cp "$FX/router-context.md" "$d/router-context.md"
  run py_helper "
import router_context as rc
ctx = rc.read_context('$d')
fm = ctx['frontmatter']; turns = ctx['turns']
assert fm['task_id'] == 'T-042'
assert fm['state'] == 'drafting'
assert fm['turn_count'] == 2
assert fm['selected_plugin'] == 'development'
assert len(fm['decisions']) == 2
assert len(turns) == 3
assert turns[0]['role'] == 'user' and turns[0]['timestamp'] == '2026-05-12T10:11:00Z'
assert turns[1]['role'] == 'router'
assert turns[2]['role'] == 'user' and turns[2]['content'] == 'Yes to both.'
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "M8.1 write_context then read_context preserves frontmatter and turns" {
  d=$(make_scratch)
  run py_helper "
import router_context as rc
fm, turns = rc.initial_context('T-100', 'first message', now='2026-05-12T10:00:00Z')
rc.write_context('$d', fm, turns)
got = rc.read_context('$d')
assert got['frontmatter'] == fm
assert got['turns'] == turns
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "M8.1 append_turn user increments turn_count and records the body" {
  d=$(make_scratch)
  run py_helper "
import router_context as rc
fm, turns = rc.initial_context('T-100', 'q1', now='2026-05-12T10:00:00Z')
rc.write_context('$d', fm, turns)
rc.append_turn('$d', 'router', 'a1', timestamp='2026-05-12T10:00:05Z')
rc.append_turn('$d', 'user',   'q2', timestamp='2026-05-12T10:00:10Z')
ctx = rc.read_context('$d')
assert ctx['frontmatter']['turn_count'] == 2, ctx['frontmatter']['turn_count']
roles = [t['role'] for t in ctx['turns']]
assert roles == ['user','router','user'], roles
assert ctx['turns'][-1]['content'] == 'q2'
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "M8.1 append_turn router does NOT increment turn_count" {
  d=$(make_scratch)
  run py_helper "
import router_context as rc
fm, turns = rc.initial_context('T-100', 'q1', now='2026-05-12T10:00:00Z')
rc.write_context('$d', fm, turns)
rc.append_turn('$d', 'router', 'a1', timestamp='2026-05-12T10:00:05Z')
rc.append_turn('$d', 'router', 'a1b', timestamp='2026-05-12T10:00:06Z')
ctx = rc.read_context('$d')
assert ctx['frontmatter']['turn_count'] == 1
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "M8.1 update_frontmatter merges keys and persists" {
  d=$(make_scratch)
  run py_helper "
import router_context as rc
fm, turns = rc.initial_context('T-100', 'q1', now='2026-05-12T10:00:00Z')
rc.write_context('$d', fm, turns)
rc.update_frontmatter('$d', selected_plugin='development', last_router_action='reply')
got = rc.read_context('$d')['frontmatter']
assert got['selected_plugin'] == 'development'
assert got['last_router_action'] == 'reply'
assert got['task_id'] == 'T-100'   # unchanged
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "M8.1 invalid state enum is rejected with ValueError" {
  d=$(make_scratch)
  run py_helper "
import router_context as rc
fm, turns = rc.initial_context('T-100', 'q1', now='2026-05-12T10:00:00Z')
rc.write_context('$d', fm, turns)
try:
    rc.update_frontmatter('$d', state='garbage')
    print('NO_RAISE')
except ValueError as e:
    print('OK', 'state' in str(e) and 'garbage' in str(e))
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK True"
}

@test "M8.1 missing required frontmatter key is rejected" {
  d=$(make_scratch)
  run py_helper "
import router_context as rc
fm, turns = rc.initial_context('T-100', 'q1', now='2026-05-12T10:00:00Z')
del fm['task_id']
try:
    rc.write_context('$d', fm, turns)
    print('NO_RAISE')
except ValueError as e:
    print('OK', 'task_id' in str(e))
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK True"
}

@test "M8.1 invalid task_id pattern is rejected" {
  d=$(make_scratch)
  run py_helper "
import router_context as rc
try:
    rc.initial_context('not-a-task', 'q1', now='2026-05-12T10:00:00Z')
    print('NO_RAISE')
except ValueError as e:
    print('OK', 'task_id' in str(e))
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK True"
}

@test "M8.1 write_context is atomic (no leftover .rctx- tempfiles)" {
  d=$(make_scratch)
  run py_helper "
import router_context as rc, os
fm, turns = rc.initial_context('T-100', 'q1', now='2026-05-12T10:00:00Z')
for _ in range(20):
    rc.write_context('$d', fm, turns)
leftovers = [n for n in os.listdir('$d') if n.startswith('.rctx-')]
assert leftovers == [], leftovers
assert os.path.isfile('$d/router-context.md')
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "M8.1 write_context truncation: tempfile cleaned up on validation failure" {
  d=$(make_scratch)
  run py_helper "
import router_context as rc, os
fm, turns = rc.initial_context('T-100', 'q1', now='2026-05-12T10:00:00Z')
fm['state'] = 'garbage'
try:
    rc.write_context('$d', fm, turns)
except ValueError:
    pass
files = sorted(os.listdir('$d'))
assert files == [] or files == ['router-context.md'], files
leftovers = [n for n in os.listdir('$d') if n.startswith('.rctx-')]
assert leftovers == []
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}
