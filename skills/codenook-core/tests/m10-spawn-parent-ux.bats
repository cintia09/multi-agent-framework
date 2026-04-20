#!/usr/bin/env bats
# M10.3 — router-agent spawn parent-UX hook (TC-M10.3-01..05).
# Spec: docs/task-chains.md §3.1 §3.2 §5
# Cases: docs/m10-test-cases.md §M10.3

load helpers/load
load helpers/assertions
load helpers/m10_chain

# ---------------------------------------------------------------- TC-M10.3-01

@test "[m10.3] TC-M10.3-01 prepare presents top-3 + independent option" {
  ws=$(m10_seed_workspace)
  # 3 high-overlap candidates + 2 noise tasks (all active).
  make_task_with_brief "$ws" T-001 "feature auth login refresh jwt token" "implementation"
  make_task_with_brief "$ws" T-002 "feature auth login design jwt"        ""
  make_task_with_brief "$ws" T-003 "feature auth login token rotation"    ""
  make_task_with_brief "$ws" T-004 "docs landing page copy edit"          ""
  make_task_with_brief "$ws" T-005 "db schema bootstrap script"           ""

  run m10_router_render T-NEW "$ws" --user-turn "unit test feature auth login"
  [ "$status" -eq 0 ] || { echo "stdout=$output"; return 1; }

  prompt=$(cat "$(render_prompt_path "$ws" T-NEW)")
  echo "$prompt" | grep -q "## Suggested parents" \
    || { echo "missing 'Suggested parents' header"; echo "$prompt"; return 1; }
  echo "$prompt" | grep -q "0\\. independent (no parent)" \
    || { echo "missing independent option"; return 1; }

  # At least one numbered candidate line "<n>. T-XXX (score=0.NN) — <reason>".
  count=$(echo "$prompt" | grep -cE '^[1-3]\. T-[A-Za-z0-9_-]+ \(score=0\.[0-9]+\) — ')
  [ "$count" -ge 1 ] || { echo "no candidate lines (count=$count)"; echo "$prompt"; return 1; }
  [ "$count" -le 3 ] || { echo "too many candidate lines (count=$count)"; return 1; }
}

# ---------------------------------------------------------------- TC-M10.3-02

@test "[m10.3] TC-M10.3-02 confirm with parent_id sets state + audit" {
  ws=$(m10_seed_workspace)
  make_task_with_brief "$ws" T-007 "feature auth login refresh jwt token" "implementation"

  # Seed prepare path so router-context.md + .router-prompt.md exist.
  run m10_router_render T-NEW "$ws" --user-turn "unit test feature auth login"
  [ "$status" -eq 0 ] || { echo "prepare failed: $output"; return 1; }

  # User picked T-007 in dialog; router-agent wrote it back to draft-config.
  seed_draft_config "$ws" T-NEW development \
    "unit test feature auth login" T-007

  before=$(tc_audit_count "$ws" chain_attached)
  run m10_router_render T-NEW "$ws" --confirm
  [ "$status" -eq 0 ] || { echo "confirm failed: $output"; return 1; }

  pid=$(tc_state_field "$ws" T-NEW parent_id)
  [ "$pid" = "T-007" ] || { echo "parent_id=$pid"; return 1; }
  root=$(tc_state_field "$ws" T-NEW chain_root)
  [ "$root" = "T-007" ] || { echo "chain_root=$root"; return 1; }

  after=$(tc_audit_count "$ws" chain_attached)
  [ "$after" -eq $((before + 1)) ] \
    || { echo "audit count: before=$before after=$after"; return 1; }
}

# ---------------------------------------------------------------- TC-M10.3-03

@test "[m10.3] TC-M10.3-03 confirm with parent_id=null leaves task independent" {
  ws=$(m10_seed_workspace)
  run m10_router_render T-NEW "$ws" --user-turn "add ssh key rotation script"
  [ "$status" -eq 0 ] || { echo "prepare failed: $output"; return 1; }

  seed_draft_config "$ws" T-NEW development \
    "add ssh key rotation script" null

  before=$(tc_audit_count "$ws" chain_attached)
  run m10_router_render T-NEW "$ws" --confirm
  [ "$status" -eq 0 ] || { echo "confirm failed: $output"; return 1; }

  pid=$(tc_state_field "$ws" T-NEW parent_id)
  [ "$pid" = "null" ] || { echo "parent_id=$pid"; return 1; }
  root=$(tc_state_field "$ws" T-NEW chain_root)
  [ "$root" = "null" ] || { echo "chain_root=$root"; return 1; }

  after=$(tc_audit_count "$ws" chain_attached)
  [ "$after" -eq "$before" ] \
    || { echo "spurious chain_attached audit: before=$before after=$after"; return 1; }
}

# ---------------------------------------------------------------- TC-M10.3-04

@test "[m10.3] TC-M10.3-04 no candidate above threshold → only independent offered" {
  ws=$(m10_seed_workspace)
  make_task_with_brief "$ws" T-101 "feature auth login refresh jwt token" ""
  make_task_with_brief "$ws" T-102 "docs landing page copy edit"          ""
  make_task_with_brief "$ws" T-103 "refactor logger emitter sink"         ""

  run m10_router_render T-NEW "$ws" \
    --user-turn "add ssh key rotation script for prod"
  [ "$status" -eq 0 ] || { echo "stdout=$output"; return 1; }

  prompt=$(cat "$(render_prompt_path "$ws" T-NEW)")
  echo "$prompt" | grep -q "## Suggested parents" \
    || { echo "missing header"; return 1; }
  echo "$prompt" | grep -q "(none above threshold)" \
    || { echo "missing '(none above threshold)' marker"; echo "$prompt"; return 1; }
  echo "$prompt" | grep -q "0\\. independent (no parent)" \
    || { echo "missing independent option"; return 1; }
  ! echo "$prompt" | grep -qE '^[1-3]\. T-[A-Za-z0-9_-]+ \(score=' \
    || { echo "unexpected candidate lines emitted"; echo "$prompt"; return 1; }
}

# ---------------------------------------------------------------- TC-M10.3-05

@test "[m10.3] TC-M10.3-05 CLI re-attach updates state.json + chain_root + audits" {
  ws=$(m10_seed_workspace)
  make_task "$ws" T-NEW
  make_task "$ws" T-007
  make_task "$ws" T-008

  snap_path="$ws/.codenook/tasks/.chain-snapshot.json"

  # First attach: T-NEW → T-007.
  run env PYTHONPATH="$M10_LIB_DIR" python3 -m task_chain \
    --workspace "$ws" attach T-NEW T-007
  [ "$status" -eq 0 ] || { echo "first attach failed: $output"; return 1; }
  pid=$(tc_state_field "$ws" T-NEW parent_id)
  [ "$pid" = "T-007" ] || { echo "parent_id=$pid"; return 1; }
  root=$(tc_state_field "$ws" T-NEW chain_root)
  [ "$root" = "T-007" ] || { echo "chain_root=$root"; return 1; }
  gen1=$(jq -r '.generation' "$snap_path")
  [ "$gen1" -ge 1 ] || { echo "gen1=$gen1"; return 1; }

  # Second attach: T-NEW → T-008 with --force.
  run env PYTHONPATH="$M10_LIB_DIR" python3 -m task_chain \
    --workspace "$ws" attach T-NEW T-008 --force
  [ "$status" -eq 0 ] || { echo "force attach failed: $output"; return 1; }
  pid=$(tc_state_field "$ws" T-NEW parent_id)
  [ "$pid" = "T-008" ] || { echo "parent_id=$pid"; return 1; }
  root=$(tc_state_field "$ws" T-NEW chain_root)
  [ "$root" = "T-008" ] || { echo "chain_root=$root"; return 1; }
  gen2=$(jq -r '.generation' "$snap_path")
  [ "$gen2" -gt "$gen1" ] || { echo "gen did not bump: $gen1 → $gen2"; return 1; }

  # Two chain_attached audits total.
  attached=$(tc_audit_count "$ws" chain_attached)
  [ "$attached" -ge 2 ] || { echo "expected ≥2 chain_attached audits, got $attached"; return 1; }
}

# ---------------------------------------------------------------- TC-M10.7-03 (MEDIUM-03 lock-in)

@test "[m10.7] TC-M10.7-03 cmd_confirm two-phase: bad parent_id leaves status=pending" {
  ws=$(m10_seed_workspace)
  # Prepare T-NEW (creates router-context.md etc).
  run m10_router_render T-NEW "$ws" --user-turn "two-phase write probe"
  [ "$status" -eq 0 ] || { echo "prepare failed: $output"; return 1; }

  # Seed draft pointing at a non-existent parent (TaskNotFoundError path).
  seed_draft_config "$ws" T-NEW development "two-phase write probe" T-DOES-NOT-EXIST

  run m10_router_render T-NEW "$ws" --confirm
  # cmd_confirm exits 4 on parent_attach_failed.
  [ "$status" -eq 4 ] || { echo "confirm exit=$status out=$output"; return 1; }
  echo "$output" | grep -q 'parent_attach_failed' \
    || { echo "missing parent_attach_failed code: $output"; return 1; }

  # Two-phase contract: state.json status MUST remain pending.
  st=$(tc_state_field "$ws" T-NEW status)
  [ "$st" = "pending" ] || { echo "status=$st want pending"; cat "$ws/.codenook/tasks/T-NEW/state.json"; return 1; }

  # parent_id never persisted (set_parent never reached the write).
  pid=$(tc_state_field "$ws" T-NEW parent_id)
  [ "$pid" = "null" ] || { echo "parent_id=$pid leaked"; return 1; }
}
