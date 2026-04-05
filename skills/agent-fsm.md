---
name: agent-fsm
description: "FSM 引擎: 管理 Agent 和任务的状态机。调用时说 'FSM 状态转移' 或 '更新任务状态'。"
---

# Agent FSM 引擎

## Agent 状态定义

Agent 有 3 种状态:
- `idle` — 空闲, 可接新任务
- `busy` — 忙碌, 正在处理任务
- `blocked` — 阻塞, 需要人工介入

## 任务状态定义与转移规则

合法的任务状态转移 (from → to):

```
created      → designing                 (designer 接单)
designing    → implementing              (设计完成)
implementing → reviewing                 (提交代码审查)
reviewing    → implementing              (审查退回)
reviewing    → testing                   (审查通过)
testing      → fixing                    (发现问题)
testing      → accepting                 (测试全通过)
fixing       → testing                   (修复完成, 重新测试)
accepting    → accepted                  (验收通过 ✅)
accepting    → accept_fail               (验收失败)
accept_fail  → designing                 (重新进入流程)
ANY          → blocked                   (遇到无法解决的问题)
blocked      → [previous_state]          (人工 unblock)
```

## 操作指令

### 读取 Agent 状态
```bash
cat <project>/.copilot/agents/<agent>/state.json
```

### 更新 Agent 状态
读取 → 检查 version → 修改 → 写入 (version + 1)

state.json 格式:
```json
{
  "agent": "<agent_name>",
  "status": "idle|busy|blocked",
  "current_task": null,
  "sub_state": null,
  "queue": [],
  "last_activity": "<ISO 8601>",
  "version": 0,
  "error": null
}
```

### 任务状态转移
1. 读取 task-board.json
2. 找到目标任务
3. 验证转移是否合法 (参考上面的转移规则)
4. 如果不合法, **拒绝并说明原因** — 绝不执行非法转移
5. 如果合法:
   a. 更新 task status
   b. 更新 assigned_to (根据新状态确定下一个负责 Agent)
   c. 记录 history entry: `{"from": "old", "to": "new", "by": "agent", "at": "ISO8601", "note": "..."}`
   d. 写入目标 Agent 的 inbox.json (通知)
   e. 更新 task-board.json 的 version
   f. 同步更新 task-board.md

### 状态 → Agent 映射
| 新状态 | 分配给 |
|--------|--------|
| created | designer |
| designing | designer |
| implementing | implementer |
| reviewing | reviewer |
| testing | tester |
| fixing | implementer |
| accepting | acceptor |
| accepted | — (完成) |
| accept_fail | designer |
| blocked | — (等待人工) |

### Guard 规则
在执行转移前, 检查:
1. 当前状态 → 目标状态是否在合法转移列表中
2. 执行转移的 Agent 是否是当前任务的 assigned_to
3. task-board.json 的 version 是否与读取时一致 (乐观锁)

如果任何 Guard 检查失败, 中止转移, 报告原因。
