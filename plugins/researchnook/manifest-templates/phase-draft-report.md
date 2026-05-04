# Phase dispatch manifest -- report-drafter

## Header

```text
Task:        {task_id}
Plugin:      researchnook
Phase:       draft_report
Role:        report-drafter
Iteration:   {iteration}
Target dir:  {target_dir}
Prior summary: {prior_summary_path}
Criteria:    {criteria_path}
```

## 相关 workspace 知识

{KNOWLEDGE_HITS}

## Your job

根据综合洞察输出中文优先的完整研究报告或决策简报草稿。

## Inputs you MUST read

- `.codenook/tasks/{task_id}/state.json`
- `.codenook/tasks/{task_id}/outputs/phase-synthesis.md`
- `.codenook/plugins/researchnook/knowledge/_template-report/index.md`
- `.codenook/plugins/researchnook/roles/report-drafter/role.md`
- The criteria document at `{criteria_path}` (if non-empty).

## Output contract

Write the report to:

```text
.codenook/tasks/{task_id}/outputs/phase-draft-report.md
```

Begin with YAML frontmatter containing `phase`, `role`, `task`, `iteration`, `status`, `verdict`, and `summary`.
