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
4. 追加协作规则到 `~/.copilot/copilot-instructions.md` (幂等)
5. 清理临时目录

安装完成后, `~/.copilot/` 将包含:
```
~/.copilot/
├── copilot-instructions.md       # 含 Agent 协作规则
├── skills/
│   └── agent-*.md                # 10 个 skill 文件
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
- 检测项目技术栈 (语言、框架、测试、CI、部署)
- 创建 `.copilot/agents/` 目录 (5 个角色, 含 workspace)
- 初始化 `state.json`, `inbox.json`, `task-board.json`
- 基于全局模板 + 项目特征生成定制化 instructions
- 创建 `.copilot/.gitignore` (排除运行时状态文件)

## Usage

```
"初始化 Agent 系统"    → 在当前项目中初始化 .copilot/ 目录
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

## File Structure

```
~/.copilot/                            # 全局层 (安装后)
├── copilot-instructions.md            # 含 Agent 协作规则
├── skills/agent-*.md                  # 10 个 skill
└── agents/
    ├── acceptor.agent.md              # 验收者 (原生 agent profile)
    ├── designer.agent.md              # 设计者
    ├── implementer.agent.md           # 实现者
    ├── reviewer.agent.md              # 审查者
    └── tester.agent.md               # 测试者

<project>/                             # 项目层 (/init 生成)
├── AGENTS.md                          # Copilot 自动读取的 Agent 指引
└── .copilot/
    ├── task-board.json / .md
    ├── tasks/T-NNN.json
    └── agents/<role>/
        ├── state.json / inbox.json
        ├── instructions.md            # 定制化版本
        └── workspace/                 # 工作产出物
```

## Design Inspirations

| Project | Stars | Key Insight Adopted |
|---------|-------|-------------------|
| [MetaGPT](https://github.com/geekan/MetaGPT) | 66K | `Code = SOP(Team)` — Embed standard processes into agents |
| [NTCoding/autonomous-claude-agent-team](https://github.com/NTCoding/autonomous-claude-agent-team) | 36 | Hook enforcement, RESPAWN pattern, event sourcing |
| [dragonghy/agents](https://github.com/dragonghy/agents) | — | YAML config, MCP messaging, staleness detection |
| [TaskGuild](https://github.com/kazz187/taskguild) | 3 | Status-driven agent triggering, Kanban automation |

## Roadmap

- **Phase 1** ✅ Manual role switching + FSM + task board + goals (current)
- **Phase 2** — events.db (SQLite audit log) + enhanced /init
- **Phase 3** — Auto-dispatch, staleness detection, scheduled prompts

## License

MIT
