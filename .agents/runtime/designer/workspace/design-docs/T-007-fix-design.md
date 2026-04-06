# T-007 Fix Design: agent-switch 事件摘要集成 + 清理命令

## 问题
- G2: agent-switch 状态面板缺少事件摘要（每个 Agent 的最近活动统计）
- G3: 事件清理命令未在 agent-switch 中暴露

## 修改方案

### 文件 1: `skills/agent-switch/SKILL.md`

#### G2 修复：在状态面板中添加事件摘要

在 "查看所有 Agent 状态 (/agent status)" 部分的输出模板末尾，添加事件摘要区块：

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
  ⛔ T-004: blocked — "依赖的 API 尚未就绪"
```

实现步骤中添加 events.db 查询：
```bash
# 查询每个 Agent 的近 24h 活动数
if [ -f "$AGENTS_DIR/events.db" ]; then
  sqlite3 "$AGENTS_DIR/events.db" \
    "SELECT agent, count(*) FROM events WHERE created_at > datetime('now', '-24 hours') GROUP BY agent ORDER BY count(*) DESC;"
fi
```

#### G3 修复：添加事件管理命令

在 SKILL.md 末尾、"可用角色" 表格之前，添加新章节：

```markdown
## 事件管理

### 查看活动摘要
```bash
sqlite3 .agents/events.db "SELECT agent, count(*) as actions FROM events WHERE created_at > datetime('now', '-24 hours') GROUP BY agent ORDER BY actions DESC;"
```

### 清理旧事件
```bash
# 清理 30 天前的事件
sqlite3 .agents/events.db "DELETE FROM events WHERE created_at < datetime('now', '-30 days');"
# 清理所有事件（重置）
sqlite3 .agents/events.db "DELETE FROM events; DELETE FROM sqlite_sequence WHERE name='events';"
```

参考 `agent-events` skill 了解更多查询方式。
```

## Implementer 注意事项
- 只改 `skills/agent-switch/SKILL.md`
- 事件摘要是在 `/agent status` 输出中追加，不影响现有内容
- 清理命令是新增章节，放在"可用角色"表格之前
- events.db 查询需要检查文件是否存在（可能未初始化）
