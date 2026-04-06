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

**⚡ 状态转移后必须保存记忆**:
每次任务状态成功转移后, 当前 Agent 必须调用 agent-memory skill 保存本阶段的上下文快照:
```
FSM 验证通过 → 写入 task-board.json → 同步 Markdown → 💾 保存记忆 → 通知下游 Agent
```
记忆内容包括: 工作摘要、关键决策、产出物、修改文件、交接备注。
详见 agent-memory skill。

### 阻塞任务 (block)
任何 Agent 遇到无法解决的问题时:
1. 将任务 status 设为 `blocked`
2. 在任务中记录 `blocked_reason` 和 `blocked_from` (之前的状态)
3. 发送消息到 acceptor 的 inbox: "⚠️ T-NNN blocked: <reason>"

### 解除阻塞 (unblock)
用户说 "unblock T-NNN" 或 "解除 T-NNN 阻塞" 时:
1. 读取任务的 `blocked_from` 字段获取之前的状态
2. 将 status 恢复为 `blocked_from` 的值
3. 清除 `blocked_reason` 和 `blocked_from`
4. 发送消息到原负责 Agent 的 inbox: "✅ T-NNN unblocked, 恢复到 <status>"

```json
// blocked 任务示例
{
  "id": "T-003",
  "status": "blocked",
  "blocked_from": "implementing",
  "blocked_reason": "依赖的 API 尚未就绪",
  "assigned_to": "implementer"
}
```

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

---

## 分组视图 (Grouped View)

### 触发方式

用户说 `/board --grouped` 或 "任务分组视图" 或 "按状态分组" 时显示。

### 状态分组定义

| 分组 | 包含状态 | 图标 |
|------|---------|------|
| 🔴 阻塞 (Blocked) | `blocked` | ⛔ |
| 🟡 进行中 (In Progress) | `created`, `designing`, `implementing`, `reviewing`, `testing`, `accepting`, `fixing` | ⏳ |
| 🟢 已完成 (Completed) | `accepted` | ✅ |
| ❌ 验收失败 (Accept Failed) | `accept_fail` | 🔄 |

### 输出格式

```
📋 任务表 — 分组视图 (version: N)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔴 阻塞 (1)
  ⛔ T-004  P0  implementing  💻 实现者  依赖 API 模块
     阻塞原因: 依赖的 API 尚未就绪

🟡 进行中 (3)
  ⏳ T-001  P0  reviewing     🔍 审查者  用户认证系统
  ⏳ T-003  P1  implementing  💻 实现者  题库展示模块
  ⏳ T-005  P2  designing     🏗️ 设计者  主题系统

🟢 已完成 (2)
  ✅ T-002  P0  accepted      —         数据库初始化
  ✅ T-006  P1  accepted      —         日志系统

❌ 验收失败 (1)
  🔄 T-007  P1  accept_fail   🏗️ 设计者  搜索功能

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
总计: 7 个任务 | 阻塞: 1 | 进行中: 3 | 完成: 2 | 失败: 1
```

### 实现步骤

1. 读取 `task-board.json`
2. 按 `status` 将任务分配到对应分组
3. 每个分组内按 `priority` 排序 (P0 > P1 > P2)
4. 阻塞任务额外显示 `blocked_reason`
5. 空分组不显示

---

## 项目统计面板 (Project Stats)

### 触发方式

用户说 `/board --stats` 或 "项目统计" 或 "项目概况" 时显示。

### 输出格式

```
📊 项目统计面板
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 完成率
  ████████████░░░░░░░░  60% (6/10 任务已完成)

⏱️ 平均周期时间
  全流程平均: 5.2h
  最快任务: T-006 (2.1h)
  最慢任务: T-001 (9.8h)

🐢 最慢阶段 (瓶颈分析)
  implementing  平均 2.8h  ← 瓶颈
  designing     平均 1.2h
  testing       平均 0.9h
  reviewing     平均 0.5h
  accepting     平均 0.3h

📈 吞吐量 (Throughput)
  本周完成: 4 个任务
  上周完成: 2 个任务
  趋势: ↑ 提升 100%

🔄 退回率
  审查退回: 2/8 (25%)
  测试退回: 1/8 (12.5%)
  验收退回: 0/6 (0%)

⛔ 阻塞统计
  当前阻塞: 1 个任务
  平均阻塞时间: 2.5h
  最常阻塞阶段: implementing

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### 数据源

| 指标 | 数据来源 | 计算方式 |
|------|---------|---------|
| 完成率 | `task-board.json` | `count(status=accepted) / count(all)` |
| 平均周期时间 | `tasks/T-NNN.json` 的 `cycle_time` | `avg(total_elapsed_minutes)` (仅 accepted 任务) |
| 最慢阶段 | `tasks/T-NNN.json` 的 `cycle_time.stages` | 按阶段分组, 取 `avg(duration_minutes)`, 找最大值 |
| 吞吐量 | `task-board.json` + `tasks/T-NNN.json` | 统计本周/上周 `accepted` 的任务数量 |
| 退回率 | `tasks/T-NNN.json` 的 `history` | 统计 reviewing→implementing, testing→fixing 转移次数 |
| 阻塞统计 | `task-board.json` + `cycle_time.blocked_time` | 当前 blocked 任务数, 平均阻塞时长 |

### 实现步骤

1. 读取 `task-board.json` 获取所有任务列表
2. 读取每个任务的 `tasks/T-NNN.json` 获取 `cycle_time` 数据
3. 按上表公式计算各指标
4. 格式化输出 (进度条使用 `█` 和 `░` 字符)
5. 趋势用箭头表示: ↑ 提升 / ↓ 下降 / → 持平

---

## 进度追踪 (Progress Tracking)

### 概述

根据任务 goals 的完成情况, 计算每个任务和整个项目的完成百分比。

### 任务级进度

在**任务列表**和**分组视图**中, 每个任务显示 goals 完成进度:

```
📋 任务表 (version: N)
ID      状态           负责      优先级  进度        标题
T-001   implementing   实现者    P0      ██░░░ 2/5   用户认证系统
T-002   accepted       —        P0      █████ 3/3   数据库初始化
T-003   reviewing      审查者    P1      ███░░ 3/5   题库展示模块
```

### 进度计算公式

```
任务进度 = count(goals where status in ["done", "verified"]) / count(goals)

项目整体进度 = sum(所有任务的已完成 goals) / sum(所有任务的总 goals)
```

### 进度条渲染

| 完成率 | 进度条 | 颜色语义 |
|--------|--------|---------|
| 0% | `░░░░░` | 未开始 |
| 1-25% | `█░░░░` | 刚开始 |
| 26-50% | `██░░░` | 进行中 |
| 51-75% | `███░░` | 过半 |
| 76-99% | `████░` | 接近完成 |
| 100% | `█████` | 已完成 |

### 实现步骤

1. 读取 `tasks/T-NNN.json` 的 `goals` 数组
2. 统计各 status 的 goal 数量
3. 计算百分比: `done + verified` 视为已完成
4. 渲染 5 格进度条 + 数字 (如 `███░░ 3/5`)
5. 在任务列表输出中插入进度列

### 在统计面板中显示项目进度

```
📋 项目总进度
  Goals: ████████████████░░░░  32/40 (80%)
  已验证: 28/40 (70%)  待验证: 4/40 (10%)  待实现: 8/40 (20%)
```

---

## 过滤与排序 (Filter & Sort)

### 触发方式

用户在查看任务列表时附加过滤/排序参数:

| 命令 | 说明 |
|------|------|
| `/board --assignee implementer` | 只看分配给 implementer 的任务 |
| `/board --assignee designer,reviewer` | 看多个角色的任务 |
| `/board --sort age` | 按任务年龄排序 (最老的排前面) |
| `/board --sort priority` | 按优先级排序 (P0 > P1 > P2) |
| `/board --sort progress` | 按完成进度排序 (最低进度排前面) |
| `/board --priority P0` | 只看 P0 优先级任务 |
| `/board --priority P0,P1` | 看 P0 和 P1 |
| `/board --status implementing,fixing` | 只看特定状态的任务 |
| `/board --age ">2h"` | 只看创建超过 2 小时的任务 |
| 组合使用 | 参数可叠加: `/board --assignee implementer --sort age --priority P0` |

### 过滤规则

| 过滤器 | 字段 | 匹配方式 |
|--------|------|---------|
| `--assignee <role>` | `assigned_to` | 精确匹配, 支持逗号分隔多值 |
| `--priority <level>` | `priority` | 精确匹配, 支持逗号分隔多值 |
| `--status <status>` | `status` | 精确匹配, 支持逗号分隔多值 |
| `--age "<op><duration>"` | `created_at` | 支持 `>2h`, `<1d`, `>30m` 等 |

### 排序规则

| 排序方式 | 字段 | 默认方向 |
|---------|------|---------|
| `priority` | `priority` | P0 > P1 > P2 (降序) |
| `age` | `created_at` | 最老的排前 (升序) |
| `updated` | `updated_at` | 最近更新排前 (降序) |
| `progress` | goals 完成率 | 最低进度排前 (升序) |
| `cycle` | `cycle_time.total_elapsed_minutes` | 最慢排前 (降序) |

### 默认排序

未指定排序时, 使用**复合排序**:
1. 第一排序: `priority` 降序 (P0 优先)
2. 第二排序: `updated_at` 降序 (最近更新优先)

### 实现步骤

1. 读取 `task-board.json` 获取所有任务
2. 依次应用过滤器 (AND 逻辑 — 所有过滤器都必须匹配)
3. 如需 goals 或 cycle_time 数据, 读取对应 `tasks/T-NNN.json`
4. 按指定排序方式排列
5. 格式化输出 (保持与标准列表相同的列格式, 但底部显示过滤条件)

```
📋 任务表 — 已过滤 (version: N)
过滤: assignee=implementer, priority=P0 | 排序: age ↑
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ID      状态           负责      优先级  进度        年龄    标题
T-001   implementing   实现者    P0      ██░░░ 2/5   3.2h   用户认证系统
T-004   fixing         实现者    P0      ███░░ 3/5   1.5h   API 错误处理
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
显示 2/7 个任务
```
