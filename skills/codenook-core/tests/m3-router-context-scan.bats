#!/usr/bin/env bats
# M3 Unit 1 — router-context-scan
#
# Contract:
#   scan.sh [--workspace <dir>] [--max-tasks N] [--json]
#   exit 0 = scan complete; 2 = usage error.
#
# Output (JSON, ≤2KB) reports:
#   installed_plugins: [{id, version}, ...]
#   active_tasks:      [{task_id, plugin, phase, last_tick_at}, ...]
#   hitl_pending:      integer count
#   fanout_pending:    integer count of subtasks queued under active tasks
#   workspace_warnings: [strings]   # >100MB or >10K files

load helpers/load
load helpers/assertions

SCAN_SH="$CORE_ROOT/skills/builtin/router-context-scan/scan.sh"
M3_FX="$FIXTURES_ROOT/m3"

stage_ws() {
  local src="$1" dst
  dst="$(make_scratch)/ws"
  cp -R "$src" "$dst"
  echo "$dst"
}

@test "scan.sh exists and is executable" {
  assert_file_exists "$SCAN_SH"
  assert_file_executable "$SCAN_SH"
}

@test "missing --workspace and no .codenook in cwd → exit 2" {
  d="$(make_scratch)"
  run_with_stderr "cd \"$d\" && \"$SCAN_SH\""
  [ "$status" -eq 2 ]
}

@test "empty workspace: 0 plugins, 0 tasks, 0 hitl" {
  ws="$(stage_ws "$M3_FX/workspaces/empty")"
  run_with_stderr "\"$SCAN_SH\" --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.installed_plugins == []' >/dev/null
  echo "$output" | jq -e '.active_tasks      == []' >/dev/null
  echo "$output" | jq -e '.hitl_pending      == 0'  >/dev/null
  echo "$output" | jq -e '.fanout_pending    == 0'  >/dev/null
}

@test "one-plugin workspace: 1 installed, no tasks" {
  ws="$(stage_ws "$M3_FX/workspaces/one-plugin")"
  run_with_stderr "\"$SCAN_SH\" --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.installed_plugins | length == 1' >/dev/null
  echo "$output" | jq -e '.installed_plugins[0].id == "writing-stub"' >/dev/null
  echo "$output" | jq -e '.installed_plugins[0].version == "0.1.0"'  >/dev/null
}

@test "full workspace: 3 plugins reported sorted by id" {
  ws="$(stage_ws "$M3_FX/workspaces/full")"
  run_with_stderr "\"$SCAN_SH\" --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  ids=$(echo "$output" | jq -c '[.installed_plugins[].id]')
  [ "$ids" = '["ambiguous-stub","coding-stub","writing-stub"]' ]
}

@test "full workspace: 2 active tasks reported with phase + last_tick_at" {
  ws="$(stage_ws "$M3_FX/workspaces/full")"
  run_with_stderr "\"$SCAN_SH\" --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.active_tasks | length == 2' >/dev/null
  echo "$output" | jq -e '.active_tasks[] | select(.task_id=="T-001") | .phase == "draft"' >/dev/null
  echo "$output" | jq -e '.active_tasks[] | select(.task_id=="T-002") | .last_tick_at == "2026-04-18T10:45:00Z"' >/dev/null
}

@test "HITL queue size reported" {
  ws="$(stage_ws "$M3_FX/workspaces/full")"
  run_with_stderr "\"$SCAN_SH\" --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.hitl_pending == 1' >/dev/null
}

@test "fan-out subtasks counted across active tasks" {
  ws="$(stage_ws "$M3_FX/workspaces/full")"
  run_with_stderr "\"$SCAN_SH\" --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  # T-001 has subtasks ["T-001.1"], T-002 has []. fanout_pending == 1
  echo "$output" | jq -e '.fanout_pending == 1' >/dev/null
}

@test "--max-tasks limits active_tasks length" {
  ws="$(stage_ws "$M3_FX/workspaces/full")"
  run_with_stderr "\"$SCAN_SH\" --workspace \"$ws\" --max-tasks 1 --json"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.active_tasks | length == 1' >/dev/null
}

@test "workspace size warning emitted when >10K files" {
  ws="$(stage_ws "$M3_FX/workspaces/empty")"
  # plant 10001 marker files under workspace (cheap inode count)
  mkdir -p "$ws/bulk"
  python3 -c "
import os
for i in range(10001):
    open(f'$ws/bulk/f{i}', 'w').close()
"
  run_with_stderr "\"$SCAN_SH\" --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.workspace_warnings | length >= 1' >/dev/null
  echo "$output" | jq -e '.workspace_warnings | any(. | contains("files"))' >/dev/null
}

@test "JSON envelope ≤2KB" {
  ws="$(stage_ws "$M3_FX/workspaces/full")"
  run_with_stderr "\"$SCAN_SH\" --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  size=$(printf '%s' "$output" | wc -c | tr -d ' ')
  [ "$size" -le 2048 ] || { echo "scan output is $size bytes (>2048)" >&2; exit 1; }
}
