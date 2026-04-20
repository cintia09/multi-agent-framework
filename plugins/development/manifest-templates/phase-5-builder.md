# Phase-5 dispatch manifest — builder

> Template rendered by orchestrator-tick into
> `.codenook/tasks/{task_id}/prompts/phase-5-builder.md` before
> dispatching the builder role.

## Header (set by orchestrator)

```
Task:        {task_id}
Plugin:      development
Phase:       build                (5 of 11)
Role:        builder
Iteration:   {iteration}
Target dir:  {target_dir}
Prior summary: {prior_summary_path}
Criteria:    {criteria_path}
```

## Your job (one line)

Mechanical compile + lint + smoke. Pure pass/fail.

## Inputs you MUST read

- `.codenook/tasks/{task_id}/state.json` — task metadata.
- `.codenook/config/build-cmd.yaml` — cached build command (your role
  is responsible for asking the user once via HITL when missing, then
  caching the answer here per design §6.3).
- The plugin role profile at
  `.codenook/plugins/development/roles/builder.md` — your operating
  contract; read first.

## Output contract

Write the report to:

```
.codenook/tasks/{task_id}/outputs/phase-5-builder.md
```

Begin with YAML frontmatter:

```
---
verdict: ok                # ok = build (and lint) passed
                           # needs_revision = build/lint failed (bounce
                           #   to implementer per design §3)
                           # blocked = environment unusable
summary: <≤200 chars>
build_command: "<from build-cmd.yaml>"
exit_code: 0
iteration: {iteration}
---
```

**YAML safety**: when `summary` (or any frontmatter scalar) contains a
`:`, `#`, `{`, `[`, `&`, `*`, `?`, `|`, `>`, or starts with
`-`, **wrap the value in double quotes**. Example: `summary: "Test plan: 3 unit tests for parse_percent"`.
Unquoted colons are the most common cause of `yaml_parse_error` blocks.

The orchestrator reads ONLY the `verdict` field to compute the next
transition (per `.codenook/plugins/development/transitions.yaml`).

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
