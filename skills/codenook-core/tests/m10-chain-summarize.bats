#!/usr/bin/env bats
# M10.4 — _lib/chain_summarize.py two-pass LLM compression (TC-M10.4-01..04, 06..08).
# Spec: docs/v6/task-chains-v6.md §6 §9
# Cases: docs/v6/m10-test-cases.md §M10.4

load helpers/load
load helpers/assertions
load helpers/m10_chain

# ---------------------------------------------------------------- TC-M10.4-01

@test "[m10.4] TC-M10.4-01 single ancestor, fits budget, 1 H3 with state fields" {
  ws=$(m10_seed_workspace)
  mock="$ws/_mock"
  make_ancestor_with_briefs "$ws" T-007 "feature/auth" "implement" "done" "build JWT auth"
  make_task "$ws" T-012
  make_chain "$ws" T-007 T-012  # T-012.parent=T-007
  seed_mock_llm "$mock" chain_summarize $'目标：JWT 登录\n关键决策：bcrypt cost=12\n'

  out=$(PYTHONPATH="$M10_LIB_DIR" CN_LLM_MOCK_DIR="$mock" WS="$ws" python3 -c '
import os, chain_summarize as cs
print(cs.summarize(os.environ["WS"], "T-012"))
')
  echo "$out" | head -1 | grep -qF "## TASK_CHAIN (M10)" || { echo "missing H2; out=$out"; return 1; }
  c=$(echo "$out" | grep -c '^### T-' || true)
  [ "$c" -eq 1 ] || { echo "expected 1 H3, got $c; out=$out"; return 1; }
  echo "$out" | grep -F "T-007" | grep -F "feature/auth" | grep -F "phase: implement" | grep -F "status: done" >/dev/null \
    || { echo "H3 missing fields; out=$out"; return 1; }
  ! echo "$out" | grep -qE 'AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{36}' \
    || { echo "secret leaked; out=$out"; return 1; }
}

# ---------------------------------------------------------------- TC-M10.4-02

@test "[m10.4] TC-M10.4-02 5 ancestors fit budget, 5 LLM calls (no pass-2)" {
  ws=$(m10_seed_workspace)
  mock="$ws/_mock"
  # ~800 token fixture (~3200 chars) for pass-1
  payload=$(python3 -c 'print("x" * 3200, end="")')
  seed_mock_llm "$mock" chain_summarize "$payload"

  # Build chain: T-001 (root) ← T-002 ← ... ← T-006 (leaf)
  for i in 001 002 003 004 005 006; do
    make_ancestor_with_briefs "$ws" "T-$i" "task-$i" "implement" "done" "brief $i"
  done
  PYTHONPATH="$M10_LIB_DIR" WS="$ws" python3 - <<'PY'
import os, task_chain as tc
ws=os.environ["WS"]
for child, parent in [("T-002","T-001"),("T-003","T-002"),("T-004","T-003"),
                      ("T-005","T-004"),("T-006","T-005")]:
    tc.set_parent(ws, child, parent)
PY

  out=$(PYTHONPATH="$M10_LIB_DIR" CN_LLM_MOCK_DIR="$mock" \
        CN_CALL_LOG="$ws/_calls.log" WS="$ws" python3 -c '
import os, chain_summarize as cs, llm_call as L
log = os.environ["CN_CALL_LOG"]
orig = L.call_llm
def spy(prompt, **kw):
    open(log,"a").write(kw.get("call_name","?")+"\n")
    return orig(prompt, **kw)
L.call_llm = spy
cs.call_llm = spy   # in case module imported by name
print(cs.summarize(os.environ["WS"], "T-006"))
')
  [ -n "$out" ] || { echo "empty output"; return 1; }
  c=$(grep -c "chain_summarize" "$ws/_calls.log" || true)
  [ "$c" -eq 5 ] || { echo "expected 5 LLM calls, got $c"; return 1; }
  h3=$(echo "$out" | grep -c '^### T-' || true)
  [ "$h3" -eq 5 ] || { echo "expected 5 H3, got $h3"; return 1; }
  est=$(PYTHONPATH="$M10_LIB_DIR" python3 -c '
import sys, token_estimate as te
print(te.estimate(sys.stdin.read()))
' <<<"$out")
  [ "$est" -le 8192 ] || { echo "exceeds budget: $est"; return 1; }
}

# ---------------------------------------------------------------- TC-M10.4-03

@test "[m10.4] TC-M10.4-03 12 ancestors overflow → pass-2 invoked, newest 3 verbatim" {
  ws=$(m10_seed_workspace)
  mock="$ws/_mock"
  # ~1400 token fixture (~5600 chars). Includes markers tying back to
  # the newest 3 ancestors and a 远祖背景 section, so the pass-2 mock
  # response covers the assertion-required substrings.
  body="### T-013 newest1
content-13
### T-012 newest2
content-12
### T-011 newest3
content-11
## 远祖背景
ancient summary line"
  pad=$(python3 -c 'print("x" * 5400, end="")')
  seed_mock_llm "$mock" chain_summarize "$body
$pad"

  # 13 tasks → leaf T-013 has 12 ancestors after dropping self.
  ids=()
  for i in 001 002 003 004 005 006 007 008 009 010 011 012 013; do
    make_ancestor_with_briefs "$ws" "T-$i" "task-$i" "implement" "done" "brief $i"
    ids+=("T-$i")
  done
  PYTHONPATH="$M10_LIB_DIR" WS="$ws" python3 - <<'PY'
import os, task_chain as tc
ws=os.environ["WS"]
ids=["T-%03d"%i for i in range(1,14)]
for c,p in zip(ids[1:], ids[:-1]):
    tc.set_parent(ws, c, p)
PY

  out=$(PYTHONPATH="$M10_LIB_DIR" CN_LLM_MOCK_DIR="$mock" \
        CN_CALL_LOG="$ws/_calls.log" WS="$ws" python3 -c '
import os, chain_summarize as cs, llm_call as L
log = os.environ["CN_CALL_LOG"]
orig = L.call_llm
def spy(prompt, **kw):
    open(log,"a").write(kw.get("call_name","?")+"\n")
    return orig(prompt, **kw)
L.call_llm = spy
cs.call_llm = spy
print(cs.summarize(os.environ["WS"], "T-013"))
')
  c=$(grep -c "chain_summarize" "$ws/_calls.log" || true)
  [ "$c" -eq 13 ] || { echo "expected 13 (12 pass-1 + 1 pass-2) calls, got $c"; return 1; }
  echo "$out" | grep -qF "T-013" || { echo "missing T-013"; return 1; }
  echo "$out" | grep -qF "T-012" || { echo "missing T-012"; return 1; }
  echo "$out" | grep -qF "T-011" || { echo "missing T-011"; return 1; }
  echo "$out" | grep -qF "远祖背景" || { echo "missing 远祖背景"; return 1; }
  est=$(PYTHONPATH="$M10_LIB_DIR" python3 -c '
import sys, token_estimate as te
print(te.estimate(sys.stdin.read()))
' <<<"$out")
  [ "$est" -le 8192 ] || { echo "exceeds budget: $est"; return 1; }
}

# ---------------------------------------------------------------- TC-M10.4-04

@test "[m10.4] TC-M10.4-04 artifact list shows only existing files" {
  ws=$(m10_seed_workspace)
  mock="$ws/_mock"
  seed_mock_llm "$mock" chain_summarize $'目标：foo\n'
  make_ancestor_with_briefs "$ws" T-007 "feature/auth" "implement" "done" "build it"
  make_task "$ws" T-012
  make_chain "$ws" T-007 T-012
  # T-007: only design.md + decisions.md, no impl-plan / no test
  echo "design content" >"$ws/.codenook/tasks/T-007/design.md"
  echo "decisions content" >"$ws/.codenook/tasks/T-007/decisions.md"
  : >"$ws/.codenook/tasks/T-007/outputs/auth_router.py"
  : >"$ws/.codenook/tasks/T-007/outputs/test_auth.py"

  out=$(PYTHONPATH="$M10_LIB_DIR" CN_LLM_MOCK_DIR="$mock" WS="$ws" python3 -c '
import os, chain_summarize as cs
print(cs.summarize(os.environ["WS"], "T-012"))
')
  echo "$out" | grep -qF "**产物**:" || { echo "missing 产物 header; out=$out"; return 1; }
  echo "$out" | grep -qF "outputs/auth_router.py" || { echo "missing auth_router.py"; return 1; }
  echo "$out" | grep -qF "outputs/test_auth.py" || { echo "missing test_auth.py"; return 1; }
  echo "$out" | grep -qF "design.md" || { echo "missing design.md"; return 1; }
  echo "$out" | grep -qF "decisions.md" || { echo "missing decisions.md"; return 1; }
  ! echo "$out" | grep -qF "impl-plan.md" || { echo "impl-plan.md should not appear"; return 1; }
  ! echo "$out" | grep -qF "test.md" || { echo "test.md should not appear"; return 1; }
  # Cap is 20 (spec §6.3); not exceeded here.
  n=$(echo "$out" | sed -n '/\*\*产物\*\*:/,/^$/p' | grep -c '^- ' || true)
  [ "$n" -le 20 ] || { echo "artifact cap exceeded: $n"; return 1; }
}

# ---------------------------------------------------------------- TC-M10.4-06

@test "[m10.4] TC-M10.4-06 mock resolution priority (file > env > global)" {
  ws=$(m10_seed_workspace)
  mock="$ws/_mock"
  make_ancestor_with_briefs "$ws" T-007 "feat" "implement" "done" "x"
  make_task "$ws" T-012
  make_chain "$ws" T-007 T-012

  # 1) fixture file wins
  seed_mock_llm "$mock" chain_summarize "FIXTURE_PASS1_RESPONSE"
  out=$(PYTHONPATH="$M10_LIB_DIR" CN_LLM_MOCK_DIR="$mock" WS="$ws" python3 -c '
import os, chain_summarize as cs
print(cs.summarize(os.environ["WS"], "T-012"))
')
  echo "$out" | grep -qF "FIXTURE_PASS1_RESPONSE" || { echo "fixture priority broken"; return 1; }

  # 2) remove fixture, env var should win
  rm "$mock/chain_summarize.txt"
  out=$(PYTHONPATH="$M10_LIB_DIR" CN_LLM_MOCK_DIR="$mock" \
        CN_LLM_MOCK_CHAIN_SUMMARIZE="ENV_RESPONSE" WS="$ws" python3 -c '
import os, chain_summarize as cs
print(cs.summarize(os.environ["WS"], "T-012"))
')
  echo "$out" | grep -qF "ENV_RESPONSE" || { echo "env priority broken; out=$out"; return 1; }

  # 3) global fallback
  out=$(PYTHONPATH="$M10_LIB_DIR" \
        CN_LLM_MOCK_RESPONSE="GLOBAL_FALLBACK" WS="$ws" python3 -c '
import os, chain_summarize as cs
print(cs.summarize(os.environ["WS"], "T-012"))
')
  echo "$out" | grep -qF "GLOBAL_FALLBACK" || { echo "global fallback broken; out=$out"; return 1; }
}

# ---------------------------------------------------------------- TC-M10.4-07

@test "[m10.4] TC-M10.4-07 LLM error → empty string + audit chain_summarize_failed" {
  ws=$(m10_seed_workspace)
  make_ancestor_with_briefs "$ws" T-007 "feat" "implement" "done" "x"
  make_task "$ws" T-012
  make_chain "$ws" T-007 T-012

  # Spec mentions CN_LLM_MOCK_FORCE_RAISE=1; llm_call.py implements
  # injection via CN_LLM_MOCK_ERROR_<CALL_NAME>. Use the existing
  # convention (documented as deviation in commit body).
  out=$(PYTHONPATH="$M10_LIB_DIR" \
        CN_LLM_MOCK_ERROR_CHAIN_SUMMARIZE="mock injected" WS="$ws" python3 -c '
import os, chain_summarize as cs
r = cs.summarize(os.environ["WS"], "T-012")
print(repr(r))
')
  [ "$out" = "''" ] || { echo "expected empty string, got $out"; return 1; }
  assert_audit "$ws" chain_summarize_failed
  log="$ws/.codenook/memory/history/extraction-log.jsonl"
  jq -c 'select(.outcome=="chain_summarize_failed")' "$log" | grep -qF "RuntimeError" \
    || { echo "reason missing RuntimeError"; cat "$log"; return 1; }
}

# ---------------------------------------------------------------- TC-M10.4-08

@test "[m10.4] TC-M10.4-08 token budget enforced for N in {1,5,12,24} (deterministic)" {
  ws_root=$(m10_seed_workspace)
  mock="$ws_root/_mock"
  # 1400-token fixture (~5600 chars).
  payload=$(python3 -c 'print("x" * 5600, end="")')
  seed_mock_llm "$mock" chain_summarize "$payload"

  for N in 1 5 12 24; do
    ws="$ws_root/run-$N"
    mkdir -p "$ws/.codenook/tasks"
    # build chain with N+1 tasks (N ancestors after dropping self)
    PYTHONPATH="$M10_LIB_DIR" WS="$ws" N="$N" python3 - <<'PY'
import json, os, pathlib, task_chain as tc
ws = os.environ["WS"]
n = int(os.environ["N"])
ids = [f"T-{i:03d}" for i in range(1, n + 2)]
for tid in ids:
    d = pathlib.Path(ws) / ".codenook" / "tasks" / tid
    (d / "outputs").mkdir(parents=True, exist_ok=True)
    (d / "state.json").write_text(json.dumps({
        "schema_version": 1, "task_id": tid, "title": tid,
        "plugin": "development", "phase": "implement",
        "iteration": 0, "max_iterations": 5,
        "status": "done", "history": [],
    }))
for c, p in zip(ids[1:], ids[:-1]):
    tc.set_parent(ws, c, p)
PY
    leaf=$(printf "T-%03d" $((N + 1)))
    # Run twice and verify identical output (determinism).
    out1=$(PYTHONPATH="$M10_LIB_DIR" CN_LLM_MOCK_DIR="$mock" python3 -c "
import chain_summarize as cs
print(cs.summarize('$ws', '$leaf'), end='')
")
    out2=$(PYTHONPATH="$M10_LIB_DIR" CN_LLM_MOCK_DIR="$mock" python3 -c "
import chain_summarize as cs
print(cs.summarize('$ws', '$leaf'), end='')
")
    [ "$out1" = "$out2" ] || { echo "N=$N: non-deterministic"; return 1; }
    est=$(PYTHONPATH="$M10_LIB_DIR" python3 -c '
import sys, token_estimate as te
print(te.estimate(sys.stdin.read()))
' <<<"$out1")
    [ "$est" -le 8192 ] || { echo "N=$N: exceeds 8192: $est"; return 1; }
    if [ "$N" = "1" ]; then
      [ "$est" -le 1700 ] || { echo "N=1: exceeds 1700: $est"; return 1; }
    fi
  done
}
