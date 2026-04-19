#!/usr/bin/env bats
# M9.7 — CLAUDE.md linter (memory protocol extensions).
# Spec: docs/v6/memory-and-extraction-v6.md §2.1, §5.4, §8
# Cases: docs/v6/m9-test-cases.md TC-M9.7-04, TC-M9.7-05, TC-M9.7-06

load helpers/load
load helpers/assertions

LINTER="$CORE_ROOT/skills/builtin/_lib/claude_md_linter.py"
FIX="$TESTS_ROOT/fixtures/m9-claude-md-linter"

@test "[m9.7] linter script present" {
  assert_file_exists "$LINTER"
}

@test "[m9.7] TC-M9.7-04 linter flags write to plugins" {
  run_with_stderr "python3 '$LINTER' '$FIX/bad-write-plugins.md'"
  [ "$status" -eq 1 ] || { echo "stdout: $output"; echo "stderr: $STDERR"; return 1; }
  assert_contains "$STDERR" "plugins/"
  assert_contains "$STDERR" "ERROR"
}

@test "[m9.7] TC-M9.7-06 main session cannot scan memory" {
  run_with_stderr "python3 '$LINTER' '$FIX/bad-scan-memory.md'"
  [ "$status" -eq 1 ] || { echo "stdout: $output"; echo "stderr: $STDERR"; return 1; }
  assert_contains "$STDERR" ".codenook/memory"
  assert_contains "$STDERR" "ERROR"
}

@test "[m9.7] TC-M9.7-05 fixture good CLAUDE.md passes" {
  run python3 "$LINTER" "$FIX/good-memory-protocol.md"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
}

@test "[m9.7] TC-M9.7-05 fixture missing memory protocol section fails" {
  # When --check-claude-md is passed, linter requires the memory protocol section.
  ws="$(make_scratch)"
  cp "$FIX/bad-no-memory-protocol.md" "$ws/CLAUDE.md"
  run_with_stderr "python3 '$LINTER' --check-claude-md '$ws/CLAUDE.md'"
  [ "$status" -eq 1 ] || { echo "stdout: $output"; echo "stderr: $STDERR"; return 1; }
  assert_contains "$STDERR" "上下文水位监控"
}

@test "[m9.7] TC-M9.7-05 real repo CLAUDE.md is self-consistent" {
  # The actual root CLAUDE.md must pass its own linter (self-lint gate).
  run python3 "$LINTER" "$CORE_ROOT/../../CLAUDE.md"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
}

@test "[m9.7] TC-M9.7-05 real CLAUDE.md mentions ≥5 memory-protocol tokens" {
  count=$(grep -E 'memory|extraction-log|MEMORY_INDEX|80%' "$CORE_ROOT/../../CLAUDE.md" | wc -l | tr -d ' ')
  [ "$count" -ge 5 ] || { echo "memory token count = $count, expected ≥5"; return 1; }
}

@test "[m9.7] memory-protocol checks bypass forbidden fenced blocks" {
  ws="$(make_scratch)"
  f="$ws/sample.md"
  cat > "$f" <<'EOF'
# Sample
## Anti-pattern
```forbidden
let me write plugins/foo.yaml here
grep -r ".codenook/memory" .
```
EOF
  run python3 "$LINTER" "$f"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
}
