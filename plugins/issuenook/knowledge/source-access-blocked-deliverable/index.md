---
id: source-access-blocked-deliverable
type: playbook
title: "Methodology: useful investigation output when source-code access is blocked"
summary: "When source-code access is unavailable, do not silently stop. Deliver a medium-confidence analysis with log-derived evidence, predicted code-query plan, explicit caveats, and the exact artefacts needed to upgrade confidence."
tags:
  - issuenook
  - methodology
  - source-access-blocked
  - fallback
  - code-analysis
  - hypothesis-verification
---

# Source access blocked deliverable

## Problem

Issue investigations often need source code that the current operator
cannot access. Blocking immediately wastes time when logs, issue context,
and public API behaviour can still narrow the search space.

## Contract

The analysis may proceed at **medium confidence** when the report includes
all of these:

1. **Evidence-derived call / event graph** from logs, configuration,
   public interfaces, or user-provided snippets.
2. **Executable source-query plan** for the owner who has access.
3. **Explicit confidence caveat** that names what is inferred and what
   still requires source confirmation.

## Required wording

> Confidence: MEDIUM. The suspected code path is inferred from logs,
> configuration, issue context, or public interfaces. Final confirmation
> requires running the source-query plan against the restricted source
> tree.

## Source-query plan shape

```bash
git grep -nE '<symptom-or-symbol-regex>' -- '<suspected-path>/**'
git log --oneline <good-ref>..<bad-ref> -- '<suspected-path>/**'
git grep -nE '<state|error|timeout|retry keyword>' -- '<related-path>/**'
```

Replace placeholders with concrete symbols, paths, refs, or log strings
from the investigation.

## When not to use this fallback

- The issue has no reliable logs, context, or observable behaviour.
- The user requires high-confidence source-confirmed RCA.
- The inferred graph would be mostly invented rather than evidence-linked.
