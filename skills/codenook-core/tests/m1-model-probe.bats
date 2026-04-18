#!/usr/bin/env bats
# Unit 4 — model-probe (M-001..M-010)

load helpers/load
load helpers/assertions

setup() {
  unset CODENOOK_AVAILABLE_MODELS || true
}

run_probe_stdout() {
  # Run probe; capture stdout to $output, stderr to $STDERR.
  STDERR_FILE="${BATS_TEST_TMPDIR:-/tmp}/probe-stderr.$$"
  run bash -c "$* 2>\"$STDERR_FILE\""
  STDERR="$(cat "$STDERR_FILE" 2>/dev/null || echo)"
  export STDERR
}

@test "probe.sh exists and is executable" {
  assert_file_exists "$PROBE_SH"
  assert_file_executable "$PROBE_SH"
}

@test "Source 1: env var CODENOOK_AVAILABLE_MODELS populates available[]" {
  CODENOOK_AVAILABLE_MODELS="opus-4.7,sonnet-4.6,haiku-4.5" \
    run_probe_stdout "\"$PROBE_SH\""
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.available | length == 3' >/dev/null
  echo "$output" | jq -e '[.available[].id] == ["opus-4.7","sonnet-4.6","haiku-4.5"]' >/dev/null
}

@test "Source 2: no env var → built-in fallback used" {
  run_probe_stdout "\"$PROBE_SH\""
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '[.available[].id] == ["opus-4.7","sonnet-4.5","haiku-4.5"]' >/dev/null
}

@test "Output catalog has refreshed_at / runtime / available / resolved_tiers (M-003)" {
  run_probe_stdout "\"$PROBE_SH\""
  [ "$status" -eq 0 ]
  echo "$output" | jq -e 'has("refreshed_at") and has("runtime") and has("available") and has("resolved_tiers")' >/dev/null
}

@test "Each available[] entry has id / tier / cost / provider" {
  CODENOOK_AVAILABLE_MODELS="opus-4.7,gpt-5.4,haiku-4.5" \
    run_probe_stdout "\"$PROBE_SH\""
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.available | all(has("id") and has("tier") and has("cost") and has("provider"))' >/dev/null
}

@test "resolved_tiers maps to first available per built-in priority" {
  CODENOOK_AVAILABLE_MODELS="opus-4.7,sonnet-4.6,haiku-4.5" \
    run_probe_stdout "\"$PROBE_SH\""
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.resolved_tiers.strong   == "opus-4.7"' >/dev/null
  echo "$output" | jq -e '.resolved_tiers.balanced == "sonnet-4.6"' >/dev/null
  echo "$output" | jq -e '.resolved_tiers.cheap    == "haiku-4.5"' >/dev/null
}

@test "--output <file> writes the catalog JSON to that file" {
  out="${BATS_TEST_TMPDIR}/cat.json"
  CODENOOK_AVAILABLE_MODELS="opus-4.7,sonnet-4.6,haiku-4.5" \
    run_probe_stdout "\"$PROBE_SH\" --output \"$out\""
  [ "$status" -eq 0 ]
  [ -f "$out" ]
  jq -e '.resolved_tiers.strong == "opus-4.7"' "$out" >/dev/null
}

@test "--check-ttl: 5-day-old catalog → exit 0" {
  cat_file="${BATS_TEST_TMPDIR}/c.json"
  ts="$(python3 -c 'import datetime as d; print((d.datetime.utcnow()-d.timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ"))')"
  jq -n --arg ts "$ts" '{refreshed_at:$ts, ttl_days:30, runtime:"x", available:[], resolved_tiers:{strong:null,balanced:null,cheap:null}}' >"$cat_file"
  run "$PROBE_SH" --check-ttl "$cat_file" --ttl-days 30
  [ "$status" -eq 0 ]
}

@test "--check-ttl: 35-day-old catalog → exit 1" {
  cat_file="${BATS_TEST_TMPDIR}/c.json"
  ts="$(python3 -c 'import datetime as d; print((d.datetime.utcnow()-d.timedelta(days=35)).strftime("%Y-%m-%dT%H:%M:%SZ"))')"
  jq -n --arg ts "$ts" '{refreshed_at:$ts, ttl_days:30, runtime:"x", available:[], resolved_tiers:{strong:null,balanced:null,cheap:null}}' >"$cat_file"
  run "$PROBE_SH" --check-ttl "$cat_file" --ttl-days 30
  [ "$status" -eq 1 ]
}

@test "--tier-priority <yaml>: user override wins (M-009)" {
  prio="${BATS_TEST_TMPDIR}/prio.yaml"
  cat >"$prio" <<'EOF'
strong:   [gpt-5.4, opus-4.7]
balanced: [sonnet-4.6]
cheap:    [haiku-4.5]
EOF
  CODENOOK_AVAILABLE_MODELS="opus-4.7,gpt-5.4,sonnet-4.6,haiku-4.5" \
    run_probe_stdout "\"$PROBE_SH\" --tier-priority \"$prio\""
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.resolved_tiers.strong == "gpt-5.4"' >/dev/null
}

@test "Probe failure path → stderr 'probe failed' + non-zero exit" {
  # Force the probe into failure by passing an unreadable --tier-priority file.
  run "$PROBE_SH" --tier-priority "/no/such/path/xx.yaml"
  [ "$status" -ne 0 ]
  assert_contains "$output" "probe failed"
}
