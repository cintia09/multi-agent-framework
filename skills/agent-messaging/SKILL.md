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

---

## 结构化消息模式 (Structured Message Schema)

所有 Agent 间消息**必须**遵循以下结构化模式。这确保消息语义明确、可机器解析、可追溯。

### 完整消息结构

```json
{
  "id": "msg-1717600000000",
  "from": "implementer",
  "to": "reviewer",
  "task_id": "T-001",
  "timestamp": "2026-04-05T10:00:00Z",
  "read": false,

  "type": "request | response | notification | escalation | broadcast",
  "severity": "critical | high | medium | low",
  "priority": "urgent | normal | info",

  "thread_id": "msg-1717599000000",
  "reply_to": "msg-1717599500000",

  "context": {
    "file": "src/auth/jwt.ts",
    "line": 42,
    "function": "validateToken"
  },

  "content": "Token 验证逻辑有竞态条件，请审查 validateToken 函数",
  "references": ["msg-1717599000000"]
}
```

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | ✅ | `msg-{timestamp-ms}` 格式 |
| `from` | string | ✅ | 发送者角色 |
| `to` | string | ✅ | 接收者角色 |
| `task_id` | string | ✅ | 关联任务 ID |
| `timestamp` | ISO 8601 | ✅ | 发送时间 |
| `read` | boolean | ✅ | 是否已读 |
| `type` | enum | ✅ | 消息类型 (见下表) |
| `severity` | enum | ✅ | 严重程度 |
| `priority` | enum | ✅ | 优先级 |
| `context` | object | ❌ | 代码定位上下文 (有代码相关时填写) |
| `context.file` | string | ❌ | 相关文件路径 |
| `context.line` | number | ❌ | 相关行号 |
| `context.function` | string | ❌ | 相关函数/方法名 |
| `content` | string | ✅ | 消息正文 |
| `thread_id` | string | ❌ | 会话线程 ID (首条消息的 id) |
| `reply_to` | string | ❌ | 回复的消息 ID |
| `references` | string[] | ❌ | 引用的相关消息 ID 列表 |

### 消息类型 (type)

| type | 说明 | 典型场景 |
|------|------|---------|
| `request` | 请求对方执行操作 | implementer → reviewer: "请审查 T-001" |
| `response` | 对 request 的回复 | reviewer → implementer: "审查完成, 3 个问题" |
| `notification` | 单向通知, 不需回复 | acceptor → all: "新任务 T-005 已创建" |
| `escalation` | 升级/上报问题 | tester → acceptor: "T-001 测试持续失败, 需介入" |
| `broadcast` | 广播给所有 Agent | acceptor → all: "T-001 优先级提升为 critical" |

### 严重程度 (severity)

| severity | 说明 | 示例 |
|----------|------|------|
| `critical` | 阻塞流水线, 需立即处理 | 构建失败、安全漏洞、数据丢失风险 |
| `high` | 严重问题, 当前阶段必须解决 | 逻辑错误、未处理边界条件 |
| `medium` | 需关注但不阻塞 | 代码风格问题、缺少单元测试 |
| `low` | 建议性信息 | 优化建议、文档改进 |

### 优先级 (priority)

| priority | 说明 | 处理规则 |
|----------|------|---------|
| `urgent` | 阻塞流水线 | **立即处理** — Agent 切换后第一件事处理 urgent 消息; 在状态面板标红显示 🔴 |
| `normal` | 标准流程 | 按顺序处理 — 在当前任务处理完毕后按时间排序处理 |
| `info` | 仅供参考 (FYI) | 不需回复 — 标记已读即可; 不出现在待处理队列中 |

### 优先级处理规则

Agent 查看收件箱时, 按以下顺序排序:
1. **urgent** 消息置顶 (🔴 标记)
2. **normal** 消息按时间排序
3. **info** 消息折叠显示 (仅显示数量, 展开查看)

```
📬 收件箱 (5 条未读)
🔴 [msg-001] URGENT 来自 tester (10:00): T-001 测试全部失败, 构建阻塞
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[msg-002] 来自 reviewer (11:00): T-003 审查完成, 2 个 medium 问题
[msg-003] 来自 acceptor (11:30): 请处理 T-005 实现
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ℹ️ 2 条 info 消息 (展开查看: /inbox --info)
```

---

## 消息路由规则 (Routing Rules)

### 谁发什么类型给谁

消息路由遵循 SDLC 流水线顺序。每个 Agent 只向**直接上下游**和 **acceptor (升级通道)** 发送消息。

```
   acceptor ←──── 所有 Agent 可 escalation
      │
      ▼ notification (task_created)
   designer
      │
      ▼ request (请求实现)
   implementer
      │
      ▼ request (请求审查)
   reviewer ────► implementer (response: 退回修复)
      │
      ▼ request (请求测试)
   tester ──────► implementer (response: 退回修复)
      │
      ▼ request (请求验收)
   acceptor
```

### 路由矩阵

| 发送者 → 接收者 | type | severity | priority | 触发场景 |
|----------------|------|----------|----------|---------|
| acceptor → designer | notification | medium | normal | 新任务创建, 分配设计 |
| acceptor → 任何 | notification | high | urgent | 验收失败, 任务退回 |
| designer → implementer | request | medium | normal | 设计完成, 请求实现 |
| implementer → reviewer | request | medium | normal | 实现完成, 请求审查 |
| reviewer → implementer | response | high/medium | normal | 审查反馈 (通过/退回) |
| reviewer → tester | request | medium | normal | 审查通过, 请求测试 |
| tester → implementer | response | high | normal | 测试失败, 退回修复 |
| tester → acceptor | request | medium | normal | 测试通过, 请求验收 |
| 任何 → acceptor | escalation | critical/high | urgent | 遇到无法解决的阻塞问题 |
| 任何 → 任何 | notification | low | info | 一般信息共享 (FYI) |

### 路由规则

1. **直接通知**: 状态转移时, 自动向下游 Agent 发送 `request` 类型消息
2. **退回通知**: reviewer/tester 退回时, 向 implementer 发送 `response` 类型消息, severity 至少 `high`
3. **升级通道**: 任何 Agent 遇到阻塞问题, 向 acceptor 发送 `escalation`, priority = `urgent`
4. **广播消息**: `type: broadcast` 时, 将消息写入**所有 5 个** Agent 的 inbox.json (`to` 设为 `"all"`)
5. **会话线程**: 回复消息时设置 `reply_to` 指向原消息 ID, `thread_id` 指向线程首条消息 ID
6. **关联引用**: 如果消息是对某条消息的回复, 填写 `references` 字段指向原消息 ID

---

## 消息回放 (Message Replay)

### 功能说明

查看某个任务的完整协作时间线 — 所有 Agent 围绕该任务发送的消息按时间排序。

### 触发方式

用户说 `/inbox --history T-NNN` 或 "查看 T-NNN 消息历史" 时执行。

### 实现步骤

1. 扫描**所有 Agent** 的 inbox.json:
   ```bash
   AGENTS_DIR="$(git rev-parse --show-toplevel 2>/dev/null)/.agents"
   for agent in acceptor designer implementer reviewer tester; do
     cat "$AGENTS_DIR/runtime/$agent/inbox.json"
   done
   ```
2. 过滤 `task_id == T-NNN` 的消息
3. 按 `timestamp` 升序排列
4. 格式化输出完整时间线

### 输出格式

```
📜 消息历史 — T-001: 用户认证系统
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

08:00  🎯 acceptor → 🏗️ designer  [notification/medium/normal]
       "新任务 T-001: 用户认证系统, 请开始设计"

10:00  🏗️ designer → 💻 implementer  [request/medium/normal]
       "T-001 设计完成, 请按 design-docs/T-001-design.md 实现"

14:00  💻 implementer → 🔍 reviewer  [request/medium/normal]
       "T-001 实现完成, 请审查 src/auth/*.ts"
       📎 context: src/auth/jwt.ts

14:30  🔍 reviewer → 💻 implementer  [response/high/normal]
       "T-001 审查发现 2 个问题: token 刷新竞态 + 缺少错误处理"
       📎 context: src/auth/jwt.ts:42 validateToken()

15:00  💻 implementer → 🔍 reviewer  [request/medium/normal]
       "T-001 修复完成, 请重新审查"

15:30  🔍 reviewer → 🧪 tester  [request/medium/normal]
       "T-001 审查通过, 请执行测试"

16:00  🧪 tester → 🎯 acceptor  [request/medium/normal]
       "T-001 全部测试通过 (12/12), 请验收"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
共 7 条消息 | 时间跨度: 08:00 → 16:00 (8h)
```

### 回放过滤选项

| 命令 | 说明 |
|------|------|
| `/inbox --history T-001` | 查看 T-001 完整消息历史 |
| `/inbox --history T-001 --type escalation` | 只看升级消息 |
| `/inbox --history T-001 --from reviewer` | 只看 reviewer 发出的消息 |
| `/inbox --history T-001 --severity critical,high` | 只看高严重度消息 |
| `/inbox --history T-001 --priority urgent` | 只看紧急消息 |

### 注意事项
- 回放只读取已有消息, 不修改 read 状态
- 如果某个 Agent 的 inbox.json 不存在, 跳过 (不报错)
- 消息 context 信息在时间线中以 📎 标记显示
