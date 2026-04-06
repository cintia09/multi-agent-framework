---
name: agent-switch
description: "Agent 状态面板: 查看所有 Agent 的状态、任务分配和消息队列。Use when checking agent status or task overview."
---

# Agent 角色管理

## 查看所有 Agent 状态 (/agent status)
读取项目下每个 Agent 的 state.json, 汇总显示:

```
🤖 Agent 状态面板
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
角色       状态     当前任务    队列        最后活动
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 验收者   idle     —          —          10:00
🏗️ 设计者   busy     T-002      —          10:30
💻 实现者   idle     —          [T-003]    09:45
🔍 审查者   idle     —          —          09:00
🧪 测试者   busy     T-001      —          10:15
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 任务表摘要: 3 个任务 (1 完成, 1 进行中, 1 待处理)

📊 近 24h 活动 (来自 events.db):
  💻 实现者: 42 次操作 | 🔍 审查者: 15 次 | 🧪 测试者: 8 次

📋 任务流水线:

  T-008: "自动记忆沉淀"
  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐
  │Acceptor│─▶│Designer│─▶│Implemen│─▶│Reviewer│─▶│ Tester │
  │  🎯 ✅ │  │ 🏗️ ✅ │  │ 💻 ⏳  │  │ 🔍 ⏸️ │  │ 🧪 ⏸️ │
  └────────┘  └────────┘  └────────┘  └────────┘  └────────┘
                               ▲ 当前

  T-009: "智能记忆加载"
  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐
  │Acceptor│─▶│Designer│─▶│Implemen│─▶│Reviewer│─▶│ Tester │
  │  🎯 ✅ │  │ 🏗️ ⏳ │  │ 💻 ⏸️ │  │ 🔍 ⏸️ │  │ 🧪 ⏸️ │
  └────────┘  └────────┘  └────────┘  └────────┘  └────────┘
                    ▲ 当前

### 流水线渲染逻辑
根据任务 status 确定当前阶段:
- `created` / `designing` → Designer 位置
- `implementing` / `fixing` → Implementer 位置
- `reviewing` → Reviewer 位置
- `testing` → Tester 位置
- `accepting` → Acceptor (第二轮)
- `accepted` → 全部 ✅
- `blocked` → 当前阶段标记 ⛔

状态图标:
- ✅ 已完成的阶段
- ⏳ 当前活动阶段
- ⏸️ 尚未到达的阶段
- ⛔ 阻塞的阶段

只显示 status != accepted 的任务（进行中的任务）。

🚨 阻塞任务 (如有):
  ⛔ T-004: blocked — "依赖的 API 尚未就绪" (来自 implementing)
  → 说 "unblock T-004" 解除
```

### 实现步骤:
```bash
AGENTS_DIR="$(git rev-parse --show-toplevel 2>/dev/null)/.agents"
[ -d "$AGENTS_DIR" ] || AGENTS_DIR="./.agents"

for agent in acceptor designer implementer reviewer tester; do
  cat "$AGENTS_DIR/runtime/$agent/state.json"
done

cat "$AGENTS_DIR/task-board.json"

# 事件摘要 (如果 events.db 存在)
if [ -f "$AGENTS_DIR/events.db" ]; then
  sqlite3 "$AGENTS_DIR/events.db" \
    "SELECT agent, count(*) as actions FROM events WHERE created_at > datetime('now', '-24 hours') GROUP BY agent ORDER BY actions DESC;"
fi
```

## 切换角色 (/agent <name>)
用户说 "/agent <name>" 或 "切换到 <角色名>" 时:
1. 确认目标角色有效: acceptor | designer | implementer | reviewer | tester
2. **⛔ 前置条件预检**: 读取 task-board.json，检查目标角色是否有匹配状态的任务:
   | 角色 | 需要的任务状态 | 例外 |
   |------|---------------|------|
   | acceptor | `accepting` 或有新需求 | 始终可切换（可接收新需求） |
   | designer | `created` 或 `accept_fail` | — |
   | implementer | `implementing` 或 `fixing` | — |
   | reviewer | `reviewing` | — |
   | tester | `testing` | — |
   - 如果无匹配任务 (且无例外):
     - **⚠️ 警告** (不直接阻断，但明确提示): "⚠️ 当前没有 `<expected_status>` 状态的任务。切换到 <角色> 后将无任务可处理。"
     - 显示任务状态分布
     - 询问用户: "是否仍要切换？" (给用户最终决定权)
     - 如用户确认 → 继续切换; 如用户取消 → 建议正确的角色
3. 保存当前 Agent 状态 (如果有)
4. **写入 active-agent 标记** (供 Hooks 读取):
   ```bash
   echo "<agent_name>" > <project>/.agents/runtime/active-agent
   ```
5. 清洁上下文 (RESPAWN 模式 — 不携带上一个 Agent 的工作记忆)
6. 加载目标 Agent 的 skill (agent-<name>.md)
7. **自动处理 inbox**: 读取未读消息, 显示给用户, 标记为已读:
   ```bash
   INBOX="<project>/.agents/runtime/<agent>/inbox.json"
   UNREAD=$(jq '[.messages[] | select(.read == false)]' "$INBOX")
   # 显示每条未读消息, 然后标记已读:
   jq '.messages |= [.[] | .read = true]' "$INBOX" > "${INBOX}.tmp" && mv "${INBOX}.tmp" "$INBOX"
   ```
8. **显示任务概览**: 检查 task-board 中分配给当前 agent 的任务
9. **智能加载任务记忆**: 如果有分配的任务, 自动读取 `.agents/memory/T-NNN-memory.json`, 根据当前角色过滤字段 (参见 agent-memory 的"智能记忆加载"章节), 以可读文本格式展示上一阶段的关键信息
10. **Staleness 警告**: 如果有长时间 (>24h) 未活动的任务, 提醒用户
11. 执行目标 Agent 的启动流程 (定义在对应 skill 中)
12. 打印: "🔄 已切换到 <角色名> (<emoji>)"

### 退出角色
用户说 "退出角色" 或 "exit agent" 时:
```bash
rm -f <project>/.agents/runtime/active-agent
```

## 批处理模式 (自动处理所有待办)

用户说 "处理任务" / "process tasks" / "监控任务" / "开始工作" 时，进入批处理循环：

### 循环流程

```
┌─────────────────────────────────────────┐
│           批处理循环开始                   │
│  当前角色: <active-agent>                │
└─────────┬───────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────┐
│ 1. 检查 inbox — 读取所有未读消息          │
│    显示每条消息内容                       │
│    标记已读                              │
└─────────┬───────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────┐
│ 2. 扫描 task-board.json                  │
│    筛选: assigned_to == 当前角色          │
│    且 status 属于当前角色负责的状态        │
│    按 priority 排序 (high > medium > low) │
└─────────┬───────────────────────────────┘
          │
     有待办任务？
     ┌────┴────┐
     │ YES     │ NO
     ▼         ▼
┌──────────┐  ┌──────────────────────────┐
│ 3. 处理   │  │ 报告: "✅ 没有更多待办任务 │
│ 第一个    │  │  <角色> 进入待命状态"      │
│ 优先级最  │  │  显示处理摘要             │
│ 高的任务  │  └──────────────────────────┘
└────┬─────┘
     │ 处理完成
     ▼
┌─────────────────────────────────────────┐
│ 4. 更新任务状态 (FSM 转移)               │
│    💾 保存本阶段记忆 (agent-memory)       │
│    写入下一个 Agent 的 inbox             │
│    auto-dispatch 触发                    │
└─────────┬───────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────┐
│ 5. 报告进度:                             │
│    "✅ T-NNN 已完成 → 状态: <new_status>" │
│    "🔄 检查下一个任务..."                  │
└─────────┬───────────────────────────────┘
          │
          └──── 回到步骤 2
```

### 每个角色的处理逻辑

| 角色 | 负责状态 | 处理动作 | 完成后转移到 |
|------|---------|---------|-------------|
| 🎯 acceptor | `accepting` | 逐项验证 goals → 标记 verified/failed | `accepted` 或 `accept_fail` |
| 🏗️ designer | `created`, `accept_fail` | 输出设计文档 + 测试规格 | `designing` → `implementing` |
| 💻 implementer | `implementing`, `fixing` | 编码实现 + 标记 goals done | `reviewing` |
| 🔍 reviewer | `reviewing` | 审查代码 + 输出审查报告 | `testing` 或退回 `implementing` |
| 🧪 tester | `testing` | 执行测试 + 输出测试报告 | `accepting` 或 `fixing` |

### 处理摘要 (循环结束时)

```
📊 批处理完成
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
角色: 💻 implementer
处理任务: 3 个
  ✅ T-003 implementing → reviewing
  ✅ T-005 implementing → reviewing
  ⛔ T-006 implementing → blocked (缺少 API 文档)
跳过任务: 0 个
剩余任务: 0 个
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### 批处理安全规则
- **单任务隔离**: 处理每个任务时，只关注当前任务的上下文，不混合
- **失败不阻塞**: 如果某个任务处理失败或需要 block，标记 blocked 后继续处理下一个
- **乐观锁保护**: 每次读写 task-board 都检查 version
- **自动通知**: 每处理完一个任务，自动写入下游 Agent 的 inbox

## 事件管理

### 查看活动摘要
```bash
AGENTS_DIR="$(git rev-parse --show-toplevel 2>/dev/null)/.agents"
[ -d "$AGENTS_DIR" ] || AGENTS_DIR="./.agents"
sqlite3 "$AGENTS_DIR/events.db" "SELECT agent, count(*) as actions FROM events WHERE created_at > datetime('now', '-24 hours') GROUP BY agent ORDER BY actions DESC;"
```

### 清理旧事件
```bash
# 清理 30 天前的事件
sqlite3 .agents/events.db "DELETE FROM events WHERE created_at < datetime('now', '-30 days');"

# 清理所有事件（重置）
sqlite3 .agents/events.db "DELETE FROM events; DELETE FROM sqlite_sequence WHERE name='events';"
```

> 参考 `agent-events` skill 了解更多查询方式（按 Agent、按任务、工具使用统计等）。

## 可用角色
| 命令 | 角色 | Emoji |
|------|------|-------|
| `/agent acceptor` | 验收者 | 🎯 |
| `/agent designer` | 设计者 | 🏗️ |
| `/agent implementer` | 实现者 | 💻 |
| `/agent reviewer` | 审查者 | 🔍 |
| `/agent tester` | 测试者 | 🧪 |
| `/agent status` | 状态面板 | 🤖 |

---

## 周期时间追踪 (Cycle Time Tracking)

### 概述

记录每个任务在各 FSM 阶段的进入/离开时间戳, 计算每阶段耗时, 识别瓶颈和超时任务。

### 时间戳记录

每次 FSM 状态转移时, 在任务元数据 (`tasks/T-NNN.json`) 中记录时间戳:

```json
{
  "id": "T-001",
  "title": "用户认证系统",
  "status": "reviewing",
  "cycle_time": {
    "created_at": "2026-04-05T08:00:00Z",
    "stages": {
      "designing": {
        "entered_at": "2026-04-05T08:30:00Z",
        "exited_at": "2026-04-05T10:00:00Z",
        "duration_minutes": 90
      },
      "implementing": {
        "entered_at": "2026-04-05T10:30:00Z",
        "exited_at": "2026-04-05T14:00:00Z",
        "duration_minutes": 210
      },
      "reviewing": {
        "entered_at": "2026-04-05T14:30:00Z",
        "exited_at": null,
        "duration_minutes": null
      }
    },
    "total_elapsed_minutes": null
  }
}
```

### 记录规则

1. **进入阶段**: FSM 转移到新状态时, 写入 `stages.<new_status>.entered_at = now()`
2. **离开阶段**: FSM 转移离开当前状态时, 写入 `stages.<old_status>.exited_at = now()` 并计算 `duration_minutes`
3. **重入处理**: 如果阶段被重复进入 (如多次 fixing → reviewing), 追加 round:
   ```json
   "implementing": {
     "entered_at": "2026-04-05T10:30:00Z",
     "exited_at": "2026-04-05T14:00:00Z",
     "duration_minutes": 210,
     "rounds": [
       {"entered_at": "2026-04-05T16:00:00Z", "exited_at": "2026-04-05T17:00:00Z", "duration_minutes": 60}
     ]
   }
   ```
4. **完成任务**: 当状态变为 `accepted` 时, 计算 `total_elapsed_minutes` = 从 `created_at` 到当前时间
5. **阻塞扣除**: `blocked` 期间的时间**不计入**当前阶段的 `duration_minutes`, 在 cycle_time 中单独记录:
   ```json
   "blocked_time": [
     {"from": "2026-04-05T12:00:00Z", "to": "2026-04-05T13:00:00Z", "duration_minutes": 60, "reason": "等待 API 文档"}
   ]
   ```

### 实现步骤 (集成到 FSM 转移)

在每次 `agent-fsm` 状态转移成功后, **额外执行**:

```
FSM 验证通过
  → 记录旧状态的 exited_at + duration_minutes
  → 记录新状态的 entered_at
  → 写入 tasks/T-NNN.json
  → 继续原有流程 (task-board 更新 → 记忆保存 → 通知)
```

### 每阶段耗时计算

```bash
# 计算方式: exited_at - entered_at (如阶段已结束)
#          now() - entered_at      (如阶段进行中)
# 如有 rounds, 累加所有 round 的 duration_minutes

# 示例: 读取 T-001 的 cycle_time
TASK_FILE="<project>/.agents/tasks/T-001.json"
jq '.cycle_time.stages | to_entries[] | "\(.key): \(.value.duration_minutes // "进行中") 分钟"' "$TASK_FILE"
```

---

## 停滞阈值 (Staleness Thresholds)

### 每阶段超时阈值

| 阶段 | 阈值 | 说明 |
|------|------|------|
| `designing` | **2 小时** (120 min) | 设计不应过度纠结, 超时应简化或拆分 |
| `implementing` | **4 小时** (240 min) | 最长阶段, 超时应检查范围是否过大 |
| `reviewing` | **1 小时** (60 min) | 审查应快速, 超时说明问题太多或审查者阻塞 |
| `testing` | **2 小时** (120 min) | 包含手动+自动测试, 超时应检查测试策略 |
| `accepting` | **1 小时** (60 min) | 验收应基于测试报告快速决策 |

### 停滞检测逻辑

在以下时机检测停滞:
1. **`/agent status`** 面板刷新时
2. **agent-switch** 切换角色时
3. **批处理循环** 扫描任务时

```bash
# 检测逻辑伪代码
for each task in task-board where status != "accepted" and status != "blocked":
    current_stage = task.status
    entered_at = task.cycle_time.stages[current_stage].entered_at
    elapsed = now() - entered_at
    threshold = THRESHOLDS[current_stage]

    if elapsed > threshold:
        emit_staleness_warning(task, current_stage, elapsed, threshold)
```

### 停滞警告格式

```
⏰ 停滞警告
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ T-003 在 implementing 已停留 5h 12m (阈值: 4h)
   → 建议: 检查任务范围是否过大, 考虑拆分
⚠️ T-007 在 reviewing 已停留 1h 30m (阈值: 1h)
   → 建议: 切换到 reviewer 处理, 或检查是否需要 escalation
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### 停滞自动响应

| 超时等级 | 条件 | 动作 |
|---------|------|------|
| ⚠️ 警告 | 超过阈值 1x | 在状态面板显示黄色警告 |
| 🔴 严重 | 超过阈值 2x | 自动发送 `escalation` 消息给 acceptor |
| ⛔ 阻塞 | 超过阈值 3x | 建议将任务标记为 `blocked`, 等待人工介入 |

---

## 周期时间摘要面板 (Cycle Time Summary)

### 在 `/agent status` 中显示

在现有状态面板的**任务流水线**区域下方, 追加周期时间摘要:

```
🤖 Agent 状态面板
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
... (现有角色状态表和任务流水线) ...

⏱️ 周期时间摘要
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
任务      设计     实现      审查    测试    验收    总耗时    状态
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
T-001    1.5h    3.5h     0.5h   1.0h    —      6.5h+   ⏳ testing
T-002    0.8h    2.0h     0.3h   0.5h   0.2h    3.8h    ✅ accepted
T-003    1.0h    ⚠️5.2h    —      —      —      6.2h+   ⏳ implementing
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
平均      1.1h    3.6h     0.4h   0.8h   0.2h    —
最慢      T-001   T-003    T-001  T-001   —      —
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⏰ 停滞警告:
  ⚠️ T-003 implementing 已超时 (5.2h / 阈值 4h)
```

### 摘要面板渲染逻辑

1. 读取所有非 `accepted` 任务的 `tasks/T-NNN.json`
2. 提取 `cycle_time.stages` 数据
3. 对已完成的阶段显示实际耗时 (小时, 1 位小数)
4. 对进行中的阶段显示 `now() - entered_at`
5. 超过阈值的阶段用 ⚠️ 标记
6. 计算**每列平均值**和**每列最慢任务**
7. 底部列出所有停滞警告

### 单任务周期时间查看

用户说 `/task T-001 --cycle` 或 "查看 T-001 耗时" 时, 显示该任务的详细周期时间:

```
⏱️ T-001 周期时间详情
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
阶段          进入时间      耗时     阈值    状态
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
designing     08:30        1.5h    2h     ✅ 正常
implementing  10:00        3.5h    4h     ✅ 正常
  → fixing    14:30        1.0h    —      (退回修复)
reviewing     16:00        0.5h    1h     ✅ 正常
testing       16:30        ⏳ 0.3h  2h     进行中
accepting     —            —       1h     未到达
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
总耗时: 6.8h (含 blocked 0h)
阻塞次数: 0
退回次数: 1 (reviewing → implementing)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```
