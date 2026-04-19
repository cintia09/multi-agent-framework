#!/usr/bin/env bats
# M9.8 fix-r2 — plugin_readonly.py --exclude regression.
# Verifies:
#   1. Default excludes skip files under tests/fixtures/** so the
#      shipped pre-commit hook does not flag the very fixtures used to
#      test the static checker.
#   2. --exclude PATTERN augments the defaults.
#   3. --no-default-excludes restores the legacy "scan everything"
#      behaviour.

load helpers/load

CHECKER="$CORE_ROOT/skills/builtin/_lib/plugin_readonly.py"

setup() {
  WS="$(make_scratch)"
  mkdir -p "$WS/tests/fixtures" "$WS/src" "$WS/legacy"
  # Fixture-style file (intentionally writes plugins/ — must be ignored
  # by default).
  cat >"$WS/tests/fixtures/foo.py" <<'PY'
from pathlib import Path
def bad():
    Path("plugins/sub/bar.yaml").write_text("nope")
PY
  # Real source-tree file (must always be reported).
  cat >"$WS/src/foo.py" <<'PY'
def bad():
    open("plugins/foo.txt", "w").write("nope")
PY
  # A second tree we will only exclude in test #2.
  cat >"$WS/legacy/old.py" <<'PY'
from pathlib import Path
def bad():
    Path("plugins/legacy.yaml").write_text("nope")
PY
}

@test "[m9.8] plugin_readonly defaults skip tests/fixtures/** (only src/ reported)" {
  run python3 "$CHECKER" --target "$WS" --json
  [ "$status" -ne 0 ] || { echo "expected non-zero, got 0; out=$output"; return 1; }
  echo "$output" | python3 -c '
import json, sys
d = json.loads(sys.stdin.read())
files = sorted({h["file"] for h in d["writes_to_plugins"]})
joined = "\n".join(files)
assert any(f.endswith("/src/foo.py") for f in files), files
assert not any("/tests/fixtures/" in f for f in files), files
# legacy/ is not excluded by defaults — still reported.
assert any(f.endswith("/legacy/old.py") for f in files), files
'
}

@test "[m9.8] --exclude '**/legacy/**' adds an additional exclusion (defaults still apply)" {
  run python3 "$CHECKER" --target "$WS" --exclude '**/legacy/**' --json
  [ "$status" -ne 0 ] || { echo "expected non-zero, got 0; out=$output"; return 1; }
  echo "$output" | python3 -c '
import json, sys
d = json.loads(sys.stdin.read())
files = sorted({h["file"] for h in d["writes_to_plugins"]})
assert any(f.endswith("/src/foo.py") for f in files), files
assert not any("/tests/fixtures/" in f for f in files), files
assert not any("/legacy/" in f for f in files), files
'
}

@test "[m9.8] --no-default-excludes restores legacy behaviour (fixtures flagged)" {
  run python3 "$CHECKER" --target "$WS" --no-default-excludes --json
  [ "$status" -ne 0 ] || { echo "expected non-zero, got 0; out=$output"; return 1; }
  echo "$output" | python3 -c '
import json, sys
d = json.loads(sys.stdin.read())
files = sorted({h["file"] for h in d["writes_to_plugins"]})
assert any("/tests/fixtures/" in f for f in files), files
assert any(f.endswith("/src/foo.py") for f in files), files
assert any(f.endswith("/legacy/old.py") for f in files), files
'
}

@test "[m9.8] repo-wide scan with defaults exits 0 (fixtures excluded)" {
  run python3 "$CHECKER" --target "$CORE_ROOT/.." --json
  [ "$status" -eq 0 ] || { echo "out=$output"; return 1; }
}
