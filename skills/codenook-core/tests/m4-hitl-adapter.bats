#!/usr/bin/env bats
# M4.U4 — hitl-adapter terminal skill (list/decide/show).

load helpers/load
load helpers/assertions

HITL_SH="$CORE_ROOT/skills/builtin/hitl-adapter/terminal.sh"

mk_ws_with_entry() {
  local ws; ws="$(make_scratch)"
  mkdir -p "$ws/.codenook/hitl-queue" "$ws/.codenook/history" \
           "$ws/.codenook/tasks/T-501/outputs"
  cp "$FIXTURES_ROOT/m4/hitl-valid.json" \
     "$ws/.codenook/hitl-queue/T-501-design_signoff.json"
  echo "context body for T-501" \
     >"$ws/.codenook/tasks/T-501/outputs/phase-2-designer-summary.md"
  # adjust id+task in the copied fixture
  python3 -c "
import json
p='$ws/.codenook/hitl-queue/T-501-design_signoff.json'
d=json.load(open(p))
d['id']='T-501-design_signoff'
d['task_id']='T-501'
d['context_path']='.codenook/tasks/T-501/outputs/phase-2-designer-summary.md'
json.dump(d, open(p,'w'), indent=2)
"
  echo "$ws"
}

@test "terminal.sh exists and is executable" {
  assert_file_exists "$HITL_SH"
  assert_file_executable "$HITL_SH"
}

@test "list: shows only entries with decision==null" {
  ws="$(mk_ws_with_entry)"
  # Add a decided one
  jq '.id="T-501-other" | .decision="approve" | .decided_at="2026-01-01T00:00:00Z" | .reviewer="alice"' \
     "$ws/.codenook/hitl-queue/T-501-design_signoff.json" \
     >"$ws/.codenook/hitl-queue/T-501-other.json"
  run bash -c "\"$HITL_SH\" list --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.entries | length == 1' >/dev/null
  echo "$output" | jq -e '.entries[0].id == "T-501-design_signoff"' >/dev/null
}

@test "decide: updates decision, decided_at, reviewer, comment" {
  ws="$(mk_ws_with_entry)"
  run bash -c "\"$HITL_SH\" decide --id T-501-design_signoff --decision approve --reviewer alice --comment 'looks ok' --workspace \"$ws\""
  [ "$status" -eq 0 ]
  jq -e '.decision=="approve" and .reviewer=="alice" and .comment=="looks ok"' \
     "$ws/.codenook/hitl-queue/T-501-design_signoff.json" >/dev/null
  jq -e '.decided_at != null' "$ws/.codenook/hitl-queue/T-501-design_signoff.json" >/dev/null
}

@test "decide: immutable replay — second decide on same id exits 1" {
  ws="$(mk_ws_with_entry)"
  run bash -c "\"$HITL_SH\" decide --id T-501-design_signoff --decision approve --reviewer alice --workspace \"$ws\""
  [ "$status" -eq 0 ]
  run_with_stderr "\"$HITL_SH\" decide --id T-501-design_signoff --decision reject --reviewer bob --workspace \"$ws\""
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" "already decided"
}

@test "decide: --decision must be approve|reject|needs_changes" {
  ws="$(mk_ws_with_entry)"
  run_with_stderr "\"$HITL_SH\" decide --id T-501-design_signoff --decision maybe --reviewer alice --workspace \"$ws\""
  [ "$status" -ne 0 ]
  assert_contains "$STDERR" "decision"
}

@test "decide: missing entry → exit 2" {
  ws="$(mk_ws_with_entry)"
  run_with_stderr "\"$HITL_SH\" decide --id T-999-nope --decision approve --reviewer alice --workspace \"$ws\""
  [ "$status" -eq 2 ]
}

@test "decide: mirrors to history/hitl.jsonl" {
  ws="$(mk_ws_with_entry)"
  run bash -c "\"$HITL_SH\" decide --id T-501-design_signoff --decision approve --reviewer alice --workspace \"$ws\""
  [ "$status" -eq 0 ]
  [ -f "$ws/.codenook/history/hitl.jsonl" ]
  jq -e '.id=="T-501-design_signoff" and .decision=="approve"' \
     "$ws/.codenook/history/hitl.jsonl" >/dev/null
}

@test "show: prints the context_path file content" {
  ws="$(mk_ws_with_entry)"
  run bash -c "\"$HITL_SH\" show --id T-501-design_signoff --workspace \"$ws\""
  [ "$status" -eq 0 ]
  [[ "$output" == *"context body for T-501"* ]]
}

@test "show: missing entry → exit 2" {
  ws="$(mk_ws_with_entry)"
  run_with_stderr "\"$HITL_SH\" show --id T-999-nope --workspace \"$ws\""
  [ "$status" -eq 2 ]
}

@test "atomic decide: no .tmp file remains after success" {
  ws="$(mk_ws_with_entry)"
  run bash -c "\"$HITL_SH\" decide --id T-501-design_signoff --decision approve --reviewer alice --workspace \"$ws\""
  [ "$status" -eq 0 ]
  shopt -s nullglob
  tmps=("$ws"/.codenook/hitl-queue/.*.tmp "$ws"/.codenook/hitl-queue/*.tmp)
  [ "${#tmps[@]}" -eq 0 ]
}

@test "unknown subcommand → exit 2" {
  ws="$(mk_ws_with_entry)"
  run_with_stderr "\"$HITL_SH\" frobnicate --workspace \"$ws\""
  [ "$status" -eq 2 ]
}
