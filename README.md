# Multi-Agent Software Development Framework

A zero-dependency, file-based multi-agent collaboration framework for GitHub Copilot CLI and Claude Code.

## Overview

5 specialized AI agent roles collaborate through a file-based state machine to deliver complete software development lifecycle (SDLC) coverage:

| Role | Emoji | Responsibility |
|------|-------|---------------|
| **Acceptor** | 🎯 | Requirements gathering, task publishing, acceptance testing |
| **Designer** | 🏗️ | Architecture design, technical research, test specifications |
| **Implementer** | 💻 | TDD development, bug fixes, code submission |
| **Reviewer** | 🔍 | Code review, security audit, quality checks |
| **Tester** | 🧪 | Test case generation, E2E testing, issue reporting |

## Key Features

- **Zero dependencies** — Pure Markdown skills + JSON state files
- **File-based persistence** — All state in Git-trackable files
- **FSM-enforced workflow** — Illegal state transitions are rejected
- **Role isolation** — Each agent only operates within its scope
- **Hook enforcement** — Agent boundaries enforced by shell hooks, not LLM self-discipline
- **Inbox messaging** — Agents communicate via `inbox.json` files
- **Goals checklist** — Each task has verifiable feature goals
- **Auto-dispatch** — Task status changes automatically notify the next agent
- **Batch processing** — Agents process all pending tasks in a single loop
- **Watch mode** — Tester↔Implementer automatic fix-verify cycle
- **Issue tracking** — Structured JSON with optimistic locking for concurrent safety
- **SQLite audit log** — Every tool use logged to events.db
- **Staleness detection** — Warns about tasks idle for too long

## Task Lifecycle

```
created → designing → implementing → reviewing → testing → accepting → accepted ✅
                         ▲                          ▲  │
                         └── reviewing (reject) ────┘  └── fixing ──┘
                                                              ↕
                                                     (tester↔implementer
                                                      auto fix-verify cycle)
```

Any task can also transition to `blocked` (human intervention required) via `/unblock`.

## Installation

Tell your AI assistant (Copilot CLI, Claude Code, etc.):

> "根据 cintia09/multi-agent-framework 仓库里的指引, 将 agents 安装到我本地。"

The assistant will read the AGENTS.md in the repo and automatically:
1. Clone 仓库到临时目录
2. 复制 11 个 skill 目录到 `~/.copilot/skills/`
3. 复制 5 个 `.agent.md` 文件到 `~/.copilot/agents/`
4. 复制 4 个 hook 脚本 + hooks.json 到 `~/.copilot/hooks/`
5. 追加协作规则到 `~/.copilot/copilot-instructions.md` (幂等)
6. 清理临时目录

Verify with the included script:
```bash
bash /tmp/multi-agent-framework/scripts/verify-install.sh
```

安装完成后, `~/.copilot/` 将包含:
```
~/.copilot/
├── copilot-instructions.md       # 含 Agent 协作规则
├── hooks/
│   ├── hooks.json                # Hook 配置
│   ├── agent-session-start.sh    # 初始化 events.db, 检查待办
│   ├── agent-pre-tool-use.sh     # Agent 边界执行
│   ├── agent-post-tool-use.sh    # 审计日志 + 自动调度
│   └── agent-staleness-check.sh  # 超时任务检测
├── skills/
│   └── agent-*/SKILL.md          # 11 个 skill 目录 (每个含 SKILL.md)
└── agents/
    ├── acceptor.agent.md         # 验收者 (原生 agent profile)
    ├── designer.agent.md         # 设计者
    ├── implementer.agent.md      # 实现者
    ├── reviewer.agent.md         # 审查者
    └── tester.agent.md           # 测试者
```

**原生集成**: `/agent` 命令可直接列出并切换到这 5 个角色。
**幂等**: 重复安装只覆盖 skills 和 agents, 不会重复追加 rules。

## Project Initialization

在任何项目目录中, 对 Copilot 说 **"初始化 Agent 系统"**, 它会调用 `agent-init` skill 自动:

1. **收集上下文** (4 个来源):
   - 检测项目技术栈 (语言、框架、测试、CI、部署、monorepo)
   - 读取 `.github/copilot-instructions.md` (项目规范, 如果存在)
   - 读取全局 agent profiles (`~/.copilot/agents/*.agent.md`, 角色定义)
   - 读取全局 skills (`~/.copilot/skills/agent-*/SKILL.md`, 工作流定义)
2. 创建 `.agents/runtime/` 运行时目录 (state.json, inbox.json)
3. 初始化 `events.db` (SQLite 审计日志)
4. 创建 `.agents/task-board.json` 空任务表
5. **AI 生成 6 个项目级 skill** (基于上下文, 非拷贝!):
   - `project-agents-context` — 项目技术栈、构建命令、部署方式
   - `project-acceptor` — 验收标准、业务背景
   - `project-designer` — 架构约束、技术选型
   - `project-implementer` — 编码规范、开发命令
   - `project-reviewer` — 审查标准、质量要求
   - `project-tester` — 测试框架、覆盖率要求
6. (可选) 生成项目级 hooks (`.agents/hooks/`)
7. 创建 `.agents/.gitignore` (排除运行时状态)

Verify with:
```bash
bash /tmp/multi-agent-framework/scripts/verify-init.sh
```

## Usage

### Basic Commands
```
"初始化 Agent 系统"    → 在当前项目中初始化 .agents/ 目录
/agent                → 浏览并选择角色 (原生命令)
/agent acceptor       → 切换到验收者
/agent implementer    → 切换到实现者
"查看 Agent 状态"      → 状态面板 (含阻塞任务提醒)
"unblock T-003"       → 解除任务阻塞
```

### Batch Processing Mode
切换到任何 Agent 后说 **"处理任务"** / **"开始工作"**, Agent 自动:
1. 扫描任务表，找出分配给自己的所有待办任务
2. 按优先级排序 (high > medium > low)
3. 逐个处理，处理完自动拿下一个
4. 全部完成后输出处理摘要

### Watch Mode (Tester ↔ Implementer)

**测试者**:
```
"监控实现者的修复"     → 自动验证 fixed issues, 全部通过则转 accepting
```

**实现者**:
```
"监控测试者的反馈"     → 自动修复 open/reopened issues, 等待验证
```

两边全自动循环 — 无需手动 "check"。通过 auto-dispatch + inbox 实现自动重入。

## 11 Skills

| # | Skill | Description |
|---|-------|-------------|
| 1 | `agent-fsm` | FSM engine — 10 state transitions + guard rules |
| 2 | `agent-task-board` | Task CRUD + goals + block/unblock + optimistic locking |
| 3 | `agent-messaging` | Inter-agent inbox messaging |
| 4 | `agent-init` | Project initialization + enhanced tech stack detection |
| 5 | `agent-switch` | Role switching + status panel + batch processing |
| 6 | `agent-acceptor` | Acceptor workflow |
| 7 | `agent-designer` | Designer workflow |
| 8 | `agent-implementer` | Implementer + TDD + watch mode |
| 9 | `agent-reviewer` | Reviewer workflow |
| 10 | `agent-tester` | Tester + issue JSON + watch mode |
| 11 | `agent-events` | events.db query, analysis, cleanup, export |

## Issue Tracking (Tester ↔ Implementer)

Structured JSON (`T-NNN-issues.json`) is the single source of truth:

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
      "title": "Login returns 500 on empty password",
      "fix_note": "Added null check",
      "fix_commit": "abc1234"
    }
  ]
}
```

**Issue status flow**: `open → fixed → verified ✅` (or `→ reopened → fixed → ...`)

**Field ownership**:
- Tester writes: issue details, status (open/verified/reopened)
- Implementer writes: fix_note, fix_commit, status (fixed)
- Markdown reports auto-generated (read-only)

**Concurrency**: Optimistic locking (version field) + field isolation prevents conflicts.

## Goals Checklist

每个任务包含功能目标清单 (goals):
- **Acceptor** 创建任务时定义 goals (每个 goal 是一个可独立验证的功能点)
- **Implementer** 逐个实现 goals, 标记为 `done`, 全部 done 才能提交审查
- **Acceptor** 验收时逐个验证 goals, 标记为 `verified`, 全部 verified 才能通过验收

## Hooks (4 Scripts)

| Hook | File | Function |
|------|------|----------|
| **session-start** | `agent-session-start.sh` | Initialize events.db, check pending messages/tasks |
| **pre-tool-use** | `agent-pre-tool-use.sh` | Enforce agent boundaries — deny unauthorized edits |
| **post-tool-use** | `agent-post-tool-use.sh` | Audit log + auto-dispatch to next agent |
| **staleness-check** | `agent-staleness-check.sh` | Detect tasks idle >24h, warn user |

### Agent Boundary Rules (pre-tool-use)

| Role | Can Edit | Cannot Edit |
|------|----------|-------------|
| 🎯 Acceptor | `.agents/` directory | Source code ⛔ |
| 🏗️ Designer | `.agents/` directory | Source code ⛔ |
| 💻 Implementer | Source code + own workspace | Other agents' workspace ⛔ |
| 🔍 Reviewer | Review reports + task board | Source code ⛔ |
| 🧪 Tester | Test files + own workspace | Source code ⛔ |

### Auto-dispatch (post-tool-use)

When `task-board.json` is written, the hook automatically:
1. Detects the new task status
2. Maps it to the responsible agent
3. Writes a message to that agent's inbox
4. Logs `auto_dispatch` event to events.db

## Audit Log (events.db)

All agent actions logged to `.agents/events.db` (SQLite):

| Column | Type | Description |
|--------|------|-------------|
| timestamp | INTEGER | Unix timestamp (ms) |
| event_type | TEXT | session_start, tool_use, task_board_write, auto_dispatch |
| agent | TEXT | Active agent name |
| task_id | TEXT | Related task ID |
| tool_name | TEXT | Tool used |
| detail | TEXT | JSON detail string |

Query with the `agent-events` skill or directly:
```bash
sqlite3 .agents/events.db "SELECT * FROM events ORDER BY id DESC LIMIT 20;"
```

## File Structure

```
~/.copilot/                            # 全局层 (安装后)
├── hooks/
│   ├── hooks.json                     # Hook 配置
│   ├── agent-session-start.sh         # 初始化 events.db
│   ├── agent-pre-tool-use.sh          # 边界执行
│   ├── agent-post-tool-use.sh         # 审计日志 + 自动调度
│   └── agent-staleness-check.sh       # 超时检测
├── skills/
│   └── agent-*/SKILL.md               # 11 个 skill 目录
└── agents/
    └── *.agent.md                     # 5 个角色 profile

<project>/.agents/                     # 项目层 (初始化后)
├── events.db                          # SQLite 审计日志
├── skills/project-*/SKILL.md          # 6 个 AI 生成的项目级 skill
├── task-board.json / .md              # 任务表
├── tasks/T-NNN.json                   # 任务详情 + goals
└── runtime/
    ├── active-agent                   # 当前活跃 agent
    └── <role>/
        ├── state.json / inbox.json
        └── workspace/                 # 工作产出物
            └── issues/T-NNN-issues.json  # 结构化问题追踪
```

## Design Inspirations

| Project | Stars | Key Insight Adopted |
|---------|-------|-------------------|
| [MetaGPT](https://github.com/geekan/MetaGPT) | 66K | `Code = SOP(Team)` — Embed standard processes into agents |
| [NTCoding/autonomous-claude-agent-team](https://github.com/NTCoding/autonomous-claude-agent-team) | 36 | Hook enforcement, RESPAWN pattern, event sourcing |
| [dragonghy/agents](https://github.com/dragonghy/agents) | — | YAML config, MCP messaging, staleness detection |
| [TaskGuild](https://github.com/kazz187/taskguild) | 3 | Status-driven agent triggering, Kanban automation |

## Roadmap

- **Phase 1** ✅ Manual role switching + FSM + task board + goals
- **Phase 2** ✅ Hooks (boundary enforcement) + events.db (audit log)
- **Phase 3** ✅ Auto-dispatch + staleness detection + batch processing + watch mode
- **Phase 4** — External scheduler (cron-based autonomous agent loop)
- **Phase 5** — Claude Code Agent Teams integration (parallel multi-agent)

---

## Why This Framework? — A Vibe Coding Story

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

## License

MIT
