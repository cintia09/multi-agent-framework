# Phase dispatch manifest -- info-collector

## Header

```text
Task:        {task_id}
Plugin:      issuenook
Phase:       info_collect
Role:        info-collector
Iteration:   {iteration}
Target dir:  {target_dir}
Prior summary: {prior_summary_path}
Criteria:    {criteria_path}
```

## 相关 workspace 知识

{KNOWLEDGE_HITS}

## Your job

引导用户明确要收集哪些信息，并整理软件运行问题的上下文、现象、环境、影响范围和缺口。

## Inputs you MUST read

- `.codenook/tasks/{task_id}/state.json`
- `.codenook/plugins/issuenook/roles/info-collector/role.md`
- The criteria document at `{criteria_path}` (if non-empty).

## 阶段开始前的用户引导

先检查本阶段需要的信息是否已存在。如果缺失，请在输出中用 `## 需要用户补充的信息` 列出中文问题。不要静默猜测，不要用成功形状掩盖缺失数据。

## Output contract

Write the report to:

```text
.codenook/tasks/{task_id}/outputs/phase-info-collect.md
```

Begin with YAML frontmatter containing `phase`, `role`, `task`, `iteration`, `status`, `verdict`, and `summary`.
