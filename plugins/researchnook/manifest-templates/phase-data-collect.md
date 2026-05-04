# Phase dispatch manifest -- data-collector

## Header

```text
Task:        {task_id}
Plugin:      researchnook
Phase:       data_collect
Role:        data-collector
Iteration:   {iteration}
Target dir:  {target_dir}
Prior summary: {prior_summary_path}
Criteria:    {criteria_path}
```

## 相关 workspace 知识

{KNOWLEDGE_HITS}

## Your job

汇总用户提供或可访问的资料、指标、引用、摘录和证据清单。

## Inputs you MUST read

- `.codenook/tasks/{task_id}/state.json`
- `.codenook/tasks/{task_id}/outputs/phase-source-plan.md`
- `.codenook/plugins/researchnook/roles/data-collector/role.md`
- The criteria document at `{criteria_path}` (if non-empty).

## Output contract

Write the report to:

```text
.codenook/tasks/{task_id}/outputs/phase-data-collect.md
```

Begin with YAML frontmatter containing `phase`, `role`, `task`, `iteration`, `status`, `verdict`, and `summary`.
