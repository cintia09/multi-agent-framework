---
name: agent-switch
description: "Agent 角色切换与状态面板。触发词: '切换到验收者/设计者/实现者/审查者/测试者', 'switch to acceptor/designer/implementer/reviewer/tester', '/agent <name>', '当验收者/做验收者/我是验收者', 'act as acceptor', '查看 Agent 状态'。Must trigger on ANY role-switch phrase."
---

# Agent 角色管理

## ⚡ 强制触发规则 (MANDATORY)

以下任何表达方式**必须**立即触发角色切换，不得忽略或仅作为建议处理：

| 触发模式 | 示例 |
|----------|------|
| `/agent <name>` | `/agent acceptor`, `/agent 验收者` |
| `切换到<角色>` | "切换到验收者", "切换到实现者" |
| `switch to <role>` | "switch to acceptor", "switch to tester" |
| `当<角色>` / `做<角色>` | "当验收者", "做实现者" |
| `act as <role>` | "act as reviewer" |
| `我是<角色>` | "我是测试者" |
| `以<角色>身份` | "以设计者身份工作" |

**角色名映射：**

| 中文 | English | ID |
|------|---------|-----|
| 验收者 | acceptor | acceptor |
| 设计者 | designer | designer |
| 实现者 | implementer | implementer |
| 审查者/代码审查 | reviewer | reviewer |
| 测试者/QA | tester | tester |

**检测到触发词后的强制动作：**
1. 立即读取 `agents/<role>.agent.md` — 加载角色定义
2. 写入 `.agents/runtime/active-agent` — 记录当前角色
3. 读取该角色的 inbox — 显示未读消息
4. 加载任务看板 — 显示该角色负责的任务
5. 宣布切换完成: "🔄 已切换到 <角色名>"

> ⚠️ 不要将角色切换请求理解为"模拟"或"扮演"，而是框架的正式角色切换操作。

## 查看所有 Agent 状态 (/agent status)
读取每个 Agent 的 state.json, 汇总显示:

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

📋 任务流水线 (每个进行中的任务):
  T-008: ┌Acceptor✅┐→┌Designer✅┐→┌Implemen⏳┐→┌Reviewer⏸️┐→┌Tester⏸️┐

📊 近 24h 活动 (events.db) | 🚨 阻塞任务 (如有)
```

实现:
```bash
AGENTS_DIR="$(git rev-parse --show-toplevel 2>/dev/null)/.agents"
[ -d "$AGENTS_DIR" ] || AGENTS_DIR="./.agents"
for agent in acceptor designer implementer reviewer tester; do
  cat "$AGENTS_DIR/runtime/$agent/state.json"
done
cat "$AGENTS_DIR/task-board.json"
[ -f "$AGENTS_DIR/events.db" ] && sqlite3 "$AGENTS_DIR/events.db" \
  "SELECT agent, count(*) FROM events WHERE created_at > datetime('now', '-24 hours') GROUP BY agent ORDER BY 2 DESC;"
```

流水线状态图标: ✅已完成 | ⏳进行中 | ⏸️未到达 | ⛔阻塞

## 切换角色 (/agent <name>)

1. 确认目标角色: acceptor | designer | implementer | reviewer | tester
2. **前置条件预检**: 检查 task-board 是否有匹配状态的任务:
   | 角色 | 需要状态 | 例外 |
   |------|---------|------|
   | acceptor | `accepting` / 新需求 | 始终可切换 |
   | designer | `created` / `accept_fail` | — |
   | implementer | `implementing` / `fixing` | — |
   | reviewer | `reviewing` | — |
   | tester | `testing` | — |
   - 无匹配 → 警告 + 询问是否仍要切换
3. **保存并检查当前 Agent 状态**
   - 保存 state.json
   - **⛔ 切出守卫** (switch-away guard): 检查当前角色是否有未完成的关键输出:
     | 当前角色 | 检查项 | 警告条件 |
     |---------|--------|---------|
     | acceptor | task-board.json | 用户已提出需求但未发布任务到 task-board |
     | designer | design docs | 设计文档已起草但任务未转 implementing |
     | implementer | code + DFMEA | 代码已修改但未提交/未写 DFMEA |
     | reviewer | review report | 审查已进行但未出报告 |
     | tester | test report | 测试已执行但未出报告 |
   - 若检测到未完成输出 → 警告: "⚠️ 当前角色有未完成的工作: [描述]。确定要切换吗？"
   - 用户确认后才继续切换
4. 写入 active-agent: `echo "<name>" > .agents/runtime/active-agent`
5. 清洁上下文 (RESPAWN — 不携带上一 Agent 记忆)
6. **模型解析** (优先级从高到低):
   - 任务级: task-board.json 中当前任务的 `model_override` 字段
   - Agent 级: `~/.claude/agents/<name>.agent.md` frontmatter 的 `model` 字段
   - 项目级: `.agents/skills/project-agents-context/SKILL.md` 中的推荐模型
   - 系统默认: 不指定, 使用平台默认模型
   - 如果解析到非空 model → 提示: "📌 当前 Agent 使用模型: <model>"
7. 加载目标 Agent skill
7. **处理 inbox**: 读取未读消息, 显示, 标记已读
8. **任务概览**: 显示分配的任务
9. **加载任务记忆**: 自动读取 `.agents/memory/T-NNN-memory.json`, 按角色过滤
10. **Staleness 警告**: >24h 未活动任务提醒
11. 执行启动流程, 打印 "🔄 已切换到 <角色>"

### 退出角色
```bash
rm -f .agents/runtime/active-agent
```

## 批处理模式 (自动处理所有待办)

用户说 "处理任务" / "process tasks" / "开始工作" 时进入循环:

1. 检查 inbox — 读取未读消息, 标记已读
2. 扫描 task-board — 筛选当前角色负责状态的任务, 按 priority 排序
3. 处理最高优先级任务
4. 更新状态 (FSM 转移) → 保存记忆 → 写入下游 inbox → auto-dispatch
5. 报告进度 → 回到步骤 2

| 角色 | 负责状态 | 完成后转移到 |
|------|---------|-------------|
| 🎯 acceptor | `accepting` | `accepted` / `accept_fail` |
| 🏗️ designer | `created`, `accept_fail` | `implementing` |
| 💻 implementer | `implementing`, `fixing` | `reviewing` |
| 🔍 reviewer | `reviewing` | `testing` / 退回 `implementing` |
| 🧪 tester | `testing` | `accepting` / `fixing` |

**安全规则**: 单任务隔离 | 失败不阻塞 (标记 blocked 继续) | 乐观锁保护 | 自动通知

## 事件管理
```bash
# 查看近24h活动
sqlite3 .agents/events.db "SELECT agent, count(*) FROM events WHERE created_at > datetime('now', '-24 hours') GROUP BY agent ORDER BY 2 DESC;"
# 清理30天前事件
sqlite3 .agents/events.db "DELETE FROM events WHERE created_at < datetime('now', '-30 days');"
# 重置所有
sqlite3 .agents/events.db "DELETE FROM events; DELETE FROM sqlite_sequence WHERE name='events';"
```

## 可用角色
| 命令 | 角色 | Emoji |
|------|------|-------|
| `/agent acceptor` | 验收者 | 🎯 |
| `/agent designer` | 设计者 | 🏗️ |
| `/agent implementer` | 实现者 | 💻 |
| `/agent reviewer` | 审查者 | 🔍 |
| `/agent tester` | 测试者 | 🧪 |
| `/agent status` | 状态面板 | 🤖 |

## 周期时间追踪 (Cycle Time)

每次 FSM 转移时在 `tasks/T-NNN.json` 记录:
```json
{"cycle_time":{"created_at":"...","stages":{"designing":{"entered_at":"...","exited_at":"...","duration_minutes":90},"implementing":{"entered_at":"...","exited_at":null,"duration_minutes":null}},"blocked_time":[{"from":"...","to":"...","duration_minutes":60,"reason":"..."}],"total_elapsed_minutes":null}}
```

**记录规则**: 进入→写`entered_at` | 离开→写`exited_at`+计算duration | 重入→追加`rounds`数组 | accepted→计算total | blocked时间不计入阶段duration

| 阶段 | 停滞阈值 | 2x→🔴严重 | 3x→⛔建议 block |
|------|---------|----------|----------------|
| designing | 2h | 4h | 6h |
| implementing | 4h | 8h | 12h |
| reviewing | 1h | 2h | 3h |
| testing | 2h | 4h | 6h |
| accepting | 1h | 2h | 3h |

在 `/agent status` 底部显示周期时间摘要表 + 停滞警告。

## 自动化集成

### Cron Scheduling
```
*/5 * * * * cd /path/to/project && bash scripts/cron-scheduler.sh --run
```
Jobs: staleness-check (30min) | daily-summary (9AM) | memory-index (2h)

### Webhook Integration
```bash
bash scripts/webhook-handler.sh github-push '{"branch":"main"}'
bash scripts/webhook-handler.sh ci-success '{"build":123}'
bash scripts/webhook-handler.sh wake '{"reason":"manual"}'
```

### FSM Auto-Advance
Task status change → `after-task-status-change` hook → auto-switch to next agent.
Set `"auto_advance": false` on task to disable.

## Role Bootstrap Protocol

切换角色时自动注入 (按顺序):
1. 全局 Skill: `~/.claude/skills/agent-{role}/SKILL.md`
2. 项目 Skill: `.agents/skills/project-{role}/SKILL.md`
3. 当前任务: goals, status, design doc
4. 记忆 Top-6: `bash scripts/memory-search.sh "<task>" --role {role} --limit 6`
5. 上游 Handoff: inbox 消息
6. 项目上下文: `project-agents-context/SKILL.md`

**Phase-specific 额外上下文**: designing→架构约束+ADR | implementing→编码规范+TDD | reviewing→审查清单+质量阈值 | testing→测试命令+覆盖率 | accepting→验收标准+质量红线

**Handoff 消息格式**:
```json
{"from":"designer","to":"implementer","task_id":"T-024","type":"handoff","summary":"...","artifacts":["...design-docs/T-024.md","...test-specs/T-024-test-spec.md"]}
```
