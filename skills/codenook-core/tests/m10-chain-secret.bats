#!/usr/bin/env bats
# M10.4 — secret-scan + redact + audit (TC-M10.4-05).
# Spec: docs/task-chains.md §6.8 §9.2
# Cases: docs/m10-test-cases.md §M10.4 TC-M10.4-05

load helpers/load
load helpers/assertions
load helpers/m10_chain

# ---------------------------------------------------------------- TC-M10.4-05

@test "[m10.4] TC-M10.4-05 secret in summary stripped via secret_scan + audit" {
  ws=$(m10_seed_workspace)
  mock="$ws/_mock"
  # Pass-1 mock returns AWS-key-shaped fake secret.
  seed_mock_llm "$mock" chain_summarize $'aws-key=AKIAIOSFODNN7EXAMPLE\nrest of summary\n'

  make_ancestor_with_briefs "$ws" T-007 "feat" "implement" "done" "x"
  make_task "$ws" T-012
  make_chain "$ws" T-007 T-012

  out=$(PYTHONPATH="$M10_LIB_DIR" CN_LLM_MOCK_DIR="$mock" WS="$ws" python3 -c '
import os, chain_summarize as cs
print(cs.summarize(os.environ["WS"], "T-012"))
')
  ! echo "$out" | grep -qF "AKIAIOSFODNN7EXAMPLE" || { echo "raw secret leaked; out=$out"; return 1; }
  echo "$out" | grep -qE '\*\*\*|\[REDACTED\]' || { echo "missing redaction marker; out=$out"; return 1; }
  assert_audit "$ws" chain_summarize_redacted
  # redact != failure
  c=$(tc_audit_count "$ws" chain_summarize_failed)
  [ "$c" -eq 0 ] || { echo "should not write chain_summarize_failed; count=$c"; return 1; }
}
