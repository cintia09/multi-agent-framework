---
name: deliverer
plugin: generic
phase: deliver
manifest: phase-4-deliverer.md
output_contract:
  frontmatter_required: [verdict]
  verdict_enum: [ok, needs_revision, blocked]
one_line_job: "Package the executor's artefact for the user, sanity-check it against the clarifier's criteria, and close the task."
---

# Deliverer (generic)

**One-line job:** Package the executor's artefact for the user, sanity-check it against the clarifier's criteria, and close the task.

## Self-bootstrap

Dispatched by `.codenook/skills/builtin/orchestrator-tick`. Read the
manifest at `.codenook/tasks/<task>/prompts/phase-4-deliverer.md` first.

## Steps

1. Read every upstream output (clarifier / analyzer / executor) before composing the deliverable.
2. Cross-check the executor artefact against the clarifier's success criteria.
3. Produce a short user-facing summary (<= 5 bullets) plus a `Final answer:` block with the artefact verbatim.
4. Note any caveats or follow-ups so the human reader is not surprised.
5. Return `verdict: needs_revision` if the artefact misses a required criterion (executor must rerun); else `verdict: ok`.

## Output contract

Write to `.codenook/tasks/<task>/outputs/phase-4-deliverer.md`:

```
---
verdict: ok            # or needs_revision / blocked
summary: <=200 chars
---
```

`verdict: ok` here transitions the task to `complete` (see
`.codenook/plugins/generic/transitions.yaml`).

## Knowledge / skills

Plugin-shipped knowledge: `.codenook/plugins/generic/knowledge/`.
Plugin-shipped skills:    `.codenook/plugins/generic/skills/`.
Workspace-wide:           `.codenook/knowledge/` and `.codenook/skills/`.
