#!/usr/bin/env bats
# M3 Unit 4 — router-triage (the actual routing decision).
#
# Contract:
#   triage.sh --user-input "<text>" [--workspace <dir>] [--task <T-NNN>] [--json]
#
# Decisions:
#   chat   — small talk / clarification / no side effects
#   skill  — a builtin skill matches (M3 hardcoded set: list/show/help)
#   plugin — an installed plugin's intent_patterns regex matches
#   hitl   — multiple plugins match equally → require user confirmation
#
# Algorithm priority:
#   1. builtin intent table (regex on common verbs: list/show/help)
#   2. plugin intent_patterns from each manifest
#   3. fall-through: chat (low confidence), or hitl (tied plugins)
#
# Output:
#   {decision, target, confidence, reasons:[...], dispatch_payload?}

load helpers/load
load helpers/assertions

TRIAGE_SH="$CORE_ROOT/skills/builtin/router-triage/triage.sh"
M3_FX="$FIXTURES_ROOT/m3"

stage_ws() {
  local src="$1" dst
  dst="$(make_scratch)/ws"
  cp -R "$src" "$dst"
  echo "$dst"
}

@test "triage.sh exists and is executable" {
  assert_file_exists "$TRIAGE_SH"
  assert_file_executable "$TRIAGE_SH"
}

@test "no --user-input → exit 2" {
  ws="$(stage_ws "$M3_FX/workspaces/empty")"
  run_with_stderr "\"$TRIAGE_SH\" --workspace \"$ws\""
  [ "$status" -eq 2 ]
}

@test "chat decision: small talk on empty workspace" {
  ws="$(stage_ws "$M3_FX/workspaces/empty")"
  run_with_stderr "\"$TRIAGE_SH\" --user-input 'hi how are you' --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.decision == "chat"' >/dev/null
}

@test "chat decision: 'what is X' question" {
  ws="$(stage_ws "$M3_FX/workspaces/full")"
  run_with_stderr "\"$TRIAGE_SH\" --user-input 'what is RAG?' --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.decision == "chat"' >/dev/null
}

@test "skill decision: 'list installed plugins' → list-plugins" {
  ws="$(stage_ws "$M3_FX/workspaces/full")"
  run_with_stderr "\"$TRIAGE_SH\" --user-input 'list installed plugins' --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.decision == "skill"' >/dev/null
  echo "$output" | jq -e '.target   == "list-plugins"' >/dev/null
}

@test "skill decision: 'show config' → show-config" {
  ws="$(stage_ws "$M3_FX/workspaces/full")"
  run_with_stderr "\"$TRIAGE_SH\" --user-input 'show config' --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.decision == "skill"' >/dev/null
  echo "$output" | jq -e '.target   == "show-config"' >/dev/null
}

@test "plugin decision: chinese intent matches writing-stub" {
  ws="$(stage_ws "$M3_FX/workspaces/full")"
  run_with_stderr "\"$TRIAGE_SH\" --user-input '新建小说章节' --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.decision == "plugin"' >/dev/null
  echo "$output" | jq -e '.target   == "writing-stub"' >/dev/null
}

@test "plugin decision: 'fix bug in parser' → coding-stub" {
  ws="$(stage_ws "$M3_FX/workspaces/full")"
  run_with_stderr "\"$TRIAGE_SH\" --user-input 'fix bug in parser' --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.decision == "plugin"' >/dev/null
  echo "$output" | jq -e '.target   == "coding-stub"' >/dev/null
}

@test "plugin decision: regex anchor matches writing-stub on chinese partial" {
  ws="$(stage_ws "$M3_FX/workspaces/full")"
  run_with_stderr "\"$TRIAGE_SH\" --user-input '请帮我写章节五' --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.decision == "plugin"' >/dev/null
  echo "$output" | jq -e '.target   == "writing-stub"' >/dev/null
}

@test "hitl decision: builtin and plugin both match 'help' → builtin wins (priority)" {
  # 'help' is a builtin AND ambiguous-stub's intent. Priority order says
  # builtin > plugin, so this should NOT escalate; it should pick builtin.
  ws="$(stage_ws "$M3_FX/workspaces/full")"
  run_with_stderr "\"$TRIAGE_SH\" --user-input 'help' --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.decision == "skill"' >/dev/null
  echo "$output" | jq -e '.target   == "help"' >/dev/null
}

@test "hitl decision: multiple plugin tie → hitl" {
  # Plant a 4th stub whose pattern also matches '新建小说章节'
  ws="$(stage_ws "$M3_FX/workspaces/full")"
  mkdir -p "$ws/.codenook/plugins/writing-alt"
  cat > "$ws/.codenook/plugins/writing-alt/plugin.yaml" <<'EOF'
id: writing-alt
version: 0.1.0
type: domain
entry_points: {install: install.sh}
declared_subsystems: [skills]
intent_patterns:
  - "新建小说.*"
EOF
  run_with_stderr "\"$TRIAGE_SH\" --user-input '新建小说章节' --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.decision == "hitl"' >/dev/null
  echo "$output" | jq -e '.reasons | any(. | contains("multiple"))' >/dev/null
}

@test "confidence threshold: chat confidence ≤ 0.5; plugin match > 0.7" {
  ws="$(stage_ws "$M3_FX/workspaces/full")"
  run_with_stderr "\"$TRIAGE_SH\" --user-input 'hi' --workspace \"$ws\" --json"
  echo "$output" | jq -e '.confidence <= 0.5' >/dev/null

  run_with_stderr "\"$TRIAGE_SH\" --user-input 'fix bug now' --workspace \"$ws\" --json"
  echo "$output" | jq -e '.confidence > 0.7' >/dev/null
}

@test "dispatch_payload size guard: when decision=plugin, payload ≤500 chars" {
  ws="$(stage_ws "$M3_FX/workspaces/full")"
  run_with_stderr "\"$TRIAGE_SH\" --user-input '新建小说章节' --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  payload=$(echo "$output" | jq -c '.dispatch_payload')
  [ "$payload" != "null" ]
  size=$(printf '%s' "$payload" | wc -c | tr -d ' ')
  [ "$size" -le 500 ]
}

@test "--task context propagation into dispatch_payload" {
  ws="$(stage_ws "$M3_FX/workspaces/full")"
  run_with_stderr "\"$TRIAGE_SH\" --user-input '新建小说章节' --task T-001 --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.dispatch_payload | fromjson | .task == "T-001"' >/dev/null
}

@test "chat decision: dispatch_payload is null" {
  ws="$(stage_ws "$M3_FX/workspaces/empty")"
  run_with_stderr "\"$TRIAGE_SH\" --user-input 'hello' --workspace \"$ws\" --json"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.dispatch_payload == null' >/dev/null
}

@test "fix#3: malicious ReDoS plugin pattern is rejected and triage stays fast" {
  ws="$(stage_ws "$M3_FX/workspaces/empty")"
  mkdir -p "$ws/.codenook/plugins/redos-stub"
  cat > "$ws/.codenook/plugins/redos-stub/plugin.yaml" <<'EOF'
id: redos-stub
version: 0.1.0
type: domain
entry_points: {install: install.sh}
declared_subsystems: [skills]
intent_patterns:
  - "(a+)+b"
EOF
  evil="$(python3 -c "print('a'*40 + '!', end='')")"
  start=$(python3 -c "import time;print(time.time())")
  run_with_stderr "\"$TRIAGE_SH\" --user-input '$evil' --workspace \"$ws\" --json"
  end=$(python3 -c "import time;print(time.time())")
  elapsed=$(python3 -c "print(${end}-${start})")
  [ "$status" -eq 0 ]
  python3 -c "import sys; sys.exit(0 if ${elapsed} < 2.0 else 1)" \
    || { echo "triage took ${elapsed}s (>2s) — ReDoS not mitigated" >&2; exit 1; }
  echo "$output" | jq -e '.reasons | any(. | contains("regex rejected: ReDoS risk"))' >/dev/null
}
