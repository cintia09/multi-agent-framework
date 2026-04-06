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
2. 保存当前 Agent 状态 (如果有)
3. **写入 active-agent 标记** (供 Hooks 读取):
   ```bash
   echo "<agent_name>" > <project>/.agents/runtime/active-agent
   ```
4. 清洁上下文 (RESPAWN 模式 — 不携带上一个 Agent 的工作记忆)
5. 加载目标 Agent 的 skill (agent-<name>.md)
6. **自动处理 inbox**: 读取未读消息, 显示给用户, 标记为已读:
   ```bash
   INBOX="<project>/.agents/runtime/<agent>/inbox.json"
   UNREAD=$(jq '[.messages[] | select(.read == false)]' "$INBOX")
   # 显示每条未读消息, 然后标记已读:
   jq '.messages |= [.[] | .read = true]' "$INBOX" > "${INBOX}.tmp" && mv "${INBOX}.tmp" "$INBOX"
   ```
7. **显示任务概览**: 检查 task-board 中分配给当前 agent 的任务
8. **加载任务记忆**: 如果有分配的任务, 自动读取 `.agents/memory/T-NNN-memory.json`, 显示上一阶段的上下文摘要和交接备注 (调用 agent-memory skill 的"加载记忆"操作)
9. **Staleness 警告**: 如果有长时间 (>24h) 未活动的任务, 提醒用户
10. 执行目标 Agent 的启动流程 (定义在对应 skill 中)
11. 打印: "🔄 已切换到 <角色名> (<emoji>)"

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
