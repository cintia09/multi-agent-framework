#!/usr/bin/env bash
# test-runner/runner.sh — minimal wrapper that detects pytest / npm /
# go test based on marker files under --target-dir, runs it, and emits
# a JSON envelope (with --json) plus an exit code suitable for the
# tester role to map onto verdict.
#
# Spec: see SKILL.md in this directory.
set -euo pipefail

TARGET=""
JSON="0"
while [ $# -gt 0 ]; do
  case "$1" in
    --target-dir) TARGET="$2"; shift 2 ;;
    --json)       JSON="1"; shift ;;
    -h|--help)    sed -n '1,40p' "$(dirname "$0")/SKILL.md"; exit 0 ;;
    *) echo "runner.sh: unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [ -z "$TARGET" ]; then
  echo "runner.sh: --target-dir required" >&2
  exit 2
fi
if [ ! -d "$TARGET" ]; then
  echo "runner.sh: target dir not found: $TARGET" >&2
  exit 2
fi

emit() {
  local ok="$1" runner="$2" code="$3" dur="$4"
  if [ "$JSON" = "1" ]; then
    printf '{"ok":%s,"runner":"%s","exit_code":%s,"duration_ms":%s}\n' \
      "$ok" "$runner" "$code" "$dur"
  fi
}

start_ms=$(python3 -c 'import time;print(int(time.time()*1000))')

runner="none"
if   [ -f "$TARGET/pyproject.toml" ] \
  || [ -f "$TARGET/setup.py" ] \
  || [ -f "$TARGET/pytest.ini" ] \
  || [ -f "$TARGET/tox.ini" ]; then
  runner="pytest"
elif [ -f "$TARGET/package.json" ]; then
  runner="npm"
elif [ -f "$TARGET/go.mod" ]; then
  runner="go"
fi

case "$runner" in
  pytest)
    if ! command -v pytest >/dev/null 2>&1; then
      end_ms=$(python3 -c 'import time;print(int(time.time()*1000))')
      emit false "pytest" 2 $((end_ms - start_ms))
      echo "runner.sh: pytest not installed" >&2
      exit 2
    fi
    set +e
    ( cd "$TARGET" && pytest -q ) >&2
    rc=$?
    set -e
    end_ms=$(python3 -c 'import time;print(int(time.time()*1000))')
    if [ "$rc" -eq 0 ]; then emit true  "pytest" "$rc" $((end_ms - start_ms))
    else                      emit false "pytest" "$rc" $((end_ms - start_ms)); fi
    exit "$rc"
    ;;
  npm)
    set +e
    ( cd "$TARGET" && npm test --silent ) >/dev/null 2>&1; rc=$?
    set -e
    end_ms=$(python3 -c 'import time;print(int(time.time()*1000))')
    if [ "$rc" -eq 0 ]; then emit true  "npm" "$rc" $((end_ms - start_ms))
    else                      emit false "npm" "$rc" $((end_ms - start_ms)); fi
    exit "$rc"
    ;;
  go)
    set +e
    ( cd "$TARGET" && go test ./... ) >/dev/null 2>&1; rc=$?
    set -e
    end_ms=$(python3 -c 'import time;print(int(time.time()*1000))')
    if [ "$rc" -eq 0 ]; then emit true  "go" "$rc" $((end_ms - start_ms))
    else                      emit false "go" "$rc" $((end_ms - start_ms)); fi
    exit "$rc"
    ;;
  none)
    end_ms=$(python3 -c 'import time;print(int(time.time()*1000))')
    emit true "none" 0 $((end_ms - start_ms))
    echo "runner.sh: no recognised runner (no pyproject.toml/package.json/go.mod)" >&2
    exit 0
    ;;
esac
