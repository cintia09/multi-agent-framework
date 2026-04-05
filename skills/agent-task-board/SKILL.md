---
name: agent-task-board
description: "任务表操作: 创建/更新/查看任务。调用时说 '创建任务'、'任务列表'、'更新任务状态'。"
---

# 任务表操作

## 文件位置
- JSON (机器读): `<project>/.agents/task-board.json`
- Markdown (人读): `<project>/.agents/task-board.md`
- 任务详情: `<project>/.agents/tasks/T-NNN.json`

## task-board.json 格式

```json
{
  "version": 1,
  "tasks": [
    {
      "id": "T-001",
      "title": "用户认证系统",
      "status": "created",
      "assigned_to": "designer",
      "priority": "P0",
      "created_by": "acceptor",
      "created_at": "2026-04-05T08:00:00Z",
      "updated_at": "2026-04-05T08:00:00Z"
    }
  ]
}
```

## 操作

### 创建任务 (仅 acceptor 可执行)
1. 读取 task-board.json
2. 生成新 ID: T-{max_id + 1}, 补零到 3 位
3. 创建任务 entry, status = "created", assigned_to = "designer"
4. 创建 tasks/T-NNN.json 详情文件
5. 写入 task-board.json (version + 1)
6. 同步更新 task-board.md
7. 写入 designer 的 inbox.json: "新任务 T-NNN: <title>"

### 查看任务列表
读取 task-board.json, 格式化输出:
```
📋 任务表 (version: N)
ID      状态           负责      优先级  标题
T-001   implementing   实现者    P0      用户认证系统
T-002   designing      设计者    P1      题库展示模块
```

### 更新任务状态
调用 agent-fsm skill 的状态转移逻辑。

### 同步 Markdown
每次修改 task-board.json 后, 自动生成对应的 task-board.md。

## 任务详情文件 (tasks/T-NNN.json)

```json
{
  "id": "T-001",
  "title": "用户认证系统",
  "description": "实现基于 cookie 的用户认证系统...",
  "status": "created",
  "assigned_to": "designer",
  "priority": "P0",
  "created_by": "acceptor",
  "created_at": "2026-04-05T08:00:00Z",
  "updated_at": "2026-04-05T08:00:00Z",
  "history": [],
  "goals": [
    {"id": "G-001", "title": "功能目标描述", "status": "pending", "completed_at": null, "verified_at": null}
  ],
  "artifacts": {
    "requirement": null,
    "acceptance_doc": null,
    "design": null,
    "test_spec": null,
    "test_cases": null,
    "issues_report": null,
    "fix_tracking": null,
    "review_report": null,
    "acceptance_report": null
  }
}
```

## 注意事项
- 所有写入操作使用乐观锁 (读取 version → 写入时检查 version 一致 → version + 1)
- 每次修改 JSON 后必须同步 Markdown
- 只有 acceptor 可以创建和删除任务
- 状态变更必须通过 agent-fsm 验证

## 功能目标清单 (goals)

### goals 字段说明
```json
{
  "id": "G-001",
  "title": "实现用户登录接口",
  "status": "pending|done|verified|failed",
  "completed_at": null,
  "verified_at": null,
  "note": ""
}
```

### 目标状态
| status | 含义 | 谁设置 |
|--------|------|--------|
| `pending` | 待实现 | acceptor 创建任务时定义 |
| `done` | 实现者标记完成 | implementer |
| `verified` | 验收者确认通过 | acceptor |
| `failed` | 验收者确认不通过 | acceptor |
