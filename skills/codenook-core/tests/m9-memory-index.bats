#!/usr/bin/env bats
# M9.1 — Memory index (TC-M9.1-08).

load helpers/load
load helpers/assertions
load helpers/m9_memory

@test "[m9.1] TC-M9.1-08 scan_memory under 500ms for 1000 files" {
  ws=$(m9_seed_workspace); m9_init_memory "$ws"

  # Seed 1000 small knowledge files.
  m9_seed_n_knowledge "$ws" 1000

  # Cold scan (no snapshot).
  rm -f "$ws/.codenook/memory/.index-snapshot.json"
  run m9_py "
import time, memory_layer as ml
t0 = time.perf_counter()
idx = ml.scan_memory('$ws')
dt = (time.perf_counter() - t0) * 1000
assert len(idx['knowledge']) == 1000, len(idx['knowledge'])
print('cold_ms', round(dt, 2))
assert dt <= 500, f'cold scan {dt}ms > 500ms'
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "cold_ms"

  # Warm scan: snapshot present, no file changes → must hit cache and be fast.
  run m9_py "
import time, memory_layer as ml
t0 = time.perf_counter()
idx = ml.scan_memory('$ws')
dt = (time.perf_counter() - t0) * 1000
assert len(idx['knowledge']) == 1000
print('warm_ms', round(dt, 2))
assert dt <= 200, f'warm scan {dt}ms > 200ms'
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "warm_ms"
}

@test "[m9.1] memory_index get_hash sha256 of first 512 chars" {
  run m9_py "
import memory_index as mi
import hashlib
content = 'A' * 600
expected = hashlib.sha256(content[:512].encode('utf-8')).hexdigest()
assert mi.get_hash(content) == expected
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "[m9.1] memory_index invalidate drops a path from snapshot" {
  ws=$(m9_seed_workspace); m9_init_memory "$ws"
  m9_seed_n_knowledge "$ws" 3
  run m9_py "
import memory_index as mi, os
ws = '$ws'
idx = mi.build_index(ws)
assert len(idx['knowledge']) == 3
victim = ws + '/.codenook/memory/knowledge/topic-0001.md'
mi.invalidate(ws, victim)
import json
snap = json.load(open(ws + '/.codenook/memory/.index-snapshot.json'))
assert victim not in snap.get('knowledge', {}), 'snapshot still has victim'
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}
