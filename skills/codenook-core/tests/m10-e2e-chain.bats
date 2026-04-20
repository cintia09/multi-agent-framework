#!/usr/bin/env bats
# M10.7 — End-to-end task-chain integration TC.
# Spec: docs/task-chains.md §3 §4 §7 §8 §9
# Cases: docs/m10-test-cases.md §M10.7 (e2e)
#
# Single comprehensive scenario: scaffold a workspace via the init
# skill, build a 5-deep linear chain (T-005 → T-004 → T-003 → T-002 →
# T-001), exercise router prepare→confirm with a parent suggestion,
# run chain_summarize end-to-end, and trip every chain_* audit
# outcome plus a diagnostic. Asserts:
#   • Snapshot v2 schema present (schema_version, generation,
#     built_at, entries[<tid>].chain_root).
#   • Workspace .gitignore lists .chain-snapshot.json.
#   • All 6 chain_* audit outcomes recorded at least once.
#   • At least one diagnostic side-record (asset_type=chain).

load helpers/load
load helpers/assertions
load helpers/m10_chain
load helpers/m9_memory

INIT_SKILL_SH="$CORE_ROOT/skills/builtin/init/init.sh"
RENDER_PY="$CORE_ROOT/skills/builtin/router-agent/render_prompt.py"

# -------------------------------------------------------------- TC-M10.7-E2E-01

@test "[m10.7] TC-M10.7-E2E-01 e2e chain: 5-deep, router flow, 6 outcomes, snapshot v2, gitignore" {
  ws=$(make_scratch)
  mock="$ws/_mock"
  mkdir -p "$mock"

  # ---- Scaffold workspace via the real init skill (creates .gitignore).
  bash "$INIT_SKILL_SH" "$ws"
  gi="$ws/.codenook/tasks/.gitignore"
  [ -f "$gi" ] || { echo "init did not create $gi"; return 1; }
  grep -qx '.chain-snapshot.json' "$gi" \
    || { echo ".chain-snapshot.json missing from .gitignore"; cat "$gi"; return 1; }

  # ---- Build the 5-task chain via the public CLI (T-002…T-005 attach
  #      onto their predecessor; T-001 is the root).
  for tid in T-001 T-002 T-003 T-004 T-005; do
    make_task "$ws" "$tid"
  done
  prev=T-001
  for cur in T-002 T-003 T-004 T-005; do
    run env PYTHONPATH="$M10_LIB_DIR" python3 -m task_chain attach "$cur" "$prev" --workspace "$ws"
    [ "$status" -eq 0 ] || { echo "attach $cur→$prev exit=$status out=$output"; return 1; }
    prev="$cur"
  done

  # Sanity: T-005 walks back to T-001.
  run env PYTHONPATH="$M10_LIB_DIR" WS="$ws" python3 -c \
    'import os, task_chain as tc; print(",".join(tc.walk_ancestors(os.environ["WS"], "T-005")))'
  [ "$status" -eq 0 ] && [ "$output" = "T-005,T-004,T-003,T-002,T-001" ] \
    || { echo "walk got: $output"; return 1; }

  # ---- Snapshot v2 schema assertions.
  snap="$ws/.codenook/tasks/.chain-snapshot.json"
  [ -f "$snap" ] || { echo "snapshot missing"; return 1; }
  jq -e '
    .schema_version >= 1
    and (.generation | type == "number")
    and (.built_at   | type == "string")
    and (.entries    | type == "object")
    and (.entries["T-005"].chain_root == "T-001")
    and (.entries["T-005"].parent_id  == "T-004")
    and (.entries["T-001"].chain_root == null)
  ' "$snap" >/dev/null || { echo "snapshot v2 schema mismatch"; cat "$snap"; return 1; }

  # ---- Outcome: chain_attach_failed (cycle: T-001's parent = T-005).
  run env PYTHONPATH="$M10_LIB_DIR" python3 -m task_chain attach T-001 T-005 --workspace "$ws"
  [ "$status" -ne 0 ] || { echo "expected cycle to fail"; return 1; }

  # ---- Router prepare→confirm flow with a parent suggestion (T-NEW).
  #      Use make_task_with_brief siblings so suggester finds candidates.
  make_task_with_brief "$ws" T-100 "feature auth login refresh jwt token" "implementation"
  run env PYTHONPATH="$M10_LIB_DIR" python3 "$RENDER_PY" \
    --task-id T-NEW --workspace "$ws" \
    --user-turn "unit test feature auth login refresh"
  [ "$status" -eq 0 ] || { echo "prepare exit=$status out=$output"; return 1; }
  prompt="$ws/.codenook/tasks/T-NEW/.router-prompt.md"
  [ -f "$prompt" ] || { echo "router prompt not rendered"; return 1; }
  grep -q "## Suggested parents" "$prompt" \
    || { echo "Suggested parents header missing"; return 1; }

  # User picks T-100 → router writes draft-config back, then --confirm.
  seed_draft_config "$ws" T-NEW development \
    "unit test feature auth login refresh" T-100
  run env PYTHONPATH="$M10_LIB_DIR" python3 "$RENDER_PY" \
    --task-id T-NEW --workspace "$ws" --confirm
  [ "$status" -eq 0 ] || { echo "confirm exit=$status out=$output"; return 1; }
  [ "$(tc_state_field "$ws" T-NEW parent_id)" = "T-100" ]
  [ "$(tc_state_field "$ws" T-NEW status)" = "in_progress" ]

  # ---- Outcome: chain_summarized (mock LLM ok, run on T-005).
  seed_mock_llm "$mock" chain_summarize "## TASK_CHAIN (M10)

ancestor summary OK"
  run env PYTHONPATH="$M10_LIB_DIR" CN_LLM_MOCK_DIR="$mock" WS="$ws" python3 -c \
    'import os, chain_summarize as cs; print(len(cs.summarize(os.environ["WS"], "T-005")))'
  [ "$status" -eq 0 ] || { echo "chain_summarize exit=$status out=$output"; return 1; }

  # ---- Outcome: chain_summarize_failed (mock LLM error).
  run env PYTHONPATH="$M10_LIB_DIR" CN_LLM_MOCK_ERROR="boom" WS="$ws" python3 -c \
    'import os, chain_summarize as cs; cs.summarize(os.environ["WS"], "T-005")'
  # cs.summarize swallows error & returns ""; just need the audit.
  [ "$status" -eq 0 ] || true

  # ---- Diagnostic: chain_root_stale. Touch a mid-chain state.json
  #      (without going through set_parent / detach so the snapshot is
  #      NOT bumped); the next walk_ancestors observes a state_mtime
  #      drift and emits a single chain_root_stale diag side-record.
  sleep 1
  touch "$ws/.codenook/tasks/T-002/state.json"
  run env PYTHONPATH="$M10_LIB_DIR" WS="$ws" python3 -c \
    'import os, task_chain as tc; tc.walk_ancestors(os.environ["WS"], "T-005")'
  [ "$status" -eq 0 ] || { echo "diag walk failed: $output"; return 1; }

  # ---- Outcome: chain_walk_truncated (corrupt T-003 mid-chain).
  printf '%s' '{ broken json' > "$ws/.codenook/tasks/T-003/state.json"
  run env PYTHONPATH="$M10_LIB_DIR" WS="$ws" python3 -c \
    'import os, task_chain as tc; tc.walk_ancestors(os.environ["WS"], "T-005")'
  [ "$status" -eq 0 ] || { echo "walk on corrupt mid-chain failed: $output"; return 1; }

  # Repair T-003 so detach can run cleanly.
  cat >"$ws/.codenook/tasks/T-003/state.json" <<'JSON'
{
  "schema_version": 1,
  "task_id": "T-003",
  "plugin": "development",
  "phase": "design",
  "iteration": 0,
  "max_iterations": 5,
  "status": "in_progress",
  "history": [],
  "parent_id": "T-002",
  "chain_root": "T-001"
}
JSON

  # ---- Outcome: chain_detached.
  run env PYTHONPATH="$M10_LIB_DIR" python3 -m task_chain detach T-005 --workspace "$ws"
  [ "$status" -eq 0 ] || { echo "detach exit=$status out=$output"; return 1; }
  [ "$(tc_state_field "$ws" T-005 parent_id)" = "null" ]

  # ---- Verify all 6 chain_* outcomes appeared at least once.
  log="$ws/$M10_AUDIT_LOG_REL"
  [ -f "$log" ] || { echo "audit log missing"; return 1; }
  for oc in chain_attached chain_attach_failed chain_walk_truncated \
            chain_summarized chain_summarize_failed chain_detached; do
    n=$(jq -c --arg o "$oc" 'select(.outcome==$o)' "$log" | wc -l | tr -d ' ')
    [ "$n" -ge 1 ] || { echo "missing outcome=$oc"; cat "$log"; return 1; }
  done

  # ---- Diagnostic side-record present (chain asset_type, outcome=diagnostic).
  diag=$(jq -c 'select(.asset_type=="chain" and .outcome=="diagnostic")' "$log" \
         | wc -l | tr -d ' ')
  [ "$diag" -ge 1 ] || { echo "no chain diagnostic side-record"; cat "$log"; return 1; }

  # ---- Snapshot still v2-shaped after detach + truncated walk + summarize.
  jq -e '.schema_version >= 1 and (.entries | type == "object")' "$snap" >/dev/null \
    || { echo "snapshot drifted off v2"; cat "$snap"; return 1; }
}
