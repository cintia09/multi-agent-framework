---
name: agent-memory
description: "任务记忆管理: 每个阶段完成后自动保存上下文快照。调用时说 '保存记忆'、'查看记忆'、'任务上下文'。"
---

# 任务记忆管理

## 文件位置
- 记忆文件: `<project>/.agents/memory/T-NNN-memory.json`
- 每个任务一个文件, 跨阶段积累上下文

## T-NNN-memory.json 格式

```json
{
  "task_id": "T-001",
  "version": 1,
  "last_updated": "2026-04-05T12:00:00Z",
  "stages": {
    "designing": {
      "agent": "designer",
      "started_at": "2026-04-05T08:30:00Z",
      "completed_at": "2026-04-05T10:00:00Z",
      "summary": "设计了基于 JWT 的用户认证系统, 采用无状态架构...",
      "decisions": [
        "选择 JWT 而非 session, 原因: 需支持移动端",
        "密码哈希使用 bcrypt, cost factor = 12"
      ],
      "artifacts": [
        ".agents/runtime/designer/workspace/design-docs/T-001-design.md",
        ".agents/runtime/designer/workspace/test-specs/T-001-tests.md"
      ],
      "files_modified": [],
      "issues_encountered": [],
      "handoff_notes": "实现者应先完成 JWT 中间件, 再做登录/注册接口。注意: refresh token 需存 httpOnly cookie。"
    }
  }
}
```

## 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `task_id` | string | 关联的任务 ID |
| `version` | number | 乐观锁版本号 |
| `last_updated` | ISO 8601 | 最后更新时间 |
| `stages` | object | 以阶段名为 key 的记忆快照集合 |

### 阶段快照字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `agent` | string | 执行此阶段的 Agent 角色 |
| `started_at` | ISO 8601 | 开始处理的时间 |
| `completed_at` | ISO 8601 | 完成/转移的时间 |
| `summary` | string | 本阶段工作摘要 (2-5 句话) |
| `decisions` | string[] | 关键决策及其原因 |
| `artifacts` | string[] | 产出的工件路径 (设计文档、测试报告等) |
| `files_modified` | string[] | 修改/新增的源代码文件 |
| `issues_encountered` | string[] | 遇到的问题或障碍 |
| `handoff_notes` | string | 给下一个 Agent 的交接备注 |

## 操作

### 保存记忆 (⚡ 阶段转移时自动触发)

当任务状态转移成功后, 当前 Agent **必须**保存本阶段的记忆:

1. 读取 `.agents/memory/T-NNN-memory.json` (不存在则创建)
2. 在 `stages` 中添加或更新当前阶段的快照
3. 填写所有字段:
   - `summary`: 回顾本阶段做了什么 (2-5 句话)
   - `decisions`: 列出所有关键决策及原因
   - `artifacts`: 本阶段产出的文件路径
   - `files_modified`: 修改的源代码文件 (用 `git diff --name-only` 获取)
   - `issues_encountered`: 遇到的任何问题
   - `handoff_notes`: 给下一个 Agent 的提示和注意事项
4. version + 1, 更新 last_updated
5. 写入文件

**触发时机** (对应状态转移):

| 转移 | 保存阶段 | 保存者 |
|------|---------|--------|
| `created → designing` | — | — (刚接单, 无需保存) |
| `designing → implementing` | `designing` | designer |
| `implementing → reviewing` | `implementing` | implementer |
| `reviewing → testing` | `reviewing` | reviewer |
| `reviewing → implementing` (退回) | `reviewing` | reviewer |
| `testing → accepting` | `testing` | tester |
| `testing → fixing` | `testing` | tester |
| `fixing → testing` | `fixing` | implementer |
| `accepting → accepted` | `accepting` | acceptor |
| `accepting → accept_fail` | `accepting` | acceptor |
| `accept_fail → designing` | — | — (自动转移) |
| 任何 → `blocked` | 当前阶段 | 当前 Agent |

### 加载记忆 (🔄 接手任务时自动执行)

当 Agent 接手一个任务时, 自动加载该任务的记忆:

1. 读取 `.agents/memory/T-NNN-memory.json`
2. 如果存在, 显示上下文摘要:

```
📝 任务记忆 — T-001: 用户认证系统
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📌 上一阶段: designing (by designer)
   完成时间: 2026-04-05 10:00
   摘要: 设计了基于 JWT 的用户认证系统, 采用无状态架构...
   关键决策:
     • 选择 JWT 而非 session, 原因: 需支持移动端
     • 密码哈希使用 bcrypt, cost factor = 12
   产出物:
     • .agents/runtime/designer/workspace/design-docs/T-001-design.md
     • .agents/runtime/designer/workspace/test-specs/T-001-tests.md
   📮 交接备注: 实现者应先完成 JWT 中间件, 再做登录/注册接口。
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

3. 如果不存在, 正常继续 (首次处理)

### 查看完整记忆

用户说 "查看记忆" / "任务上下文" / "memory" 时:

1. 读取当前任务的 memory.json
2. 按时间顺序展示所有阶段的记忆:

```
📝 任务完整记忆 — T-001: 用户认证系统
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[1] designing — designer — 2026-04-05 08:30 → 10:00
    摘要: 设计了基于 JWT 的用户认证系统...
    决策: JWT (无状态) / bcrypt (安全) / httpOnly cookie (refresh token)
    产出: design-docs/T-001-design.md, test-specs/T-001-tests.md

[2] implementing — implementer — 2026-04-05 10:30 → 14:00
    摘要: 实现了 JWT 中间件和登录/注册接口...
    决策: 使用 jsonwebtoken 库 / token 有效期 15 分钟
    修改: src/auth/jwt.ts, src/routes/auth.ts, src/middleware/auth.ts
    问题: 初始方案中 token 刷新有竞态条件, 改用滑动窗口

[3] reviewing — reviewer — 2026-04-05 14:30 → 15:00
    摘要: 审查通过, 无严重问题...
    产出: review-reports/review-T-001-20260405.md

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
共 3 个阶段记录 | 最后更新: 2026-04-05 15:00
```

### 更新记忆 (同一阶段内追加)

如果 Agent 在同一阶段内有重要进展需要记录 (如 fixing 阶段修了多个 issue):

1. 读取 memory.json
2. 更新当前阶段的快照 (追加到 decisions/files_modified/issues_encountered)
3. version + 1, 更新 last_updated 和 stages[当前阶段].completed_at
4. 写入

## 与其他 Skill 的集成

### agent-task-board
状态转移操作的**最后一步**必须调用记忆保存:
```
更新任务状态 → FSM 验证 → 写入 task-board → 同步 Markdown → 💾 保存记忆 → 通知下游 Agent
```

### agent-switch
切换到 Agent 后加载任务时, 自动读取并展示记忆:
```
切换角色 → 检查 inbox → 扫描任务 → 📝 加载任务记忆 → 开始工作
```

### agent-events
记忆保存/加载事件记录到 events.db:
- `event_type: "memory_save"`, detail: `{"task_id": "T-001", "stage": "designing"}`
- `event_type: "memory_load"`, detail: `{"task_id": "T-001", "stages_loaded": 3}`

## 注意事项
- 所有写入使用乐观锁 (version 字段)
- 记忆文件**应提交到 git** — 它是有价值的项目知识, 不是临时运行时状态
- summary 和 handoff_notes 是最重要的字段 — 确保信息密度高, 不是泛泛而谈
- 如果阶段重复进入 (如多次 fixing), 每次都更新该阶段的快照 (追加 round 信息到 summary)
