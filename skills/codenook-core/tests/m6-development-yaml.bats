#!/usr/bin/env bats
# m6-development-yaml.bats — v0.2.0 phases/transitions/entry-questions/gates
#
# v0.2.0 changes vs v0.1.x:
#   * phases.yaml now uses {phases: <catalogue map>, profiles: <map>}.
#   * 11 phases in the catalogue; the active chain is profile-resolved.
#   * 7 profiles: feature/hotfix/refactor/test-only/docs/review/design.
#   * transitions.yaml is profile-keyed (with a `default` fallback).
#   * 10 HITL gates (every non-implement phase).

load helpers/load
load helpers/assertions

PLUGIN_DIR="$CORE_ROOT/../../plugins/development"
TICK_LIB="$CORE_ROOT/skills/builtin/orchestrator-tick/_tick.py"

py_yaml_load() {
  python3 - "$1" <<'PY'
import sys, yaml
with open(sys.argv[1]) as f:
    yaml.safe_load(f)
PY
}

@test "plugin dir exists" {
  [ -d "$PLUGIN_DIR" ]
}

@test "phases.yaml loads as valid YAML" {
  py_yaml_load "$PLUGIN_DIR/phases.yaml"
}

@test "phases.yaml: catalogue contains the 11 expected phase ids" {
  run python3 - "$PLUGIN_DIR/phases.yaml" <<'PY'
import sys, yaml
doc = yaml.safe_load(open(sys.argv[1]))
phases = doc["phases"]
assert isinstance(phases, dict), "v0.2.0 catalogue must be a map"
expected = {"clarify","design","plan","implement","build","review",
            "submit","test-plan","test","accept","ship"}
assert set(phases.keys()) == expected, sorted(phases.keys())
for pid, spec in phases.items():
    assert "role" in spec and "produces" in spec, (pid, spec)
print("ok")
PY
  [ "$status" -eq 0 ]
  [ "$output" = "ok" ]
}

@test "phases.yaml: every non-implement phase has a HITL gate" {
  run python3 - "$PLUGIN_DIR/phases.yaml" <<'PY'
import sys, yaml
phases = yaml.safe_load(open(sys.argv[1]))["phases"]
for pid, spec in phases.items():
    if pid == "implement":
        assert "gate" not in spec, "implement must NOT have a gate"
    else:
        assert "gate" in spec, f"{pid} missing gate"
print("ok")
PY
  [ "$status" -eq 0 ]
}

@test "phases.yaml: implement supports iteration AND fanout" {
  run python3 - "$PLUGIN_DIR/phases.yaml" <<'PY'
import sys, yaml
imp = yaml.safe_load(open(sys.argv[1]))["phases"]["implement"]
assert imp.get("supports_iteration") is True
assert imp.get("allows_fanout") is True
assert imp.get("dual_mode_compatible") is True
print("ok")
PY
  [ "$status" -eq 0 ]
}

@test "phases.yaml: design has dual_mode_compatible" {
  run python3 - "$PLUGIN_DIR/phases.yaml" <<'PY'
import sys, yaml
des = yaml.safe_load(open(sys.argv[1]))["phases"]["design"]
assert des.get("dual_mode_compatible") is True
print("ok")
PY
  [ "$status" -eq 0 ]
}

@test "phases.yaml: defines all 7 profiles" {
  run python3 - "$PLUGIN_DIR/phases.yaml" <<'PY'
import sys, yaml
profs = yaml.safe_load(open(sys.argv[1]))["profiles"]
expected = {"feature","hotfix","refactor","test-only","docs","review","design"}
assert set(profs.keys()) == expected, sorted(profs.keys())
for name, spec in profs.items():
    chain = spec["phases"] if isinstance(spec, dict) else spec
    assert chain[-1] == "ship" or chain[-1] in ("accept","ship"), \
        f"{name} chain must end at ship/accept (terminal); got {chain[-1]}"
print("ok")
PY
  [ "$status" -eq 0 ]
}

@test "transitions.yaml loads and defines all 7 profiles + default" {
  run python3 - "$PLUGIN_DIR/transitions.yaml" <<'PY'
import sys, yaml
t = yaml.safe_load(open(sys.argv[1]))["transitions"]
need = {"feature","hotfix","refactor","test-only","docs","review","design","default"}
assert need <= set(t.keys()), sorted(t.keys())
print("ok")
PY
  [ "$status" -eq 0 ]
}

@test "transitions.yaml: every (profile, chain phase, verdict) lookup resolves" {
  run python3 - "$PLUGIN_DIR/phases.yaml" "$PLUGIN_DIR/transitions.yaml" "$TICK_LIB" <<'PY'
import sys, yaml, importlib.util
phases_doc = yaml.safe_load(open(sys.argv[1]))
trans_doc  = yaml.safe_load(open(sys.argv[2]))
spec = importlib.util.spec_from_file_location("_tick", sys.argv[3])
mod  = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
profiles = phases_doc["profiles"]
catalog  = phases_doc["phases"]
verdicts = ["ok","needs_revision","blocked"]
for pname, spec in profiles.items():
    chain = spec["phases"] if isinstance(spec, dict) else spec
    for pid in chain:
        assert pid in catalog, f"{pname} references unknown phase {pid}"
        for v in verdicts:
            nxt = mod.lookup_transition(trans_doc, pid, v, profile=pname)
            assert nxt is not None, f"{pname}: missing transition {pid}/{v}"
            assert nxt == "complete" or nxt in catalog, \
                f"bad target {pname}/{pid}/{v}={nxt}"
print("ok")
PY
  [ "$status" -eq 0 ]
}

@test "transitions.yaml: every profile's terminal phase ok→complete" {
  run python3 - "$PLUGIN_DIR/phases.yaml" "$PLUGIN_DIR/transitions.yaml" "$TICK_LIB" <<'PY'
import sys, yaml, importlib.util
phases_doc = yaml.safe_load(open(sys.argv[1]))
trans_doc  = yaml.safe_load(open(sys.argv[2]))
spec = importlib.util.spec_from_file_location("_tick", sys.argv[3])
mod  = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
for pname, p in phases_doc["profiles"].items():
    chain = p["phases"] if isinstance(p, dict) else p
    last = chain[-1]
    assert mod.lookup_transition(trans_doc, last, "ok", profile=pname) == "complete", \
        f"{pname}: terminal {last}.ok must lead to complete"
print("ok")
PY
  [ "$status" -eq 0 ]
}

@test "entry-questions.yaml loads and covers all 11 catalogue phases" {
  run python3 - "$PLUGIN_DIR/entry-questions.yaml" <<'PY'
import sys, yaml
doc = yaml.safe_load(open(sys.argv[1]))
expected = {"clarify","design","plan","implement","build","review",
            "submit","test-plan","test","accept","ship"}
for p in expected:
    assert p in doc, f"missing entry-question stanza: {p}"
    assert isinstance(doc[p].get("required", []), list)
assert "dual_mode" in doc["clarify"]["required"]
imp = doc["implement"]["required"]
assert "dual_mode" in imp and "max_iterations" in imp and "target_dir" in imp
print("ok")
PY
  [ "$status" -eq 0 ]
}

@test "hitl-gates.yaml: every gate referenced from phases.yaml is defined" {
  run python3 - "$PLUGIN_DIR/phases.yaml" "$PLUGIN_DIR/hitl-gates.yaml" <<'PY'
import sys, yaml
phases = yaml.safe_load(open(sys.argv[1]))["phases"]
gates = yaml.safe_load(open(sys.argv[2])).get("gates", {})
referenced = {spec["gate"] for spec in phases.values() if spec.get("gate")}
for g in referenced:
    assert g in gates, f"phases.yaml references undefined gate: {g}"
    assert "trigger" in gates[g], g
    assert "required_reviewers" in gates[g], g
# v0.2.0 removes pre_test_review; assert it's gone
assert "pre_test_review" not in gates
print("ok")
PY
  [ "$status" -eq 0 ]
}

@test "hitl-gates.yaml: defines exactly the 10 v0.2.0 gates" {
  run python3 - "$PLUGIN_DIR/hitl-gates.yaml" <<'PY'
import sys, yaml
gates = yaml.safe_load(open(sys.argv[1])).get("gates", {})
expected = {
    "requirements_signoff","design_signoff","plan_signoff","build_signoff",
    "local_review_signoff","submit_signoff","test_plan_signoff",
    "test_signoff","acceptance","ship_signoff",
}
assert set(gates.keys()) == expected, sorted(gates.keys())
print("ok")
PY
  [ "$status" -eq 0 ]
}
