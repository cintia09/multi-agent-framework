#!/usr/bin/env bats
# M7 writing U3 -- plugin.yaml + config-defaults.yaml + config-schema.yaml

load helpers/load
load helpers/assertions

PLUGIN_DIR="$CORE_ROOT/../../plugins/writing"
SCHEMA_GATE="$CORE_ROOT/skills/builtin/plugin-schema/schema-check.sh"
ID_GATE="$CORE_ROOT/skills/builtin/plugin-id-validate/id-validate.sh"
VER_GATE="$CORE_ROOT/skills/builtin/plugin-version-check/version-check.sh"
DEPS_GATE="$CORE_ROOT/skills/builtin/plugin-deps-check/deps-check.sh"
CORE_VERSION="$(cat "$CORE_ROOT/../../VERSION" | tr -d '[:space:]')"

@test "writing plugin.yaml exposes M2 + v6 contract fields" {
  run python3 - "$PLUGIN_DIR/plugin.yaml" <<'PY'
import sys, yaml
d = yaml.safe_load(open(sys.argv[1]))
assert d["id"] == "writing"
assert d["version"] == "0.1.1"
assert d["type"] == "domain"
assert isinstance(d["entry_points"], dict) and d["entry_points"]
assert isinstance(d["declared_subsystems"], list) and d["declared_subsystems"]
assert d["requires"]["core_version"].startswith(">=0.5.0-m5")
assert d["name"] == "writing"
assert "writing" in d["applies_to"]
assert d["routing"]["priority"] == 50
for k in ("article","blog","essay"):
    assert k in d["keywords"], k
assert d["entry_point"] == "phases.yaml"
assert d["config"]["schema"] == "config-schema.yaml"
assert d["config"]["defaults"] == "config-defaults.yaml"
print("ok")
PY
  [ "$status" -eq 0 ]
}

@test "writing config-defaults.yaml: every model leaf is a tier_* symbol" {
  run python3 - "$PLUGIN_DIR/config-defaults.yaml" <<'PY'
import sys, yaml
d = yaml.safe_load(open(sys.argv[1]))
TIERS = {"tier_strong","tier_balanced","tier_cheap"}
for role, val in d["models"].items():
    assert val in TIERS, f"{role} = {val!r}"
assert d["hitl"]["gates"] == ["pre_publish"]
print("ok")
PY
  [ "$status" -eq 0 ]
}

@test "writing config-schema.yaml is loadable as the M5 DSL" {
  run python3 - "$PLUGIN_DIR/config-schema.yaml" <<'PY'
import sys, yaml
d = yaml.safe_load(open(sys.argv[1]))
assert "fields" in d
def walk(node):
    if not isinstance(node, dict): return
    for k, spec in node.items():
        assert isinstance(spec, dict), k
        assert "type" in spec, k
        if spec["type"] == "object" and "fields" in spec:
            walk(spec["fields"])
walk(d["fields"])
print("ok")
PY
  [ "$status" -eq 0 ]
}

@test "M2 G02 plugin-schema accepts writing" {
  run_with_stderr "\"$SCHEMA_GATE\" --src \"$PLUGIN_DIR\" --json"
  [ "$status" -eq 0 ]
  echo "$output" | grep -q '"ok": *true'
}

@test "M2 G03 plugin-id-validate accepts id=writing" {
  run_with_stderr "\"$ID_GATE\" --src \"$PLUGIN_DIR\" --json"
  [ "$status" -eq 0 ]
  echo "$output" | grep -q '"ok": *true'
}

@test "M2 G04 plugin-version-check accepts writing 0.1.0" {
  run_with_stderr "\"$VER_GATE\" --src \"$PLUGIN_DIR\" --json"
  [ "$status" -eq 0 ]
  echo "$output" | grep -q '"ok": *true'
}

@test "M2 G06 plugin-deps-check accepts writing core_version range" {
  CN_SRC="$PLUGIN_DIR" CN_CORE_VERSION="$CORE_VERSION" CN_JSON=1 \
    run python3 "$CORE_ROOT/skills/builtin/plugin-deps-check/_deps_check.py"
  [ "$status" -eq 0 ]
  echo "$output" | grep -q '"ok": *true'
}
