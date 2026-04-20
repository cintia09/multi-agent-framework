# Phase-6 dispatch manifest — reviewer (review/local mode)

> Template rendered by orchestrator-tick into
> `.codenook/tasks/{task_id}/prompts/phase-6-reviewer.md` before
> dispatching the reviewer role in `review` (local) mode.

## Header (set by orchestrator)

```
Task:        {task_id}
Plugin:      development
Phase:       review                (6 of 11)
Role:        reviewer (local mode)
Iteration:   {iteration}
Target dir:  {target_dir}
Prior summary: {prior_summary_path}
Criteria:    {criteria_path}
```

## Your job (one line)

Critique the diff and list ≤5 must-fix defects. No edits.

## Inputs you MUST read

- `.codenook/tasks/{task_id}/state.json` — task metadata.
- All upstream outputs under `.codenook/tasks/{task_id}/outputs/` for
  phases earlier than review (especially `phase-4-implementer.md` and
  `phase-5-builder.md`).
- The plugin role profile at
  `.codenook/plugins/development/roles/reviewer.md` — your operating
  contract; read first. Note the dual phase id table (review vs ship).

## Output contract

Write the report to:

```
.codenook/tasks/{task_id}/outputs/phase-6-reviewer.md
```

Begin with YAML frontmatter:

```
---
verdict: ok                # or needs_revision / blocked
mode: review
summary: <≤200 chars>
iteration: {iteration}
---
```

The orchestrator reads ONLY the `verdict` field to compute the next
transition (per `.codenook/plugins/development/transitions.yaml`).
Failure routing:
* feature/hotfix/refactor/docs: `needs_revision` → `implement`
* review profile:               `needs_revision` → `clarify`

## Knowledge / skills

{{TASK_CONTEXT}}

- Plugin-shipped knowledge: `.codenook/plugins/development/knowledge/`.
- Plugin-shipped skills:    `.codenook/plugins/development/skills/`.
- Workspace-wide:           `.codenook/memory/knowledge/` and
                            `.codenook/memory/skills/` (consume only —
                            do not write).

## Iteration cap

`{iteration}` is bumped each time the previous attempt returned
`verdict: needs_revision`. Cap is `state.max_iterations`. Beyond the
cap the orchestrator blocks the task (status=blocked).
