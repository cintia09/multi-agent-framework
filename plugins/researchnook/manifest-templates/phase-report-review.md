# Phase dispatch manifest -- report-reviewer

## Header

```text
Task:        {task_id}
Plugin:      researchnook
Phase:       review
Role:        report-reviewer
Iteration:   {iteration}
Target dir:  {target_dir}
Prior summary: {prior_summary_path}
Criteria:    {criteria_path}
```

## 相关 workspace 知识

{KNOWLEDGE_HITS}

## Your job

审查报告的事实、引用、逻辑、结论强度、预测/因果边界和受众适配。

## Inputs you MUST read

- `.codenook/tasks/{task_id}/state.json`
- `.codenook/tasks/{task_id}/outputs/phase-draft-report.md` (if present)
- `.codenook/tasks/{task_id}/outputs/phase-synthesis.md` (if present)
- `.codenook/plugins/researchnook/roles/report-reviewer/role.md`
- The criteria document at `{criteria_path}` (if non-empty).

## Output contract

Write the report to:

```text
.codenook/tasks/{task_id}/outputs/phase-report-review.md
```

Begin with YAML frontmatter containing `phase`, `role`, `task`, `iteration`, `status`, `verdict`, and `summary`.
