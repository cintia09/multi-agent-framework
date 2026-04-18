#!/usr/bin/env bats
# M3 Unit 3 — router-dispatch-build (constructs the ≤500-char dispatch payload).
#
# Contract:
#   build.sh --target <plugin-id|skill-name> --user-input "<text>"
#            [--task <T-NNN>] [--workspace <dir>] [--json]
#
# Reads the target's plugin.yaml (or builtin SKILL.md) and emits a JSON
# payload conforming to architecture §3.1.7:
#   { role, target, task?, user_input, context: {plugins, active_phase?} }
#
# Hard limit: 500 chars (architecture §3.1.7 / decision #T-3).
# user_input truncated to 200 chars + "..." if longer.
# After building, automatically calls dispatch-audit emit.
#
# Exit: 0 ok / 1 build/audit failure / 2 usage.

load helpers/load
load helpers/assertions

BUILD_SH="$CORE_ROOT/skills/builtin/router-dispatch-build/build.sh"
M3_FX="$FIXTURES_ROOT/m3"

stage_ws() {
  local src="$1" dst
  dst="$(make_scratch)/ws"
  cp -R "$src" "$dst"
  echo "$dst"
}

@test "build.sh exists and is executable" {
  assert_file_exists "$BUILD_SH"
  assert_file_executable "$BUILD_SH"
}

@test "missing --target → exit 2" {
  ws="$(stage_ws "$M3_FX/workspaces/full")"
  run_with_stderr "\"$BUILD_SH\" --user-input 'hi' --workspace \"$ws\""
  [ "$status" -eq 2 ]
}

@test "happy path: plugin target produces valid payload, exit 0" {
  ws="$(stage_ws "$M3_FX/workspaces/full")"
  run_with_stderr "\"$BUILD_SH\" --target writing-stub --user-input 'write chapter 3' --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.role        == "plugin-worker"'  >/dev/null
  echo "$output" | jq -e '.target      == "writing-stub"'   >/dev/null
  echo "$output" | jq -e '.user_input  == "write chapter 3"'>/dev/null
  echo "$output" | jq -e '.context.plugins | type == "array"' >/dev/null
}

@test "200-char user_input passed through unchanged" {
  ws="$(stage_ws "$M3_FX/workspaces/one-plugin")"
  long=$(python3 -c "print('a'*200, end='')")
  run_with_stderr "\"$BUILD_SH\" --target writing-stub --user-input '$long' --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  passed=$(echo "$output" | jq -r '.user_input')
  [ ${#passed} -eq 200 ]
}

@test "500-char user_input truncated to 200 + ellipsis" {
  ws="$(stage_ws "$M3_FX/workspaces/one-plugin")"
  long=$(python3 -c "print('b'*500, end='')")
  run_with_stderr "\"$BUILD_SH\" --target writing-stub --user-input '$long' --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  passed=$(echo "$output" | jq -r '.user_input')
  # 200 chars + "..." suffix (per spec)
  [ ${#passed} -le 203 ]
  echo "$passed" | grep -q '\.\.\.$'
}

@test "builtin target (skill) produces role=builtin-skill" {
  ws="$(stage_ws "$M3_FX/workspaces/empty")"
  run_with_stderr "\"$BUILD_SH\" --target list-plugins --user-input 'list' --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.role   == "builtin-skill"' >/dev/null
  echo "$output" | jq -e '.target == "list-plugins"'  >/dev/null
}

@test "payload exceeding 500 chars after truncation → exit 1" {
  # Force a target whose id is itself huge so the envelope can't fit.
  ws="$(make_scratch)/ws"
  mkdir -p "$ws/.codenook/plugins"
  big_id=$(python3 -c "print('p'*230, end='')")
  big_input=$(python3 -c "print('q'*250, end='')")
  mkdir -p "$ws/.codenook/plugins/$big_id"
  cat > "$ws/.codenook/plugins/$big_id/plugin.yaml" <<EOF
id: $big_id
version: 0.1.0
type: domain
entry_points: {install: install.sh}
declared_subsystems: [skills]
EOF
  cat > "$ws/.codenook/state.json" <<EOF
{"schema_version":1,"installed_plugins":{"$big_id":{"version":"0.1.0"}},"active_tasks":[]}
EOF
  run_with_stderr "\"$BUILD_SH\" --target $big_id --user-input '$big_input' --workspace \"$ws\" --json"
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" "payload still too large"
}

@test "dispatch-audit invoked: history/dispatch.jsonl gets one new line" {
  ws="$(stage_ws "$M3_FX/workspaces/full")"
  run_with_stderr "\"$BUILD_SH\" --target writing-stub --user-input 'hi' --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  assert_file_exists "$ws/.codenook/history/dispatch.jsonl"
  n=$(wc -l <"$ws/.codenook/history/dispatch.jsonl" | tr -d ' ')
  [ "$n" -eq 1 ]
}

@test "missing manifest for target → exit 1" {
  ws="$(stage_ws "$M3_FX/workspaces/empty")"
  run_with_stderr "\"$BUILD_SH\" --target ghost-plugin --user-input 'hi' --workspace \"$ws\" --json"
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" "ghost-plugin"
}

@test "--task included in payload as 'task' field" {
  ws="$(stage_ws "$M3_FX/workspaces/full")"
  run_with_stderr "\"$BUILD_SH\" --target writing-stub --user-input 'hi' --task T-001 --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.task == "T-001"' >/dev/null
}

@test "payload total size never exceeds 500 chars" {
  ws="$(stage_ws "$M3_FX/workspaces/full")"
  run_with_stderr "\"$BUILD_SH\" --target writing-stub --user-input 'small' --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  size=$(printf '%s' "$output" | tr -d '\n' | wc -c | tr -d ' ')
  [ "$size" -le 500 ] || { echo "payload is $size chars (>500)" >&2; exit 1; }
}

@test "fix#2: --target containing path-traversal '../escape' → exit 1, invalid target" {
  ws="$(stage_ws "$M3_FX/workspaces/full")"
  run_with_stderr "\"$BUILD_SH\" --target '../escape' --user-input 'hi' --workspace \"$ws\" --json"
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" "invalid target name"
}

@test "fix#2: --target with slash → exit 1, invalid target" {
  ws="$(stage_ws "$M3_FX/workspaces/full")"
  run_with_stderr "\"$BUILD_SH\" --target 'foo/bar' --user-input 'hi' --workspace \"$ws\" --json"
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" "invalid target name"
}

@test "fix#5: 200 CJK '章' chars (600 UTF-8 bytes) exceeds 500-byte limit → exit 1" {
  ws="$(stage_ws "$M3_FX/workspaces/full")"
  cjk=$(python3 -c "print('章'*200, end='')")
  run_with_stderr "\"$BUILD_SH\" --target writing-stub --user-input '$cjk' --workspace \"$ws\" --json"
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" "payload still too large"
}
