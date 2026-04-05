<p align="center">
  <img src="blog/images/architecture.png" alt="Multi-Agent Framework" width="680" />
</p>

<h1 align="center">🤖 Multi-Agent Software Development Framework</h1>

<p align="center">
  <a href="https://github.com/cintia09/multi-agent-framework/releases"><img src="https://img.shields.io/github/v/release/cintia09/multi-agent-framework?style=for-the-badge&color=6366f1" alt="Release"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge" alt="MIT License"></a>
  <a href="https://github.com/cintia09/multi-agent-framework/stargazers"><img src="https://img.shields.io/github/stars/cintia09/multi-agent-framework?style=for-the-badge&color=f59e0b" alt="Stars"></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Agents-5-6366f1?style=flat-square" alt="5 Agents">
  <img src="https://img.shields.io/badge/Skills-12-10b981?style=flat-square" alt="12 Skills">
  <img src="https://img.shields.io/badge/Hooks-4-f59e0b?style=flat-square" alt="4 Hooks">
  <img src="https://img.shields.io/badge/FSM_States-10-ef4444?style=flat-square" alt="10 FSM States">
  <img src="https://img.shields.io/badge/Zero_Dependencies-✓-8b5cf6?style=flat-square" alt="Zero Dependencies">
</p>

<p align="center">
  <strong>5 个 AI Agent 角色协作的软件开发框架 — 零依赖、基于文件、FSM 驱动</strong>
</p>

<p align="center">
  <a href="#安装">安装</a> ·
  <a href="#使用方式">使用</a> ·
  <a href="#12-个-skills">12 Skills</a> ·
  <a href="#为什么需要这个框架">为什么</a> ·
  <a href="blog/vibe-coding-and-multi-agent.md">博客</a>
</p>

---

零依赖、基于文件的多 Agent 协作框架，适用于 GitHub Copilot CLI 和 Claude Code。

## 概述

5 个专业 AI Agent 角色通过基于文件的状态机协作，覆盖完整的软件开发生命周期 (SDLC)：

| 角色 | Emoji | 职责 |
|------|-------|------|
| **验收者** (Acceptor) | 🎯 | 需求收集、任务发布、验收测试 |
| **设计者** (Designer) | 🏗️ | 架构设计、技术调研、测试规格 |
| **实现者** (Implementer) | 💻 | TDD 开发、Bug 修复、代码提交 |
| **审查者** (Reviewer) | 🔍 | 代码审查、安全审计、质量检查 |
| **测试者** (Tester) | 🧪 | 测试用例生成、E2E 测试、问题报告 |

## 核心特性

- **零依赖** — 纯 Markdown Skills + JSON 状态文件
- **文件持久化** — 所有状态存储在 Git 可追踪的文件中
- **FSM 强制工作流** — 非法状态转移会被拒绝
- **角色隔离** — 每个 Agent 只能在自己的职责范围内操作
- **Hook 强制执行** — Agent 边界由 Shell Hook 强制执行，不靠 LLM 自律
- **消息收件箱** — Agent 之间通过 `inbox.json` 通信
- **功能目标清单** — 每个任务有可独立验证的功能目标
- **自动调度** — 任务状态变更自动通知下一个 Agent
- **批处理模式** — Agent 在一个循环中处理所有待办任务
- **监控模式** — 测试者↔实现者全自动修复-验证循环
- **问题追踪** — 结构化 JSON + 乐观锁保证并发安全
- **SQLite 审计日志** — 每次工具使用都记录到 events.db
- **任务记忆** — 每个阶段完成后自动保存上下文快照，下个 Agent 接手时自动加载
- **超时检测** — 对长时间闲置的任务发出警告

## 任务生命周期

```
created → designing → implementing → reviewing → testing → accepting → accepted ✅
                         ▲                          ▲  │
                         └── reviewing (退回) ───────┘  └── fixing ──┘
                                                              ↕
                                                     (测试者↔实现者
                                                      全自动修复-验证循环)
```

任何任务都可以转为 `blocked` 状态（需要人工介入），通过 `unblock` 解除。

## 安装

对你的 AI 助手（Copilot CLI、Claude Code 等）说：

> "根据 cintia09/multi-agent-framework 仓库里的指引, 将 agents 安装到我本地。"

助手会读取仓库中的 AGENTS.md 并自动：
1. 克隆仓库到临时目录
2. 复制 12 个 Skill 目录到 `~/.copilot/skills/`
3. 复制 5 个 `.agent.md` 文件到 `~/.copilot/agents/`
4. 复制 5 个 Hook 脚本 + hooks.json 到 `~/.copilot/hooks/`
5. 追加协作规则到 `~/.copilot/copilot-instructions.md`（幂等）
6. 清理临时目录

使用内置脚本验证：
```bash
bash /tmp/multi-agent-framework/scripts/verify-install.sh
```

安装完成后，`~/.copilot/` 目录结构：
```
~/.copilot/
├── copilot-instructions.md       # 含 Agent 协作规则
├── hooks/
│   ├── hooks.json                # Hook 配置
│   ├── agent-session-start.sh    # 初始化 events.db，检查待办
│   ├── agent-pre-tool-use.sh     # Agent 边界执行
│   ├── agent-post-tool-use.sh    # 审计日志 + 自动调度
│   └── agent-staleness-check.sh  # 超时任务检测
├── skills/
│   └── agent-*/SKILL.md          # 12 个 Skill 目录（每个含 SKILL.md）
└── agents/
    ├── acceptor.agent.md         # 验收者（原生 Agent Profile）
    ├── designer.agent.md         # 设计者
    ├── implementer.agent.md      # 实现者
    ├── reviewer.agent.md         # 审查者
    └── tester.agent.md           # 测试者
```

**原生集成**：`/agent` 命令可直接列出并切换到这 5 个角色。
**幂等**：重复安装只覆盖 Skills 和 Agents，不会重复追加规则。

## 项目初始化

在任何项目目录中，对 Copilot 说 **"初始化 Agent 系统"**，它会调用 `agent-init` Skill 自动：

1. **收集上下文**（4 个来源）：
   - 检测项目技术栈（语言、框架、测试、CI、部署、Monorepo）
   - 读取 `.github/copilot-instructions.md`（项目规范，如果存在）
   - 读取全局 Agent Profiles（`~/.copilot/agents/*.agent.md`，角色定义）
   - 读取全局 Skills（`~/.copilot/skills/agent-*/SKILL.md`，工作流定义）
2. 创建 `.agents/runtime/` 运行时目录（state.json、inbox.json）
3. 初始化 `events.db`（SQLite 审计日志）
4. 创建 `.agents/task-board.json` 空任务表
5. **AI 生成 6 个项目级 Skill**（基于上下文定制，非拷贝！）：
   - `project-agents-context` — 项目技术栈、构建命令、部署方式
   - `project-acceptor` — 验收标准、业务背景
   - `project-designer` — 架构约束、技术选型
   - `project-implementer` — 编码规范、开发命令
   - `project-reviewer` — 审查标准、质量要求
   - `project-tester` — 测试框架、覆盖率要求
6. （可选）生成项目级 Hooks（`.agents/hooks/`）
7. 创建 `.agents/.gitignore`（排除运行时状态）

使用内置脚本验证：
```bash
bash /tmp/multi-agent-framework/scripts/verify-init.sh
```

## 使用方式

### 基本命令
```
"初始化 Agent 系统"    → 在当前项目中初始化 .agents/ 目录
/agent                → 浏览并选择角色（原生命令）
/agent acceptor       → 切换到验收者
/agent implementer    → 切换到实现者
"查看 Agent 状态"      → 状态面板（含阻塞任务提醒）
"unblock T-003"       → 解除任务阻塞
```

### 批处理模式
切换到任何 Agent 后说 **"处理任务"** / **"开始工作"**，Agent 自动：
1. 扫描任务表，找出分配给自己的所有待办任务
2. 按优先级排序（high > medium > low）
3. 逐个处理，处理完自动拿下一个
4. 全部完成后输出处理摘要

### 监控模式（测试者 ↔ 实现者）

**测试者**：
```
"监控实现者的修复"     → 自动验证 fixed issues，全部通过则转 accepting
```

**实现者**：
```
"监控测试者的反馈"     → 自动修复 open/reopened issues，等待验证
```

两边全自动循环 — 无需手动 check。通过自动调度 + 收件箱实现自动重入。

## 12 个 Skills

| # | Skill | 描述 |
|---|-------|------|
| 1 | `agent-fsm` | FSM 引擎 — 10 种状态转移 + Guard 规则 |
| 2 | `agent-task-board` | 任务 CRUD + 功能目标 + 阻塞/解阻塞 + 乐观锁 |
| 3 | `agent-messaging` | Agent 间收件箱消息 |
| 4 | `agent-init` | 项目初始化 + 增强技术栈检测 |
| 5 | `agent-switch` | 角色切换 + 状态面板 + 批处理模式 |
| 6 | `agent-memory` | 任务记忆 — 阶段完成后自动保存上下文快照 |
| 7 | `agent-acceptor` | 验收者工作流 |
| 8 | `agent-designer` | 设计者工作流 |
| 9 | `agent-implementer` | 实现者 + TDD + 监控模式 |
| 10 | `agent-reviewer` | 审查者工作流 |
| 11 | `agent-tester` | 测试者 + Issue JSON + 监控模式 |
| 12 | `agent-events` | events.db 查询、分析、清理、导出 |

## 问题追踪（测试者 ↔ 实现者）

结构化 JSON（`T-NNN-issues.json`）是唯一真相源：

```json
{
  "task_id": "T-003",
  "version": 5,
  "round": 2,
  "issues": [
    {
      "id": "ISS-001",
      "severity": "high",
      "status": "verified",
      "title": "登录接口空密码返回 500",
      "fix_note": "添加了空值检查",
      "fix_commit": "abc1234"
    }
  ]
}
```

**Issue 状态流转**：`open → fixed → verified ✅`（或 `→ reopened → fixed → ...`）

**字段归属**：
- 测试者写：问题详情、状态（open/verified/reopened）
- 实现者写：fix_note、fix_commit、状态（fixed）
- Markdown 报告从 JSON 自动生成（只读）

**并发安全**：乐观锁（version 字段）+ 字段隔离防止冲突。

## 任务记忆

每个任务有独立的记忆文件（`.agents/memory/T-NNN-memory.json`），跨阶段积累上下文：

- **自动保存** — 任务状态转移时，当前 Agent 自动保存工作摘要、关键决策、产出物、修改文件
- **自动加载** — 下一个 Agent 接手任务时，自动读取并展示上一阶段的记忆和交接备注
- **完整可追溯** — 记录每个阶段的 `handoff_notes`（交接备注），确保上下文不丢失
- **提交到 Git** — 记忆文件是有价值的项目知识，不是临时运行时状态

```json
{
  "task_id": "T-001",
  "version": 3,
  "stages": {
    "designing": {
      "agent": "designer",
      "summary": "设计了基于 JWT 的用户认证系统...",
      "decisions": ["选择 JWT 而非 session", "使用 bcrypt"],
      "artifacts": ["design-docs/T-001-design.md"],
      "handoff_notes": "实现者应先完成 JWT 中间件"
    },
    "implementing": {
      "agent": "implementer",
      "summary": "实现了登录/注册接口...",
      "files_modified": ["src/auth/jwt.ts", "src/routes/auth.ts"],
      "handoff_notes": "注意 token 刷新使用滑动窗口"
    }
  }
}
```

查看方式：对 Agent 说 **"查看记忆"** / **"任务上下文"** 即可展示完整的阶段记忆。

### 搜索记忆

对 Agent 说 **"搜索记忆 redis"** 或 **"有没有类似的经验"**：
- 跨所有任务搜索过去的**决策**、**踩坑记录**、**交接备注**
- 按相关度排序：精确匹配 decisions/issues > 同类阶段 > 最近任务
- 当前任务上下文感知：不指定关键词时，自动从任务描述提取关键词搜索

### 项目级摘要

对 Agent 说 **"项目摘要"** 或 **"lessons learned"**：
- 从所有任务记忆中汇总：架构决策、踩坑记录、技术栈选择、文件修改热区
- 自动识别高风险文件（被多个任务反复修改的文件）
- 可保存为 `.agents/memory/PROJECT-SUMMARY.md`

## 功能目标清单

每个任务包含功能目标清单（goals）：
- **验收者** 创建任务时定义 goals（每个 goal 是一个可独立验证的功能点）
- **实现者** 逐个实现 goals，标记为 `done`，全部 done 才能提交审查
- **验收者** 验收时逐个验证 goals，标记为 `verified`，全部 verified 才能通过验收

## Hooks（5 个脚本）

| Hook | 文件 | 功能 |
|------|------|------|
| **security-scan** | `security-scan.sh` | 🔒 提交前扫描 staged 文件中的密钥（独立于 Agent 系统，始终运行） |
| **session-start** | `agent-session-start.sh` | 初始化 events.db，检查待办消息/任务 |
| **pre-tool-use** | `agent-pre-tool-use.sh` | 强制执行 Agent 边界 — 拒绝越权操作 |
| **post-tool-use** | `agent-post-tool-use.sh` | 审计日志 + 自动调度到下一个 Agent |
| **staleness-check** | `agent-staleness-check.sh` | 检测闲置超过 24 小时的任务，发出警告 |

### Agent 边界规则（pre-tool-use）

| 角色 | 可编辑 | 不可编辑 |
|------|--------|---------|
| 🎯 验收者 | `.agents/` 目录 | 源代码 ⛔ |
| 🏗️ 设计者 | `.agents/` 目录 | 源代码 ⛔ |
| 💻 实现者 | 源代码 + 自己的工作区 | 其他 Agent 的工作区 ⛔ |
| 🔍 审查者 | 审查报告 + 任务看板 | 源代码 ⛔ |
| 🧪 测试者 | 测试文件 + 自己的工作区 | 源代码 ⛔ |

### 自动调度（post-tool-use）

当 `task-board.json` 被写入时，Hook 自动：
1. 检测新的任务状态
2. 映射到负责的 Agent
3. 写入该 Agent 的收件箱
4. 记录 `auto_dispatch` 事件到 events.db

## 审计日志（events.db）

所有 Agent 操作记录到 `.agents/events.db`（SQLite）：

| 字段 | 类型 | 描述 |
|------|------|------|
| timestamp | INTEGER | Unix 时间戳（毫秒） |
| event_type | TEXT | session_start、tool_use、task_board_write、auto_dispatch |
| agent | TEXT | 当前活跃 Agent |
| task_id | TEXT | 关联任务 ID |
| tool_name | TEXT | 使用的工具 |
| detail | TEXT | JSON 详情字符串 |

通过 `agent-events` Skill 或直接查询：
```bash
sqlite3 .agents/events.db "SELECT * FROM events ORDER BY id DESC LIMIT 20;"
```

## 文件结构

```
~/.copilot/                            # 全局层（安装后）
├── hooks/
│   ├── hooks.json                     # Hook 配置
│   ├── agent-session-start.sh         # 初始化 events.db
│   ├── agent-pre-tool-use.sh          # 边界执行
│   ├── agent-post-tool-use.sh         # 审计日志 + 自动调度
│   └── agent-staleness-check.sh       # 超时检测
├── skills/
│   └── agent-*/SKILL.md               # 11 个 Skill 目录
└── agents/
    └── *.agent.md                     # 5 个角色 Profile

<项目>/.agents/                        # 项目层（初始化后）
├── events.db                          # SQLite 审计日志
├── skills/project-*/SKILL.md          # 6 个 AI 生成的项目级 Skill
├── task-board.json / .md              # 任务表
├── tasks/T-NNN.json                   # 任务详情 + 功能目标
├── memory/T-NNN-memory.json           # 任务记忆（跨阶段上下文快照）
└── runtime/
    ├── active-agent                   # 当前活跃 Agent
    └── <角色>/
        ├── state.json / inbox.json
        └── workspace/                 # 工作产出物
            └── issues/T-NNN-issues.json  # 结构化问题追踪
```

## 设计灵感

| 项目 | Stars | 采纳的关键思想 |
|------|-------|-------------|
| [MetaGPT](https://github.com/geekan/MetaGPT) | 66K | `Code = SOP(Team)` — 将标准流程嵌入 Agent |
| [NTCoding/autonomous-claude-agent-team](https://github.com/NTCoding/autonomous-claude-agent-team) | 36 | Hook 强制执行、RESPAWN 模式、事件溯源 |
| [dragonghy/agents](https://github.com/dragonghy/agents) | — | YAML 配置、MCP 通信、超时检测 |
| [TaskGuild](https://github.com/kazz187/taskguild) | 3 | 状态驱动 Agent 触发、看板自动化 |

## 路线图

- **Phase 1** ✅ 手动角色切换 + FSM + 任务看板 + 功能目标
- **Phase 2** ✅ Hooks（边界执行）+ events.db（审计日志）
- **Phase 3** ✅ 自动调度 + 超时检测 + 批处理模式 + 监控模式
- **Phase 4** — 外部调度器（基于 cron 的自主 Agent 循环）
- **Phase 5** — Claude Code Agent Teams 集成（并行多 Agent）

---

## 为什么需要这个框架？

### 从编译器到 Agent：不变的本质

Vibe Coding 其实就是自然语言编程。

传统编程中，我们使用专用语言 —— Java、C++、Python —— 来描述功能，然后通过编译器将其转换为 CPU 可执行的代码。

Vibe Coding 也是同一件事：用自然语言描述功能，由 AI Agent 将其转换为 CPU 可执行的代码。

**不变的是**：不管你用自然语言还是 Java，它们都只是描述"我需要实现什么功能"的工具。

**变的是**：因为 Agent 足够智能，自然语言描述不必像传统语言那样精确，你也不必学习那些晦涩难懂的编程知识。这极大地拉低了编程的门槛。

但 —— **软件工程的本质没有变化**。如果你想构建一个足够好的应用，你仍然需要理解需求分析、架构设计、代码审查、测试验证这些环节。

### 一段痛苦的 Vibe Coding 经历

这个结论来自真实的痛苦经历：

```
我: "帮我实现用户登录功能"
Agent: (一通操作，代码写好了)
我: (手动测试)...不行，登录后页面空白
我: "登录后页面空白，帮我修"
Agent: (又一通操作)
我: (手动测试)...这次登录行了，但注册不行了
我: "注册怎么又坏了？"
...重复 N 次...
```

你要一直坐在电脑前，不停地和 Agent 交流、打字、手动验证、反复返工。**很痛苦。**

问题不是 Agent 不够聪明，而是整个过程缺乏**流程**：没有设计、没有自动化测试、没有代码审查、没有结构化的问题追踪。

![传统 Vibe Coding vs Multi-Agent Framework](blog/images/comparison.png)

这些不就是传统软件工程早已解决的问题吗？

### 解决方案：Agent 团队协作

于是我做了这个框架。核心理念 —— 既然 Vibe Coding 是"自然语言编程"，那整个软件开发流程也应该能用自然语言来定义和执行。

![Multi-Agent Framework 系统架构](blog/images/architecture.png)

**全程你只需要做两件事：创建任务 + 最终验收。** 中间的设计、实现、审查、测试、修复，全部由 Agent 自动完成。

### 好处

1. **不再人肉验证循环** — 测试者 Agent 自动运行测试、报告 Bug、验证修复
2. **质量由流程保证** — 不取决于"Agent 今天状态好不好"
3. **Bug 修复有追踪** — 结构化 JSON 记录，不在聊天记录里翻找
4. **流程不可绕过** — Shell Hook 强制执行规则，不靠 AI 的"自觉"
5. **随时可接手** — 所有状态在文件里，CLI 崩溃也能继续

> 这可能就是 Vibe Coding 的最终形态 —— 不是一个人和一个 Agent 反复拉扯，而是一个 **Agent 团队**各司其职，像真正的软件开发团队一样协作。而有意思的是，连这个框架本身，也是由 Agent 写的。

## 许可证

MIT
