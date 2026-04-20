#!/usr/bin/env bats
# M6 U4 — roles/*.md (8 role profiles)

load helpers/load
load helpers/assertions

ROLES_DIR="$CORE_ROOT/../../plugins/development/roles"
ROLE_NAMES="clarifier designer planner implementer builder reviewer submitter test-planner tester acceptor"

@test "all 10 role files exist" {
  for r in $ROLE_NAMES; do
    [ -f "$ROLES_DIR/$r.md" ] || { echo "missing $r.md" >&2; return 1; }
  done
}

@test "each role file has at least 10 non-blank lines" {
  for r in $ROLE_NAMES; do
    n=$(grep -c '[^[:space:]]' "$ROLES_DIR/$r.md")
    [ "$n" -ge 10 ] || { echo "$r.md only $n non-blank lines" >&2; return 1; }
  done
}

@test "each role file has YAML frontmatter naming the role" {
  for r in $ROLE_NAMES; do
    head -10 "$ROLES_DIR/$r.md" | grep -q "^name: $r$" \
      || { echo "$r.md missing 'name: $r' frontmatter" >&2; return 1; }
  done
}

@test "no role references v5 home-dir path ~/.codenook" {
  for r in $ROLE_NAMES; do
    if grep -q '~/\.codenook' "$ROLES_DIR/$r.md"; then
      echo "$r.md still references ~/.codenook" >&2
      return 1
    fi
  done
}

@test "no role references v5 templates/ path" {
  for r in $ROLE_NAMES; do
    # Allow .codenook/plugins/development/... but not bare templates/
    if grep -E "(^|[^./])templates/" "$ROLES_DIR/$r.md" >/dev/null; then
      echo "$r.md still references templates/" >&2
      grep -nE "(^|[^./])templates/" "$ROLES_DIR/$r.md" >&2
      return 1
    fi
  done
}

@test "every role file is reachable from phases.yaml roles" {
  PHASES="$CORE_ROOT/../../plugins/development/phases.yaml"
  run python3 - "$PHASES" "$ROLES_DIR" <<'PY'
import sys, yaml, os
doc = yaml.safe_load(open(sys.argv[1]))
phases = doc["phases"]
# v0.2.0 catalogue is a map; v0.1.x was a list — support both.
items = phases.values() if isinstance(phases, dict) else phases
for p in items:
    role = p["role"]
    assert os.path.isfile(f"{sys.argv[2]}/{role}.md"), f"missing role file: {role}"
print("ok")
PY
  [ "$status" -eq 0 ]
}
