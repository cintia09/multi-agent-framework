#!/usr/bin/env bats
# M8.1 Unit 3 — _lib/draft_config.py read/write/freeze helpers.

load helpers/load
load helpers/assertions

LIB_DIR="$CORE_ROOT/skills/builtin/_lib"
STATE_SCHEMA="$CORE_ROOT/schemas/task-state.schema.json"

py_helper() {
  PYTHONPATH="$LIB_DIR" python3 -c "$1"
}

@test "M8.1 draft_config module imports cleanly" {
  run py_helper "import draft_config as dc; print('OK')"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "M8.1 read_draft loads a valid draft" {
  d=$(make_scratch)
  run py_helper "
import draft_config as dc
dc.write_draft('$d/draft-config.yaml', {'plugin':'development','input':'do thing'})
got = dc.read_draft('$d/draft-config.yaml')
assert got['_draft'] is True
assert got['plugin'] == 'development'
assert got['input'] == 'do thing'
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "M8.1 write_draft rejects missing required fields (plugin)" {
  d=$(make_scratch)
  run py_helper "
import draft_config as dc
try:
    dc.write_draft('$d/draft-config.yaml', {'input':'do thing'})
    print('NO_RAISE')
except ValueError as e:
    print('OK', 'plugin' in str(e))
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK True"
}

@test "M8.1 write_draft rejects missing required fields (input)" {
  d=$(make_scratch)
  run py_helper "
import draft_config as dc
try:
    dc.write_draft('$d/draft-config.yaml', {'plugin':'development'})
    print('NO_RAISE')
except ValueError as e:
    print('OK', 'input' in str(e))
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK True"
}

@test "M8.1 write_draft always sets _draft: true even if caller omitted it" {
  d=$(make_scratch)
  run py_helper "
import draft_config as dc, yaml
dc.write_draft('$d/draft-config.yaml', {'plugin':'development','input':'x'})
raw = open('$d/draft-config.yaml').read()
assert '_draft: true' in raw, raw
parsed = yaml.safe_load(raw)
assert parsed['_draft'] is True
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "M8.1 write_draft overrides _draft=false back to true (invariant)" {
  d=$(make_scratch)
  run py_helper "
import draft_config as dc
dc.write_draft('$d/draft-config.yaml', {'_draft':False,'plugin':'development','input':'x'})
got = dc.read_draft('$d/draft-config.yaml')
assert got['_draft'] is True
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "M8.1 write_draft rejects literal model id (only tier symbols allowed)" {
  d=$(make_scratch)
  run py_helper "
import draft_config as dc
try:
    dc.write_draft('$d/draft-config.yaml', {'plugin':'development','input':'x','models':{'implementer':'gpt-5'}})
    print('NO_RAISE')
except ValueError as e:
    print('OK', 'tier_' in str(e))
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK True"
}

@test "M8.1 write_draft rejects models.router (decision #37)" {
  d=$(make_scratch)
  run py_helper "
import draft_config as dc
try:
    dc.write_draft('$d/draft-config.yaml', {'plugin':'development','input':'x','models':{'router':'tier_strong'}})
    print('NO_RAISE')
except ValueError as e:
    print('OK', 'router' in str(e))
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK True"
}

@test "M8.1 freeze_to_state_json strips _draft sentinels" {
  run py_helper "
import draft_config as dc
draft = {'_draft':True,'_draft_revision':3,'_draft_updated_at':'2026-05-12T10:13:18Z',
         'plugin':'development','input':'do thing','max_iterations':4}
seed = dc.freeze_to_state_json(draft, plugin='development', task_id='T-042')
for k in seed:
    assert not k.startswith('_draft'), k
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "M8.1 freeze_to_state_json output validates against M4 task-state schema" {
  run py_helper "
import sys, json
sys.path.insert(0, '$LIB_DIR')
import draft_config as dc
from jsonschema_lite import validate
draft = {'_draft':True,'plugin':'development','input':'do thing',
         'target_dir':'~/code/xueba/','dual_mode':False,'max_iterations':4,
         'models':{'implementer':'tier_strong'},
         'hitl_overrides':{'accept':'required'},
         'custom':{'test_runner':'pytest'}}
seed = dc.freeze_to_state_json(draft, plugin='development', task_id='T-042', now='2026-05-12T10:13:18Z')
with open('$STATE_SCHEMA') as h: schema = json.load(h)
validate(seed, schema)
assert seed['plugin'] == 'development'
assert seed['phase'] is None
assert seed['status'] == 'pending'
assert seed['max_iterations'] == 4
assert seed['dual_mode'] == 'serial'
assert seed['target_dir'] == '~/code/xueba/'
co = seed['config_overrides']
assert co['input'] == 'do thing'
assert co['models']['implementer'] == 'tier_strong'
assert co['hitl_overrides']['accept'] == 'required'
assert co['custom']['test_runner'] == 'pytest'
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "M8.1 freeze_to_state_json defaults max_iterations when draft omits it" {
  run py_helper "
import draft_config as dc
seed = dc.freeze_to_state_json({'_draft':True,'plugin':'development','input':'x'}, plugin='development', task_id='T-042')
assert seed['max_iterations'] == 8
assert seed['iteration'] == 0
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "M8.1 write_draft is atomic (no leftover .draft- tempfiles)" {
  d=$(make_scratch)
  run py_helper "
import draft_config as dc, os
for _ in range(20):
    dc.write_draft('$d/draft-config.yaml', {'plugin':'development','input':'x'})
leftovers = [n for n in os.listdir('$d') if n.startswith('.draft-')]
assert leftovers == [], leftovers
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

# ─── M8.10: selected_plugins + role_constraints ────────────────────────

@test "M8.10 write_draft accepts selected_plugins + role_constraints" {
  d=$(make_scratch)
  run py_helper "
import draft_config as dc
dc.write_draft('$d/draft-config.yaml', {
    'plugin':'development','input':'x',
    'selected_plugins':['development','generic'],
    'role_constraints':{'excluded':[{'plugin':'development','role':'validator'}]},
})
got = dc.read_draft('$d/draft-config.yaml')
assert got['selected_plugins'] == ['development','generic']
assert got['role_constraints']['excluded'][0]['plugin'] == 'development'
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "M8.10 write_draft rejects malformed role_constraints" {
  d=$(make_scratch)
  run py_helper "
import draft_config as dc
try:
    dc.write_draft('$d/draft-config.yaml', {'plugin':'development','input':'x',
        'role_constraints':{'excluded':[{'plugin':'development'}]}})
    print('NO_RAISE')
except ValueError as e:
    print('OK', 'role_constraints' in str(e))
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK True"
}

@test "M8.10 write_draft rejects non-string selected_plugins entries" {
  d=$(make_scratch)
  run py_helper "
import draft_config as dc
try:
    dc.write_draft('$d/draft-config.yaml', {'plugin':'development','input':'x',
        'selected_plugins':['development', 7]})
    print('NO_RAISE')
except ValueError as e:
    print('OK', 'selected_plugins' in str(e))
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK True"
}

@test "M8.10 freeze_to_state_json copies selected_plugins + role_constraints to state root" {
  run py_helper "
import sys, json
sys.path.insert(0, '$LIB_DIR')
import draft_config as dc
from jsonschema_lite import validate
draft = {'_draft':True,'plugin':'development','input':'x',
         'selected_plugins':['development','generic'],
         'role_constraints':{'excluded':[{'plugin':'development','role':'validator'}],
                             'included':[{'plugin':'generic','role':'executor'}]}}
seed = dc.freeze_to_state_json(draft, plugin='development', task_id='T-077')
assert seed['selected_plugins'] == ['development','generic']
assert seed['role_constraints']['excluded'][0]['role'] == 'validator'
assert seed['role_constraints']['included'][0]['role'] == 'executor'
# top-level, NOT under config_overrides
assert 'selected_plugins' not in seed.get('config_overrides', {})
assert 'role_constraints' not in seed.get('config_overrides', {})
with open('$STATE_SCHEMA') as h: schema = json.load(h)
validate(seed, schema)
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "M8.10 freeze_to_state_json omits role_constraints when not set" {
  run py_helper "
import draft_config as dc
seed = dc.freeze_to_state_json({'_draft':True,'plugin':'development','input':'x'},
                               plugin='development', task_id='T-001')
assert 'role_constraints' not in seed
assert 'selected_plugins' not in seed
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}
