#!/usr/bin/env bats
# m3-tick-profiles.bats — unit-level coverage for orchestrator-tick's
# v0.2.0 profile resolution helpers (`_resolve_profile`,
# `_load_pipeline`, `lookup_transition` profile-keyed mode).
#
# Complements m2-profiles.bats (full e2e per profile) and
# m4-orchestrator-tick.bats (legacy flat-layout tick).

load helpers/load
load helpers/assertions

TICK_LIB="$CORE_ROOT/skills/builtin/orchestrator-tick/_tick.py"

mk_v2_plugin() {
  local ws="$1"
  local pdir="$ws/.codenook/plugins/p2"
  mkdir -p "$pdir"
  cat >"$pdir/phases.yaml" <<'EOF'
phases:
  clarify: { role: clarifier, produces: outputs/phase-1-clarifier.md }
  small:   { role: smallrole, produces: outputs/phase-small.md }
  big:     { role: bigrole,   produces: outputs/phase-big.md }
  ship:    { role: shiprole,  produces: outputs/phase-ship.md }
profiles:
  alpha:  { phases: [clarify, small, ship] }
  bravo:  { phases: [clarify, big, ship] }
  feature: { phases: [clarify, small, big, ship] }
EOF
  cat >"$pdir/transitions.yaml" <<'EOF'
transitions:
  default:
    clarify: { ok: small, needs_revision: clarify, blocked: clarify }
    small:   { ok: big,   needs_revision: small,   blocked: small }
    big:     { ok: ship,  needs_revision: big,     blocked: big }
    ship:    { ok: complete, needs_revision: ship, blocked: ship }
  alpha:
    clarify: { ok: small, needs_revision: clarify, blocked: clarify }
    small:   { ok: ship,  needs_revision: small,   blocked: small }
    ship:    { ok: complete, needs_revision: ship, blocked: ship }
  bravo:
    clarify: { ok: big,   needs_revision: clarify, blocked: clarify }
    big:     { ok: ship,  needs_revision: big,     blocked: big }
    ship:    { ok: complete, needs_revision: ship, blocked: ship }
EOF
}

mk_state() {
  local ws="$1" tid="$2" extra="${3:-}"
  local d="$ws/.codenook/tasks/$tid"
  mkdir -p "$d/outputs"
  python3 - "$d/state.json" "$tid" "$extra" <<'PY'
import json, sys
out, tid, extra = sys.argv[1], sys.argv[2], sys.argv[3]
state = {
  "schema_version": 1, "task_id": tid, "plugin": "p2",
  "phase": None, "iteration": 0, "max_iterations": 3,
  "dual_mode": "serial", "status": "in_progress",
  "config_overrides": {}, "history": [],
}
if extra:
    state.update(json.loads(extra))
open(out, "w").write(json.dumps(state))
PY
}

write_clarifier_output() {
  local ws="$1" tid="$2" tt="$3"
  local p="$ws/.codenook/tasks/$tid/outputs/phase-1-clarifier.md"
  mkdir -p "$(dirname "$p")"
  cat >"$p" <<EOF
---
verdict: ok
task_type: $tt
summary: x
---
EOF
}

resolve() {
  local ws="$1" tid="$2"
  python3 - "$TICK_LIB" "$ws" "$tid" <<'PY'
import importlib.util, sys, json
spec = importlib.util.spec_from_file_location("_tick", sys.argv[1])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
from pathlib import Path
ws = Path(sys.argv[2]); tid = sys.argv[3]
state_file = ws / ".codenook" / "tasks" / tid / "state.json"
state = json.load(open(state_file))
phases, trans, profile = m._load_pipeline(ws, state)
ids = [p.get("id") for p in phases]
print(json.dumps({"profile": profile, "chain": ids,
                  "cached": state.get("profile")}))
PY
}

@test "v2: empty state + no clarifier output → provisional 'feature' chain (NOT cached)" {
  ws="$(make_scratch)"; mk_v2_plugin "$ws"; mk_state "$ws" T-1
  out=$(resolve "$ws" T-1)
  echo "$out" | jq -e '.profile == null' >/dev/null
  echo "$out" | jq -e '.cached == null' >/dev/null
  echo "$out" | jq -e '.chain == ["clarify","small","big","ship"]' >/dev/null
}

@test "v2: state.task_type='alpha' resolves to alpha and caches" {
  ws="$(make_scratch)"; mk_v2_plugin "$ws"
  mk_state "$ws" T-2 '{"task_type": "alpha"}'
  out=$(resolve "$ws" T-2)
  echo "$out" | jq -e '.profile == "alpha"' >/dev/null
  echo "$out" | jq -e '.cached == "alpha"' >/dev/null
  echo "$out" | jq -e '.chain == ["clarify","small","ship"]' >/dev/null
}

@test "v2: clarifier frontmatter task_type beats state.task_type" {
  ws="$(make_scratch)"; mk_v2_plugin "$ws"
  mk_state "$ws" T-3 '{"task_type": "alpha"}'
  write_clarifier_output "$ws" T-3 bravo
  out=$(resolve "$ws" T-3)
  echo "$out" | jq -e '.profile == "bravo"' >/dev/null
  echo "$out" | jq -e '.cached == "bravo"' >/dev/null
  echo "$out" | jq -e '.chain == ["clarify","big","ship"]' >/dev/null
}

@test "v2: cached state.profile pins resolution even if clarifier disagrees" {
  ws="$(make_scratch)"; mk_v2_plugin "$ws"
  mk_state "$ws" T-4 '{"profile": "alpha"}'
  write_clarifier_output "$ws" T-4 bravo
  out=$(resolve "$ws" T-4)
  echo "$out" | jq -e '.profile == "alpha"' >/dev/null
}

@test "v2: unknown task_type falls through to provisional default chain" {
  ws="$(make_scratch)"; mk_v2_plugin "$ws"
  mk_state "$ws" T-5 '{"task_type": "nope"}'
  out=$(resolve "$ws" T-5)
  echo "$out" | jq -e '.profile == null' >/dev/null
  echo "$out" | jq -e '.cached == null' >/dev/null
  echo "$out" | jq -e '.chain == ["clarify","small","big","ship"]' >/dev/null
}

@test "lookup_transition: profile-keyed lookup wins over default" {
  ws="$(make_scratch)"; mk_v2_plugin "$ws"
  python3 - "$TICK_LIB" "$ws/.codenook/plugins/p2/transitions.yaml" <<'PY'
import importlib.util, sys, yaml
spec = importlib.util.spec_from_file_location("_tick", sys.argv[1])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
trans = yaml.safe_load(open(sys.argv[2]))
# alpha: small.ok → ship (per alpha override)
assert m.lookup_transition(trans, "small", "ok", profile="alpha") == "ship"
# bravo: clarify.ok → big (per bravo override)
assert m.lookup_transition(trans, "clarify", "ok", profile="bravo") == "big"
# default profile (explicit): small.ok → big (default table)
assert m.lookup_transition(trans, "small", "ok", profile="default") == "big"
print("ok")
PY
}

@test "lookup_transition: unknown profile falls through to default table inheritance" {
  ws="$(make_scratch)"; mk_v2_plugin "$ws"
  python3 - "$TICK_LIB" "$ws/.codenook/plugins/p2/transitions.yaml" <<'PY'
import importlib.util, sys, yaml
spec = importlib.util.spec_from_file_location("_tick", sys.argv[1])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
trans = yaml.safe_load(open(sys.argv[2]))
# alpha doesn't define a transition for 'big' but inherits via default.
assert m.lookup_transition(trans, "big", "ok", profile="alpha") == "ship"
print("ok")
PY
}

@test "backward-compat: flat phases (no profiles:) loads as legacy chain" {
  ws="$(make_scratch)"
  pdir="$ws/.codenook/plugins/legacy"
  mkdir -p "$pdir"
  cat >"$pdir/phases.yaml" <<'EOF'
phases:
  - { id: a, role: ra, produces: outputs/a.md }
  - { id: b, role: rb, produces: outputs/b.md }
EOF
  cat >"$pdir/transitions.yaml" <<'EOF'
transitions:
  a: { ok: b }
  b: { ok: complete }
EOF
  d="$ws/.codenook/tasks/T-LEG"
  mkdir -p "$d/outputs"
  python3 -c "
import json
state = {'schema_version':1,'task_id':'T-LEG','plugin':'legacy',
         'phase':None,'iteration':0,'max_iterations':3,
         'dual_mode':'serial','status':'in_progress',
         'config_overrides':{},'history':[]}
open('$d/state.json','w').write(json.dumps(state))
"
  python3 - "$TICK_LIB" "$ws" <<'PY'
import importlib.util, sys, json
from pathlib import Path
spec = importlib.util.spec_from_file_location("_tick", sys.argv[1])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
ws = Path(sys.argv[2])
state = json.load(open(ws/".codenook/tasks/T-LEG/state.json"))
phases, trans, profile = m._load_pipeline(ws, state)
assert profile is None, profile
assert [p["id"] for p in phases] == ["a","b"]
assert "profile" not in state or state.get("profile") is None
print("ok")
PY
}
