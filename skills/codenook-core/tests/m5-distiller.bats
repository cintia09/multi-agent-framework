#!/usr/bin/env bats
# M5.4 — distiller routing skill (LLM-less; routes content to memory or knowledge)

load helpers/load
load helpers/assertions

DISTILL_SH="$CORE_ROOT/skills/builtin/distiller/distill.sh"

mk_ws_with_plugin() {
  local rules_block="$1"
  local d; d="$(make_scratch)"
  mkdir -p "$d/.codenook/plugins/development" \
           "$d/.codenook/memory" \
           "$d/.codenook/knowledge" \
           "$d/.codenook/history"
  cat >"$d/.codenook/plugins/development/plugin.yaml" <<EOF
id: development
version: 1.0.0
knowledge:
  produces:
$rules_block
EOF
  echo "$d"
}

write_content() {
  local f="$1" body="$2"
  printf '%s' "$body" > "$f"
}

@test "m5-distiller: skill exists and is executable" {
  assert_file_exists "$DISTILL_SH"
  assert_file_executable "$DISTILL_SH"
}

@test "m5-distiller: no rules → routes to memory/<plugin>/by-topic/" {
  ws="$(mk_ws_with_plugin "")"
  c="${BATS_TEST_TMPDIR}/c.md"; write_content "$c" "body content"
  run_with_stderr "\"$DISTILL_SH\" --plugin development --topic pytest-style --content \"$c\" --workspace \"$ws\""
  [ "$status" -eq 0 ]
  [ -f "$ws/.codenook/memory/development/by-topic/pytest-style.md" ]
  [ ! -f "$ws/.codenook/knowledge/by-topic/pytest-style.md" ]
}

@test "m5-distiller: matching rule routes to .codenook/knowledge/by-topic/" {
  ws="$(mk_ws_with_plugin "    promote_to_workspace_when:
      - 'topic == \"pytest-style\"'")"
  c="${BATS_TEST_TMPDIR}/c.md"; write_content "$c" "body"
  run_with_stderr "\"$DISTILL_SH\" --plugin development --topic pytest-style --content \"$c\" --workspace \"$ws\""
  [ "$status" -eq 0 ]
  [ -f "$ws/.codenook/knowledge/by-topic/pytest-style.md" ]
  [ ! -f "$ws/.codenook/memory/development/by-topic/pytest-style.md" ]
}

@test "m5-distiller: distillation log appended" {
  ws="$(mk_ws_with_plugin "")"
  c="${BATS_TEST_TMPDIR}/c.md"; write_content "$c" "body"
  run_with_stderr "\"$DISTILL_SH\" --plugin development --topic pytest-style --content \"$c\" --workspace \"$ws\""
  [ "$status" -eq 0 ]
  [ -f "$ws/.codenook/history/distillation-log.jsonl" ]
  last=$(tail -1 "$ws/.codenook/history/distillation-log.jsonl")
  echo "$last" | jq -e '.plugin == "development"' >/dev/null
  echo "$last" | jq -e '.topic  == "pytest-style"' >/dev/null
  echo "$last" | jq -e '.target_root | test("memory")' >/dev/null
  echo "$last" | jq -e '.rule_matched == false' >/dev/null
}

@test "m5-distiller: malicious __import__ expression rejected" {
  ws="$(mk_ws_with_plugin "    promote_to_workspace_when:
      - '__import__(\"os\")'")"
  c="${BATS_TEST_TMPDIR}/c.md"; write_content "$c" "x"
  run_with_stderr "\"$DISTILL_SH\" --plugin development --topic foo --content \"$c\" --workspace \"$ws\""
  # Either reject (exit 1) or treat as no-match. Per spec: rejected.
  [ "$status" -ne 0 ]
  assert_contains "$STDERR" "expression"
}

@test "m5-distiller: atomic write leaves no .tmp files" {
  ws="$(mk_ws_with_plugin "")"
  c="${BATS_TEST_TMPDIR}/c.md"; write_content "$c" "body"
  run_with_stderr "\"$DISTILL_SH\" --plugin development --topic pytest-style --content \"$c\" --workspace \"$ws\""
  [ "$status" -eq 0 ]
  found=$(find "$ws/.codenook" -name "*.tmp" -o -name ".state-*" | wc -l | tr -d ' ')
  [ "$found" = "0" ]
}

@test "m5-distiller: topic == \"pytest-style\" rule with non-matching topic stays in memory" {
  ws="$(mk_ws_with_plugin "    promote_to_workspace_when:
      - 'topic == \"pytest-style\"'")"
  c="${BATS_TEST_TMPDIR}/c.md"; write_content "$c" "body"
  run_with_stderr "\"$DISTILL_SH\" --plugin development --topic some-other-topic --content \"$c\" --workspace \"$ws\""
  [ "$status" -eq 0 ]
  [ -f "$ws/.codenook/memory/development/by-topic/some-other-topic.md" ]
  [ ! -f "$ws/.codenook/knowledge/by-topic/some-other-topic.md" ]
}
