#!/usr/bin/env bats
# M8.9 — _lib/workspace_overlay.py: workspace user-overlay layer.

load helpers/load
load helpers/assertions

LIB_DIR="$CORE_ROOT/skills/builtin/_lib"

py_helper() {
  local script="$1"
  PYTHONPATH="$LIB_DIR" python3 -c "$script"
}

@test "M8.9 workspace_overlay module imports cleanly" {
  run py_helper "import workspace_overlay as wo; print('OK', wo.overlay_root('/tmp/x').name)"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK user-overlay"
}

@test "M8.9 has_overlay false on bare workspace, true once dir exists" {
  d=$(make_scratch)
  run py_helper "
import workspace_overlay as wo, os
assert wo.has_overlay('$d') is False
os.makedirs('$d/.codenook/user-overlay')
assert wo.has_overlay('$d') is True
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "M8.9 read_description returns empty when missing, contents when present" {
  d=$(make_scratch)
  mkdir -p "$d/.codenook/user-overlay"
  run py_helper "
import workspace_overlay as wo
assert wo.read_description('$d') == ''
print('OK1')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK1"
  printf 'Project context line.\n' > "$d/.codenook/user-overlay/description.md"
  run py_helper "
import workspace_overlay as wo
got = wo.read_description('$d')
assert got == 'Project context line.\n', repr(got)
print('OK2')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK2"
}

@test "M8.9 read_config missing returns empty dict, valid yaml parses, malformed raises" {
  d=$(make_scratch)
  mkdir -p "$d/.codenook/user-overlay"
  run py_helper "
import workspace_overlay as wo
assert wo.read_config('$d') == {}
print('OK1')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK1"
  cat > "$d/.codenook/user-overlay/config.yaml" <<'YAML'
plugin: development
max_iterations: 5
YAML
  run py_helper "
import workspace_overlay as wo
cfg = wo.read_config('$d')
assert cfg == {'plugin': 'development', 'max_iterations': 5}, cfg
print('OK2')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK2"
  printf '::: not yaml :::\n  - [\n' > "$d/.codenook/user-overlay/config.yaml"
  run py_helper "
import workspace_overlay as wo
try:
    wo.read_config('$d')
    print('NO_RAISE')
except ValueError as e:
    msg = str(e)
    print('OK3', 'config.yaml' in msg)
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK3 True"
}

@test "M8.9 discover_overlay_skills empty returns [], populated returns entries" {
  d=$(make_scratch)
  mkdir -p "$d/.codenook/user-overlay/skills"
  run py_helper "
import workspace_overlay as wo
assert wo.discover_overlay_skills('$d') == []
print('OK1')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK1"
  mkdir -p "$d/.codenook/user-overlay/skills/alpha" "$d/.codenook/user-overlay/skills/beta"
  printf '# Alpha skill\n' > "$d/.codenook/user-overlay/skills/alpha/SKILL.md"
  run py_helper "
import workspace_overlay as wo
got = wo.discover_overlay_skills('$d')
got = sorted(got, key=lambda x: x['name'])
assert len(got) == 2, got
assert got[0]['name'] == 'alpha' and got[0]['has_skill_md'] is True
assert got[1]['name'] == 'beta'  and got[1]['has_skill_md'] is False
assert str(got[0]['path']).endswith('/skills/alpha')
print('OK2')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK2"
}

@test "M8.9 discover_overlay_knowledge handles frontmatter and bare files" {
  d=$(make_scratch)
  mkdir -p "$d/.codenook/user-overlay/knowledge"
  cat > "$d/.codenook/user-overlay/knowledge/with-fm.md" <<'MD'
---
title: Project Style
summary: How we write here.
tags: [style, docs]
---
Body content.
MD
  printf '# Bare file\n\nNo frontmatter at all.\n' > "$d/.codenook/user-overlay/knowledge/bare.md"
  run py_helper "
import workspace_overlay as wo
got = sorted(wo.discover_overlay_knowledge('$d'), key=lambda x: x['path'])
assert len(got) == 2, got
by_name = {p['path'].rsplit('/',1)[-1]: p for p in got}
fm = by_name['with-fm.md']
assert fm['title'] == 'Project Style'
assert fm['summary'] == 'How we write here.'
assert fm['tags'] == ['style', 'docs']
bare = by_name['bare.md']
assert bare['title'] == 'bare', bare
assert bare['summary'] == ''
assert bare['tags'] == []
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "M8.9 overlay_bundle absent returns present=False with empty fields" {
  d=$(make_scratch)
  run py_helper "
import workspace_overlay as wo
b = wo.overlay_bundle('$d')
assert b == {'present': False, 'description': '', 'config': {}, 'skills': [], 'knowledge': []}, b
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "M8.9 overlay_bundle present aggregates all four assets" {
  d=$(make_scratch)
  mkdir -p "$d/.codenook/user-overlay/skills/s1" "$d/.codenook/user-overlay/knowledge"
  printf 'Workspace context.\n' > "$d/.codenook/user-overlay/description.md"
  printf 'plugin: writing\n'   > "$d/.codenook/user-overlay/config.yaml"
  printf '# s1\n'              > "$d/.codenook/user-overlay/skills/s1/SKILL.md"
  printf '# topic\n'           > "$d/.codenook/user-overlay/knowledge/topic.md"
  run py_helper "
import workspace_overlay as wo
b = wo.overlay_bundle('$d')
assert b['present'] is True
assert b['description'] == 'Workspace context.\n'
assert b['config'] == {'plugin': 'writing'}
assert len(b['skills']) == 1 and b['skills'][0]['name'] == 's1'
assert len(b['knowledge']) == 1 and b['knowledge'][0]['title'] == 'topic'
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "M8.9 merge_config_into_draft overlay overrides draft, inputs not mutated" {
  run py_helper "
import workspace_overlay as wo
draft = {'plugin': 'generic', 'max_iterations': 8, 'input': 'hi'}
overlay = {'plugin': 'development', 'extra': True}
merged = wo.merge_config_into_draft(draft, overlay)
assert merged == {'plugin': 'development', 'max_iterations': 8, 'input': 'hi', 'extra': True}, merged
assert draft   == {'plugin': 'generic', 'max_iterations': 8, 'input': 'hi'}
assert overlay == {'plugin': 'development', 'extra': True}
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "M8.9 merge_config_into_draft empty cases" {
  run py_helper "
import workspace_overlay as wo
draft = {'plugin': 'generic'}
assert wo.merge_config_into_draft(draft, {}) == draft
assert wo.merge_config_into_draft(draft, None) == draft
assert wo.merge_config_into_draft({}, draft) == draft
assert wo.merge_config_into_draft(None, draft) == draft
assert wo.merge_config_into_draft({}, {}) == {}
assert wo.merge_config_into_draft(None, None) == {}
# returned dicts must be fresh
m = wo.merge_config_into_draft(draft, {})
m['plugin'] = 'mutated'
assert draft['plugin'] == 'generic'
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}
