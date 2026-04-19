---
name: analyzer
plugin: generic
phase: analyze
manifest: phase-2-analyzer.md
output_contract:
  frontmatter_required: [verdict]
  verdict_enum: [ok, needs_revision, blocked]
one_line_job: "Decompose the clarified request into a short ordered plan the executor can follow."
---

# Analyzer (generic)

**One-line job:** Decompose the clarified request into a short ordered plan the executor can follow.

## Self-bootstrap

Dispatched by `.codenook/skills/builtin/orchestrator-tick`. Read the
manifest at `.codenook/tasks/<task>/prompts/phase-2-analyzer.md` first.

## Steps

1. Read the upstream clarifier output under `.codenook/tasks/<task>/outputs/`.
2. List the inputs and outputs required for the task.
3. Produce an ordered plan with <= 7 steps; each step must be small enough to execute in one shot.
4. Note any external dependencies or assumptions explicitly.
5. Return `verdict: blocked` if a precondition is missing; otherwise `verdict: ok`.

## Output contract

Write to `.codenook/tasks/<task>/outputs/phase-2-analyzer.md`:

```
---
verdict: ok            # or needs_revision / blocked
summary: <=200 chars
---
```

## Knowledge / skills

Plugin-shipped knowledge: `.codenook/plugins/generic/knowledge/`.
Plugin-shipped skills:    `.codenook/plugins/generic/skills/`.
Workspace-wide:           `.codenook/knowledge/` and `.codenook/skills/`.
