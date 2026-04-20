# Phase-2 dispatch manifest — designer

> Template rendered by orchestrator-tick into
> `.codenook/tasks/{task_id}/prompts/phase-2-designer.md` before
> dispatching the designer role.

## Header (set by orchestrator)

```
Task:        {task_id}
Plugin:      development
Phase:       design                (2 of 11)
Role:        designer
Iteration:   {iteration}
Target dir:  {target_dir}
Prior summary: {prior_summary_path}
Criteria:    {criteria_path}
```

## Your job (one line)

Translate clarified criteria into a technical design.

## Inputs you MUST read

- `.codenook/tasks/{task_id}/state.json` — task metadata.
- All upstream outputs under `.codenook/tasks/{task_id}/outputs/` for
  phases earlier than design.
- The criteria document at `{criteria_path}` (if non-empty).
- The plugin role profile at
  `.codenook/plugins/development/roles/designer.md` — your operating
  contract; read first.

## Output contract

Write the report to:

```
.codenook/tasks/{task_id}/outputs/phase-2-designer.md
```

Begin with YAML frontmatter:

```
---
verdict: ok                # or needs_revision / blocked
summary: <≤200 chars>
iteration: {iteration}
---
```

The orchestrator reads ONLY the `verdict` field to compute the next
transition (per `.codenook/plugins/development/transitions.yaml`).

## Knowledge / skills

- Plugin-shipped knowledge: `.codenook/plugins/development/knowledge/`.
- Plugin-shipped skills:    `.codenook/plugins/development/skills/`.
- Workspace-wide:           `.codenook/memory/knowledge/` and
                            `.codenook/memory/skills/` (consume only —
                            do not write).

## Iteration cap

`{iteration}` is bumped each time the previous attempt returned
`verdict: needs_revision`. Cap is `state.max_iterations`. Beyond the
cap the orchestrator blocks the task (status=blocked).
