# Phase-7 dispatch manifest — submitter

> Template rendered by orchestrator-tick into
> `.codenook/tasks/{task_id}/prompts/phase-7-submitter.md` before
> dispatching the submitter role.

## Header (set by orchestrator)

```
Task:        {task_id}
Plugin:      development
Phase:       submit                (7 of 11)
Role:        submitter
Iteration:   {iteration}
Target dir:  {target_dir}
Prior summary: {prior_summary_path}
Criteria:    {criteria_path}
```

## Your job (one line)

Push the change for external review (Gerrit / GitHub PR) or mark as skipped.

## Inputs you MUST read

- `.codenook/tasks/{task_id}/state.json` — task metadata.
- All upstream outputs (especially the implementer + reviewer reports).
- The plugin role profile at
  `.codenook/plugins/development/roles/submitter.md` — your operating
  contract; read first.

## Output contract

Write the report to:

```
.codenook/tasks/{task_id}/outputs/phase-7-submitter.md
```

Begin with YAML frontmatter:

```
---
verdict: ok                # or needs_revision / blocked
summary: <≤200 chars>
submission: gerrit|github|none
pr_url: "<url or empty>"
iteration: {iteration}
---
```

**YAML safety**: when `summary` (or any frontmatter scalar) contains a
`:`, `#`, `{`, `[`, `&`, `*`, `?`, `|`, `>`, or starts with `-`,
**wrap the value in double quotes**. Example:
`summary: "Test plan: 3 unit tests for parse_percent"`.
Unquoted colons are the most common cause of `yaml_parse_error` blocks.

Failure routing (per design §3): `needs_revision` bounces to `review`
(unique among phases — local review must reconsider before another
submit attempt).

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
