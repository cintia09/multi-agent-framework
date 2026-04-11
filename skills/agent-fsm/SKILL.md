---
name: agent-fsm
description: "FSM 引擎: 管理 Agent 和任务的状态机。调用时说 'FSM 状态转移' 或 '更新任务状态'。"
---

# Agent FSM 引擎

## FSM Mode

The framework uses a **unified linear workflow** for all tasks. Each task follows the same state machine:

```
created → designing → implementing → reviewing → testing → accepting → accepted
```

With feedback loops for quality control and a blocked state for manual intervention.

---

## Simple Linear FSM

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
designing    → hypothesizing             (分叉竞争方案)
implementing → hypothesizing             (分叉竞争方案)
hypothesizing → designing                (胜出方案 → 设计)
hypothesizing → implementing             (胜出方案 → 实现)
```

## 操作指令

### 读取 Agent 状态
```bash
cat <project>/.agents/runtime/<agent>/state.json
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
4. **目标清单检查 (goals guard)**:
   - `implementing → reviewing`: 任务的 goals 数组中所有目标的 status 必须为 `done` — 有任何 `pending` 则拒绝, 提示 implementer 还有未完成的功能目标
   - `accepting → accepted`: 任务的 goals 数组中所有目标的 status 必须为 `verified` — 有任何 `pending`/`done`/`failed` 则拒绝, 提示 acceptor 还有未验证或验证失败的目标
5. **文档门禁 (document gate)**:
   - 状态转换前，检查当前阶段要求的输出文档是否存在于 `.agents/docs/T-XXX/`
   - 模式由 `task-board.json` 顶层 `"doc_gate_mode"` 字段控制:
     - `"warn"` (默认): ⚠️ 输出警告，不阻止转换
     - `"strict"`: ⛔ 阻止转换（`LEGAL=false`），必须先写好文档

6. **DFMEA 门禁 (implementing → reviewing)**:
   - 检查 `.agents/runtime/implementer/workspace/T-NNN-dfmea.md` 是否存在
   - **内容验证**: RPN ≥ 100 的失效模式必须有缓解措施 (Mitigation 列非空)
   - 检查方法: 解析 DFMEA markdown 表格, 找到 RPN ≥ 100 的行, 验证最后一列有内容
   - 模式与文档门禁相同 (`doc_gate_mode`: warn / strict)
   - Strict 模式下: DFMEA 缺失或高 RPN 未缓解 → 拒绝转移
7. **反馈循环守卫**: 反馈转移时检查 `feedback_loops < MAX_FEEDBACK_LOOPS`
8. **HITL 审批守卫** (仅 `hitl.enabled == true` 时生效):
   - 检查任务的 `hitl_status.status == "approved"`
   - 未审批 → 拒绝转移: "⛔ HITL 审批未通过, 请先完成人工审批"
   - 配置来源: `.agents/config.json` 的 `hitl` 块

如果任何 Guard 检查失败, 中止转移, 报告原因。

### Safety Limit: Feedback Loops

**MAX_FEEDBACK_LOOPS = 10** per task.

Feedback transitions (reviewing → implementing, testing → fixing, accept_fail → designing) increment the `feedback_loops` counter:
```json
{
  "id": "T-005",
  "feedback_loops": 3,
  "feedback_history": [
    {"from": "reviewing", "to": "implementing", "at": "2026-04-10T14:00:00Z", "reason": "Security issue found"},
    {"from": "testing", "to": "fixing", "at": "2026-04-10T16:00:00Z", "reason": "2 test failures"},
    {"from": "accept_fail", "to": "designing", "at": "2026-04-11T09:00:00Z", "reason": "Missing requirement"}
  ]
}
```

When `feedback_loops >= MAX_FEEDBACK_LOOPS`:
1. Task automatically transitions to `blocked`
2. Reason: "Feedback loop safety limit reached (10/10). Manual intervention required."
3. Event logged to events.db: `fsm_feedback_limit`
4. Human must review, resolve root cause, reset counter, and unblock

---

## Legacy 3-Phase State Migration

> The 3-Phase Engineering workflow (18 states) has been unified into the linear workflow above.
> Existing tasks with `workflow_mode: "3phase"` or legacy states are automatically mapped:

| Legacy State (3-Phase) | Maps To (Unified) |
|------------------------|-------------------|
| `requirements` | `designing` |
| `architecture` | `designing` |
| `tdd_design` | `designing` |
| `dfmea` | `designing` |
| `design_review` | `reviewing` |
| `test_scripting` | `implementing` |
| `code_reviewing` | `reviewing` |
| `ci_monitoring` | `testing` |
| `ci_fixing` | `fixing` |
| `device_baseline` | `testing` |
| `deploying` | `implementing` |
| `regression_testing` | `testing` |
| `feature_testing` | `testing` |
| `log_analysis` | `testing` |
| `documentation` | `designing` |

When encountering a legacy state:
1. Map to unified state using the table above
2. Update task's `status` to the mapped state
3. Remove `workflow_mode`, `phase`, `step`, `parallel_tracks` fields
4. Preserve `feedback_loops` and `feedback_history` (these are now in unified FSM)
