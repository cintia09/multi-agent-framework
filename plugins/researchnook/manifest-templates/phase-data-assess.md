# Phase dispatch manifest -- evidence-assessor

## Header

```text
Task:        {task_id}
Plugin:      researchnook
Phase:       data_assess
Role:        evidence-assessor
Iteration:   {iteration}
Target dir:  {target_dir}
Prior summary: {prior_summary_path}
Criteria:    {criteria_path}
```

## 相关 workspace 知识

{KNOWLEDGE_HITS}

## Your job

评估证据强度，区分事实、数据、引用观点、假设、推断和最终判断。

## Inputs you MUST read

- `.codenook/tasks/{task_id}/state.json`
- `.codenook/tasks/{task_id}/outputs/phase-brief.md`
- `.codenook/tasks/{task_id}/outputs/phase-data-collect.md` (if present)
- `.codenook/plugins/researchnook/knowledge/evidence-confidence/index.md`
- `.codenook/plugins/researchnook/roles/evidence-assessor/role.md`
- The criteria document at `{criteria_path}` (if non-empty).

## Output contract

Write the report to:

```text
.codenook/tasks/{task_id}/outputs/phase-data-assess.md
```

Begin with YAML frontmatter containing `phase`, `role`, `task`, `iteration`, `status`, `verdict`, and `summary`.
