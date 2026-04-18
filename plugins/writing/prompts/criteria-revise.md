# Acceptance Criteria -- Revise Phase (writing)

The reviser consumes the reviewer's revision list and produces the
publish-ready article. Grade with: pass / fail / partial.

## Critical Criteria (any fail -> verdict: needs_revision)

### C1. Critical items applied
Every reviewer item flagged `critical` is reflected in the revised text.

### C2. Major items applied or justified
Every reviewer item flagged `major` is either applied OR justified in
one sentence in the audit table at the end.

### C3. No regressions
Sections not flagged by the reviewer are unchanged in structure
(small copy edits OK; rewrites NOT OK).

### C4. Citations preserved
Every citation present in the draft is still present (or replaced with
a stronger source). No silent citation removals.

### C5. Voice preserved
Voice and register match `knowledge/writing-style.md` and the original
draft. The reviser does not impose a new tone.

## Advisory Criteria

### A1. Audit table
The body ends with a `Revisions applied:` table:
`| section | severity | action taken |`.

### A2. Length boundary
Final length within +/-15% of the reviewed draft (revisions tighten,
not expand).

## Output

Begin with YAML frontmatter:

```
---
verdict: ok | needs_revision | blocked
summary: <=200 chars
---
```

`verdict: ok` advances to `publish` (which opens the `pre_publish`
HITL gate before the publisher dispatches).
