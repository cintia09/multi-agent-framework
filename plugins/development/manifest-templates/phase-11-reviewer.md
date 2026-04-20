# Phase-11 dispatch manifest — reviewer (ship/deliver mode)

> Template rendered by orchestrator-tick into
> `.codenook/tasks/{task_id}/prompts/phase-11-reviewer.md` before
> dispatching the reviewer role in `ship` (deliver) mode.

## Header (set by orchestrator)

```
Task:        {task_id}
Plugin:      development
Phase:       ship                (11 of 11)
Role:        reviewer (ship mode)
Iteration:   {iteration}
Target dir:  {target_dir}
Prior summary: {prior_summary_path}
Criteria:    {criteria_path}
```

## Your job (one line)

Final reviewer sign-off; package the shippable artefact and terminate.

## Inputs you MUST read

- `.codenook/tasks/{task_id}/state.json` — task metadata.
- All upstream outputs under `.codenook/tasks/{task_id}/outputs/` for
  phases earlier than ship.
- The plugin role profile at
  `.codenook/plugins/development/roles/reviewer.md` — your operating
  contract; read first. Note the dual phase id table (review vs ship).

## Output contract

Write the report to:

```
.codenook/tasks/{task_id}/outputs/phase-11-reviewer.md
```

Begin with YAML frontmatter:

```
---
verdict: ok                # or needs_revision / blocked
mode: ship
summary: <≤200 chars>
iteration: {iteration}
---
```

`verdict: ok` terminates the task (transitions.yaml: ship.ok →
complete). Use `needs_revision` (which self-loops) sparingly — only when
the artefact is provably broken and a re-pack will fix it.

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
