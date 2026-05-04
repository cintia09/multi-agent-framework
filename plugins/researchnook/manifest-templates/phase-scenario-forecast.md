# Phase dispatch manifest -- scenario-forecaster

## Header

```text
Task:        {task_id}
Plugin:      researchnook
Phase:       scenario_forecast
Role:        scenario-forecaster
Iteration:   {iteration}
Target dir:  {target_dir}
Prior summary: {prior_summary_path}
Criteria:    {criteria_path}
```

## 相关 workspace 知识

{KNOWLEDGE_HITS}

## Your job

构建基准、乐观、悲观情景，列出触发条件、敏感变量、置信度和不确定性。

## Inputs you MUST read

- `.codenook/tasks/{task_id}/state.json`
- `.codenook/tasks/{task_id}/outputs/phase-analysis.md`
- `.codenook/tasks/{task_id}/outputs/phase-data-assess.md`
- `.codenook/plugins/researchnook/roles/scenario-forecaster/role.md`
- The criteria document at `{criteria_path}` (if non-empty).

## Output contract

Write the report to:

```text
.codenook/tasks/{task_id}/outputs/phase-scenario-forecast.md
```

Begin with YAML frontmatter containing `phase`, `role`, `task`, `iteration`, `status`, `verdict`, and `summary`.
