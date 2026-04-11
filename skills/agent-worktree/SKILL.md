---
name: agent-worktree
description: "Git Worktree 并行任务管理: 为每个任务创建独立工作目录和分支。Use when creating parallel tasks, managing worktrees, or merging completed task branches."
---

# Skill: Git Worktree — 并行任务管理

纯 Git Worktree 操作。每个任务获得独立的工作目录和分支，互不干扰。

> ⚠️ 本 skill 只负责 git worktree 操作，不涉及 `.agents/` 系统初始化。

## 命令

### create — 创建 Worktree

```bash
TASK_ID="$1"                    # e.g. T-042
PROJECT_DIR="$(git rev-parse --show-toplevel)"
PROJECT_NAME="$(basename "$PROJECT_DIR")"
WORKTREE_DIR="${PROJECT_DIR}/../${PROJECT_NAME}--${TASK_ID}"
BRANCH_NAME="task/${TASK_ID}"

git worktree add "$WORKTREE_DIR" -b "$BRANCH_NAME"
```

输出:
```
✅ Worktree 已创建
━━━━━━━━━━━━━━━━━━
任务: T-042 | 分支: task/T-042
目录: ../project--T-042
下一步: cd ../project--T-042
```

### list — 列出活跃 Worktree

```bash
git worktree list
```

### status — Worktree 状态概览

```bash
echo "📊 Worktree 状态:"
git worktree list | while read -r dir commit branch; do
  branch="${branch//[\[\]]/}"
  if [[ "$branch" == task/* ]]; then
    task_id="${branch#task/}"
    changed=$(cd "$dir" && git diff --stat HEAD | tail -1 || echo "clean")
    ahead=$(cd "$dir" && git rev-list --count main..HEAD 2>/dev/null || echo "0")
    behind=$(cd "$dir" && git rev-list --count HEAD..main 2>/dev/null || echo "0")
    echo "  $task_id ($branch): $changed | ↑${ahead} ↓${behind} vs main"
  fi
done
```

### merge — 合并 & 清理

```bash
TASK_ID="$1"
PROJECT_DIR="$(git rev-parse --show-toplevel)"
PROJECT_NAME="$(basename "$PROJECT_DIR")"
WORKTREE_DIR="${PROJECT_DIR}/../${PROJECT_NAME}--${TASK_ID}"
BRANCH_NAME="task/${TASK_ID}"

# 1. 回到主 worktree 并合并
cd "$PROJECT_DIR"
git merge "$BRANCH_NAME" --no-ff -m "Merge task/${TASK_ID}"

# 2. 清理 worktree
git worktree remove "$WORKTREE_DIR" --force
git branch -d "$BRANCH_NAME"
```

输出:
```
✅ 合并完成
━━━━━━━━━━━━
任务: T-042 | 分支: task/T-042 → main
Worktree: 已清理 ✅
```

## 使用场景

| 场景 | 命令 |
|------|------|
| 并行开发两个功能 | `create T-042` + `create T-043` |
| 紧急修复插入 | `create T-FIX-001` |
| A/B 方案对比 | 同一需求创建两个 worktree |

## 约束

- 合并前建议 rebase: `cd ../project--T-042 && git rebase main`
- Worktree 目录命名规则: `<project-name>--<task-id>`
