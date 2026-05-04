# Phase dispatch manifest -- concluder

## Header

```text
Task:        {task_id}
Plugin:      issuenook
Phase:       conclude
Role:        concluder
Iteration:   {iteration}
Target dir:  {target_dir}
Prior summary: {prior_summary_path}
Criteria:    {criteria_path}
```

## 相关 workspace 知识

{KNOWLEDGE_HITS}

## Your job

汇总最终根因、证据链、置信度、残余未知和后续建议。

## Inputs you MUST read

- All upstream outputs available in `.codenook/tasks/{task_id}/outputs/`
- `.codenook/plugins/issuenook/roles/concluder/role.md`

## 阶段开始前的用户引导

如果用户没有指定报告受众，默认输出技术 RCA + 简短管理摘要。

## Output contract

Write the report to:

```text
.codenook/tasks/{task_id}/outputs/phase-conclusion.md
```

Begin with YAML frontmatter containing `phase`, `role`, `task`, `iteration`, `status`, `verdict`, and `summary`.
