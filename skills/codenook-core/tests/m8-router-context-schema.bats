#!/usr/bin/env bats
# M8.1 Unit 1 — router-agent schemas (M5 YAML DSL).
#
# Each schema file:
#   - loads via PyYAML
#   - is structurally a valid M5 DSL schema (top-level `fields:` mapping;
#     each leaf field declares a supported `type`)
#
# The supported M5 DSL grammar is the same one config-validate accepts
# (skills/builtin/config-validate/_validate.py): types in
# {string,integer,boolean,number,array,object}, plus required, enum,
# min, min_length, and nested `fields:` for objects.

load helpers/load
load helpers/assertions

SCHEMAS_DIR="$CORE_ROOT/skills/builtin/router-agent/schemas"

SCHEMA_FILES=(
  "router-context.frontmatter.yaml"
  "draft-config.yaml.schema.yaml"
  "router-reply.frontmatter.yaml"
  "router-lock.json.schema.yaml"
)

@test "M8.1 schemas dir contains all four schema files" {
  for f in "${SCHEMA_FILES[@]}"; do
    assert_file_exists "$SCHEMAS_DIR/$f"
  done
}

@test "M8.1 every schema loads as a YAML mapping" {
  for f in "${SCHEMA_FILES[@]}"; do
    run python3 -c "
import sys, yaml
with open('$SCHEMAS_DIR/$f') as h: d = yaml.safe_load(h)
assert isinstance(d, dict), 'not a mapping'
assert 'fields' in d, 'missing top-level fields:'
assert isinstance(d['fields'], dict), 'fields is not a mapping'
print('OK')
"
    [ "$status" -eq 0 ] || { echo "schema $f: $output"; return 1; }
    assert_contains "$output" "OK"
  done
}

@test "M8.1 every schema is a valid M5 DSL schema (recursive grammar check)" {
  for f in "${SCHEMA_FILES[@]}"; do
    run python3 - "$SCHEMAS_DIR/$f" <<'PY'
import sys, yaml
ALLOWED_TYPES = {"string","integer","boolean","number","array","object"}
ALLOWED_KEYS  = {"type","required","enum","min","min_length","fields","items"}

def check_field(spec, path):
    if not isinstance(spec, dict):
        raise AssertionError(f"{path}: field spec must be a mapping, got {type(spec).__name__}")
    extras = set(spec.keys()) - ALLOWED_KEYS
    assert not extras, f"{path}: unknown keys {sorted(extras)}"
    t = spec.get("type")
    assert t in ALLOWED_TYPES, f"{path}: type {t!r} not in {sorted(ALLOWED_TYPES)}"
    if "enum" in spec:
        assert isinstance(spec["enum"], list) and spec["enum"], f"{path}: enum must be non-empty list"
    if "required" in spec:
        assert isinstance(spec["required"], bool), f"{path}: required must be bool"
    if t == "object" and "fields" in spec:
        for k, v in spec["fields"].items():
            check_field(v, f"{path}.{k}")
    if t == "array" and "items" in spec:
        check_field(spec["items"], f"{path}[]")

with open(sys.argv[1]) as h:
    schema = yaml.safe_load(h)
assert isinstance(schema, dict), "schema not a mapping"
assert "fields" in schema, "missing top-level fields:"
assert isinstance(schema["fields"], dict), "fields is not a mapping"
for name, spec in schema["fields"].items():
    check_field(spec, name)
print("VALID")
PY
    [ "$status" -eq 0 ] || { echo "schema $f INVALID: $output"; return 1; }
    assert_contains "$output" "VALID"
  done
}

@test "M8.1 router-context frontmatter schema declares the §4.1 required keys" {
  run python3 -c "
import yaml
with open('$SCHEMAS_DIR/router-context.frontmatter.yaml') as h: s = yaml.safe_load(h)
need = {'task_id','created_at','started_at','state','turn_count','draft_config_path','selected_plugin','decisions'}
have = {k for k,v in s['fields'].items() if v.get('required')}
missing = need - have
assert not missing, f'missing required: {missing}'
assert s['fields']['state']['enum'] == ['drafting','confirmed','cancelled']
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "M8.1 draft-config schema enforces _draft sentinel and tier-only models" {
  run python3 -c "
import yaml
with open('$SCHEMAS_DIR/draft-config.yaml.schema.yaml') as h: s = yaml.safe_load(h)
fs = s['fields']
assert fs['_draft']['type'] == 'boolean' and fs['_draft'].get('required'), '_draft must be required boolean'
assert fs['plugin'].get('required'), 'plugin must be required'
assert fs['input'].get('required'), 'input must be required'
mod = fs['models']['fields']
for role, spec in mod.items():
    assert spec['enum'] == ['tier_strong','tier_balanced','tier_cheap'], role
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "M8.1 router-reply schema declares optional awaiting enum" {
  run python3 -c "
import yaml
with open('$SCHEMAS_DIR/router-reply.frontmatter.yaml') as h: s = yaml.safe_load(h)
a = s['fields']['awaiting']
assert a['type'] == 'string'
assert not a.get('required'), 'awaiting must be optional'
assert a['enum'] == ['confirmation','clarification','target_dir','cancel_ack','none']
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "M8.1 router-lock schema describes pid hostname started_at task_id payload" {
  run python3 -c "
import yaml
with open('$SCHEMAS_DIR/router-lock.json.schema.yaml') as h: s = yaml.safe_load(h)
fs = s['fields']
for k in ('pid','hostname','started_at','task_id'):
    assert fs[k].get('required'), k + ' must be required'
assert fs['pid']['type'] == 'integer' and fs['pid']['min'] == 1
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "M8.10 draft-config schema declares selected_plugins + role_constraints" {
  run python3 -c "
import yaml
with open('$SCHEMAS_DIR/draft-config.yaml.schema.yaml') as h: s = yaml.safe_load(h)
fs = s['fields']
assert fs['selected_plugins']['type'] == 'array'
assert fs['selected_plugins']['items']['type'] == 'string'
rc = fs['role_constraints']
assert rc['type'] == 'object'
for k in ('included','excluded'):
    assert rc['fields'][k]['type'] == 'array'
    item = rc['fields'][k]['items']
    assert item['type'] == 'object'
    for sub in ('plugin','role'):
        assert item['fields'][sub].get('required'), sub
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}
