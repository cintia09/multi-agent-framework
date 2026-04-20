#!/usr/bin/env bats
# M6 U3 — plugin.yaml + config-defaults.yaml + config-schema.yaml
#
# Cross-checks the development plugin's manifest, defaults, and field-
# level schema against:
#   * M2 install pipeline gates (G02 plugin-schema, G03 plugin-id-validate,
#     G04 plugin-version-check, G06 plugin-deps-check)
#   * M5 config-validate's YAML DSL (so schema can actually validate
#     a merged config tree)

load helpers/load
load helpers/assertions

PLUGIN_DIR="$CORE_ROOT/../../plugins/development"
SCHEMA_GATE="$CORE_ROOT/skills/builtin/plugin-schema/schema-check.sh"
SCHEMA_YAML="$CORE_ROOT/skills/builtin/plugin-schema/plugin-schema.yaml"
ID_GATE="$CORE_ROOT/skills/builtin/plugin-id-validate/id-validate.sh"
VER_GATE="$CORE_ROOT/skills/builtin/plugin-version-check/version-check.sh"
DEPS_GATE="$CORE_ROOT/skills/builtin/plugin-deps-check/deps-check.sh"
CORE_VERSION="$(cat "$CORE_ROOT/../../VERSION" | tr -d '[:space:]')"

@test "plugin.yaml loads and exposes both M2 + v6 contract fields" {
  run python3 - "$PLUGIN_DIR/plugin.yaml" <<'PY'
import sys, yaml
d = yaml.safe_load(open(sys.argv[1]))
# M2 contract
assert d["id"] == "development"
assert d["version"] == "0.2.0"
assert d["type"] == "domain"
assert isinstance(d["entry_points"], dict) and d["entry_points"]
assert isinstance(d["declared_subsystems"], list) and d["declared_subsystems"]
assert d["requires"]["core_version"].startswith(">=0.5.0-m5")
# v6 surface
assert d["name"] == "development"
assert "software-engineering" in d["applies_to"]
assert d["codenook_core_version"].startswith(">=0.5.0-m5")
for k in ("supports_dual_mode","supports_fanout","supports_concurrency"):
    assert d[k] is True, k
assert d["entry_point"] == "phases.yaml"
assert d["config"]["schema"] == "config-schema.yaml"
assert d["config"]["defaults"] == "config-defaults.yaml"
print("ok")
PY
  [ "$status" -eq 0 ]
}

@test "config-defaults.yaml: every model leaf is a tier_* symbol" {
  run python3 - "$PLUGIN_DIR/config-defaults.yaml" <<'PY'
import sys, yaml
d = yaml.safe_load(open(sys.argv[1]))
TIERS = {"tier_strong","tier_balanced","tier_cheap"}
for role, val in d["models"].items():
    assert val in TIERS, f"{role} = {val!r} (must be one of {TIERS})"
print("ok")
PY
  [ "$status" -eq 0 ]
}

@test "config-schema.yaml is loadable as the M5 DSL" {
  run python3 - "$PLUGIN_DIR/config-schema.yaml" <<'PY'
import sys, yaml
d = yaml.safe_load(open(sys.argv[1]))
assert "fields" in d and isinstance(d["fields"], dict)
# M5 DSL invariants: each leaf must declare a `type`
def walk(node):
    if not isinstance(node, dict): return
    for k, spec in node.items():
        assert isinstance(spec, dict), f"{k} not mapping"
        assert "type" in spec, f"{k} missing type"
        if spec["type"] == "object" and "fields" in spec:
            walk(spec["fields"])
walk(d["fields"])
print("ok")
PY
  [ "$status" -eq 0 ]
}

@test "M2 G02 plugin-schema accepts the manifest" {
  run_with_stderr "\"$SCHEMA_GATE\" --src \"$PLUGIN_DIR\" --json"
  [ "$status" -eq 0 ]
  echo "$output" | grep -q '"ok": *true'
}

@test "M2 G03 plugin-id-validate accepts id=development" {
  run_with_stderr "\"$ID_GATE\" --src \"$PLUGIN_DIR\" --json"
  [ "$status" -eq 0 ]
  echo "$output" | grep -q '"ok": *true'
}

@test "M2 G04 plugin-version-check accepts version 0.2.0" {
  run_with_stderr "\"$VER_GATE\" --src \"$PLUGIN_DIR\" --json"
  [ "$status" -eq 0 ]
  echo "$output" | grep -q '"ok": *true'
}

@test "M2 G06 plugin-deps-check accepts the core_version range" {
  CN_SRC="$PLUGIN_DIR" CN_CORE_VERSION="$CORE_VERSION" CN_JSON=1 \
    run python3 "$CORE_ROOT/skills/builtin/plugin-deps-check/_deps_check.py"
  [ "$status" -eq 0 ]
  echo "$output" | grep -q '"ok": *true'
}
