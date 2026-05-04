# Phase dispatch manifest -- scope-designer

## Header

```text
Task:        {task_id}
Plugin:      researchnook
Phase:       scope
Role:        scope-designer
Iteration:   {iteration}
Target dir:  {target_dir}
Prior summary: {prior_summary_path}
Criteria:    {criteria_path}
```

## 相关 workspace 知识

{KNOWLEDGE_HITS}

## Your job

把研究问题拆成范围、变量、假设、分析单元、时间/地域边界和交付物结构。

## Inputs you MUST read

- `.codenook/tasks/{task_id}/state.json`
- `.codenook/tasks/{task_id}/outputs/phase-brief.md`
- `.codenook/tasks/{task_id}/outputs/phase-framework-select.md`
- `.codenook/plugins/researchnook/roles/scope-designer/role.md`
- The criteria document at `{criteria_path}` (if non-empty).

## Output contract

Write the report to:

```text
.codenook/tasks/{task_id}/outputs/phase-scope.md
```

Begin with YAML frontmatter containing `phase`, `role`, `task`, `iteration`, `status`, `verdict`, and `summary`.
