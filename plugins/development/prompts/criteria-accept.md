# Acceptance Criteria (v5.0 POC)

An accept-phase output passes when **all** of:

## Structural (all required)

- [ ] Has a **Goal Achievement** section citing a specific phrase from task.md
- [ ] Has a **Criteria Checklist** with per-criterion accept/reject/conditional
- [ ] Has a **Deviations** section (may be "none" if truly none)
- [ ] Has a **User-Visible Surface Check** section
- [ ] Has a **Follow-up Work** section (may be empty)
- [ ] Ends with a **Recommendation** line: Accept / Conditional Accept / Reject

## Content Quality

- [ ] Goal Achievement quotes task.md verbatim (not paraphrase)
- [ ] Every clarify acceptance criterion appears in the Criteria Checklist
- [ ] Every "conditional" checklist item has a concrete remediation description
- [ ] Deviations either marked "justified", "neutral", or "problem" — no blank statuses
- [ ] Rejection reason (if reject) names the specific criterion that failed and why

## Verdict Gate

- `accept` → task status → done; trigger post-task distillation
- `conditional_accept` → dispatch one more implementer pass with the conditions as input
- `reject` → HITL: discuss with user; may require re-clarify

## Anti-Pattern Flags (these are failures)

- ❌ Accepted a task while test summary is `has_failures` without deviation justification
- ❌ Recommendation doesn't match the checklist (e.g., says "Accept" but 2 criteria rejected)
- ❌ Goal Achievement is a restatement of the criteria checklist (should be holistic)
- ❌ Follow-up items duplicate Deviations marked "problem" (problems belong in conditions, not follow-ups)
- ❌ Conditional Accept with no list of conditions
