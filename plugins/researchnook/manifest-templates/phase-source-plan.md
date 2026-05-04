# Phase dispatch manifest -- source-planner

## Header

```text
Task:        {task_id}
Plugin:      researchnook
Phase:       source_plan
Role:        source-planner
Iteration:   {iteration}
Target dir:  {target_dir}
Prior summary: {prior_summary_path}
Criteria:    {criteria_path}
```

## 相关 workspace 知识

{KNOWLEDGE_HITS}

## Your job

规划资料源、数据口径、引用规则、可信度检查和用户需要补充的输入。

## Inputs you MUST read

- `.codenook/tasks/{task_id}/state.json`
- `.codenook/tasks/{task_id}/outputs/phase-scope.md`
- `.codenook/plugins/researchnook/roles/source-planner/role.md`
- The criteria document at `{criteria_path}` (if non-empty).

## Output contract

Write the report to:

```text
.codenook/tasks/{task_id}/outputs/phase-source-plan.md
```

Begin with YAML frontmatter containing `phase`, `role`, `task`, `iteration`, `status`, `verdict`, and `summary`.
