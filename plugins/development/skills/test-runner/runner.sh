#!/usr/bin/env bash
# test-runner/runner.sh — workspace-agnostic test dispatcher.
#
# v0.4 — three-tier lookup:
#   1. Marker detection inside <target-dir> (pyproject.toml / package.json
#      / go.mod) → run the recognised local runner. Unchanged from v0.3.
#   2. When markers fail OR --config <yaml> is provided, source the
#      command + verdict-criterion from a workspace-supplied config
#      (typically resolved from memory by the role calling this skill —
#      e.g. <codenook> knowledge search "test-runner-config target=foo").
#   3. When neither yields a runnable command, emit a JSON envelope
#      flagged "needs_user_config":true and exit code 3 — the calling
#      role (tester / test-planner) is then expected to ask the user
#      via HITL and either pass --config back into the next call or
#      promote the answer into memory for future reuse.
#
# This script never hard-codes device / simulator semantics: ADB, QEMU,
# SSH-into-board, JTAG fixtures, etc. all flow through tier 2 (a config
# describing the command line + pass criterion). The user's environment
# is the source of truth, asked once and remembered via memory.
#
# Spec: see SKILL.md in this directory.
set -euo pipefail

TARGET=""
JSON="0"
CONFIG=""
while [ $# -gt 0 ]; do
  case "$1" in
    --target-dir)
      [ $# -ge 2 ] || { echo "runner.sh: --target-dir requires a value" >&2; exit 2; }
      TARGET="$2"; shift 2 ;;
    --config)
      [ $# -ge 2 ] || { echo "runner.sh: --config requires a value" >&2; exit 2; }
      CONFIG="$2"; shift 2 ;;
    --json)        JSON="1"; shift ;;
    -h|--help)     sed -n '1,80p' "$(dirname "$0")/SKILL.md"; exit 0 ;;
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
  # emit <ok> <runner> <exit_code> <duration_ms> [<extra_kv_pairs...>]
  local ok="$1" runner="$2" code="$3" dur="$4"; shift 4
  if [ "$JSON" = "1" ]; then
    local extra=""
    while [ $# -gt 0 ]; do extra="$extra,$1"; shift; done
    printf '{"ok":%s,"runner":"%s","exit_code":%s,"duration_ms":%s%s}\n' \
      "$ok" "$runner" "$code" "$dur" "$extra"
  fi
}

start_ms=$(python3 -c 'import time;print(int(time.time()*1000))')

# ── tier 2: --config <yaml|sh> overrides marker detection ────────────
if [ -n "$CONFIG" ]; then
  if [ ! -f "$CONFIG" ]; then
    echo "runner.sh: --config not found: $CONFIG" >&2
    exit 2
  fi
  # The config is sourced as a shell snippet; it MUST set:
  #   TEST_CMD       — full command line to run
  # and MAY set:
  #   TEST_LABEL     — display name (default: "custom")
  #   PASS_CRITERION — "exit0" (default), or "regex:<pattern>"
  TEST_CMD=""
  TEST_LABEL="custom"
  PASS_CRITERION="exit0"
  # shellcheck source=/dev/null
  . "$CONFIG"
  if [ -z "$TEST_CMD" ]; then
    echo "runner.sh: --config did not define TEST_CMD" >&2
    exit 2
  fi
  set +e
  if [ "$PASS_CRITERION" = "exit0" ]; then
    ( cd "$TARGET" && eval "$TEST_CMD" ) >&2
    rc=$?
  else
    out=$( cd "$TARGET" && eval "$TEST_CMD" 2>&1 )
    rc=$?
    pat="${PASS_CRITERION#regex:}"
    if echo "$out" | grep -Eq "$pat"; then rc=0; else rc=1; fi
    echo "$out" >&2
  fi
  set -e
  end_ms=$(python3 -c 'import time;print(int(time.time()*1000))')
  if [ "$rc" -eq 0 ]; then emit true  "$TEST_LABEL" "$rc" $((end_ms - start_ms)) '"source":"config"'
  else                      emit false "$TEST_LABEL" "$rc" $((end_ms - start_ms)) '"source":"config"'; fi
  exit "$rc"
fi

# ── tier 1: marker-based local runner detection (legacy v0.3) ────────
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
      emit false "pytest" 2 $((end_ms - start_ms)) '"source":"marker"'
      echo "runner.sh: pytest not installed" >&2
      exit 2
    fi
    set +e; ( cd "$TARGET" && pytest -q ) >&2; rc=$?; set -e
    end_ms=$(python3 -c 'import time;print(int(time.time()*1000))')
    if [ "$rc" -eq 0 ]; then emit true  "pytest" "$rc" $((end_ms - start_ms)) '"source":"marker"'
    else                      emit false "pytest" "$rc" $((end_ms - start_ms)) '"source":"marker"'; fi
    exit "$rc"
    ;;
  npm)
    set +e; ( cd "$TARGET" && npm test --silent ) >/dev/null 2>&1; rc=$?; set -e
    end_ms=$(python3 -c 'import time;print(int(time.time()*1000))')
    if [ "$rc" -eq 0 ]; then emit true  "npm" "$rc" $((end_ms - start_ms)) '"source":"marker"'
    else                      emit false "npm" "$rc" $((end_ms - start_ms)) '"source":"marker"'; fi
    exit "$rc"
    ;;
  go)
    set +e; ( cd "$TARGET" && go test ./... ) >/dev/null 2>&1; rc=$?; set -e
    end_ms=$(python3 -c 'import time;print(int(time.time()*1000))')
    if [ "$rc" -eq 0 ]; then emit true  "go" "$rc" $((end_ms - start_ms)) '"source":"marker"'
    else                      emit false "go" "$rc" $((end_ms - start_ms)) '"source":"marker"'; fi
    exit "$rc"
    ;;
  none)
    # ── tier 3: nothing local, no config — caller must ask user ──────
    end_ms=$(python3 -c 'import time;print(int(time.time()*1000))')
    emit false "none" 3 $((end_ms - start_ms)) '"source":"none"' '"needs_user_config":true'
    cat >&2 <<EOF
runner.sh: no recognised runner inside "$TARGET" (no pyproject.toml /
package.json / go.mod) and no --config was supplied. The calling role
should:
  1. Search memory:
       <codenook> knowledge search "test-runner-config target=$(basename "$TARGET")"
       <codenook> knowledge search "test-environment <repo or device hint>"
  2. If a memory entry is found, write its TEST_CMD + PASS_CRITERION
     to a temp file and re-invoke with --config <file>.
  3. Otherwise, ask the user (via HITL ask_user) for:
       - the test command line (e.g. "ssh dut@10.0.0.5 'pytest /opt/app'")
       - the pass criterion ("exit0" or "regex:<pattern>")
     Optionally promote the answer to
     .codenook/memory/knowledge/test-runner-config-<slug>/index.md so
     the next run finds it without asking.
EOF
    exit 3
    ;;
esac


