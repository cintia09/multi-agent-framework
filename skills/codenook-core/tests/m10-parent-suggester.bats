#!/usr/bin/env bats
# M10.2 — _lib/parent_suggester.py token-set Jaccard ranker (TC-M10.2-01..06).
# Spec: docs/v6/task-chains-v6.md §5
# Cases: docs/v6/m10-test-cases.md §M10.2

load helpers/load
load helpers/assertions
load helpers/m10_chain

# ---------------------------------------------------------------- TC-M10.2-01

@test "[m10.2] TC-M10.2-01 top-3 ranking with distinct scores" {
  ws=$(m10_seed_workspace)
  make_task_with_brief "$ws" T-A "feature auth login refresh jwt token" "implementation"
  make_task_with_brief "$ws" T-B "feature auth login design jwt"        ""
  make_task_with_brief "$ws" T-C "feature billing invoice"              ""
  make_task_with_brief "$ws" T-D "docs landing page copy edit"          ""
  make_task_with_brief "$ws" T-E "db schema bootstrap script preflight" ""
  run env PYTHONPATH="$M10_LIB_DIR" WS="$ws" python3 - <<'PY'
import json, os
import parent_suggester as ps
out = ps.suggest_parents(os.environ["WS"], "feature auth login token", top_k=3, threshold=0.15)
print(json.dumps([{"task_id": s.task_id, "title": s.title,
                    "score": s.score, "reason": s.reason} for s in out]))
PY
  [ "$status" -eq 0 ] || { echo "out=$output"; return 1; }
  echo "$output" | jq -e 'length == 3'
  first=$(echo "$output" | jq -r '.[0].task_id')
  case "$first" in
    T-A|T-B) ;;
    *) echo "expected first ∈ {T-A,T-B}, got $first"; return 1 ;;
  esac
  echo "$output" | jq -e '.[0].score > .[1].score and .[1].score > .[2].score'
  echo "$output" | jq -e 'all(.reason | startswith("shared:"))'
}

# ---------------------------------------------------------------- TC-M10.2-02

@test "[m10.2] TC-M10.2-02 threshold filter drops scores < 0.15" {
  ws=$(m10_seed_workspace)
  # Child brief tokens (after stopwords + len>=2): {feature,auth,login,token,refresh,jwt}
  # T-X: full overlap → ~6/6 = 1.0  (above)
  # T-Y: 2 shared / 8 total → 0.25  (above)
  # T-Z: 1 shared / 9 total → 0.11  (below)
  # T-W: 0 shared → 0.0  (below)
  make_task_with_brief "$ws" T-X "feature auth login token refresh jwt" ""
  make_task_with_brief "$ws" T-Y "feature auth alpha beta gamma delta epsilon zeta" ""
  make_task_with_brief "$ws" T-Z "feature alpha beta gamma delta epsilon zeta eta theta" ""
  make_task_with_brief "$ws" T-W "completely different vocabulary nothing matches here at all extra" ""
  run env PYTHONPATH="$M10_LIB_DIR" WS="$ws" python3 - <<'PY'
import json, os
import parent_suggester as ps
out = ps.suggest_parents(os.environ["WS"], "feature auth login token refresh jwt", threshold=0.15)
print(json.dumps([{"task_id": s.task_id, "score": s.score} for s in out]))
PY
  [ "$status" -eq 0 ] || { echo "out=$output"; return 1; }
  echo "$output" | jq -e 'length <= 2 and length >= 1'
  echo "$output" | jq -e 'all(.score >= 0.15)'
  echo "$output" | jq -e 'all(.task_id != "T-Z" and .task_id != "T-W")'
}

# ---------------------------------------------------------------- TC-M10.2-03

@test "[m10.2] TC-M10.2-03 empty workspace returns []" {
  ws=$(m10_seed_workspace)
  run env PYTHONPATH="$M10_LIB_DIR" WS="$ws" python3 - <<'PY'
import json, os
import parent_suggester as ps
out = ps.suggest_parents(os.environ["WS"], "any brief whatsoever")
print(json.dumps([s.task_id for s in out]))
PY
  [ "$status" -eq 0 ] || { echo "out=$output"; return 1; }
  [ "$output" = "[]" ]
  # No audit on empty pool (no candidates ≠ failure).
  log="$ws/$M10_AUDIT_LOG_REL"
  if [ -f "$log" ]; then
    n=$(jq -c 'select(.outcome | startswith("parent_suggest"))' "$log" | wc -l | tr -d ' ')
    [ "$n" -eq 0 ] || { echo "unexpected audit lines: $(cat "$log")"; return 1; }
  fi
}

# ---------------------------------------------------------------- TC-M10.2-04

@test "[m10.2] TC-M10.2-04 corruption / IO failure → empty list + audit" {
  ws=$(m10_seed_workspace)
  make_task_with_brief "$ws" T-001 "feature auth login token" ""
  make_task_with_brief "$ws" T-002 "feature auth design jwt" ""
  make_task_with_brief "$ws" T-003 "feature billing invoice work" ""
  # Corrupt T-002's state.json with invalid JSON.
  printf '%s' "{ broken" > "$ws/.codenook/tasks/T-002/state.json"
  # Branch A: single corruption → ≤2 valid candidates + parent_suggest_skip audit.
  run env PYTHONPATH="$M10_LIB_DIR" WS="$ws" python3 - <<'PY'
import json, os
import parent_suggester as ps
out = ps.suggest_parents(os.environ["WS"], "feature auth login token")
print(json.dumps([s.task_id for s in out]))
PY
  [ "$status" -eq 0 ] || { echo "out=$output"; return 1; }
  echo "$output" | jq -e 'length <= 2'
  echo "$output" | jq -e 'all(. != "T-002")'
  assert_audit "$ws" parent_suggest_skip
  # Branch B: monkeypatch _list_open_tasks to raise → returns [] + parent_suggest_failed audit.
  run env PYTHONPATH="$M10_LIB_DIR" WS="$ws" python3 - <<'PY'
import json, os
import parent_suggester as ps
def boom(_ws):
    raise OSError("disk on fire")
ps._list_open_tasks = boom
out = ps.suggest_parents(os.environ["WS"], "feature auth login token")
print(json.dumps([s.task_id for s in out]))
PY
  [ "$status" -eq 0 ] || { echo "out=$output"; return 1; }
  [ "$output" = "[]" ]
  assert_audit "$ws" parent_suggest_failed
}

# ---------------------------------------------------------------- TC-M10.2-05

@test "[m10.2] TC-M10.2-05 ties broken deterministically by task_id alpha" {
  ws=$(m10_seed_workspace)
  make_task_with_brief "$ws" T-105 "alpha beta gamma delta epsilon zeta" ""
  make_task_with_brief "$ws" T-099 "alpha beta gamma delta epsilon zeta" ""
  make_task_with_brief "$ws" T-200 "alpha beta gamma delta epsilon zeta" ""
  for i in 1 2 3 4 5; do
    run env PYTHONPATH="$M10_LIB_DIR" WS="$ws" python3 - <<'PY'
import json, os
import parent_suggester as ps
out = ps.suggest_parents(os.environ["WS"], "alpha beta gamma delta epsilon zeta", top_k=5)
print(json.dumps([(s.task_id, s.score) for s in out]))
PY
    [ "$status" -eq 0 ] || { echo "out=$output"; return 1; }
    ids=$(echo "$output" | jq -r '.[][0]' | tr '\n' ',' | sed 's/,$//')
    [ "$ids" = "T-099,T-105,T-200" ] || { echo "iter $i ids=$ids"; return 1; }
    echo "$output" | jq -e '.[0][1] == .[1][1] and .[1][1] == .[2][1]'
  done
}

# ---------------------------------------------------------------- TC-M10.2-06

@test "[m10.2] TC-M10.2-06 done / cancelled tasks excluded from candidate pool" {
  ws=$(m10_seed_workspace)
  make_task_with_brief "$ws" T-A1 "feature auth login token refresh jwt" "" in_progress
  make_task_with_brief "$ws" T-A2 "feature auth login token refresh jwt" "" in_progress
  make_task_with_brief "$ws" T-A3 "feature auth login token refresh jwt" "" in_progress
  make_task_with_brief "$ws" T-D1 "feature auth login token refresh jwt" "" done
  make_task_with_brief "$ws" T-C1 "feature auth login token refresh jwt" "" cancelled
  run env PYTHONPATH="$M10_LIB_DIR" WS="$ws" python3 - <<'PY'
import json, os
import parent_suggester as ps
out = ps.suggest_parents(os.environ["WS"], "feature auth login token refresh jwt", top_k=5)
print(json.dumps([s.task_id for s in out]))
PY
  [ "$status" -eq 0 ] || { echo "out=$output"; return 1; }
  echo "$output" | jq -e 'length == 3'
  echo "$output" | jq -e 'all(. != "T-D1" and . != "T-C1")'
}
