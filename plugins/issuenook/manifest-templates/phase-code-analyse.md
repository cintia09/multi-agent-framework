# Phase dispatch manifest -- code-analyst

## Header

```text
Task:        {task_id}
Plugin:      issuenook
Phase:       code_analyse
Role:        code-analyst
Iteration:   {iteration}
Target dir:  {target_dir}
Prior summary: {prior_summary_path}
Criteria:    {criteria_path}
```

## 相关 workspace 知识

{KNOWLEDGE_HITS}

## Your job

引导用户指定代码路径和分析侧重点，对源码做开放式 review，输出风险和可疑路径。

## Inputs you MUST read

- `.codenook/tasks/{task_id}/state.json`
- Any upstream `phase-info-collect.md` and `phase-log-analyse.md`
- `.codenook/plugins/issuenook/roles/code-analyst/role.md`

## 阶段开始前的用户引导

先检查代码路径、分支/版本和分析侧重点是否已存在。缺失时用中文列出问题。

## 开放式分析要求

先列代码观察，再列可能风险。不要宣称根因。

## Output contract

Write the report to:

```text
.codenook/tasks/{task_id}/outputs/phase-code-analyse.md
```

Begin with YAML frontmatter containing `phase`, `role`, `task`, `iteration`, `status`, `verdict`, and `summary`.
