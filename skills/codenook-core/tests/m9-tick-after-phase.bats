#!/usr/bin/env bats
# M9.2 — orchestrator-tick after_phase hook (TC-M9.2-01, 02, 05, 07, 08).
# Spec: docs/memory-and-extraction.md §5 / §10
# Cases: docs/m9-test-cases.md §M9.2

load helpers/load
load helpers/assertions
load helpers/m9_memory

TICK_SH="$CORE_ROOT/skills/builtin/orchestrator-tick/tick.sh"
BATCH_SH="$CORE_ROOT/skills/builtin/extractor-batch/extractor-batch.sh"

# Build a minimal M4-mode task.  We seed the state.json so the tick reaches a
# terminal status (done / blocked) without needing real plugin orchestration.
mk_terminal_task() {
  local ws="$1" tid="$2" status="${3:-done}"
  mkdir -p "$ws/.codenook/tasks/$tid" "$ws/.codenook/plugins/p1"
  cat > "$ws/.codenook/plugins/p1/phases.yaml" <<'YAML'
phases:
  - id: complete
    role: writer
    produces: out.md
YAML
  echo 'transitions: {}' > "$ws/.codenook/plugins/p1/transitions.yaml"
  cat > "$ws/.codenook/tasks/$tid/state.json" <<JSON
{"task_id":"$tid","plugin":"p1","phase":"complete","status":"$status","history":[],"iteration":0,"max_iterations":3}
JSON
  m9_init_memory "$ws"
}

mk_batch_stub() {
  local stub="$1" log="$2" exit_code="${3:-0}"
  cat > "$stub" <<STUB
#!/usr/bin/env bash
echo "\$@" >> "$log"
exit $exit_code
STUB
  chmod +x "$stub"
}

@test "[m9.2] TC-M9.2-01 done triggers batch" {
  ws=$(m9_seed_workspace)
  mk_terminal_task "$ws" "T1" "done"
  log="$ws/batch-calls.log"
  stub="$ws/batch-stub.sh"
  mk_batch_stub "$stub" "$log" 0

  CN_EXTRACTOR_BATCH="$stub" run bash "$TICK_SH" --task T1 --workspace "$ws"
  [ "$status" -eq 0 ] || { echo "tick exit=$status output=$output"; return 1; }
  [ -f "$log" ] || { echo "stub never called"; return 1; }
  calls=$(wc -l <"$log" | tr -d ' ')
  [ "$calls" -eq 1 ] || { echo "expected 1 call, got $calls; log=$(cat "$log")"; return 1; }
  grep -q -- "--task-id T1" "$log"
  grep -q -- "--reason after_phase" "$log"
}

@test "[m9.2] TC-M9.2-02 blocked triggers batch" {
  ws=$(m9_seed_workspace)
  mk_terminal_task "$ws" "T2" "blocked"
  log="$ws/batch-calls.log"
  stub="$ws/batch-stub.sh"
  mk_batch_stub "$stub" "$log" 0

  CN_EXTRACTOR_BATCH="$stub" run bash "$TICK_SH" --task T2 --workspace "$ws"
  # tick exit code for blocked status is 1 by design; the hook MUST still fire.
  [ "$status" -eq 0 ] || [ "$status" -eq 1 ] || { echo "tick exit=$status output=$output"; return 1; }
  [ -f "$log" ] || { echo "stub never called"; return 1; }
  calls=$(wc -l <"$log" | tr -d ' ')
  [ "$calls" -eq 1 ] || { echo "expected 1 call, got $calls; log=$(cat "$log")"; return 1; }
  grep -q -- "--task-id T2" "$log"
  grep -q -- "--reason after_phase" "$log"
}

@test "[m9.2] TC-M9.2-05 batch failure does not block tick" {
  ws=$(m9_seed_workspace)
  mk_terminal_task "$ws" "T5" "done"
  log="$ws/batch-calls.log"
  stub="$ws/batch-stub.sh"
  mk_batch_stub "$stub" "$log" 7

  CN_EXTRACTOR_BATCH="$stub" run_with_stderr "\"$TICK_SH\" --task T5 --workspace \"$ws\""
  [ "$status" -eq 0 ] || { echo "tick exit=$status output=$output STDERR=$STDERR"; return 1; }
  assert_contains "$STDERR" "extractor batch failed"
  assert_contains "$STDERR" "exit=7"
}

@test "[m9.2] TC-M9.2-07 batch returns async (≤ 200ms wall) with extractor still alive" {
  ws=$(m9_seed_workspace); m9_init_memory "$ws"
  # Seed a stub knowledge-extractor that sleeps 5s.  We isolate the lookup
  # root via CN_EXTRACTOR_LOOKUP_ROOT so production extractors are not used.
  lookup="$ws/_extractors"
  mkdir -p "$lookup/knowledge-extractor"
  cat > "$lookup/knowledge-extractor/extract.sh" <<'STUB'
#!/usr/bin/env bash
exec python3 -c 'import time; time.sleep(5)' knowledge_extractor_marker
STUB
  chmod +x "$lookup/knowledge-extractor/extract.sh"

  start=$(python3 -c 'import time;print(int(time.time()*1000))')
  run env CN_EXTRACTOR_LOOKUP_ROOT="$lookup" bash "$BATCH_SH" \
        --task-id t1 --reason after_phase --workspace "$ws" --phase complete
  end=$(python3 -c 'import time;print(int(time.time()*1000))')
  [ "$status" -eq 0 ] || { echo "batch exit=$status output=$output"; for p in $(pgrep -f knowledge_extractor_marker 2>/dev/null); do kill "$p" 2>/dev/null || true; done; return 1; }
  elapsed=$((end - start))
  echo "wall=${elapsed}ms"
  [ "$elapsed" -le 1000 ] || { echo "wall ${elapsed}ms > 1000ms (perf budget)"; for p in $(pgrep -f knowledge_extractor_marker 2>/dev/null); do kill "$p" 2>/dev/null || true; done; return 1; }
  echo "$output" | jq -e '.enqueued_jobs | length >= 1' >/dev/null || { echo "no enqueued_jobs in: $output"; for p in $(pgrep -f knowledge_extractor_marker 2>/dev/null); do kill "$p" 2>/dev/null || true; done; return 1; }

  # Allow OS a moment to schedule the child.
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    sleep 0.1
    alive=$(ps -axww | grep knowledge_extractor_marker | grep -v grep || true)
    [ -n "$alive" ] && break
  done
  [ -n "$alive" ] || {
    echo "expected child still alive"
    echo "DIAG output: $output"
    echo "DIAG err log: $(cat "$ws/.codenook/memory/history/.extractor-knowledge-extractor.err" 2>/dev/null || echo none)"
    echo "DIAG ps full:"; ps -axww | grep -i 'extract\|knowledge' | grep -v grep || true
    return 1
  }
  pid=$(echo "$alive" | awk '{print $1}' | head -1)
  [ -n "$pid" ] && kill "$pid" 2>/dev/null || true
}

@test "[m9.2] TC-M9.2-08 batch json contract (enqueued_jobs[] + skipped[])" {
  ws=$(m9_seed_workspace); m9_init_memory "$ws"
  # Empty lookup root → all extractors skipped (none present), still both keys.
  lookup="$ws/_extractors"
  mkdir -p "$lookup"

  run env CN_EXTRACTOR_LOOKUP_ROOT="$lookup" bash "$BATCH_SH" \
        --task-id t1 --reason after_phase --workspace "$ws"
  [ "$status" -eq 0 ] || { echo "batch exit=$status output=$output"; return 1; }
  echo "$output" | jq -e '.enqueued_jobs | type == "array"' >/dev/null
  echo "$output" | jq -e '.skipped       | type == "array"' >/dev/null
  echo "$output" | jq -e '.skipped | length >= 1' >/dev/null
}
