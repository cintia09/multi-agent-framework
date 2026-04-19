#!/usr/bin/env bats
# M10.5 — router-agent prompt.md slot ordering (TC-M10.5-01).
# Spec: docs/v6/task-chains-v6.md §7.1
# Cases: docs/v6/m10-test-cases.md TC-M10.5-01

load helpers/load
load helpers/assertions
load helpers/m10_chain

PROMPT_MD="$CORE_ROOT/skills/builtin/router-agent/prompt.md"

# ---------------------------------------------------------------- TC-M10.5-01

@test "[m10.5] TC-M10.5-01 prompt.md has {{TASK_CHAIN}} slot above {{MEMORY_INDEX}} above {{USER_TURN}}" {
  [ -f "$PROMPT_MD" ] || { echo "prompt.md not found: $PROMPT_MD"; return 1; }

  tc=$(grep -c '{{TASK_CHAIN}}' "$PROMPT_MD" || true)
  mi=$(grep -c '{{MEMORY_INDEX}}' "$PROMPT_MD" || true)
  ut=$(grep -c '{{USER_TURN}}' "$PROMPT_MD" || true)
  [ "$tc" -eq 1 ] || { echo "{{TASK_CHAIN}} count=$tc, expected 1"; return 1; }
  [ "$mi" -eq 1 ] || { echo "{{MEMORY_INDEX}} count=$mi, expected 1"; return 1; }
  [ "$ut" -eq 1 ] || { echo "{{USER_TURN}} count=$ut, expected 1"; return 1; }

  ln_tc=$(grep -n '{{TASK_CHAIN}}' "$PROMPT_MD" | head -1 | cut -d: -f1)
  ln_mi=$(grep -n '{{MEMORY_INDEX}}' "$PROMPT_MD" | head -1 | cut -d: -f1)
  ln_ut=$(grep -n '{{USER_TURN}}' "$PROMPT_MD" | head -1 | cut -d: -f1)
  [ "$ln_tc" -lt "$ln_mi" ] || { echo "TASK_CHAIN($ln_tc) not above MEMORY_INDEX($ln_mi)"; return 1; }
  [ "$ln_mi" -lt "$ln_ut" ] || { echo "MEMORY_INDEX($ln_mi) not above USER_TURN($ln_ut)"; return 1; }

  # Pre-existing M9 sections survive.
  grep -q '{{WORKSPACE}}' "$PROMPT_MD" || { echo "missing {{WORKSPACE}}"; return 1; }
  grep -q '{{PLUGINS_SUMMARY}}' "$PROMPT_MD" || { echo "missing {{PLUGINS_SUMMARY}}"; return 1; }
}
