#!/usr/bin/env bats
# M8.4 Unit 1 - per-task fcntl lock (task_lock.py).
# Covers happy path + concurrency cases per docs/v6/router-agent-v6.md S6.

load helpers/load
load helpers/assertions

LIB_DIR="$CORE_ROOT/skills/builtin/_lib"
HOLDER="$CORE_ROOT/tests/helpers/m8_lock_holder.py"
SCHEMAS_DIR="$CORE_ROOT/skills/builtin/router-agent/schemas"

py_helper() {
  local script="$1"
  PYTHONPATH="$LIB_DIR" python3 -c "$script"
}

mk_taskdir() {
  local d
  d=$(make_scratch)
  mkdir -p "$d/T-001"
  echo "$d/T-001"
}

@test "M8.4 task_lock module imports cleanly" {
  run py_helper "import task_lock as tl; print('OK', tl.LOCK_FILENAME)"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK router.lock"
}

@test "M8.4 acquire on fresh task_dir writes payload and releases on exit" {
  td=$(mk_taskdir)
  run py_helper "
import task_lock as tl, json, os
from pathlib import Path
td = Path('$td')
with tl.acquire(td) as p:
    assert (td/'router.lock').exists()
    on_disk = json.loads((td/'router.lock').read_text())
    assert on_disk == p
    assert p['pid'] == os.getpid()
    assert p['task_id'] == 'T-001'
    assert isinstance(p['hostname'], str) and p['hostname']
    assert isinstance(p['started_at'], str) and p['started_at'].endswith('Z')
assert not (td/'router.lock').exists(), 'lockfile not removed on exit'
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "M8.4 second acquire while holder lives raises LockTimeout within timeout" {
  td=$(mk_taskdir)
  # spawn an out-of-process holder; wait until it prints its pid
  out_file="$BATS_TEST_TMPDIR/holder.out"
  LIB_DIR="$LIB_DIR" python3 "$HOLDER" "$td" 5 >"$out_file" 2>&1 &
  holder_pid=$!
  # wait up to 3s for the holder to acquire
  for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
    [ -s "$out_file" ] && break
    sleep 0.2
  done
  [ -s "$out_file" ] || { kill "$holder_pid" 2>/dev/null; cat "$out_file"; return 1; }

  run py_helper "
import task_lock as tl, time
t0 = time.monotonic()
try:
    with tl.acquire('$td', timeout=0.5, poll_interval=0.05):
        print('NO_RAISE')
except tl.LockTimeout as e:
    dt = time.monotonic() - t0
    # should fail near timeout, not instantly (gives polling time) and not way over
    assert 0.4 <= dt < 2.0, dt
    print('OK', 'router.lock' in str(e))
"
  status_main=$status
  output_main=$output
  kill "$holder_pid" 2>/dev/null
  wait "$holder_pid" 2>/dev/null || true
  [ "$status_main" -eq 0 ] || { echo "$output_main"; return 1; }
  assert_contains "$output_main" "OK True"
}

@test "M8.4 parallel acquire on different task_dirs succeeds simultaneously" {
  base=$(make_scratch)
  mkdir -p "$base/T-A" "$base/T-B"
  run py_helper "
import task_lock as tl, threading, time
from pathlib import Path
results = []
barrier = threading.Barrier(2)
def hold(td, label):
    barrier.wait()
    with tl.acquire(td, timeout=2.0) as p:
        results.append((label, p['task_id'], time.monotonic()))
        time.sleep(0.3)
t1 = threading.Thread(target=hold, args=(Path('$base/T-A'), 'a'))
t2 = threading.Thread(target=hold, args=(Path('$base/T-B'), 'b'))
t1.start(); t2.start(); t1.join(); t2.join()
labels = sorted(r[0] for r in results)
ids    = sorted(r[1] for r in results)
assert labels == ['a','b'], labels
assert ids    == ['T-A','T-B'], ids
# overlap check: both started within 0.2s of each other (parallel, not serialized 0.3+)
ts = sorted(r[2] for r in results)
assert ts[1] - ts[0] < 0.2, ('serialized?', ts)
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "M8.4 stale lock with dead pid is force-released and reacquired" {
  td=$(mk_taskdir)
  # Plant a synthetic stale payload with a guaranteed-dead pid.
  # The OS releases flock on process death, so this lockfile has no
  # live flock holder; acquire takes it immediately by overwrite.
  run py_helper "
import task_lock as tl, json, os, subprocess
p = subprocess.Popen(['true']); p.wait()
dead_pid = p.pid
open('$td/router.lock','w').write(
    json.dumps({'pid': dead_pid, 'hostname':'h', 'started_at':'2099-01-01T00:00:00Z', 'task_id':'T-001'})
)
with tl.acquire('$td', timeout=2.0) as got:
    assert got['pid'] == os.getpid()
    assert got['task_id'] == 'T-001'
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "M8.4 stale recovery branch fires on live but stale-by-timestamp holder" {
  # Genuine stale-detection: child holds the flock with an old started_at.
  # Parent must peek payload, classify stale, unlink, and re-acquire.
  td=$(mk_taskdir)
  out_file="$BATS_TEST_TMPDIR/holder.out"
  LIB_DIR="$LIB_DIR" python3 - "$td" >"$out_file" 2>&1 <<'PY' &
import os, sys, time, json, fcntl
sys.path.insert(0, os.environ["LIB_DIR"])
td = sys.argv[1]
lock_path = os.path.join(td, "router.lock")
fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
fcntl.flock(fd, fcntl.LOCK_EX)
# Synthetic ancient started_at; pid is us (alive).
payload = {"pid": os.getpid(), "hostname": "h",
           "started_at": "1999-01-01T00:00:00Z", "task_id": os.path.basename(td)}
os.ftruncate(fd, 0)
os.write(fd, (json.dumps(payload) + "\n").encode())
os.fsync(fd)
print(os.getpid(), flush=True)
time.sleep(5)
PY
  holder_pid=$!
  for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
    [ -s "$out_file" ] && break
    sleep 0.2
  done
  [ -s "$out_file" ] || { kill "$holder_pid" 2>/dev/null; cat "$out_file"; return 1; }

  run_with_stderr "PYTHONPATH='$LIB_DIR' python3 -c \"
import task_lock as tl, os
with tl.acquire('$td', timeout=3.0, stale_threshold=1.0, poll_interval=0.05) as p:
    assert p['pid'] == os.getpid()
print('OK')
\""
  status_main=$status
  output_main=$output
  stderr_main=$STDERR
  kill "$holder_pid" 2>/dev/null
  wait "$holder_pid" 2>/dev/null || true
  [ "$status_main" -eq 0 ] || { echo "$output_main"; echo "STDERR: $stderr_main"; return 1; }
  assert_contains "$output_main" "OK"
  assert_contains "$stderr_main" "stale lock for T-001"
}

@test "M8.4 stale lock with old started_at is force-released even if pid alive" {
  td=$(mk_taskdir)
  run py_helper "
import task_lock as tl, json, os
# Use our own pid (definitely alive) but an ancient timestamp.
(open('$td/router.lock','w').write(
    json.dumps({'pid': os.getpid(), 'hostname':'h', 'started_at':'1999-01-01T00:00:00Z', 'task_id':'T-001'})
))
# stale_threshold=1s -> 1999 timestamp is way over.
with tl.acquire('$td', timeout=2.0, stale_threshold=1.0) as got:
    assert got['pid'] == os.getpid()
print('OK')
" 2> "$BATS_TEST_TMPDIR/err"
  [ "$status" -eq 0 ] || { echo "$output"; cat "$BATS_TEST_TMPDIR/err"; return 1; }
  assert_contains "$output" "OK"
}

@test "M8.4 payload conforms to router-lock M5 DSL schema" {
  td=$(mk_taskdir)
  run python3 - "$SCHEMAS_DIR/router-lock.json.schema.yaml" "$LIB_DIR" "$td" <<'PY'
import sys, yaml, json
schema_path, lib_dir, td = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, lib_dir)
import task_lock as tl

with open(schema_path) as f:
    schema = yaml.safe_load(f)
fields = schema["fields"]

with tl.acquire(td) as payload:
    pass

TYPE_MAP = {"integer": int, "string": str, "boolean": bool, "number": (int, float)}
for name, spec in fields.items():
    required = spec.get("required", False)
    if name not in payload:
        assert not required, f"required field {name!r} missing from payload"
        continue
    val = payload[name]
    pytype = TYPE_MAP[spec["type"]]
    assert isinstance(val, pytype) and not isinstance(val, bool) if spec["type"] == "integer" else isinstance(val, pytype), \
        f"{name}: expected {spec['type']}, got {type(val).__name__}"
    if "min" in spec:
        assert val >= spec["min"], f"{name}: {val} < min {spec['min']}"
    if "min_length" in spec:
        assert len(val) >= spec["min_length"], f"{name}: len {len(val)} < {spec['min_length']}"
    if "enum" in spec:
        assert val in spec["enum"], f"{name}: {val!r} not in {spec['enum']}"
print("OK")
PY
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "M8.4 inspect returns payload of held lock and None when absent" {
  td=$(mk_taskdir)
  run py_helper "
import task_lock as tl, os
assert tl.inspect('$td') is None
with tl.acquire('$td') as p:
    got = tl.inspect('$td')
    assert got == p, (got, p)
assert tl.inspect('$td') is None
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "M8.4 force_release removes file and returns True else False" {
  td=$(mk_taskdir)
  run py_helper "
import task_lock as tl
assert tl.force_release('$td') is False
open('$td/router.lock','w').write('{}')
assert tl.force_release('$td') is True
import os
assert not os.path.exists('$td/router.lock')
assert tl.force_release('$td') is False
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "M8.4 context exit on exception still releases the lock" {
  td=$(mk_taskdir)
  # First process: acquire, raise inside the with-block, exit nonzero.
  run py_helper "
import task_lock as tl
try:
    with tl.acquire('$td'):
        raise RuntimeError('boom')
except RuntimeError:
    pass
import os
assert not os.path.exists('$td/router.lock'), 'lockfile leaked after exception'
print('OK1')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK1"
  # Second, fully separate python process must be able to re-acquire.
  run py_helper "
import task_lock as tl
with tl.acquire('$td', timeout=1.0) as p:
    assert p['task_id'] == 'T-001'
print('OK2')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK2"
}
