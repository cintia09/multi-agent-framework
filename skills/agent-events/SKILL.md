---
name: agent-events
description: "审计日志查询: 查看 Agent 活动历史、工具使用统计、事件分析。Use when querying events.db, checking activity history, or analyzing agent behavior."
---

# 审计日志查询 (events.db)

## 前置条件
- `.agents/events.db` 存在 (由 agent-init 或 session-start hook 创建)

## 常用查询

### 最近事件
```bash
sqlite3 .agents/events.db "SELECT id, event_type, agent, tool_name, created_at FROM events ORDER BY id DESC LIMIT 20;"
```

### 按 Agent 查询
```bash
sqlite3 .agents/events.db "SELECT event_type, count(*) FROM events WHERE agent='<agent_name>' GROUP BY event_type;"
```

### 按任务查询
```bash
sqlite3 .agents/events.db "SELECT event_type, agent, detail, created_at FROM events WHERE task_id='<task_id>' ORDER BY id;"
```

### 工具使用统计
```bash
sqlite3 .agents/events.db "SELECT tool_name, count(*) as uses FROM events WHERE event_type='tool_use' GROUP BY tool_name ORDER BY uses DESC;"
```

### Auto-dispatch 历史
```bash
sqlite3 .agents/events.db "SELECT agent, task_id, detail, created_at FROM events WHERE event_type='auto_dispatch' ORDER BY id DESC;"
```

### Agent 活跃度 (过去 24 小时)
```bash
sqlite3 .agents/events.db "SELECT agent, count(*) as actions FROM events WHERE created_at > datetime('now', '-24 hours') GROUP BY agent ORDER BY actions DESC;"
```

### 状态变更时间线
```bash
sqlite3 .agents/events.db "SELECT agent, detail, created_at FROM events WHERE event_type='state_change' ORDER BY id;"
```

## 事件类型说明

| event_type | 来源 | 说明 |
|-----------|------|------|
| `session_start` | session-start hook | 会话启动 |
| `tool_use` | post-tool-use hook | 工具调用 (含 result 和 args) |
| `task_board_write` | post-tool-use hook | 任务表被修改 |
| `state_change` | post-tool-use hook | Agent state.json 被修改 |
| `auto_dispatch` | post-tool-use hook | 自动派发消息到下游 Agent |

## 清理旧事件

删除 N 天前的事件:
```bash
sqlite3 .agents/events.db "DELETE FROM events WHERE created_at < datetime('now', '-30 days');"
```

删除所有事件 (重置):
```bash
sqlite3 .agents/events.db "DELETE FROM events;"
sqlite3 .agents/events.db "DELETE FROM sqlite_sequence WHERE name='events';"
```

## 导出

导出为 CSV:
```bash
sqlite3 -header -csv .agents/events.db "SELECT * FROM events;" > events-export.csv
```

导出为 JSON Lines:
```bash
sqlite3 .agents/events.db "SELECT json_object('id',id,'type',event_type,'agent',agent,'task',task_id,'tool',tool_name,'detail',detail,'time',created_at) FROM events;" > events-export.jsonl
```
