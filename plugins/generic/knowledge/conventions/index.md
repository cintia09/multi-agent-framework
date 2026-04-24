---
id: conventions
type: knowledge
title: Generic plugin conventions
summary: Cross-phase conventions for the generic plugin pipeline, read by every role on demand.
  Captures output style (plain markdown, ATX headings), file naming, and the small set of
  rules that keep the fallback pipeline predictable.
tags:
- generic
- conventions
- plugin-shipped
---
# Generic plugin conventions (plugin-shipped knowledge)

Read by every role on demand. Captures the small set of cross-phase
conventions that keep the fallback pipeline predictable.

## Output style

- Plain Markdown, ATX headings (`##`).
- Lists use `-` (never `*` or `+`) for grep-friendliness.
- Code fences use the language tag when known (` ```python `).

## Body length budget

| Phase    | Soft cap | Hard cap |
|----------|----------|----------|
| clarify  | 80 lines | 200      |
| analyze  | 60       | 150      |
| execute  | 300      | 800      |
| deliver  | 80       | 200      |

Roles emitting beyond the hard cap should split the artefact into
sub-deliverables and note the split in the summary.

## Verdict semantics

- `ok`             -- proceed per `transitions.yaml`.
- `needs_revision` -- self-loop; orchestrator-tick bumps `iteration`
                      until `state.max_iterations` is reached.
- `blocked`        -- a precondition is missing; orchestrator pauses
                      the task until a human or upstream phase resolves.

## What this plugin does NOT do

- It does not write code (use the `development` plugin instead).
- It does not produce long-form articles (use the `writing` plugin).
- It does not ship custom skills; only the four core roles run.
