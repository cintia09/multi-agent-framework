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
- **Inbox messaging** — Agents communicate via `inbox.json` files
- **Goals checklist** — Each task has verifiable feature goals
- **Hook enforcement** — Agent boundaries enforced by shell hooks, not LLM self-discipline
- **SQLite audit log** — Every tool use logged to events.db for debugging and analysis

## Task Lifecycle

```
created → designing → implementing → reviewing → testing → accepting → accepted ✅
                         ▲                          ▲  │
                         └── reviewing (reject) ────┘  └── fixing ──┘
```

## Installation

Tell your AI assistant (Copilot CLI, Claude Code, etc.):

> "根据 cintia09/multi-agent-framework 仓库里的指引, 将 agents 安装到我本地。"

The assistant will read the AGENTS.md in the repo and automatically:
1. Clone 仓库到临时目录
2. 复制 10 个 skill 文件到 `~/.copilot/skills/`
3. 复制 5 个 `.agent.md` 文件到 `~/.copilot/agents/` (Copilot 原生 custom agent 格式)
4. 复制 3 个 hook 脚本 + hooks.json 到 `~/.copilot/hooks/`
5. 追加协作规则到 `~/.copilot/copilot-instructions.md` (幂等)
6. 清理临时目录

安装完成后, `~/.copilot/` 将包含:
```
~/.copilot/
├── copilot-instructions.md       # 含 Agent 协作规则
├── hooks/
│   ├── hooks.json                # Hook 配置
│   ├── agent-session-start.sh    # 初始化 events.db, 检查待办
│   ├── agent-pre-tool-use.sh     # Agent 边界执行
│   └── agent-post-tool-use.sh    # 审计日志
├── skills/
│   └── agent-*/SKILL.md          # 10 个 skill 目录 (每个含 SKILL.md)
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
   - 检测项目技术栈 (语言、框架、测试、CI、部署)
   - 读取 `.github/copilot-instructions.md` (项目规范, 如果存在)
   - 读取全局 agent profiles (`~/.copilot/agents/*.agent.md`, 角色定义)
   - 读取全局 skills (`~/.copilot/skills/agent-*/SKILL.md`, 工作流定义)
2. 创建 `.agents/runtime/` 运行时目录 (state.json, inbox.json)
3. 创建 `.agents/task-board.json` 空任务表
4. **AI 生成 6 个项目级 skill** (基于上下文, 非拷贝!):
   - `project-agents-context` — 项目技术栈、构建命令、部署方式
   - `project-acceptor` — 验收标准、业务背景
   - `project-designer` — 架构约束、技术选型
   - `project-implementer` — 编码规范、开发命令
   - `project-reviewer` — 审查标准、质量要求
   - `project-tester` — 测试框架、覆盖率要求
5. 创建 `.agents/.gitignore` (排除运行时状态)

所有文件统一在 `.agents/` 目录下, 项目级 skill 由 Copilot 自动发现和加载。

## Usage

```
"初始化 Agent 系统"    → 在当前项目中初始化 .agents/ 目录
/agent                → 浏览并选择角色 (原生命令)
/agent acceptor       → 切换到验收者
/agent implementer    → 切换到实现者
"使用验收者 agent"     → Copilot 自动推断并委派
"查看 Agent 状态"      → 状态面板
```

## Goals Checklist

每个任务包含功能目标清单 (goals):
- **Acceptor** 创建任务时定义 goals (每个 goal 是一个可独立验证的功能点)
- **Implementer** 逐个实现 goals, 标记为 `done`, 全部 done 才能提交审查
- **Acceptor** 验收时逐个验证 goals, 标记为 `verified`, 全部 verified 才能通过验收

## Hooks (Agent Boundary Enforcement)

The framework uses Copilot CLI's native hook system to enforce agent boundaries and maintain an audit trail.

### 3 Hook Types

| Hook | File | Function |
|------|------|----------|
| **session-start** | `agent-session-start.sh` | Initialize events.db, check pending messages/tasks |
| **pre-tool-use** | `agent-pre-tool-use.sh` | Enforce agent boundaries — deny unauthorized edits |
| **post-tool-use** | `agent-post-tool-use.sh` | Audit log all tool usage to events.db |

### Agent Boundary Rules

| Role | Can Edit | Cannot Edit |
|------|----------|-------------|
| 🎯 Acceptor | `.agents/` directory | Source code ⛔ |
| 🏗️ Designer | `.agents/` directory | Source code ⛔ |
| 💻 Implementer | Source code + own workspace | Other agents' workspace ⛔ |
| 🔍 Reviewer | Review reports + task board | Source code ⛔ |
| 🧪 Tester | Test files + own workspace | Source code ⛔ |

The `pre-tool-use` hook reads `.agents/runtime/active-agent` to determine the current role, then enforces the boundary rules above. Violations are denied with a descriptive error message.

## Audit Log (events.db)

All agent actions are logged to `.agents/events.db` (SQLite) for debugging and analysis.

### Schema

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Auto-increment primary key |
| timestamp | INTEGER | Unix timestamp (ms) |
| event_type | TEXT | session_start, tool_use, task_board_write, state_change |
| agent | TEXT | Active agent name |
| task_id | TEXT | Related task ID (if applicable) |
| tool_name | TEXT | Tool used (bash, edit, create, etc.) |
| detail | TEXT | JSON detail string |

### Querying

```bash
# Recent events
sqlite3 .agents/events.db "SELECT * FROM events ORDER BY id DESC LIMIT 20;"

# Events by agent
sqlite3 .agents/events.db "SELECT * FROM events WHERE agent='implementer';"

# Task board changes
sqlite3 .agents/events.db "SELECT * FROM events WHERE event_type='task_board_write';"
```

## File Structure

```
~/.copilot/                            # 全局层 (安装后)
├── copilot-instructions.md            # 含 Agent 协作规则
├── hooks/
│   ├── hooks.json                     # Hook 配置
│   ├── agent-session-start.sh         # 初始化 events.db
│   ├── agent-pre-tool-use.sh          # 边界执行
│   └── agent-post-tool-use.sh         # 审计日志
├── skills/
│   ├── agent-fsm/SKILL.md            # FSM 引擎
│   ├── agent-task-board/SKILL.md     # 任务表操作
│   ├── agent-messaging/SKILL.md      # 消息系统
│   ├── agent-init/SKILL.md           # 项目初始化
│   ├── agent-switch/SKILL.md         # 角色切换
│   └── agent-{role}/SKILL.md         # 5 个角色 skill
└── agents/
    ├── acceptor.agent.md              # 验收者 (原生 agent profile)
    ├── designer.agent.md              # 设计者
    ├── implementer.agent.md           # 实现者
    ├── reviewer.agent.md              # 审查者
    └── tester.agent.md               # 测试者

<project>/                             # 项目层 (初始化后)
└── .agents/                           # 统一目录
    ├── events.db                      # SQLite 审计日志
    ├── skills/                        # 项目级 skill (Copilot 自动发现)
    │   ├── project-agents-context/SKILL.md  # 技术栈、命令、部署
    │   ├── project-acceptor/SKILL.md  # 验收标准
    │   ├── project-designer/SKILL.md  # 架构约束
    │   ├── project-implementer/SKILL.md # 编码规范
    │   ├── project-reviewer/SKILL.md  # 审查标准
    │   └── project-tester/SKILL.md    # 测试策略
    ├── task-board.json / .md          # 任务表
    ├── tasks/T-NNN.json               # 任务详情
    └── runtime/
        ├── active-agent               # 当前活跃 agent (供 hooks 读取)
        └── <role>/                    # Agent 运行时
            ├── state.json / inbox.json
            └── workspace/             # 工作产出物
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
- **Phase 3** — Auto-dispatch, staleness detection, scheduled prompts

## License

MIT
