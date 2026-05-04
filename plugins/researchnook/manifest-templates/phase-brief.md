# Phase dispatch manifest -- brief-collector

## Header

```text
Task:        {task_id}
Plugin:      researchnook
Phase:       brief
Role:        brief-collector
Iteration:   {iteration}
Target dir:  {target_dir}
Prior summary: {prior_summary_path}
Criteria:    {criteria_path}
```

## 相关 workspace 知识

{KNOWLEDGE_HITS}

## Your job

收集研究目标、受众、问题、边界和输出形式，并用 OSTIN 建立报告 brief。

## Inputs you MUST read

- `.codenook/tasks/{task_id}/state.json`
- `.codenook/plugins/researchnook/roles/brief-collector/role.md`
- The criteria document at `{criteria_path}` (if non-empty).

## 阶段开始前的用户引导

先检查研究主题、受众和目标是否存在。缺失时在输出中列出 `## 需要用户补充的信息`，不要静默猜测。

## Output contract

Write the report to:

```text
.codenook/tasks/{task_id}/outputs/phase-brief.md
```

Begin with YAML frontmatter containing `phase`, `role`, `task`, `iteration`, `status`, `verdict`, and `summary`.
