# Phase dispatch manifest -- publisher

## Header

```text
Task:        {task_id}
Plugin:      researchnook
Phase:       revise_publish
Role:        publisher
Iteration:   {iteration}
Target dir:  {target_dir}
Prior summary: {prior_summary_path}
Criteria:    {criteria_path}
```

## 相关 workspace 知识

{KNOWLEDGE_HITS}

## Your job

根据审查意见修订并输出最终报告、变更摘要和剩余 caveats。

## Inputs you MUST read

- `.codenook/tasks/{task_id}/state.json`
- `.codenook/tasks/{task_id}/outputs/phase-draft-report.md` (if present)
- `.codenook/tasks/{task_id}/outputs/phase-report-review.md`
- `.codenook/plugins/researchnook/roles/publisher/role.md`
- The criteria document at `{criteria_path}` (if non-empty).

## Output contract

Write the report to:

```text
.codenook/tasks/{task_id}/outputs/phase-revise-publish.md
```

Begin with YAML frontmatter containing `phase`, `role`, `task`, `iteration`, `status`, `verdict`, and `summary`.
