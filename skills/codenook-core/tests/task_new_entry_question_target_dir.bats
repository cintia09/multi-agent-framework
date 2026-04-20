#!/usr/bin/env bats
# E2E-P-005 — implement phase with missing target_dir → entry-question
# (status=blocked, exit 2). Wrapper now defaults --target-dir to src/, so
# we explicitly clear target_dir in state.json before ticking implement.

load helpers/load
load helpers/assertions

REPO_ROOT="$(cd "$CORE_ROOT/../.." && pwd)"
INSTALL_SH="$REPO_ROOT/install.sh"

setup() {
  ws="$(make_scratch)"
  bash "$INSTALL_SH" --plugin development "$ws" >/dev/null 2>&1
}

@test "[v0.11.4 E2E-P-005] tick into implement w/o target_dir → exit 2 + missing field" {
  tid="$("$ws/.codenook/bin/codenook" task new --title "X" --dual-mode serial)"
  # Set state to "just-finished plan, about to dispatch implement, but
  # target_dir cleared". Tick should attempt implement → block with
  # missing target_dir, status=blocked, exit 2.
  python3 - <<PY
import json
sf = "$ws/.codenook/tasks/$tid/state.json"
d = json.load(open(sf))
d["phase"] = "plan"
d["max_iterations"] = 3
d["target_dir"] = ""  # clear default src/
d["status"] = "in_progress"
d["history"] = []
d["in_flight_agent"] = {
    "agent_id": "a", "role": "planner",
    "dispatched_at": "x",
    "expected_output": "outputs/phase-3-planner.md",
}
import os
os.makedirs("$ws/.codenook/tasks/$tid/outputs", exist_ok=True)
open("$ws/.codenook/tasks/$tid/outputs/phase-3-planner.md","w").write(
    "---\nverdict: ok\nsummary: ok\n---\n"
)
json.dump(d, open(sf,"w"), indent=2)
PY
  set +e
  out=$("$ws/.codenook/bin/codenook" tick --task "$tid" --json)
  rc=$?
  set -e
  [ "$rc" -eq 2 ] || { echo "rc=$rc out=$out"; return 1; }
  echo "$out" | python3 -c "
import json,sys
d=json.loads(sys.stdin.read())
assert d['status']=='blocked', d
assert 'target_dir' in d.get('missing',[]), d
"
  # state.phase should now be pinned to 'implement' with status=blocked
  python3 -c "
import json
d=json.load(open('$ws/.codenook/tasks/$tid/state.json'))
assert d['phase']=='implement', d
assert d['status']=='blocked', d
"
}

@test "[v0.11.4 E2E-P-005] task new defaults target_dir to src/" {
  tid="$("$ws/.codenook/bin/codenook" task new --title "Y" --dual-mode serial)"
  td="$(python3 -c "import json; print(json.load(open('$ws/.codenook/tasks/$tid/state.json')).get('target_dir'))")"
  [ "$td" = "src/" ] || { echo "got=$td"; return 1; }
}
