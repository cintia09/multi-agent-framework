# Phase dispatch manifest -- hypothesis-verifier

## Header

```text
Task:        {task_id}
Plugin:      issuenook
Phase:       verify_hypothesis
Role:        hypothesis-verifier
Iteration:   {iteration}
Target dir:  {target_dir}
Prior summary: {prior_summary_path}
Criteria:    {criteria_path}
```

## 相关 workspace 知识

{KNOWLEDGE_HITS}

## Your job

结合日志、代码和 memory，对用户审批后的根因假设进行推理验证和反证分析。

## Inputs you MUST read

- `.codenook/tasks/{task_id}/outputs/phase-hypothesise.md`
- Any available `phase-log-analyse.md` and `phase-code-analyse.md`
- HITL decision/comment for `hypothesis_signoff`
- `.codenook/plugins/issuenook/roles/hypothesis-verifier/role.md`

## 阶段开始前的用户引导

读取 `hypothesis_signoff` 评论并解析 `SELECTED` / `EDITS` / `NOTES`。如果评论缺失或无法解析，默认验证 hypothesizer 推荐的最高优先级假设，并记录 fallback。

## Output contract

Write the report to:

```text
.codenook/tasks/{task_id}/outputs/phase-verify-hypothesis.md
```

Begin with YAML frontmatter containing `phase`, `role`, `task`, `iteration`, `status`, `verdict`, and `summary`.
