# Phase-8 dispatch manifest — test-planner

> Template rendered by orchestrator-tick into
> `.codenook/tasks/{task_id}/prompts/phase-8-test-planner.md` before
> dispatching the test-planner role.

## Header (set by orchestrator)

```
Task:        {task_id}
Plugin:      development
Phase:       test-plan                (8 of 11)
Role:        test-planner
Iteration:   {iteration}
Target dir:  {target_dir}
Prior summary: {prior_summary_path}
Criteria:    {criteria_path}
```

## Your job (one line)

Author (or validate) the test document — cases, fixtures, pass criteria.

## Inputs you MUST read

- `.codenook/tasks/{task_id}/state.json` — task metadata.
- All upstream outputs under `.codenook/tasks/{task_id}/outputs/` for
  phases earlier than test-plan (clarifier criteria + any implementer
  output when present).
- The plugin role profile at
  `.codenook/plugins/development/roles/test-planner.md` — your
  operating contract; read first.

## Output contract

Write the report to:

```
.codenook/tasks/{task_id}/outputs/phase-8-test-planner.md
```

Begin with YAML frontmatter:

```
---
verdict: ok                # or needs_revision / blocked
summary: <≤200 chars>
case_count: <int>
runner: pytest|jest|go test|none
iteration: {iteration}
---
```

**YAML safety**: when `summary` (or any frontmatter scalar) contains a
`:`, `#`, `{`, `[`, `&`, `*`, `?`, `|`, `>`, or starts with `-`,
**wrap the value in double quotes**. Example:
`summary: "Test plan: 3 unit tests for parse_percent"`.
Unquoted colons are the most common cause of `yaml_parse_error` blocks.

Failure routing (per design §3):
* `test-only`: `needs_revision` self-loops on `test-plan`.
* All other profiles: `needs_revision` bounces to `implement`.

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
