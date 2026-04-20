#!/usr/bin/env bats
# M10.5 — render_prompt.py wires {{TASK_CHAIN}} slot to chain_summarize.
# Spec: docs/task-chains.md §7.2
# Cases: docs/m10-test-cases.md TC-M10.5-02..06

load helpers/load
load helpers/assertions
load helpers/m10_chain
load helpers/m9_memory

RENDER_PY="$CORE_ROOT/skills/builtin/router-agent/render_prompt.py"

# Build a workspace with a plugins/ directory so render_prompt's
# plugin scan succeeds (mirrors M9 router tests).
m105_seed_router_ws() {
  local ws
  ws=$(m10_seed_workspace)
  mkdir -p "$ws/.codenook/plugins"
  if [ -d "$FIXTURES_ROOT/m4/plugins/generic" ]; then
    cp -R "$FIXTURES_ROOT/m4/plugins/generic" "$ws/.codenook/plugins/generic"
  fi
  m9_init_memory "$ws" >/dev/null 2>&1 || true
  echo "$ws"
}

# Run render_prompt.py prepare and capture stdout (envelope) + the
# rendered prompt file path.
m105_run_prepare() {
  local tid="$1" ws="$2"; shift 2
  PYTHONPATH="$M10_LIB_DIR" python3 "$RENDER_PY" \
    --task-id "$tid" --workspace "$ws" --user-turn "test turn for $tid" "$@"
}

# ---------------------------------------------------------------- TC-M10.5-02

@test "[m10.5] TC-M10.5-02 parent_id == null → empty TASK_CHAIN, no cs.summarize call" {
  ws=$(m105_seed_router_ws)
  make_task "$ws" T-001
  spy_log="$ws/_cs_calls.log"
  : >"$spy_log"

  # Wrap chain_summarize with a spy that logs each call.
  WRAPPER_DIR="$ws/_wrap"
  mkdir -p "$WRAPPER_DIR"
  cat >"$WRAPPER_DIR/sitecustomize.py" <<PY
import os, sys
sys.path.insert(0, os.environ["M10_LIB_DIR"])
import chain_summarize as _cs
_orig = _cs.summarize
def _spy(*a, **kw):
    open(os.environ["CS_SPY_LOG"], "a").write("call\n")
    return _orig(*a, **kw)
_cs.summarize = _spy
PY

  run env PYTHONPATH="$WRAPPER_DIR:$M10_LIB_DIR" \
      M10_LIB_DIR="$M10_LIB_DIR" CS_SPY_LOG="$spy_log" \
      python3 "$RENDER_PY" --task-id T-001 --workspace "$ws" --user-turn "hello"
  [ "$status" -eq 0 ] || { echo "exit $status: $output"; return 1; }

  prompt="$ws/.codenook/tasks/T-001/.router-prompt.md"
  [ -f "$prompt" ] || { echo "prompt not written"; return 1; }
  ! grep -q '{{TASK_CHAIN}}' "$prompt" || { echo "raw slot left in prompt"; return 1; }
  ! grep -q '## TASK_CHAIN (M10)' "$prompt" || { echo "TASK_CHAIN section unexpectedly present"; return 1; }
  grep -q 'MEMORY_INDEX' "$prompt" || { echo "MEMORY_INDEX missing"; return 1; }

  n=$(wc -l <"$spy_log" | tr -d ' ')
  [ "$n" -eq 0 ] || { echo "cs.summarize called $n times, expected 0"; return 1; }
}

# ---------------------------------------------------------------- TC-M10.5-03

@test "[m10.5] TC-M10.5-03 parent_id set → chain_summarize invoked, output substituted above MEMORY_INDEX" {
  ws=$(m105_seed_router_ws)
  mock="$ws/_mock"
  make_chain "$ws" T-007 T-012
  seed_mock_llm "$mock" chain_summarize "MARKER_FROM_FIXTURE_2025"

  spy_log="$ws/_cs_calls.log"
  : >"$spy_log"
  WRAPPER_DIR="$ws/_wrap"
  mkdir -p "$WRAPPER_DIR"
  cat >"$WRAPPER_DIR/sitecustomize.py" <<PY
import os, sys
sys.path.insert(0, os.environ["M10_LIB_DIR"])
import chain_summarize as _cs
_orig = _cs.summarize
def _spy(*a, **kw):
    open(os.environ["CS_SPY_LOG"], "a").write("call\n")
    return _orig(*a, **kw)
_cs.summarize = _spy
PY

  run env PYTHONPATH="$WRAPPER_DIR:$M10_LIB_DIR" \
      M10_LIB_DIR="$M10_LIB_DIR" CS_SPY_LOG="$spy_log" \
      CN_LLM_MOCK_DIR="$mock" \
      python3 "$RENDER_PY" --task-id T-012 --workspace "$ws" --user-turn "child turn"
  [ "$status" -eq 0 ] || { echo "exit $status: $output"; return 1; }

  prompt="$ws/.codenook/tasks/T-012/.router-prompt.md"
  [ -f "$prompt" ] || { echo "prompt not written"; return 1; }
  grep -q "MARKER_FROM_FIXTURE_2025" "$prompt" || { echo "marker missing in prompt"; return 1; }

  ln_marker=$(grep -n "MARKER_FROM_FIXTURE_2025" "$prompt" | head -1 | cut -d: -f1)
  ln_mi=$(grep -n "MEMORY_INDEX" "$prompt" | head -1 | cut -d: -f1)
  [ "$ln_marker" -lt "$ln_mi" ] || { echo "marker($ln_marker) not above MEMORY_INDEX($ln_mi)"; return 1; }

  n=$(wc -l <"$spy_log" | tr -d ' ')
  [ "$n" -eq 1 ] || { echo "cs.summarize called $n times, expected 1"; return 1; }
}

# ---------------------------------------------------------------- TC-M10.5-04

@test "[m10.5] TC-M10.5-04 TASK_CHAIN + MEMORY_INDEX coexist with M9 router-memory regression intact" {
  ws=$(m105_seed_router_ws)
  mock="$ws/_mock"
  make_chain "$ws" T-007 T-012
  seed_mock_llm "$mock" chain_summarize "## TASK_CHAIN (M10)

### T-007 — feature/auth (phase: implement, status: done)

CHAIN_BODY_M10_5_04
"

  # Seed one matching memory entry so MEMORY_INDEX renders non-empty.
  if declare -F seed_knowledge_aw >/dev/null 2>&1; then
    seed_knowledge_aw "$ws" "auth-jwt" "JWT auth notes" "always" "JWT auth body" || true
  fi

  run env PYTHONPATH="$M10_LIB_DIR" CN_LLM_MOCK_DIR="$mock" \
      python3 "$RENDER_PY" --task-id T-012 --workspace "$ws" --user-turn "child turn"
  [ "$status" -eq 0 ] || { echo "exit $status: $output"; return 1; }

  prompt="$ws/.codenook/tasks/T-012/.router-prompt.md"
  grep -q "## TASK_CHAIN (M10)" "$prompt" || { echo "TASK_CHAIN section missing"; return 1; }
  grep -q "MEMORY_INDEX" "$prompt" || { echo "MEMORY_INDEX missing"; return 1; }

  ln_tc=$(grep -n "## TASK_CHAIN (M10)" "$prompt" | head -1 | cut -d: -f1)
  ln_mi=$(grep -n "MEMORY_INDEX" "$prompt" | head -1 | cut -d: -f1)
  [ "$ln_tc" -lt "$ln_mi" ] || { echo "TASK_CHAIN($ln_tc) not above MEMORY_INDEX($ln_mi)"; return 1; }

  # 20K char ceiling (token ~ char/4 → 80K chars; we use the spec
  # 20480 token cap as a generous char-bound proxy).
  total=$(wc -c <"$prompt" | tr -d ' ')
  [ "$total" -le 81920 ] || { echo "prompt too large: $total chars"; return 1; }
}

# ---------------------------------------------------------------- TC-M10.5-05

@test "[m10.5] TC-M10.5-05 chain_summarize fail → render_prompt exit 0, audit chain_summarize_failed, no plugins/ writes" {
  ws=$(m105_seed_router_ws)
  make_chain "$ws" T-007 T-012

  # Marker file to detect any plugins/ writes.
  marker="$ws/_marker"
  : >"$marker"
  sleep 1

  run env PYTHONPATH="$M10_LIB_DIR" \
      CN_LLM_MOCK_ERROR_CHAIN_SUMMARIZE="forced-fail-m10.5-05" \
      python3 "$RENDER_PY" --task-id T-012 --workspace "$ws" --user-turn "child turn"
  [ "$status" -eq 0 ] || { echo "exit $status: $output"; return 1; }

  prompt="$ws/.codenook/tasks/T-012/.router-prompt.md"
  [ -f "$prompt" ] || { echo "prompt not written"; return 1; }
  ! grep -q '{{TASK_CHAIN}}' "$prompt" || { echo "raw slot left in prompt"; return 1; }
  grep -q "MEMORY_INDEX" "$prompt" || { echo "MEMORY_INDEX missing"; return 1; }
  ! grep -q "## TASK_CHAIN (M10)" "$prompt" || { echo "TASK_CHAIN should be empty on failure"; return 1; }

  assert_audit "$ws" chain_summarize_failed

  # No file under .codenook/plugins/ newer than marker.
  changed=$(find "$ws/.codenook/plugins" -type f -newer "$marker" 2>/dev/null | wc -l | tr -d ' ')
  [ "$changed" -eq 0 ] || { echo "plugins/ files modified: $changed"; return 1; }
}

# ---------------------------------------------------------------- TC-M10.5-06

@test "[m10.5] TC-M10.5-06 prompt size ≤ 20480 tokens with deep chain + full memory" {
  ws=$(m105_seed_router_ws)
  mock="$ws/_mock"

  # depth=12 chain.
  ids=()
  for i in 001 002 003 004 005 006 007 008 009 010 011 012; do
    ids+=("T-$i")
  done
  make_chain "$ws" "${ids[@]}"

  # Mock pass-1/pass-2 chain_summarize body close to 8K tokens (~32K chars)
  # but not over.
  payload=$(python3 -c 'print("x" * 28000, end="")')
  seed_mock_llm "$mock" chain_summarize "## TASK_CHAIN (M10)

$payload"

  run env PYTHONPATH="$M10_LIB_DIR" CN_LLM_MOCK_DIR="$mock" \
      python3 "$RENDER_PY" --task-id T-012 --workspace "$ws" --user-turn "leaf turn"
  [ "$status" -eq 0 ] || { echo "exit $status: $output"; return 1; }

  prompt="$ws/.codenook/tasks/T-012/.router-prompt.md"
  est=$(PYTHONPATH="$M10_LIB_DIR" python3 -c '
import sys, token_estimate as te
print(te.estimate(open(sys.argv[1]).read()))
' "$prompt")
  [ "$est" -le 20480 ] || { echo "prompt over budget: $est tokens"; return 1; }
}
