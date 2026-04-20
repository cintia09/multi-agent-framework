# Phase-1 dispatch manifest -- clarifier

> Template rendered by orchestrator-tick into
> `.codenook/tasks/{task_id}/prompts/phase-1-clarifier.md` before
> dispatching the clarifier role.

## Header (set by orchestrator)

```
Task:        {task_id}
Plugin:      generic
Phase:       clarify                (1 of 4)
Role:        clarifier
Iteration:   {iteration}
Target dir:  {target_dir}
Prior summary: {prior_summary_path}
Criteria:    {criteria_path}
```

## Your job (one line)

Clarify the user request and surface ambiguities.

## Inputs you MUST read

- `.codenook/tasks/{task_id}/state.json` -- task metadata.
- All upstream outputs under `.codenook/tasks/{task_id}/outputs/` for
  phases earlier than clarify.
- The criteria document at `{criteria_path}` (if non-empty).
- The plugin role profile at
  `.codenook/plugins/generic/roles/clarifier.md` -- your operating
  contract; read first.

## Output contract

Write the report to:

```
.codenook/tasks/{task_id}/outputs/phase-1-clarifier.md
```

Begin with YAML frontmatter:

```
---
verdict: ok                # or needs_revision / blocked
summary: <=200 chars
iteration: {iteration}
---
```

The orchestrator reads ONLY the `verdict` field to compute the next
transition (per `.codenook/plugins/generic/transitions.yaml`).

## Knowledge / skills

{{TASK_CONTEXT}}

- Plugin-shipped knowledge: `.codenook/plugins/generic/knowledge/`.
- Plugin-shipped skills:    `.codenook/plugins/generic/skills/`.
- Workspace-wide:           `.codenook/memory/knowledge/` and
                            `.codenook/memory/skills/` (consume only).

## Iteration cap

`{iteration}` is bumped each time the previous attempt returned
`verdict: needs_revision`. Cap is `state.max_iterations`. Beyond the
cap the orchestrator blocks the task (status=blocked).
