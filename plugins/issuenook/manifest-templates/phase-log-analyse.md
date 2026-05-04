# Phase dispatch manifest -- log-analyst

## Header

```text
Task:        {task_id}
Plugin:      issuenook
Phase:       log_analyse
Role:        log-analyst
Iteration:   {iteration}
Target dir:  {target_dir}
Prior summary: {prior_summary_path}
Criteria:    {criteria_path}
```

## 相关 workspace 知识

{KNOWLEDGE_HITS}

## Your job

引导用户指定日志范围和分析侧重点，对日志做开放式异常分析，不预设根因。

## Inputs you MUST read

- `.codenook/tasks/{task_id}/state.json`
- Any upstream `phase-info-collect.md`
- `.codenook/plugins/issuenook/roles/log-analyst/role.md`

## 阶段开始前的用户引导

先检查日志位置、时间窗和分析侧重点是否已存在。缺失时用中文列出问题。

## 开放式分析要求

先列观察，再列可能解释，最后列置信度和缺口。不要宣称根因。

## Output contract

Write the report to:

```text
.codenook/tasks/{task_id}/outputs/phase-log-analyse.md
```

Begin with YAML frontmatter containing `phase`, `role`, `task`, `iteration`, `status`, `verdict`, and `summary`.
