# Test Criteria (v5.0 POC)

A test-phase output passes when **all** of:

## Structural (all required)

- [ ] Has a **Test Inventory** table mapping every clarify acceptance criterion to at least one test
- [ ] Has an **Execution** section with per-test pass/fail/skipped/blocked status
- [ ] Has a **Failures** section (may be empty only if zero failures)
- [ ] Has a **Coverage Gaps** section (may be empty only if zero gaps)
- [ ] Has an **Environment Notes** section

## Content Quality

- [ ] Every listed criterion is marked covered / partial / not-covered (no silent drops)
- [ ] Every failure entry contains: criterion, expected, actual, snippet
- [ ] Every skipped/blocked test has a reason
- [ ] Environment Notes lists concrete tool versions (not "latest")
- [ ] Coverage ratio in summary matches the inventory table

## Verdict Gate

- `all_pass` → advance to accept phase
- `has_failures` → route back to implementer (with failures as input) OR HITL if retries exhausted
- `blocked_by_env` → HITL with env-blocker report

## Anti-Pattern Flags (these are failures)

- ❌ Marked a test "passed" without a concrete artifact (command output, assertion, etc.)
- ❌ "Adjusted" an acceptance criterion to match what the implementation actually did
- ❌ Listed a test but did not run it (and did not mark skipped with reason)
- ❌ Coverage Gaps empty while Test Inventory shows "not-covered" rows
- ❌ Introduced new features while "testing" (scope creep — stop and return `has_failures`)
