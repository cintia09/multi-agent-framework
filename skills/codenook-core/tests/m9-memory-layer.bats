#!/usr/bin/env bats
# M9.1 — Memory layout primitives (TC-M9.1-01..07, 09, 10).
# Spec: docs/memory-and-extraction.md §10
# Cases: docs/m9-test-cases.md §M9.1

load helpers/load
load helpers/assertions
load helpers/m9_memory

@test "[m9.1] TC-M9.1-01 init creates empty skeleton" {
  ws=$(m9_seed_workspace)
  run m9_init_memory "$ws"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }

  # Directory shape: exactly memory/, memory/knowledge, memory/skills, memory/history.
  run bash -c "cd '$ws' && find .codenook/memory -maxdepth 2 -type d | sort"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  expected=$'.codenook/memory\n.codenook/memory/history\n.codenook/memory/knowledge\n.codenook/memory/skills'
  [ "$output" = "$expected" ] || { echo "got: $output"; return 1; }

  # config.yaml content is exactly the empty entries seed.
  got="$(cat "$ws/.codenook/memory/config.yaml")"
  expected_cfg=$'version: 1\nentries: []'
  [ "$got" = "$expected_cfg" ] || { echo "got: $got"; return 1; }

  # knowledge / skills directories are empty.
  [ -z "$(ls -A "$ws/.codenook/memory/knowledge")" ]
  [ -z "$(ls -A "$ws/.codenook/memory/skills")" ]
}

@test "[m9.1] TC-M9.1-02 rejects nested topic path" {
  ws=$(m9_seed_workspace); m9_init_memory "$ws"
  run m9_py "
import memory_layer as ml
try:
    ml.write_knowledge('$ws', topic='dev/foo', summary='s', tags=['x'], body='b')
    print('NO_ERROR')
except ValueError as e:
    print('OK:' + str(e))
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK:"
  assert_contains "$output" "flat layout"
  [ ! -d "$ws/.codenook/memory/knowledge/dev" ]
}

@test "[m9.1] TC-M9.1-03 atomic rename used" {
  ws=$(m9_seed_workspace); m9_init_memory "$ws"
  run m9_py "
import os, memory_layer as ml
calls = []
real_replace = os.replace
def spy(src, dst):
    calls.append((src, dst))
    return real_replace(src, dst)
os.replace = spy
target = '$ws/.codenook/memory/knowledge/alpha.md'
assert not os.path.exists(target)
ml.write_knowledge('$ws', topic='alpha', summary='s', tags=['x'], body='hello')
assert os.path.exists(target), 'final missing'
assert calls, 'os.replace never called'
src, dst = calls[-1]
assert str(dst) == target, ('dst', dst)
assert os.path.basename(str(src)).startswith('.tmp.'), ('tmp prefix', src)
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "[m9.1] TC-M9.1-04 sigkill mid-write leaves no half-file" {
  ws=$(m9_seed_workspace); m9_init_memory "$ws"
  run m9_py "
import os, signal, sys, multiprocessing
def child(ws):
    import memory_layer as ml
    real_replace = os.replace
    def killer(src, dst):
        os.kill(os.getpid(), signal.SIGKILL)
    os.replace = killer
    ml.write_knowledge(ws, topic='alpha', summary='s', tags=['x'], body='B'*4096)
multiprocessing.set_start_method('fork')
p = multiprocessing.Process(target=child, args=('$ws',))
p.start(); p.join()
final = '$ws/.codenook/memory/knowledge/alpha.md'
assert not os.path.exists(final), 'half-file leaked!'
import memory_layer as ml
got = ml.read_knowledge(final) if os.path.exists(final) else None
print('OK', got)
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "[m9.1] TC-M9.1-05 same topic prefers patch" {
  ws=$(m9_seed_workspace); m9_init_memory "$ws"
  run m9_py "
import os, memory_layer as ml
# First write (create path).
p1 = ml.write_knowledge('$ws', topic='alpha', summary='v1 sum', tags=['a','b'], body='v1 body')
# Patch-style merge: same topic gets new tags + summary appended via patch_knowledge.
def mutator(doc):
    new_tags = sorted(set(list(doc['frontmatter'].get('tags', [])) + ['c']))
    doc['frontmatter']['tags'] = new_tags
    doc['frontmatter']['summary'] = doc['frontmatter']['summary'] + ' + v2'
    doc['body'] = doc['body'] + '\n--patched--'
    return doc
p2 = ml.patch_knowledge('$ws', topic='alpha', mutator=mutator, rationale='merge tags')
import os
listing = sorted(os.listdir('$ws/.codenook/memory/knowledge'))
assert listing == ['alpha.md'], listing  # no -ts variant
got = ml.read_knowledge(p2)
assert sorted(got['frontmatter']['tags']) == ['a','b','c'], got['frontmatter']['tags']
assert 'v1 sum + v2' == got['frontmatter']['summary']
# Audit log records verdict=merge.
log = open('$ws/.codenook/memory/history/extraction-log.jsonl').read()
assert 'merge' in log, log
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "[m9.1] TC-M9.1-06 public api signature smoke (no TypeError)" {
  ws=$(m9_seed_workspace); m9_init_memory "$ws"
  run m9_py "
import memory_layer as m
# Surface check first.
required = {
    'init_memory_skeleton', 'scan_memory',
    'scan_knowledge', 'read_knowledge', 'write_knowledge', 'patch_knowledge',
    'replace_knowledge', 'promote_knowledge', 'archive_knowledge',
    'scan_skills', 'read_skill', 'write_skill', 'patch_skill', 'promote_skill',
    'read_config_entries', 'upsert_config_entry', 'match_entries_for_task',
    'promote_config_entry',
    'find_similar', 'has_hash', 'append_audit',
}
public = {n for n in dir(m) if not n.startswith('_')}
missing = required - public
assert not missing, 'missing: ' + ','.join(sorted(missing))

ws = '$ws'
# --- knowledge ---
p = m.write_knowledge(ws, topic='alpha', summary='s', tags=['x'], body='b')
doc = m.read_knowledge(p)
assert doc['frontmatter']['topic'] == 'alpha'
m.patch_knowledge(ws, topic='alpha',
                  mutator=lambda d: d, rationale='noop')
m.replace_knowledge(ws, topic='alpha',
                    frontmatter={'summary': 's2', 'tags': ['y'], 'status': 'candidate'},
                    body='b2', rationale='replace')
m.promote_knowledge(ws, p)
m.archive_knowledge(ws, p)
m.scan_knowledge(ws)

# --- skills ---
m.write_skill(ws, name='helper',
              frontmatter={'one_line_job': 'do x', 'applies_when': 'always',
                           'status': 'candidate', 'created_from_task': 't1',
                           'created_at': '2025-01-01T00:00:00Z'},
              body='echo hi')
sk = m.read_skill(ws, 'helper')
assert sk['name'] == 'helper'
m.patch_skill(ws, name='helper', mutator=lambda d: d, rationale='noop')
m.scan_skills(ws)

# --- config ---
m.upsert_config_entry(ws, entry={'key': 'log.level', 'value': 'info'},
                      rationale='init')
m.read_config_entries(ws)
m.match_entries_for_task(ws, 'some brief')

# --- generic ---
m.find_similar(ws, 'knowledge', 'alpha', tags=['x'])
m.has_hash(ws, 'knowledge', 'deadbeef')
m.append_audit(ws, {'ts': '2025-01-01T00:00:00Z', 'asset_type': 'meta'})
m.scan_memory(ws)
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "[m9.1] TC-M9.1-11 concurrent write never leaks .tmp.* into scan" {
  ws=$(m9_seed_workspace); m9_init_memory "$ws"
  run m9_py "
import os, threading, time, memory_layer as ml
ws = '$ws'
errors = []
seen_tmp = []
stop = time.time() + 1.5
def writer(i):
    n = 0
    while time.time() < stop:
        try:
            ml.write_knowledge(ws, topic=f'topic-{i}-{n}',
                               summary='s', tags=['t'], body='B'*4096)
        except Exception as e:
            errors.append(repr(e)); return
        n += 1
def scanner():
    while time.time() < stop:
        try:
            idx = ml.scan_memory(ws)
        except Exception as e:
            errors.append(repr(e)); return
        for entry in idx['knowledge']:
            base = os.path.basename(entry['path'])
            if base.startswith('.') or '.tmp' in base:
                seen_tmp.append(base); return
threads = [threading.Thread(target=writer, args=(i,)) for i in range(6)]
threads += [threading.Thread(target=scanner) for _ in range(4)]
for t in threads: t.start()
for t in threads: t.join()
assert not errors, errors
assert not seen_tmp, f'scan returned tmp file(s): {seen_tmp[:3]}'
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "[m9.1] TC-M9.1-12 parallel build_index(force=True) snapshot stays valid" {
  ws=$(m9_seed_workspace); m9_init_memory "$ws"
  m9_seed_n_knowledge "$ws" 30
  run m9_py "
import json, threading, memory_index as mi
ws = '$ws'
errors = []
def worker():
    try:
        mi.build_index(ws, force=True)
    except Exception as e:
        errors.append(repr(e))
ts = [threading.Thread(target=worker) for _ in range(20)]
for t in ts: t.start()
for t in ts: t.join()
assert not errors, errors
snap_path = ws + '/.codenook/memory/.index-snapshot.json'
data = json.load(open(snap_path))
assert data.get('version') == 1
assert len(data.get('knowledge', {})) == 30
# leftover tmp snapshot files must not exist
import os
left = [n for n in os.listdir(ws + '/.codenook/memory') if n.startswith('.tmp-snap.')]
assert not left, left
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "[m9.1] TC-M9.1-07 reads do not block writes" {
  ws=$(m9_seed_workspace); m9_init_memory "$ws"
  # Pre-seed 5 topics so reads succeed; then run threads for 1s.
  m9_seed_n_knowledge "$ws" 5
  run m9_py "
import os, threading, time, memory_layer as ml
ws = '$ws'
stop = time.time() + 1.0
read_walls = []
errors = []
def reader(idx):
    while time.time() < stop:
        t0 = time.perf_counter()
        try:
            ml.read_knowledge(ws + f'/.codenook/memory/knowledge/topic-{idx % 5:04d}.md')
        except Exception as e:
            errors.append(repr(e)); return
        read_walls.append((time.perf_counter() - t0) * 1000)
def writer(idx):
    n = 0
    while time.time() < stop:
        try:
            ml.write_knowledge(ws, topic=f'w-{idx}-{n}', summary='s', tags=['t'], body='B'*256)
        except Exception as e:
            errors.append(repr(e)); return
        n += 1
threads = [threading.Thread(target=reader, args=(i,)) for i in range(20)]
threads += [threading.Thread(target=writer, args=(i,)) for i in range(4)]
for t in threads: t.start()
for t in threads: t.join()
assert not errors, errors
assert read_walls
worst = max(read_walls)
print('reads', len(read_walls), 'worst_ms', round(worst,2))
assert worst <= 200, f'worst read {worst}ms exceeded budget'
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "[m9.1] TC-M9.1-09 no description.md created" {
  ws=$(m9_seed_workspace); m9_init_memory "$ws"
  run bash -c "cd '$ws' && find .codenook -name 'description.md'"
  [ "$status" -eq 0 ]
  [ -z "$output" ] || { echo "leak: $output"; return 1; }
}

@test "[m9.1] TC-M9.1-10 duplicate config key rejected" {
  ws=$(m9_seed_workspace); m9_init_memory "$ws"
  cat > "$ws/.codenook/memory/config.yaml" <<'YAML'
version: 1
entries:
  - key: log.level
    value: info
    applies_when: always
    summary: s1
    status: promoted
    created_from_task: t1
    created_at: '2025-01-01T00:00:00Z'
  - key: log.level
    value: debug
    applies_when: always
    summary: s2
    status: promoted
    created_from_task: t2
    created_at: '2025-01-02T00:00:00Z'
YAML
  before_md5=$(md5 -q "$ws/.codenook/memory/config.yaml" 2>/dev/null || md5sum "$ws/.codenook/memory/config.yaml" | awk '{print $1}')
  run m9_py "
import memory_layer as ml
try:
    ml.read_config_entries('$ws')
    print('NO_ERROR')
except ValueError as e:
    print('OK:' + str(e))
"
  [ "$status" -eq 0 ]
  assert_contains "$output" "OK:"
  assert_contains "$output" "duplicate key"
  after_md5=$(md5 -q "$ws/.codenook/memory/config.yaml" 2>/dev/null || md5sum "$ws/.codenook/memory/config.yaml" | awk '{print $1}')
  [ "$before_md5" = "$after_md5" ]
}
