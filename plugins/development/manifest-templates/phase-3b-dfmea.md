# Phase-3b dispatch manifest — dfmea-analyst

> Template rendered by orchestrator-tick into
> `.codenook/tasks/{task_id}/prompts/phase-3b-dfmea.md` before
> dispatching the dfmea-analyst role.

## Header (set by orchestrator)

```
Task:        {task_id}
Plugin:      development
Phase:       dfmea               (3b — between plan and implement; feature/refactor only)
Role:        dfmea-analyst
Iteration:   {iteration}
Target dir:  {target_dir}
Prior summary: {prior_summary_path}
Criteria:    {criteria_path}
```

## 相关 workspace 知识 (kernel auto-injected)

{KNOWLEDGE_HITS}

> 上述为基线参考(top-5,按本任务关键词排序)。如需要更深/不同主题的资料,
> 你可以自己跑 `<codenook> knowledge search "<keywords>"` 进行二次检索,
> 重点关注 dfmea / failure-mode / postmortem / incident 类条目。

## Your job (one line)

Stress-test the planner's output. Enumerate failure modes,
score them (S/O/D + RPN), recommend mitigations, decide whether
the plan needs another iteration before implementation.

## Inputs you MUST read (in order)

- `.codenook/tasks/{task_id}/state.json` — task metadata.
- `.codenook/tasks/{task_id}/outputs/phase-3-planner.md` — the
  plan. **Primary input.** Every failure mode you list must cite
  a section / module / step from here.
- `.codenook/tasks/{task_id}/outputs/phase-2-designer.md` — the
  design (background; understand WHAT the plan implements).
- `.codenook/tasks/{task_id}/outputs/phase-1-clarifier.md` — the
  requirements (used to gauge severity weighting).
- The criteria document at `{criteria_path}` (if non-empty).
- The plugin role profile at
  `.codenook/plugins/development/roles/dfmea-analyst/role.md` —
  your operating contract; **read first** for the scoring rubric
  and output format.

## Output contract

Write the report to:

```
.codenook/tasks/{task_id}/outputs/phase-3b-dfmea.md
```

Begin with YAML frontmatter:

```
---
phase: dfmea
role: dfmea-analyst
task: {task_id}
iteration: {iteration}
status: complete
verdict: ok                # or needs_revision / blocked
summary: <=200 chars>
---
```

**YAML safety**: when `summary` (or any frontmatter scalar) contains a
`:`, `#`, `{`, `[`, `&`, `*`, `?`, `|`, `>`, or starts with
`-`, **wrap the value in double quotes**.

The orchestrator reads ONLY the `verdict` field to compute the
next transition (per `.codenook/plugins/development/transitions.yaml`):
- `ok` → opens `dfmea_signoff` HITL gate, then proceeds to `implement`.
- `needs_revision` → loops back to **plan** (the planner re-reads
  your "## Mitigations summary" and revises).
- `blocked` → task halts; human must repair.

Body sections required (see role.md for full templates): Scope of
this DFMEA, Failure mode register (5-15 entries, all 12 columns
filled), Top concerns, Verdict reasoning, Mitigations summary
(non-empty when needs_revision), Knowledge Consultation Log.

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
