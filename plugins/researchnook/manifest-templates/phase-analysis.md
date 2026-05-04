# Phase dispatch manifest -- analyst

## Header

```text
Task:        {task_id}
Plugin:      researchnook
Phase:       analysis
Role:        analyst
Iteration:   {iteration}
Target dir:  {target_dir}
Prior summary: {prior_summary_path}
Criteria:    {criteria_path}
```

## 相关 workspace 知识

{KNOWLEDGE_HITS}

## Your job

按选定框架做结构化分析，明确证据链、反方观点、推断和局限。

## Inputs you MUST read

- `.codenook/tasks/{task_id}/state.json`
- `.codenook/tasks/{task_id}/outputs/phase-framework-select.md`
- `.codenook/tasks/{task_id}/outputs/phase-scope.md` (if present)
- `.codenook/tasks/{task_id}/outputs/phase-data-assess.md`
- `.codenook/plugins/researchnook/roles/analyst/role.md`
- The criteria document at `{criteria_path}` (if non-empty).

## Output contract

Write the report to:

```text
.codenook/tasks/{task_id}/outputs/phase-analysis.md
```

Begin with YAML frontmatter containing `phase`, `role`, `task`, `iteration`, `status`, `verdict`, and `summary`.
