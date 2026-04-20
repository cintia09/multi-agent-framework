# Phase-9 dispatch manifest — tester

> Template rendered by orchestrator-tick into
> `.codenook/tasks/{task_id}/prompts/phase-9-tester.md` before
> dispatching the tester role.

## Header (set by orchestrator)

```
Task:        {task_id}
Plugin:      development
Phase:       test                (9 of 11)
Role:        tester
Iteration:   {iteration}
Target dir:  {target_dir}
Prior summary: {prior_summary_path}
Criteria:    {criteria_path}
```

## Your job (one line)

Run the relevant tests; report failures.

## Inputs you MUST read

- `.codenook/tasks/{task_id}/state.json` — task metadata.
- All upstream outputs under `.codenook/tasks/{task_id}/outputs/` for
  phases earlier than test.
- The criteria document at `{criteria_path}` (if non-empty).
- The plugin role profile at
  `.codenook/plugins/development/roles/tester.md` — your operating
  contract; read first.

## Output contract

Write the report to:

```
.codenook/tasks/{task_id}/outputs/phase-9-tester.md
```

Begin with YAML frontmatter:

```
---
verdict: ok                # or needs_revision / blocked
summary: <≤200 chars>
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

- Plugin-shipped knowledge: `.codenook/plugins/development/knowledge/`.
- Plugin-shipped skills:    `.codenook/plugins/development/skills/`.
- Workspace-wide:           `.codenook/memory/knowledge/` and
                            `.codenook/memory/skills/` (consume only —
                            do not write).

## Iteration cap

`{iteration}` is bumped each time the previous attempt returned
`verdict: needs_revision`. Cap is `state.max_iterations`. Beyond the
cap the orchestrator blocks the task (status=blocked).
