#!/usr/bin/env bats
# E2E-P-002 — `codenook task new` without --dual-mode emits an
# entry-question JSON envelope and exits 2. v0.11.4 round-2.

load helpers/load
load helpers/assertions

REPO_ROOT="$(cd "$CORE_ROOT/../.." && pwd)"
INSTALL_SH="$REPO_ROOT/install.sh"

setup() {
  ws="$(make_scratch)"
  bash "$INSTALL_SH" --plugin development "$ws" >/dev/null 2>&1
}

@test "[v0.11.4 E2E-P-002] task new without --dual-mode → exit 2 entry_question" {
  run "$ws/.codenook/bin/codenook" task new --title "Smoke"
  [ "$status" -eq 2 ] || { echo "status=$status output=$output"; return 1; }
  echo "$output" | python3 -c "
import json, sys
d=json.loads(sys.stdin.read().strip())
assert d['action']=='entry_question', d
assert d['field']=='dual_mode', d
assert d['allowed_values']==['serial','parallel'], d
assert 'recovery' in d and 'codenook task set' in d['recovery'], d
"
}

@test "[v0.11.4 E2E-P-002] --accept-defaults bypasses entry-question" {
  run "$ws/.codenook/bin/codenook" task new --title "Smoke" --accept-defaults
  [ "$status" -eq 0 ]
  tid="$(echo "$output" | tr -d '[:space:]')"
  [[ "$tid" =~ ^T-[0-9]+$ ]]
  python3 -c "
import json
d=json.load(open('$ws/.codenook/tasks/$tid/state.json'))
assert d.get('dual_mode')=='serial', d
"
}

@test "[v0.11.4 E2E-P-002] explicit --dual-mode parallel writes correctly" {
  run "$ws/.codenook/bin/codenook" task new --title "Par" --dual-mode parallel
  [ "$status" -eq 0 ]
  tid="$(echo "$output" | tr -d '[:space:]')"
  python3 -c "
import json
d=json.load(open('$ws/.codenook/tasks/$tid/state.json'))
assert d['dual_mode']=='parallel', d
"
}
