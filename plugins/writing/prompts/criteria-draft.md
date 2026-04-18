# Acceptance Criteria -- Draft Phase (writing)

The drafter's output is graded against the bullets below. Mark each
as: pass / fail / partial.

## Critical Criteria (any fail -> verdict: needs_revision)

### C1. Outline coverage
Every section in the outliner's output has a matching section in the
draft. No invented sections.

### C2. Length budget
Body within +/-25% of the outliner's suggested word count, OR a brief
justification appended at the end of the body if outside.

### C3. Citations present
Every external claim (statistic, study, person, product name) carries
an inline citation (Markdown link or footnote).

### C4. Voice match
The draft follows the voice / audience pinned in
`knowledge/writing-style.md`. No mid-paragraph register shifts.

## Advisory Criteria

### A1. Working title
A working title is proposed at the top (the reviser may rename later).

### A2. No structural hardcoding
Markdown headings only (no inline HTML, no horizontal rules besides
section breaks).

### A3. Hooks
Opening paragraph hooks the reader within the first 3 sentences;
closing paragraph either summarises or invites action.

## Output

Begin the file with YAML frontmatter:

```
---
verdict: ok | needs_revision | blocked
summary: <=200 chars
---
```
