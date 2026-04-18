#!/usr/bin/env bats
# Unit 11 — queue-runner (generic FIFO on .codenook/queues/<name>.jsonl)

load helpers/load
load helpers/assertions

QUEUE_SH="$CORE_ROOT/skills/builtin/queue-runner/queue.sh"

mk_ws() {
  local d; d="$(make_scratch)"
  mkdir -p "$d/.codenook/queues"
  echo "$d"
}

@test "queue.sh exists and is executable" {
  assert_file_exists "$QUEUE_SH"
  assert_file_executable "$QUEUE_SH"
}

@test "enqueue + peek roundtrip" {
  ws="$(mk_ws)"
  run_with_stderr "\"$QUEUE_SH\" enqueue --queue test --payload '{\"foo\":\"bar\"}' --workspace \"$ws\""
  [ "$status" -eq 0 ]
  run bash -c "\"$QUEUE_SH\" peek --queue test --workspace \"$ws\""
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.foo == "bar"' >/dev/null
}

@test "dequeue removes head" {
  ws="$(mk_ws)"
  run_with_stderr "\"$QUEUE_SH\" enqueue --queue test --payload '{\"id\":1}' --workspace \"$ws\""
  [ "$status" -eq 0 ]
  run bash -c "\"$QUEUE_SH\" dequeue --queue test --workspace \"$ws\""
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.id == 1' >/dev/null
  # Second dequeue should fail (empty)
  run_with_stderr "\"$QUEUE_SH\" dequeue --queue test --workspace \"$ws\""
  [ "$status" -eq 1 ]
}

@test "FIFO order preserved across 3+ items" {
  ws="$(mk_ws)"
  for i in 1 2 3; do
    run_with_stderr "\"$QUEUE_SH\" enqueue --queue test --payload '{\"seq\":$i}' --workspace \"$ws\""
    [ "$status" -eq 0 ]
  done
  for expected in 1 2 3; do
    run bash -c "\"$QUEUE_SH\" dequeue --queue test --workspace \"$ws\""
    [ "$status" -eq 0 ]
    actual=$(echo "$output" | jq -r '.seq')
    [ "$actual" = "$expected" ]
  done
}

@test "empty dequeue → exit 1" {
  ws="$(mk_ws)"
  run_with_stderr "\"$QUEUE_SH\" dequeue --queue empty --workspace \"$ws\""
  [ "$status" -eq 1 ]
}

@test "size reports integer count" {
  ws="$(mk_ws)"
  run bash -c "\"$QUEUE_SH\" size --queue test --workspace \"$ws\""
  [ "$status" -eq 0 ]
  [ "$output" = "0" ]
  
  run_with_stderr "\"$QUEUE_SH\" enqueue --queue test --payload '{}' --workspace \"$ws\""
  run bash -c "\"$QUEUE_SH\" size --queue test --workspace \"$ws\""
  [ "$status" -eq 0 ]
  [ "$output" = "1" ]
}

@test "list emits JSONL to stdout" {
  ws="$(mk_ws)"
  for i in 1 2; do
    run_with_stderr "\"$QUEUE_SH\" enqueue --queue test --payload '{\"n\":$i}' --workspace \"$ws\""
  done
  run bash -c "\"$QUEUE_SH\" list --queue test --workspace \"$ws\""
  [ "$status" -eq 0 ]
  # Should have 2 lines
  lines=$(echo "$output" | wc -l | tr -d ' ')
  [ "$lines" -eq 2 ]
  # Each line should be valid JSON
  echo "$output" | while read line; do
    echo "$line" | jq -e '.n' >/dev/null
  done
}

@test "concurrent enqueue (2 background subshells) → both land, size correct" {
  ws="$(mk_ws)"
  # Launch 2 enqueues in parallel
  (
    "$QUEUE_SH" enqueue --queue test --payload '{"id":"A"}' --workspace "$ws"
  ) &
  (
    "$QUEUE_SH" enqueue --queue test --payload '{"id":"B"}' --workspace "$ws"
  ) &
  wait
  
  # Check size is 2
  run bash -c "\"$QUEUE_SH\" size --queue test --workspace \"$ws\""
  [ "$status" -eq 0 ]
  [ "$output" = "2" ]
}

@test "queue file auto-created on first enqueue" {
  ws="$(mk_ws)"
  qfile="$ws/.codenook/queues/auto.jsonl"
  [ ! -f "$qfile" ]
  run_with_stderr "\"$QUEUE_SH\" enqueue --queue auto --payload '{}' --workspace \"$ws\""
  [ "$status" -eq 0 ]
  [ -f "$qfile" ]
}

@test "invalid JSON payload → exit 2" {
  ws="$(mk_ws)"
  run_with_stderr "\"$QUEUE_SH\" enqueue --queue test --payload 'not-json' --workspace \"$ws\""
  [ "$status" -eq 2 ]
}

@test "peek doesn't modify file (compare mtime/content)" {
  ws="$(mk_ws)"
  run_with_stderr "\"$QUEUE_SH\" enqueue --queue test --payload '{\"x\":1}' --workspace \"$ws\""
  qfile="$ws/.codenook/queues/test.jsonl"
  before=$(stat -f %m "$qfile" 2>/dev/null || stat -c %Y "$qfile")
  sleep 1
  run bash -c "\"$QUEUE_SH\" peek --queue test --workspace \"$ws\""
  [ "$status" -eq 0 ]
  after=$(stat -f %m "$qfile" 2>/dev/null || stat -c %Y "$qfile")
  [ "$before" = "$after" ]
}

@test "named queue isolation (A vs B)" {
  ws="$(mk_ws)"
  run_with_stderr "\"$QUEUE_SH\" enqueue --queue A --payload '{\"queue\":\"A\"}' --workspace \"$ws\""
  run_with_stderr "\"$QUEUE_SH\" enqueue --queue B --payload '{\"queue\":\"B\"}' --workspace \"$ws\""
  
  run bash -c "\"$QUEUE_SH\" dequeue --queue A --workspace \"$ws\""
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.queue == "A"' >/dev/null
  
  run bash -c "\"$QUEUE_SH\" dequeue --queue B --workspace \"$ws\""
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.queue == "B"' >/dev/null
}

@test "list --filter <jq-expr> selects matching entries only" {
  ws="$(mk_ws)"
  run_with_stderr "\"$QUEUE_SH\" enqueue --queue test --payload '{\"type\":\"a\",\"val\":1}' --workspace \"$ws\""
  run_with_stderr "\"$QUEUE_SH\" enqueue --queue test --payload '{\"type\":\"b\",\"val\":2}' --workspace \"$ws\""
  run_with_stderr "\"$QUEUE_SH\" enqueue --queue test --payload '{\"type\":\"a\",\"val\":3}' --workspace \"$ws\""
  
  # Filter for type=a
  run bash -c "\"$QUEUE_SH\" list --queue test --filter '.type == \"a\"' --workspace \"$ws\""
  [ "$status" -eq 0 ]
  lines=$(echo "$output" | wc -l | tr -d ' ')
  [ "$lines" -eq 2 ]
  # Both should have type=a
  echo "$output" | while read line; do
    echo "$line" | jq -e '.type == "a"' >/dev/null
  done
}
