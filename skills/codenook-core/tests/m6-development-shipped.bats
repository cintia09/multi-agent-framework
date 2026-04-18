#!/usr/bin/env bats
# M6 U7 — plugin-shipped skill + validators + prompts + knowledge

load helpers/load
load helpers/assertions

PLUGIN_DIR="$CORE_ROOT/../../plugins/development"
RUNNER="$PLUGIN_DIR/skills/test-runner/runner.sh"
POST_IMPL="$PLUGIN_DIR/validators/post-implement.sh"

@test "test-runner skill ships SKILL.md + executable runner.sh" {
  [ -f "$PLUGIN_DIR/skills/test-runner/SKILL.md" ]
  [ -x "$RUNNER" ]
}

@test "validators are present and executable" {
  [ -x "$POST_IMPL" ]
  [ -x "$PLUGIN_DIR/validators/post-test.sh" ]
}

@test "prompts criteria files exist" {
  for f in criteria-implement.md criteria-test.md criteria-accept.md; do
    [ -f "$PLUGIN_DIR/prompts/$f" ] || { echo "missing $f" >&2; return 1; }
  done
}

@test "knowledge/pytest-conventions.md exists" {
  [ -f "$PLUGIN_DIR/knowledge/pytest-conventions.md" ]
}

@test "test-runner: --target-dir required -> exit 2" {
  run_with_stderr "\"$RUNNER\""
  [ "$status" -eq 2 ]
}

@test "test-runner: target dir without recognised marker -> exit 0 (none)" {
  d="$(make_scratch)/empty"
  mkdir -p "$d"
  run_with_stderr "\"$RUNNER\" --target-dir \"$d\" --json"
  [ "$status" -eq 0 ]
  echo "$output" | grep -q '"runner":"none"'
}

@test "test-runner: pytest fixture pass -> exit 0" {
  if ! command -v pytest >/dev/null 2>&1; then skip "pytest not installed"; fi
  d="$(make_scratch)/passing"
  mkdir -p "$d"
  echo > "$d/pyproject.toml"
  cat >"$d/test_ok.py" <<'PY'
def test_ok():
    assert 1 + 1 == 2
PY
  run_with_stderr "\"$RUNNER\" --target-dir \"$d\" --json"
  [ "$status" -eq 0 ]
  echo "$output" | grep -q '"runner":"pytest"'
  echo "$output" | grep -q '"ok":true'
}

@test "test-runner: pytest fixture fail -> exit non-zero" {
  if ! command -v pytest >/dev/null 2>&1; then skip "pytest not installed"; fi
  d="$(make_scratch)/failing"
  mkdir -p "$d"
  echo > "$d/pyproject.toml"
  cat >"$d/test_fail.py" <<'PY'
def test_fail():
    assert 1 + 1 == 3
PY
  run_with_stderr "\"$RUNNER\" --target-dir \"$d\" --json"
  [ "$status" -ne 0 ]
  echo "$output" | grep -q '"ok":false'
}

@test "post-implement.sh: missing output -> exit 1" {
  ws="$(make_scratch)"
  mkdir -p "$ws/.codenook/tasks/T-001/outputs"
  cd "$ws"
  run_with_stderr "\"$POST_IMPL\" T-001"
  [ "$status" -eq 1 ]
}

@test "post-implement.sh: well-formed output -> exit 0" {
  ws="$(make_scratch)"
  out="$ws/.codenook/tasks/T-001/outputs"
  mkdir -p "$out"
  cat >"$out/phase-4-implementer.md" <<'EOF'
verdict: ok
---
body
EOF
  cd "$ws"
  run_with_stderr "\"$POST_IMPL\" T-001"
  [ "$status" -eq 0 ]
}
