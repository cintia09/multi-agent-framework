# Phase dispatch manifest -- framework-selector

## Header

```text
Task:        {task_id}
Plugin:      researchnook
Phase:       framework_select
Role:        framework-selector
Iteration:   {iteration}
Target dir:  {target_dir}
Prior summary: {prior_summary_path}
Criteria:    {criteria_path}
```

## 相关 workspace 知识

{KNOWLEDGE_HITS}

## Your job

根据 brief 选择 OSTIN、PESTLE、SWOT、5 Why、情景预测等框架组合。

## Inputs you MUST read

- `.codenook/tasks/{task_id}/state.json`
- `.codenook/tasks/{task_id}/outputs/phase-brief.md`
- `.codenook/plugins/researchnook/roles/framework-selector/role.md`
- `.codenook/plugins/researchnook/skills/framework-selector/SKILL.md`
- The criteria document at `{criteria_path}` (if non-empty).

## Output contract

Write the report to:

```text
.codenook/tasks/{task_id}/outputs/phase-framework-select.md
```

Begin with YAML frontmatter containing `phase`, `role`, `task`, `iteration`, `status`, `verdict`, and `summary`.
