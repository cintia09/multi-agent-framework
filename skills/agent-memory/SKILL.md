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

---

## 搜索记忆

用户说 "搜索记忆 <关键词>" / "search memory <keyword>" / "有没有类似的经验" 时:

### 搜索范围
扫描 `.agents/memory/` 下所有 `T-NNN-memory.json` 文件, 在以下字段中匹配:

| 字段 | 权重 | 说明 |
|------|------|------|
| `decisions` | ⭐⭐⭐ | 最有价值 — 过去的决策和原因 |
| `issues_encountered` | ⭐⭐⭐ | 最有价值 — 踩过的坑 |
| `summary` | ⭐⭐ | 工作摘要 |
| `handoff_notes` | ⭐⭐ | 交接备注中的经验 |
| `files_modified` | ⭐ | 按文件路径搜索相关变更 |

### 搜索算法

```bash
# 在所有记忆文件中搜索关键词 (大小写不敏感)
MEMORY_DIR="<project>/.agents/memory"
grep -ril "<keyword>" "$MEMORY_DIR"/*.json 2>/dev/null
```

Agent 读取匹配文件后, 按以下规则排序结果:
1. **精确匹配 decisions/issues** 排在前面 (最有参考价值)
2. **同类阶段** 排在前面 (如当前是 implementing, 优先显示过去的 implementing 记忆)
3. **最近的任务** 排在前面 (时间相关性)

### 输出格式

```
🔍 搜索记忆: "redis"
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[1] T-001 / implementing — implementer
    🎯 匹配: issues_encountered
    "connect-redis v7 的 API 变了, 需要用 new RedisStore({client}) 而非 new RedisStore(client)"

[2] T-001 / designing — designer
    🎯 匹配: decisions
    "session 存储用 connect-redis 而非内存"

[3] T-003 / implementing — implementer
    🎯 匹配: decisions
    "Redis 缓存使用 ioredis 而非 node-redis, 更好的 cluster 支持"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
共 3 条匹配 (跨 2 个任务)
```

### 搜索场景示例

| 场景 | 搜索方式 | 用途 |
|------|---------|------|
| 实现者遇到 Redis 问题 | `搜索记忆 redis` | 看看之前有没有类似的踩坑经验 |
| 设计者考虑认证方案 | `搜索记忆 认证` 或 `搜索记忆 JWT` | 看看过去选过什么方案及原因 |
| 审查者检查某文件历史 | `搜索记忆 auth.ts` | 看看这个文件之前被修改过几次、为什么 |
| 测试者了解测试策略 | `搜索记忆 测试覆盖率` | 看看过去的覆盖率目标和实际达到的水平 |

### 上下文感知搜索

如果 Agent 正在处理某个任务, 可以**不指定关键词**, 直接说 "有没有类似的经验" / "搜索相关记忆":

1. 从当前任务的 description 和 goals 提取关键词
2. 在其他任务的记忆中搜索这些关键词
3. 返回相关度最高的结果

---

## 项目级摘要

用户说 "项目摘要" / "记忆总结" / "project summary" / "lessons learned" 时:

### 生成逻辑

1. 读取 `.agents/memory/` 下所有 `T-NNN-memory.json`
2. 读取 `.agents/task-board.json` 获取任务标题和状态
3. 汇总生成以下摘要:

### 输出格式

```
📊 项目记忆摘要
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 任务概况
  完成: 5 个 | 进行中: 2 个 | 阻塞: 1 个
  阶段记忆: 共 23 条记录

🏗️ 架构决策 (从所有 designing 阶段提取)
  • T-001: 选择 cookie session 而非 JWT (纯 Web, 不需移动端)
  • T-003: Redis 作为缓存层 (ioredis + cluster 模式)
  • T-005: 数据库迁移使用 Prisma (类型安全 + 自动生成)

⚠️ 踩坑记录 (从所有 issues_encountered 提取)
  • T-001: connect-redis v7 API 变化, 需要新语法
  • T-001: cookie sameSite=strict 导致跨页面丢 session
  • T-002: Playwright 截图在 CI 中需要 xvfb
  • T-004: Docker multi-stage build 需要 .dockerignore 排除 node_modules

🔧 技术栈选择 (从 decisions 聚合)
  认证: cookie session + bcrypt
  缓存: Redis (ioredis)
  ORM: Prisma
  测试: Playwright + Vitest
  部署: Docker + Caddy

📈 文件修改热区 (从 files_modified 聚合)
  src/routes/auth.ts       — 被 3 个任务修改
  src/middleware/session.ts — 被 2 个任务修改
  tests/auth.test.ts       — 被 2 个任务修改

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### 摘要分区说明

| 分区 | 数据来源 | 价值 |
|------|---------|------|
| 架构决策 | `stages.designing.decisions` | 理解项目为什么这样设计 |
| 踩坑记录 | 所有 `issues_encountered` | 避免重复踩坑 |
| 技术栈选择 | 从 decisions 中提取技术关键词聚合 | 快速了解项目用了什么 |
| 文件修改热区 | 所有 `files_modified` 计数 | 识别高风险文件 |

### 保存摘要

摘要可选保存为 `.agents/memory/PROJECT-SUMMARY.md`:
- 每次执行时覆盖 (始终是最新的)
- Markdown 格式, 人类可读
- 可提交到 git 作为项目文档的一部分

```bash
# 生成并保存
cat .agents/memory/PROJECT-SUMMARY.md
```
