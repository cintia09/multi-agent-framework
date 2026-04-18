#!/usr/bin/env bats
# Unit 8 — dispatch-audit (redacted append-only logger for sub-agent dispatches)

load helpers/load
load helpers/assertions

EMIT_SH="$CORE_ROOT/skills/builtin/dispatch-audit/emit.sh"

mk_ws() {
  local d; d="$(make_scratch)"
  mkdir -p "$d/.codenook"
  echo "$d"
}

str_n() {
  # print $1 copies of character 'x'
  python3 -c "import sys; sys.stdout.write('x'*$1)"
}

@test "emit.sh exists and is executable" {
  assert_file_exists "$EMIT_SH"
  assert_file_executable "$EMIT_SH"
}

@test "missing --role → exit 2" {
  ws="$(mk_ws)"
  run_with_stderr "\"$EMIT_SH\" --payload '{}' --workspace \"$ws\""
  [ "$status" -eq 2 ]
  assert_contains "$STDERR" "--role"
}

@test "missing --payload → exit 2" {
  ws="$(mk_ws)"
  run_with_stderr "\"$EMIT_SH\" --role planner --workspace \"$ws\""
  [ "$status" -eq 2 ]
  assert_contains "$STDERR" "--payload"
}

@test "normal 200-char payload → exit 0 + appends one line" {
  ws="$(mk_ws)"
  payload="{\"msg\":\"$(str_n 180)\"}"
  run_with_stderr "\"$EMIT_SH\" --role planner --payload '$payload' --workspace \"$ws\""
  [ "$status" -eq 0 ]
  assert_file_exists "$ws/.codenook/history/dispatch.jsonl"
  lines=$(wc -l <"$ws/.codenook/history/dispatch.jsonl" | tr -d ' ')
  [ "$lines" -eq 1 ]
}

@test "500-char payload → exit 0 (boundary ok)" {
  ws="$(mk_ws)"
  # Build exactly 500 chars
  export payload="$(python3 -c "import json; s='x'*492; print(json.dumps({'k':s},separators=(',',':')),end='')")"
  run_with_stderr "\"$EMIT_SH\" --role planner --payload \"\$payload\" --workspace \"$ws\""
  [ "$status" -eq 0 ]
}

@test "501-char payload → exit 1 + stderr mentions 500 char limit" {
  ws="$(mk_ws)"
  export payload="$(python3 -c "import json; s='x'*493; print(json.dumps({'k':s},separators=(',',':')),end='')")"
  run_with_stderr "\"$EMIT_SH\" --role planner --payload \"\$payload\" --workspace \"$ws\""
  [ "$status" -eq 1 ]
  assert_contains "$STDERR" "500"
}

@test "invalid JSON payload → exit 1" {
  ws="$(mk_ws)"
  run_with_stderr "\"$EMIT_SH\" --role planner --payload 'not-json' --workspace \"$ws\""
  [ "$status" -eq 1 ]
}

@test "appended line has required redacted fields" {
  ws="$(mk_ws)"
  payload='{"task":"T-007","note":"hello world this is a fairly long note for preview"}'
  run_with_stderr "\"$EMIT_SH\" --role planner --payload '$payload' --workspace \"$ws\""
  [ "$status" -eq 0 ]
  line="$(cat "$ws/.codenook/history/dispatch.jsonl")"
  echo "$line" | jq -e '.ts' >/dev/null
  echo "$line" | jq -e '.role == "planner"' >/dev/null
  echo "$line" | jq -e '.payload_size | type == "number"' >/dev/null
  echo "$line" | jq -e '.payload_sha256 | type == "string"' >/dev/null
  echo "$line" | jq -e '.payload_preview | length <= 80' >/dev/null
  # must NOT contain the full payload
  echo "$line" | jq -e '.payload == null' >/dev/null
}

@test ".codenook/history/ auto-created if missing" {
  ws="$(make_scratch)"
  # no .codenook yet
  run_with_stderr "\"$EMIT_SH\" --role planner --payload '{\"k\":1}' --workspace \"$ws\""
  [ "$status" -eq 0 ]
  assert_file_exists "$ws/.codenook/history/dispatch.jsonl"
}

@test "two consecutive calls append two distinct lines" {
  ws="$(mk_ws)"
  run_with_stderr "\"$EMIT_SH\" --role a --payload '{\"i\":1}' --workspace \"$ws\""
  [ "$status" -eq 0 ]
  run_with_stderr "\"$EMIT_SH\" --role b --payload '{\"i\":2}' --workspace \"$ws\""
  [ "$status" -eq 0 ]
  lines=$(wc -l <"$ws/.codenook/history/dispatch.jsonl" | tr -d ' ')
  [ "$lines" -eq 2 ]
}

@test "workspace defaults to \$CODENOOK_WORKSPACE when --workspace omitted" {
  ws="$(mk_ws)"
  CODENOOK_WORKSPACE="$ws" run_with_stderr "\"$EMIT_SH\" --role planner --payload '{\"k\":1}'"
  [ "$status" -eq 0 ]
  assert_file_exists "$ws/.codenook/history/dispatch.jsonl"
}

@test "payload_preview redacts sk-proj-* secrets" {
  ws="$(mk_ws)"
  payload='{"k":"sk-proj-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"}'
  run_with_stderr "\"$EMIT_SH\" --role planner --payload '$payload' --workspace \"$ws\""
  [ "$status" -eq 0 ]
  log="$ws/.codenook/history/dispatch.jsonl"
  assert_file_exists "$log"
  grep -q '\[REDACTED\]' "$log"
  ! grep -q 'sk-proj-' "$log"
}
