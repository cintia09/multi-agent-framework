#!/usr/bin/env bats
# M8.3 — plugin_manifest_index.py + knowledge_index.py discovery helpers.

load helpers/load
load helpers/assertions

LIB_DIR="$CORE_ROOT/skills/builtin/_lib"

py_helper() {
  local script="$1"
  PYTHONPATH="$LIB_DIR" python3 -c "$script"
}

# Build a fake workspace with three plugins, exercising the routing
# index, manifest summary, and knowledge frontmatter behaviour.
make_fake_workspace() {
  local d="$1"
  mkdir -p "$d/plugins/development/knowledge"
  mkdir -p "$d/plugins/writing/knowledge"
  mkdir -p "$d/plugins/generic/knowledge"
  mkdir -p "$d/plugins/empty"

  cat >"$d/plugins/development/plugin.yaml" <<'YAML'
id: development
name: development
summary: Software development pipeline.
applies_to: [code, software-engineering]
routing:
  priority: 50
  keywords:
    - python
    - refactor
    - PYTHON
    - cli
YAML

  cat >"$d/plugins/writing/plugin.yaml" <<'YAML'
id: writing
name: writing
summary: |
  Long-form authoring
  pipeline.
applies_to: [content, writing]
routing:
  priority: 50
  keywords:
    - article
    - blog
    - newsletter
YAML

  cat >"$d/plugins/generic/plugin.yaml" <<'YAML'
id: generic
name: generic
summary: Fallback pipeline.
applies_to: [any]
routing:
  priority: 10
  keywords: []
YAML

  # Plugin without a manifest at all — must be ignored cleanly.

  cat >"$d/plugins/development/knowledge/cli-style.md" <<'MD'
---
title: CLI flag conventions
summary: Long flags use --kebab-case; short flags reserved for the top 8.
tags: [cli, argparse]
---
Body content here.
MD

  cat >"$d/plugins/development/knowledge/no-frontmatter.md" <<'MD'
This file has no frontmatter. It should still be listed.
MD

  cat >"$d/plugins/writing/knowledge/style.md" <<'MD'
---
title: Writing style
summary: Active voice, short sentences.
tags: [style, writing]
---
Body.
MD

  cat >"$d/plugins/generic/knowledge/conventions.md" <<'MD'
---
title: Generic conventions
summary: Cross-cutting cli conventions.
tags: [conventions]
---
Body.
MD
}

# ---------- plugin_manifest_index ----------

@test "M8.3 discover_plugins returns 3 plugins with _path injected" {
  d=$(make_scratch); make_fake_workspace "$d"
  run py_helper "
import plugin_manifest_index as pmi
plugins = pmi.discover_plugins('$d')
names = [p.get('name') for p in plugins]
assert names == ['development','generic','writing'], names
paths = [p['_path'] for p in plugins]
assert paths == ['plugins/development/plugin.yaml','plugins/generic/plugin.yaml','plugins/writing/plugin.yaml'], paths
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "M8.3 discover_plugins on missing workspace returns empty list (no crash)" {
  run py_helper "
import plugin_manifest_index as pmi
assert pmi.discover_plugins('/nonexistent/workspace/path/xyz123') == []
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "M8.3 index_by_keyword lowercases, dedupes, and skips empty routing.keywords" {
  d=$(make_scratch); make_fake_workspace "$d"
  run py_helper "
import plugin_manifest_index as pmi
plugins = pmi.discover_plugins('$d')
idx = pmi.index_by_keyword(plugins)
# generic has empty keywords -> excluded entirely from the index values
flat = sorted({n for names in idx.values() for n in names})
assert 'generic' not in flat, flat
# 'PYTHON' duplicate of 'python' should be deduped to a single entry
assert idx.get('python') == ['development'], idx.get('python')
assert idx.get('article') == ['writing']
assert 'PYTHON' not in idx, list(idx.keys())
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "M8.3 match_plugins returns hits sorted by count desc then name asc, case-insensitive" {
  d=$(make_scratch); make_fake_workspace "$d"
  run py_helper "
import plugin_manifest_index as pmi
plugins = pmi.discover_plugins('$d')
idx = pmi.index_by_keyword(plugins)
# 'cli' hits development; 'PYTHON' (uppercase) hits development via case-insensitive lookup
res = pmi.match_plugins('Refactor the PYTHON CLI', idx)
assert res == [('development', 3)], res
# multi-plugin tie: 'article' (writing) and 'cli' (development) both hit once
res2 = pmi.match_plugins('write an article about a cli', idx)
assert res2 == [('development', 1), ('writing', 1)], res2
# no hits
assert pmi.match_plugins('hello world', idx) == []
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "M8.3 summary_for_router projects the prompt-embedded shape" {
  d=$(make_scratch); make_fake_workspace "$d"
  run py_helper "
import plugin_manifest_index as pmi
plugins = pmi.discover_plugins('$d')
summ = pmi.summary_for_router(plugins)
by_name = {s['name']: s for s in summ}
assert set(by_name) == {'development','writing','generic'}, list(by_name)
dev = by_name['development']
assert dev['priority'] == 50
assert dev['applies_to'] == ['code','software-engineering']
assert 'python' in dev['keywords']
assert dev['description'] == 'Software development pipeline.'
# block-scalar summary collapses whitespace
wri = by_name['writing']
assert wri['description'] == 'Long-form authoring pipeline.', wri['description']
# generic has no priority override here -> still 10 from yaml
assert by_name['generic']['priority'] == 10
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "M8.3 summary_for_router defaults priority to 100 when routing omitted" {
  d=$(make_scratch)
  mkdir -p "$d/plugins/p1"
  cat >"$d/plugins/p1/plugin.yaml" <<'YAML'
id: p1
name: p1
summary: bare manifest
YAML
  run py_helper "
import plugin_manifest_index as pmi
summ = pmi.summary_for_router(pmi.discover_plugins('$d'))
assert len(summ) == 1
assert summ[0]['priority'] == 100, summ[0]
assert summ[0]['keywords'] == []
assert summ[0]['applies_to'] == []
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

# ---------- knowledge_index ----------

@test "M8.3 discover_knowledge parses frontmatter and falls back for plain files" {
  d=$(make_scratch); make_fake_workspace "$d"
  run py_helper "
import knowledge_index as ki
recs = ki.discover_knowledge('$d/plugins/development')
titles = [r['title'] for r in recs]
assert titles == ['CLI flag conventions','no-frontmatter'], titles
assert recs[0]['tags'] == ['cli','argparse']
assert recs[0]['summary'].startswith('Long flags')
# fallback row — no frontmatter, but v0.21.0+ derives an implicit
# summary from the first non-empty paragraph of the body.
assert recs[1]['tags'] == []
assert recs[1]['summary'] == 'This file has no frontmatter. It should still be listed.'
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "M8.3 discover_knowledge on missing knowledge dir returns empty" {
  d=$(make_scratch)
  mkdir -p "$d/plugins/p1"
  run py_helper "
import knowledge_index as ki
assert ki.discover_knowledge('$d/plugins/p1') == []
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "M8.3 aggregate_knowledge keys by plugin dir name" {
  d=$(make_scratch); make_fake_workspace "$d"
  run py_helper "
import knowledge_index as ki
agg = ki.aggregate_knowledge('$d')
assert set(agg) == {'development','writing','generic','empty'}, list(agg)
assert agg['empty'] == []
assert len(agg['development']) == 2
assert len(agg['writing']) == 1
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "M8.3 find_relevant ranks by score with stable plugin,path tie-break" {
  d=$(make_scratch); make_fake_workspace "$d"
  run py_helper "
import knowledge_index as ki
agg = ki.aggregate_knowledge('$d')
# 'cli' hits development: tag 'cli' (+3) + title 'CLI flag conventions' (+2) = 5;
# generic gets +1 from summary 'Cross-cutting cli conventions.'
res = ki.find_relevant('cli', agg, limit=5)
plugins_paths = [(r['plugin'], r['title'], r['score']) for r in res]
assert plugins_paths[0][0] == 'development', plugins_paths
assert plugins_paths[0][2] == 5, plugins_paths
assert plugins_paths[1][0] == 'generic', plugins_paths
assert plugins_paths[1][2] == 1, plugins_paths
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "M8.3 find_relevant tie-breaker is deterministic across equal scores" {
  d=$(make_scratch)
  mkdir -p "$d/plugins/alpha/knowledge" "$d/plugins/beta/knowledge"
  cat >"$d/plugins/alpha/knowledge/a.md" <<'MD'
---
title: alpha doc
summary: about widgets
tags: [widget]
---
MD
  cat >"$d/plugins/beta/knowledge/a.md" <<'MD'
---
title: beta doc
summary: about widgets
tags: [widget]
---
MD
  run py_helper "
import knowledge_index as ki
agg = ki.aggregate_knowledge('$d')
res = ki.find_relevant('widget', agg, limit=5)
order = [(r['plugin'], r['score']) for r in res]
assert order == [('alpha', 4), ('beta', 4)], order
# Re-run to confirm stability
res2 = ki.find_relevant('widget', agg, limit=5)
assert [(r['plugin'], r['score']) for r in res2] == order
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "M8.3 find_relevant respects limit and skips zero scores" {
  d=$(make_scratch); make_fake_workspace "$d"
  run py_helper "
import knowledge_index as ki
agg = ki.aggregate_knowledge('$d')
res = ki.find_relevant('cli', agg, limit=1)
assert len(res) == 1
assert ki.find_relevant('zzznotpresent', agg, limit=5) == []
assert ki.find_relevant('', agg, limit=5) == []
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}
