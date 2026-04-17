# Clarification Criteria (v5.0 POC)

A clarify-phase output passes when **all** of:

## Structural (all required)

- [ ] Has a **Goal** section with a one-sentence success statement
- [ ] Has a **Scope** section with in-scope, out-of-scope, related-deferred
- [ ] Has an **Acceptance Criteria** section with ≥ 1 testable, ordered checklist
- [ ] Has an **Assumptions** section (may be empty only if truly zero assumptions)
- [ ] Has an **Open Questions** section (may be empty only if truly zero questions)

## Content Quality

- [ ] At least one acceptance criterion can be checked automatically (not purely subjective)
- [ ] No acceptance criterion contradicts project CONVENTIONS.md or ARCHITECTURE.md
- [ ] Out-of-scope items are concrete (not "anything else")
- [ ] Blocker open questions are distinguishable from nice-to-have
- [ ] The approach sketch is ≤ 7 bullets and does NOT dive into code-level detail

## Verdict Gate

- `ready_to_implement` → pass clarify phase, advance to implement
- `needs_user_input` → route to HITL before any implementer dispatch
- `fundamental_ambiguity` → HITL with strong recommendation to rewrite task.md

## Anti-Pattern Flags (these are failures)

- ❌ Acceptance criteria phrased as tasks (verbs like "implement", "design", "write") — they must be checkable states
- ❌ Out-of-scope is empty or says "n/a" when the task has obvious adjacent work
- ❌ Open Questions contains questions the clarifier could answer from project docs
- ❌ Approach sketch includes pseudo-code or filenames (that's the implementer's job)
- ❌ The whole output is just a restatement of task.md with no added structure
