# Phase dispatch manifest -- causal-analyst

## Header

```text
Task:        {task_id}
Plugin:      researchnook
Phase:       causal_probe
Role:        causal-analyst
Iteration:   {iteration}
Target dir:  {target_dir}
Prior summary: {prior_summary_path}
Criteria:    {criteria_path}
```

## 相关 workspace 知识

{KNOWLEDGE_HITS}

## Your job

可选使用 5 Why 或 driver tree 做因果追问，并标注证据边界。

## Inputs you MUST read

- `.codenook/tasks/{task_id}/state.json`
- `.codenook/tasks/{task_id}/outputs/phase-analysis.md`
- `.codenook/plugins/researchnook/roles/causal-analyst/role.md`
- The criteria document at `{criteria_path}` (if non-empty).

## Output contract

Write the report to:

```text
.codenook/tasks/{task_id}/outputs/phase-causal-probe.md
```

Begin with YAML frontmatter containing `phase`, `role`, `task`, `iteration`, `status`, `verdict`, and `summary`.
