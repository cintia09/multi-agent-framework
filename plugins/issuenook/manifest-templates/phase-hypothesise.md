# Phase dispatch manifest -- hypothesizer

## Header

```text
Task:        {task_id}
Plugin:      issuenook
Phase:       hypothesise
Role:        hypothesizer
Iteration:   {iteration}
Target dir:  {target_dir}
Prior summary: {prior_summary_path}
Criteria:    {criteria_path}
```

## 相关 workspace 知识

{KNOWLEDGE_HITS}

## Your job

基于上游信息收集、日志分析、代码分析和 memory/knowledge，为当前 issue 生成 3-5 个可证伪根因假设。

## Inputs you MUST read

- Any existing upstream outputs under `.codenook/tasks/{task_id}/outputs/`:
  - `phase-info-collect.md`
  - `phase-log-analyse.md`
  - `phase-code-analyse.md`
- `.codenook/plugins/issuenook/roles/hypothesizer/role.md`
- The criteria document at `{criteria_path}` (if non-empty).

## 阶段开始前的用户引导

如果上游材料缺失，不要静默补全；说明缺失材料如何影响假设置信度。

## Output contract

Write the report to:

```text
.codenook/tasks/{task_id}/outputs/phase-hypothesise.md
```

Begin with YAML frontmatter containing `phase`, `role`, `task`, `iteration`, `status`, `verdict`, `hypothesis_count`, and `summary`.
