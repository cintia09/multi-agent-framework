---
name: agent-messaging
description: "Agent 间消息: 发送消息给其他 Agent 或查看收件箱。调用时说 '发消息给测试者' 或 '查看收件箱'。"
---

# Agent 间消息

## 收件箱格式
文件: `<project>/.agents/runtime/<agent>/inbox.json`

```json
{
  "messages": [
    {
      "id": "msg-001",
      "from": "implementer",
      "to": "tester",
      "type": "task_update",
      "task_id": "T-001",
      "content": "T-001 修复完成, 请重新验证",
      "timestamp": "2026-04-05T10:00:00Z",
      "read": false
    }
  ]
}
```

## 消息类型
| type | 说明 | 触发场景 |
|------|------|---------|
| `task_created` | 新任务发布 | acceptor 创建任务 |
| `task_update` | 任务状态变更 | 任何状态转移 |
| `review_result` | 审查结果 | reviewer 完成审查 |
| `test_result` | 测试结果 | tester 完成测试 |
| `accept_result` | 验收结果 | acceptor 完成验收 |
| `info` | 一般通知 | 任何需要通知的场景 |
| `blocked` | 阻塞通知 | Agent 遇到无法解决的问题 |

## 操作

### 发送消息
1. 读取目标 Agent 的 inbox.json
2. 生成消息 ID: `msg-{timestamp-ms}`
3. 追加新消息到 messages 数组
4. 写入 inbox.json

### 查看收件箱
1. 读取当前 Agent 的 inbox.json
2. 列出未读消息 (read: false)
3. 格式化输出:
```
📬 收件箱 (3 条未读)
[msg-001] 来自 implementer (10:00): T-001 修复完成, 请重新验证
[msg-002] 来自 acceptor (11:00): 新任务 T-003: 主题系统
[msg-003] 来自 reviewer (11:30): T-002 审查通过
```

### 标记已读
将指定消息的 read 改为 true。

### 清理旧消息
消息默认保留 30 天。Agent 启动时可清理超过 30 天的已读消息。
