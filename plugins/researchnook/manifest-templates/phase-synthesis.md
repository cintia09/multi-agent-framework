# Phase dispatch manifest -- synthesizer

## Header

```text
Task:        {task_id}
Plugin:      researchnook
Phase:       synthesis
Role:        synthesizer
Iteration:   {iteration}
Target dir:  {target_dir}
Prior summary: {prior_summary_path}
Criteria:    {criteria_path}
```

## 相关 workspace 知识

{KNOWLEDGE_HITS}

## Your job

综合关键发现、反方观点、置信度、决策含义和 OSTIN Next action。

## Inputs you MUST read

- `.codenook/tasks/{task_id}/state.json`
- `.codenook/tasks/{task_id}/outputs/phase-brief.md`
- `.codenook/tasks/{task_id}/outputs/phase-analysis.md`
- `.codenook/tasks/{task_id}/outputs/phase-causal-probe.md` (if present)
- `.codenook/tasks/{task_id}/outputs/phase-scenario-forecast.md` (if present)
- `.codenook/plugins/researchnook/roles/synthesizer/role.md`
- The criteria document at `{criteria_path}` (if non-empty).

## Output contract

Write the report to:

```text
.codenook/tasks/{task_id}/outputs/phase-synthesis.md
```

Begin with YAML frontmatter containing `phase`, `role`, `task`, `iteration`, `status`, `verdict`, and `summary`.
