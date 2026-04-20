#!/usr/bin/env bats
# M9.2 — extractor-batch dispatcher (TC-M9.2-03, 04, 06).
# Spec: docs/memory-and-extraction.md §5
# Cases: docs/m9-test-cases.md §M9.2

load helpers/load
load helpers/assertions
load helpers/m9_memory

BATCH_SH="$CORE_ROOT/skills/builtin/extractor-batch/extractor-batch.sh"
ROOT_CLAUDE_MD="$CORE_ROOT/../../CLAUDE.md"

# Seed an empty lookup root so every extractor is "skipped: not_present".
seed_empty_lookup() {
  local ws="$1"
  mkdir -p "$ws/_extractors"
  echo "$ws/_extractors"
}

@test "[m9.2] TC-M9.2-03 idempotent on repeat tick (same task/phase/reason)" {
  ws=$(m9_seed_workspace); m9_init_memory "$ws"
  lookup=$(seed_empty_lookup "$ws")

  for i in 1 2 3; do
    run env CN_EXTRACTOR_LOOKUP_ROOT="$lookup" bash "$BATCH_SH" \
          --task-id T-IDEM --reason after_phase --workspace "$ws" --phase complete
    [ "$status" -eq 0 ] || { echo "iter=$i status=$status output=$output"; return 1; }
  done

  keys="$ws/.codenook/memory/history/.trigger-keys"
  [ -f "$keys" ] || { echo ".trigger-keys not created"; return 1; }
  lines=$(wc -l <"$keys" | tr -d ' ')
  [ "$lines" -eq 1 ] || { echo "expected 1 trigger key line, got $lines:"; cat "$keys"; return 1; }
}

@test "[m9.2] TC-M9.2-04 different reason bypasses dedup" {
  ws=$(m9_seed_workspace); m9_init_memory "$ws"
  lookup=$(seed_empty_lookup "$ws")

  run env CN_EXTRACTOR_LOOKUP_ROOT="$lookup" bash "$BATCH_SH" \
        --task-id T-DIFF --reason after_phase --workspace "$ws" --phase complete
  [ "$status" -eq 0 ] || { echo "first call: $output"; return 1; }

  run env CN_EXTRACTOR_LOOKUP_ROOT="$lookup" bash "$BATCH_SH" \
        --task-id T-DIFF --reason context-pressure --workspace "$ws" --phase complete
  [ "$status" -eq 0 ] || { echo "second call: $output"; return 1; }

  keys="$ws/.codenook/memory/history/.trigger-keys"
  [ -f "$keys" ]
  lines=$(wc -l <"$keys" | tr -d ' ')
  [ "$lines" -eq 2 ] || { echo "expected 2 trigger key lines, got $lines:"; cat "$keys"; return 1; }
  uniq=$(sort -u "$keys" | wc -l | tr -d ' ')
  [ "$uniq" -eq 2 ] || { echo "expected 2 unique hashes, got $uniq"; return 1; }
}

@test "[m9.2] TC-M9.2-06 watermark protocol documented in CLAUDE.md" {
  [ -f "$ROOT_CLAUDE_MD" ] || { echo "no CLAUDE.md at $ROOT_CLAUDE_MD"; return 1; }
  count=$(grep -E '80%|water-?mark|context-pressure' "$ROOT_CLAUDE_MD" | wc -l | tr -d ' ')
  [ "$count" -ge 3 ] || { echo "expected ≥3 lines matching watermark vocab, got $count"; return 1; }
  grep -q "extractor-batch.sh --reason context-pressure" "$ROOT_CLAUDE_MD" \
    || { echo "literal extractor-batch.sh --reason context-pressure missing"; return 1; }
}

@test "[m9.5] TC-M9.5-08 batch inits memory skeleton before fan-out (config.yaml present)" {
  ws=$(m9_seed_workspace)
  # Simulate the partial mid-batch state the defect describes: the memory
  # directory exists but config.yaml is missing.  Pre-fix, config-extractor
  # would crash with MemoryLayoutError.
  mkdir -p "$ws/.codenook/memory/knowledge" \
           "$ws/.codenook/memory/skills" \
           "$ws/.codenook/memory/history"
  [ ! -f "$ws/.codenook/memory/config.yaml" ] || { echo "precondition failed"; return 1; }

  lookup=$(seed_empty_lookup "$ws")
  run env CN_EXTRACTOR_LOOKUP_ROOT="$lookup" bash "$BATCH_SH" \
        --task-id T-M95 --reason after_phase --workspace "$ws" --phase impl
  [ "$status" -eq 0 ] || { echo "out=$output"; return 1; }

  [ -f "$ws/.codenook/memory/config.yaml" ] \
    || { echo "config.yaml not created by extractor-batch"; ls -la "$ws/.codenook/memory"; return 1; }
}
