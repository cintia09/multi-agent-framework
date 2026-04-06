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

## 自动记忆沉淀 (Auto-Capture)

### 触发时机
当 FSM 状态转移发生（任务从一个阶段进入下一阶段）时，当前 Agent 自动保存记忆快照。

### 触发条件
post-tool-use hook 检测到 task-board.json 中某任务的 status 发生变化时，自动执行记忆保存。

### 自动提取内容

| 字段 | 提取方式 |
|------|---------|
| `summary` | Agent 总结本阶段工作（2-5 句话） |
| `decisions` | 从对话中提取 "选择 X 因为 Y" 格式的决策 |
| `files_modified` | 从 git diff 中提取本阶段修改的文件列表 |
| `issues_encountered` | 从对话中提取遇到的问题和解决方案 |
| `handoff_notes` | Agent 对下游角色的交接要点 |
| `artifacts` | 本阶段产出的文档路径 |

### 实现流程
```
1. post-tool-use hook 检测 task-board.json 变化
2. 对比前后 status，识别状态转移
3. 读取当前 Agent 上下文
4. 提取上述字段
5. 写入 .agents/memory/T-NNN-memory.json 对应 stage
6. 更新 version 和 last_updated
```

### 注意事项
- 自动提取是最佳努力 (best-effort)，Agent 仍可手动补充
- 敏感信息自动脱敏（API key、密码、IP 地址）
- 如果 memory 文件不存在，自动创建

## 智能记忆加载 (Smart Loading)

### 按角色差异化加载

Agent 切换时（agent-switch），自动加载分配任务的记忆，但只加载**当前角色需要的字段**:

| 下游角色 | 加载字段 | 省略字段 | 理由 |
|---------|---------|---------|------|
| Designer (← Acceptor) | goals, description | — | 设计需要完整需求 |
| Implementer (← Designer) | decisions, artifacts, handoff_notes | issues_encountered | 实现者需要设计决策和文档路径 |
| Reviewer (← Implementer) | files_modified, decisions, summary | handoff_notes | 审查者关注改了什么和为什么 |
| Tester (← Reviewer) | files_modified, review issues, summary | decisions | 测试者关注测什么和已知问题 |
| Acceptor (← Tester) | 全部 stages 的 summary | 详细字段 | 验收者需要全局视角 |

### 加载格式

记忆加载后以**可读文本**呈现，不是原始 JSON:

```
📝 任务记忆: T-008 "自动记忆沉淀"
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🏗️ 设计阶段 (Designer, 完成于 10:30):
  决策: 使用 post-tool-use hook 检测状态变化触发记忆保存
  产出: docs/design.md (已更新 T-008 章节)
  交接: 在 hook 中检测 task-board.json diff，提取 status 变化

💻 上一阶段交接要点:
  - 修改 agent-post-tool-use.sh 添加 auto-capture 逻辑
  - memory 文件格式不变，只增加自动写入
```

### 集成到 agent-switch

在 agent-switch 的角色切换流程中:
1. 检查是否有分配给新角色的任务
2. 如有，读取 `.agents/memory/T-NNN-memory.json`
3. 根据角色过滤字段
4. 格式化为可读文本
5. 展示给 Agent

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
4. **🔒 脱敏处理** (写入前必须执行):
   扫描所有文本字段, 替换敏感信息:
   
   | 敏感类型 | 匹配模式 | 替换为 |
   |---------|---------|--------|
   | API Key | `AIza...`, `sk-...`, `ghp_...`, `ghr_...`, `AKIA...` 等已知前缀 | `[REDACTED:API_KEY]` |
   | 密码/密钥 | `password=xxx`, `secret=xxx`, `token=xxx` 等 key=value 模式 | `[REDACTED:CREDENTIAL]` |
   | 内网 IP | `192.168.x.x`, `10.x.x.x`, `172.16-31.x.x` 等 RFC 1918 地址 | `[REDACTED:INTERNAL_IP]` |
   | SSH/连接串 | `ssh user@host`, `mysql://user:pass@host` 等 | `[REDACTED:CONNECTION]` |
   | 环境变量值 | 从 `.env` 文件引用的具体值 | `[REDACTED:ENV_VALUE]` |
   | 邮箱 | 个人邮箱地址 | `[REDACTED:EMAIL]` |
   
   **脱敏原则**:
   - 保留技术决策和上下文信息, 只替换具体的秘密值
   - 例: "使用 Google API key 调用 Gemini" ✅ 保留; "API key 是 AIzaSy..." ❌ 替换
   - 例: "部署到内网服务器" ✅ 保留; "服务器地址 192.168.31.107" ❌ 替换
   - 如果不确定是否敏感, 宁可替换
   
5. version + 1, 更新 last_updated
6. 写入文件

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
- **🔒 写入前必须脱敏** — API key、密码、内网 IP、连接串等敏感信息必须替换为 `[REDACTED:类型]`
- summary 和 handoff_notes 是最重要的字段 — 确保信息密度高, 不是泛泛而谈
- 如果阶段重复进入 (如多次 fixing), 每次都更新该阶段的快照 (追加 round 信息到 summary)
- 脱敏不影响上下文理解 — 保留"用了什么技术"的信息, 只删除具体秘密值

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

---

## 项目记忆 (Project Memory)

### 概述

项目记忆是**跨任务**的持久化知识库, 记录整个项目的技术栈、架构决策、经验教训和高频修改文件。区别于**任务记忆** (per-task), 项目记忆是**全局共享**的项目级知识。

### 文件位置

```
<project>/.agents/memory/project-memory.json
```

### project-memory.json Schema

```json
{
  "version": 1,
  "last_updated": "2026-04-10T15:00:00Z",

  "tech_stack": {
    "language": "TypeScript",
    "runtime": "Node.js 20",
    "framework": "Express.js",
    "database": "PostgreSQL + Prisma ORM",
    "cache": "Redis (ioredis)",
    "testing": "Vitest + Playwright",
    "deployment": "Docker + Caddy",
    "ci_cd": "GitHub Actions",
    "other": ["pnpm", "ESLint", "Prettier"]
  },

  "architecture_decisions": [
    {
      "id": "ADR-001",
      "title": "选择 cookie session 而非 JWT",
      "date": "2026-04-05",
      "status": "accepted",
      "context": "纯 Web 应用, 不需要移动端支持",
      "decision": "使用 express-session + connect-redis 的 cookie session 方案",
      "consequences": "服务端需维护 session 存储; 需配置 Redis; 不适合未来移动端",
      "source_task": "T-001",
      "superseded_by": null
    },
    {
      "id": "ADR-002",
      "title": "数据库迁移使用 Prisma",
      "date": "2026-04-06",
      "status": "accepted",
      "context": "需要类型安全的数据库访问和自动迁移",
      "decision": "使用 Prisma ORM 管理数据库 schema 和迁移",
      "consequences": "强依赖 Prisma 生态; 复杂查询可能需要 raw SQL",
      "source_task": "T-005",
      "superseded_by": null
    }
  ],

  "lessons_learned": [
    {
      "id": "LL-001",
      "date": "2026-04-05",
      "category": "dependency",
      "title": "connect-redis v7 API 变更",
      "description": "connect-redis v7 的 API 变了, 需要用 new RedisStore({client}) 而非 new RedisStore(client)",
      "impact": "high",
      "source_task": "T-001",
      "tags": ["redis", "session", "breaking-change"]
    },
    {
      "id": "LL-002",
      "date": "2026-04-06",
      "category": "testing",
      "title": "Playwright CI 需要 xvfb",
      "description": "Playwright 截图在 CI 中需要 xvfb, 否则报 headless 错误",
      "impact": "medium",
      "source_task": "T-002",
      "tags": ["playwright", "ci", "headless"]
    }
  ],

  "hot_files": [
    {
      "path": "src/routes/auth.ts",
      "modification_count": 5,
      "last_modified_by": "T-004",
      "last_modified_at": "2026-04-08T14:00:00Z",
      "risk_level": "high",
      "note": "认证核心路由, 修改需完整回归测试"
    },
    {
      "path": "src/middleware/session.ts",
      "modification_count": 3,
      "last_modified_by": "T-003",
      "last_modified_at": "2026-04-07T10:00:00Z",
      "risk_level": "medium",
      "note": "session 中间件, 与 Redis 耦合"
    }
  ]
}
```

### 字段说明

#### tech_stack

| 字段 | 类型 | 说明 |
|------|------|------|
| `language` | string | 主要编程语言 |
| `runtime` | string | 运行时及版本 |
| `framework` | string | Web 框架 |
| `database` | string | 数据库及 ORM |
| `cache` | string | 缓存层 |
| `testing` | string | 测试框架 |
| `deployment` | string | 部署方案 |
| `ci_cd` | string | CI/CD 工具 |
| `other` | string[] | 其他工具和库 |

#### architecture_decisions (ADR)

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | `ADR-NNN` 格式, 自增 |
| `title` | string | 决策标题 |
| `date` | string | 决策日期 (YYYY-MM-DD) |
| `status` | enum | `proposed` / `accepted` / `deprecated` / `superseded` |
| `context` | string | 为什么需要做这个决策 |
| `decision` | string | 做了什么决策 |
| `consequences` | string | 决策的后果和影响 |
| `source_task` | string | 产生此决策的任务 ID |
| `superseded_by` | string\|null | 如果被替代, 指向新的 ADR ID |

#### lessons_learned

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | `LL-NNN` 格式, 自增 |
| `date` | string | 记录日期 |
| `category` | enum | `dependency` / `testing` / `deployment` / `architecture` / `performance` / `security` / `other` |
| `title` | string | 简短标题 |
| `description` | string | 详细描述 (包含解决方案) |
| `impact` | enum | `high` / `medium` / `low` |
| `source_task` | string | 来源任务 ID |
| `tags` | string[] | 关键词标签, 用于搜索 |

#### hot_files

| 字段 | 类型 | 说明 |
|------|------|------|
| `path` | string | 文件路径 (项目根目录相对路径) |
| `modification_count` | number | 跨任务被修改的次数 |
| `last_modified_by` | string | 最后修改此文件的任务 ID |
| `last_modified_at` | ISO 8601 | 最后修改时间 |
| `risk_level` | enum | `high` / `medium` / `low` — 根据修改频率自动计算 |
| `note` | string | 关于此文件的备注 (如: 为什么经常被改) |

---

## 项目记忆自动更新 (Auto-Update on Task Acceptance)

### 触发时机

当任务状态变为 `accepted` 时, acceptor **必须**执行项目记忆更新。

### 更新流程

```
任务 accepted
  → 读取 project-memory.json (不存在则创建空结构)
  → 读取 tasks/T-NNN.json (goals, history)
  → 读取 .agents/memory/T-NNN-memory.json (所有阶段记忆)
  → 提取并更新以下内容:
     1. architecture_decisions — 从 designing 阶段的 decisions 提取
     2. lessons_learned — 从所有阶段的 issues_encountered 提取
     3. hot_files — 从所有阶段的 files_modified 聚合更新
     4. tech_stack — 从 decisions 中检测新技术引入
  → 写入 project-memory.json (version + 1)
```

### 提取规则

#### 1. 架构决策提取

从 `T-NNN-memory.json` 的 `stages.designing.decisions` 中提取**架构级**决策:

```
判断标准:
  - 涉及技术选型 (如 "选择 X 而非 Y")
  - 涉及架构模式 (如 "采用微服务 / 单体 / 事件驱动")
  - 涉及数据存储策略 (如 "缓存使用 Redis")
  - 不提取实现细节决策 (如 "变量命名用 camelCase")
```

对每个提取的决策:
1. 检查 `architecture_decisions` 中是否已有**相同主题**的 ADR
2. 如有且结论一致 → 跳过 (不重复记录)
3. 如有且结论不同 → 创建新 ADR, 将旧 ADR 状态改为 `superseded`, 设置 `superseded_by`
4. 如没有 → 创建新 ADR, 分配新 `id`

#### 2. 经验教训提取

从所有阶段的 `issues_encountered` 中提取:

```
判断标准:
  - 有明确的问题描述和解决方案
  - 可能在未来任务中复现的问题
  - 不提取一次性的配置问题 (如 "忘记 git add")
```

对每个提取的教训:
1. 检查是否与已有 `lessons_learned` 重复 (按 tags 和 description 相似度判断)
2. 不重复 → 添加新条目
3. 重复 → 更新 `impact` (如果新实例更严重) 或追加 `source_task`

#### 3. 热点文件更新

从所有阶段的 `files_modified` 聚合:

```bash
# 对每个修改的文件:
for file in files_modified:
    if file in hot_files:
        hot_files[file].modification_count += 1
        hot_files[file].last_modified_by = task_id
        hot_files[file].last_modified_at = now()
    else:
        hot_files.append({path: file, modification_count: 1, ...})

# 重新计算 risk_level:
if modification_count >= 5: risk_level = "high"
elif modification_count >= 3: risk_level = "medium"
else: risk_level = "low"
```

#### 4. 技术栈检测

从 decisions 中扫描技术关键词, 如果检测到新技术引入, 更新 `tech_stack`:

```
扫描模式: "使用 X", "引入 X", "选择 X", "采用 X", "迁移到 X"
如检测到 tech_stack 中未记录的技术:
  → 提示 acceptor 确认是否添加到 tech_stack
  → 确认后写入对应字段
```

---

## 项目记忆加载 (Load on Agent Init)

### 触发时机

**agent-init** 或 **agent-switch** 初始化 Agent 时, 自动加载项目记忆。

### 加载流程

```
Agent 初始化
  → 读取 .agents/memory/project-memory.json
  → 如文件存在:
     → 根据当前角色选择性加载 (见下表)
     → 格式化为可读文本
     → 作为项目上下文提供给 Agent
  → 如文件不存在:
     → 跳过 (首次运行, 无项目记忆)
```

### 按角色差异化加载

| 角色 | 加载内容 | 省略内容 | 理由 |
|------|---------|---------|------|
| 🎯 acceptor | tech_stack, architecture_decisions (全部), hot_files | lessons_learned (详情) | 验收需全局视角, 不需实现细节 |
| 🏗️ designer | tech_stack, architecture_decisions (全部), lessons_learned (architecture 类) | hot_files | 设计需理解技术栈和过往架构决策 |
| 💻 implementer | tech_stack, architecture_decisions (accepted), lessons_learned (全部), hot_files | deprecated ADRs | 实现需知道用什么技术、踩过什么坑、哪些文件敏感 |
| 🔍 reviewer | tech_stack, architecture_decisions (accepted), hot_files, lessons_learned (全部) | deprecated ADRs | 审查需知道标准和高风险文件 |
| 🧪 tester | tech_stack (testing 字段), lessons_learned (testing 类), hot_files | architecture_decisions | 测试关注测试工具和高风险文件 |

### 加载输出格式

```
🧠 项目记忆
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔧 技术栈: TypeScript / Node.js 20 / Express.js / PostgreSQL + Prisma
   测试: Vitest + Playwright | 部署: Docker + Caddy

📐 架构决策 (3 条):
  ADR-001: cookie session 而非 JWT (T-001)
  ADR-002: Prisma ORM 管理数据库 (T-005)
  ADR-003: Redis 缓存 + ioredis (T-003)

⚠️ 经验教训 (与当前角色相关, 2 条):
  LL-001: connect-redis v7 API 变更 [redis, breaking-change]
  LL-003: Prisma 迁移需要 DATABASE_URL 环境变量 [prisma, env]

🔥 热点文件 (修改 ≥ 3 次):
  src/routes/auth.ts (5 次修改, 高风险)
  src/middleware/session.ts (3 次修改, 中风险)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### 集成到 agent-switch / agent-init

在现有流程中插入项目记忆加载步骤:

```
切换角色
  → 检查 inbox
  → 扫描任务
  → 📝 加载任务记忆 (已有)
  → 🧠 加载项目记忆 (新增)
  → 开始工作
```

---

## 项目记忆搜索 (Memory Search)

### 触发方式

用户说 `/memory search <keyword>` 或 "搜索项目记忆 <关键词>" 时执行。

### 搜索范围

在 `project-memory.json` 的以下字段中搜索:

| 字段 | 搜索内容 | 权重 |
|------|---------|------|
| `architecture_decisions` | title, context, decision, consequences | ⭐⭐⭐ |
| `lessons_learned` | title, description, tags | ⭐⭐⭐ |
| `tech_stack` | 所有值 | ⭐⭐ |
| `hot_files` | path, note | ⭐ |

### 搜索算法

```bash
# 1. 在 project-memory.json 中搜索
PROJECT_MEMORY="<project>/.agents/memory/project-memory.json"

# 2. 搜索 architecture_decisions
jq --arg kw "$KEYWORD" '.architecture_decisions[] | select(
  (.title | ascii_downcase | contains($kw | ascii_downcase)) or
  (.decision | ascii_downcase | contains($kw | ascii_downcase)) or
  (.context | ascii_downcase | contains($kw | ascii_downcase))
)' "$PROJECT_MEMORY"

# 3. 搜索 lessons_learned
jq --arg kw "$KEYWORD" '.lessons_learned[] | select(
  (.title | ascii_downcase | contains($kw | ascii_downcase)) or
  (.description | ascii_downcase | contains($kw | ascii_downcase)) or
  (.tags[] | ascii_downcase | contains($kw | ascii_downcase))
)' "$PROJECT_MEMORY"
```

### 输出格式

```
🔍 项目记忆搜索: "redis"
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📐 架构决策:
  [ADR-003] Redis 缓存 + ioredis (T-003)
    决策: 使用 ioredis 而非 node-redis, 更好的 cluster 支持
    影响: 需要配置 Redis 集群连接

⚠️ 经验教训:
  [LL-001] connect-redis v7 API 变更 (T-001) [HIGH]
    需要用 new RedisStore({client}) 而非 new RedisStore(client)

🔥 相关文件:
  src/lib/redis.ts (2 次修改, 中风险)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
共 3 条匹配
```

### 与任务记忆搜索的区别

| | 任务记忆搜索 (`搜索记忆`) | 项目记忆搜索 (`/memory search`) |
|---|---|---|
| 搜索范围 | `.agents/memory/T-NNN-memory.json` (所有任务) | `.agents/memory/project-memory.json` (项目级) |
| 内容类型 | 原始阶段快照 (summary, decisions, issues...) | 提炼后的知识 (ADR, lessons, hot_files) |
| 适用场景 | 查找具体任务的细节和上下文 | 查找项目级的决策和经验 |
| 数据更新 | 每次阶段转移自动写入 | 每次任务 accepted 时提炼写入 |

### 联合搜索

用户说 "搜索所有记忆 <关键词>" 时, 同时搜索**项目记忆**和**任务记忆**, 合并结果:

1. 先搜索 `project-memory.json` (高层知识)
2. 再搜索所有 `T-NNN-memory.json` (详细上下文)
3. 合并去重, 按权重排序
4. 输出时分为 "📐 项目级" 和 "📋 任务级" 两个区域
