#!/usr/bin/env bats
# M5 — model-probe wired into init.sh --refresh-models writing
# .codenook/state.json model_catalog atomically.

load helpers/load
load helpers/assertions

setup() {
  unset CODENOOK_AVAILABLE_MODELS || true
}

@test "m5-probe: --output-state-json writes model_catalog into state.json" {
  ws="$(make_scratch)"
  mkdir -p "$ws/.codenook"
  CODENOOK_AVAILABLE_MODELS="opus-4.7,sonnet-4.6,haiku-4.5" \
    run_with_stderr "\"$PROBE_SH\" --output-state-json \"$ws/.codenook/state.json\""
  [ "$status" -eq 0 ]
  [ -f "$ws/.codenook/state.json" ]
  assert_jq "$ws/.codenook/state.json" '.model_catalog.refreshed_at | test("^[0-9]{4}-[0-9]{2}-[0-9]{2}T")'
  assert_jq "$ws/.codenook/state.json" '.model_catalog.resolved_tiers.strong   == "opus-4.7"'
  assert_jq "$ws/.codenook/state.json" '.model_catalog.resolved_tiers.balanced == "sonnet-4.6"'
  assert_jq "$ws/.codenook/state.json" '.model_catalog.resolved_tiers.cheap    == "haiku-4.5"'
  assert_jq "$ws/.codenook/state.json" '.model_catalog.ttl_days >= 30'
  assert_jq "$ws/.codenook/state.json" '.model_catalog._source == "probe"'
}

@test "m5-probe: env empty → fallback recorded with _source=fallback" {
  ws="$(make_scratch)"
  mkdir -p "$ws/.codenook"
  run_with_stderr "\"$PROBE_SH\" --output-state-json \"$ws/.codenook/state.json\""
  [ "$status" -eq 0 ]
  assert_jq "$ws/.codenook/state.json" '.model_catalog._source == "fallback"'
}

@test "m5-probe: re-probe overwrites atomically (no .tmp leftover, prior keys preserved)" {
  ws="$(make_scratch)"
  mkdir -p "$ws/.codenook"
  echo '{"orchestrator": {"phase": "ready"}}' > "$ws/.codenook/state.json"
  CODENOOK_AVAILABLE_MODELS="opus-4.7,sonnet-4.6,haiku-4.5" \
    run_with_stderr "\"$PROBE_SH\" --output-state-json \"$ws/.codenook/state.json\""
  [ "$status" -eq 0 ]
  # Existing top-level state must survive the merge.
  assert_jq "$ws/.codenook/state.json" '.orchestrator.phase == "ready"'
  assert_jq "$ws/.codenook/state.json" '.model_catalog.resolved_tiers.strong == "opus-4.7"'
  # No tempfile leftover from atomic write.
  run bash -c "ls -A \"$ws/.codenook\" | grep -E '^\\.state-' | wc -l | tr -d ' '"
  [ "$status" -eq 0 ]
  [ "$output" = "0" ]
}

@test "m5-probe: init.sh --refresh-models writes model_catalog into workspace state.json" {
  ws="$(make_scratch)"
  mkdir -p "$ws/.codenook"
  CODENOOK_AVAILABLE_MODELS="opus-4.7,sonnet-4.6,haiku-4.5" \
    run_with_stderr "cd \"$ws\" && \"$INIT_SH\" --refresh-models"
  [ "$status" -eq 0 ]
  [ -f "$ws/.codenook/state.json" ]
  assert_jq "$ws/.codenook/state.json" '.model_catalog.resolved_tiers.strong == "opus-4.7"'
}

@test "m5-probe: --check-ttl handles tz-aware refreshed_at (+08:00 offset)" {
  ws="$(make_scratch)"
  mkdir -p "$ws/.codenook"
  # 2099 + tz offset → comfortably fresh.
  cat >"$ws/.codenook/state.json" <<'JSON'
{"refreshed_at": "2099-01-01T00:00:00+08:00", "ttl_days": 30}
JSON
  run_with_stderr "\"$PROBE_SH\" --check-ttl \"$ws/.codenook/state.json\" --ttl-days 30"
  [ "$status" -eq 0 ]
  assert_not_contains "$STDERR" "unparsable"
  assert_not_contains "$STDERR" "Traceback"
}
