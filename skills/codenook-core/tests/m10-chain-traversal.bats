#!/usr/bin/env bats
# M10.4 review-r1 lock-in tests.
# TC-M10.4-09: asset_type contract (spec §9.1 — must equal "chain").
# TC-M10.4-10: ancestor-id path-traversal hardening (review-r1 fix #2).

load helpers/load
load helpers/assertions
load helpers/m10_chain

# ---------------------------------------------------------------- TC-M10.4-09
# review-r1 fix #1 lock-in: every audit emitted by chain_summarize must
# carry asset_type="chain" (spec §9.1 — fixed value across the chain
# family: task_chain, parent_suggester, chain_summarize).

@test "[m10.4] TC-M10.4-09 audit asset_type==chain for redacted + failed outcomes" {
  ws=$(m10_seed_workspace)
  mock="$ws/_mock"
  make_ancestor_with_briefs "$ws" T-007 "feat" "implement" "done" "x"
  make_task "$ws" T-012
  make_chain "$ws" T-007 T-012

  # --- redacted path -----------------------------------------------------
  seed_mock_llm "$mock" chain_summarize $'aws-key=AKIAIOSFODNN7EXAMPLE\nrest\n'
  PYTHONPATH="$M10_LIB_DIR" CN_LLM_MOCK_DIR="$mock" WS="$ws" python3 -c '
import os, chain_summarize as cs
cs.summarize(os.environ["WS"], "T-012")
' >/dev/null

  log="$ws/.codenook/memory/history/extraction-log.jsonl"
  redacted_at=$(jq -c 'select(.outcome=="chain_summarize_redacted")' "$log" | tail -n1)
  [ -n "$redacted_at" ] || { echo "no chain_summarize_redacted line"; cat "$log"; return 1; }
  asset=$(echo "$redacted_at" | jq -r '.asset_type')
  [ "$asset" = "chain" ] || { echo "expected asset_type=chain, got $asset"; return 1; }

  # --- failed path -------------------------------------------------------
  ws2=$(m10_seed_workspace)
  make_ancestor_with_briefs "$ws2" T-007 "feat" "implement" "done" "x"
  make_task "$ws2" T-012
  make_chain "$ws2" T-007 T-012
  PYTHONPATH="$M10_LIB_DIR" CN_LLM_MOCK_ERROR_CHAIN_SUMMARIZE="boom" \
    WS="$ws2" python3 -c '
import os, chain_summarize as cs
cs.summarize(os.environ["WS"], "T-012")
' >/dev/null

  log2="$ws2/.codenook/memory/history/extraction-log.jsonl"
  failed_at=$(jq -c 'select(.outcome=="chain_summarize_failed")' "$log2" | tail -n1)
  [ -n "$failed_at" ] || { echo "no chain_summarize_failed line"; cat "$log2"; return 1; }
  asset2=$(echo "$failed_at" | jq -r '.asset_type')
  [ "$asset2" = "chain" ] || { echo "expected asset_type=chain, got $asset2"; return 1; }
}

# ---------------------------------------------------------------- TC-M10.4-10
# review-r1 fix #2 lock-in: a corrupted state.json with a path-traversal
# parent_id must NOT cause _safe_resolve / _list_artifacts to enumerate
# arbitrary directories. The bad ancestor is rejected at the top of
# _collect_ancestor; if it is the only ancestor, summarize returns "".

@test "[m10.4] TC-M10.4-10 path-traversal parent_id rejected, returns empty" {
  ws=$(m10_seed_workspace)
  mock="$ws/_mock"
  seed_mock_llm "$mock" chain_summarize $'目标：foo\n'

  # Build a leaf whose state.json hand-points to a traversal id.
  make_task "$ws" T-012
  WS="$ws" python3 - <<'PY'
import json, os, pathlib
ws = os.environ["WS"]
p = pathlib.Path(ws) / ".codenook" / "tasks" / "T-012" / "state.json"
state = json.loads(p.read_text())
state["parent_id"] = "../../../etc"
p.write_text(json.dumps(state))
PY

  # 1) End-to-end: summarize must return "" without enumerating
  #    anything outside <ws>/.codenook/tasks/. Either path is OK:
  #    (a) walk_ancestors truncates because state.json is unreadable
  #        for the bogus id, leaving zero real ancestors → "".
  #    (b) the bogus id reaches _collect_ancestor and is rejected
  #        with chain_summarize_failed/bad_ancestor_id.
  out=$(PYTHONPATH="$M10_LIB_DIR" CN_LLM_MOCK_DIR="$mock" WS="$ws" python3 -c '
import os, chain_summarize as cs
print(repr(cs.summarize(os.environ["WS"], "T-012")))
')
  [ "$out" = "''" ] || { echo "expected empty string, got $out"; return 1; }

  log="$ws/.codenook/memory/history/extraction-log.jsonl"
  [ -f "$log" ] || { echo "no audit log"; return 1; }
  # No audit line may carry asset_type other than "chain".
  bad_at=$(jq -c 'select(.asset_type != "chain")' "$log" || true)
  [ -z "$bad_at" ] || { echo "non-chain asset_type leaked: $bad_at"; return 1; }

  # 2) Direct lock-in: feed _collect_ancestor a bogus id and verify it
  #    returns None + writes chain_summarize_failed/bad_ancestor_id —
  #    this is the actual gate fix #2 installs (independent of whether
  #    walk_ancestors happens to filter the id earlier).
  ws2=$(m10_seed_workspace)
  PYTHONPATH="$M10_LIB_DIR" WS="$ws2" python3 - <<'PY'
import os, pathlib, chain_summarize as cs
ws = pathlib.Path(os.environ["WS"]).resolve()
for bad in ("../../../etc", "..", "/abs/path", "T-../../etc", ""):
    r = cs._collect_ancestor(ws, bad)
    assert r is None, f"expected None for {bad!r}, got {r!r}"
PY

  log2="$ws2/.codenook/memory/history/extraction-log.jsonl"
  [ -f "$log2" ] || { echo "no audit log for direct test"; return 1; }
  n=$(jq -c 'select(.outcome=="chain_summarize_failed" and (.reason|tostring|contains("bad_ancestor_id")))' "$log2" | wc -l | tr -d ' ')
  [ "$n" -ge 1 ] || { echo "expected >=1 bad_ancestor_id audit; got $n"; cat "$log2"; return 1; }
  asset=$(jq -r 'select(.outcome=="chain_summarize_failed") | .asset_type' "$log2" | sort -u)
  [ "$asset" = "chain" ] || { echo "expected asset_type=chain only, got: $asset"; return 1; }
}
