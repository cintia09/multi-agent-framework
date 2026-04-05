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

The assistant will:
1. 从 GitHub 读取本仓库内容
2. 将 `skills/` 目录下的 10 个 agent skill 文件复制到 `~/.copilot/skills/`
3. 将 `agents/` 目录下的 5 个角色模板复制到 `~/.copilot/agents/`
4. 将 `docs/agent-rules.md` 的内容追加到 `~/.copilot/copilot-instructions.md` (如果尚未包含)

安装完成后, `~/.copilot/` 将包含:
```
~/.copilot/
├── copilot-instructions.md      # 含 Agent 协作规则
├── skills/
│   └── agent-*.md               # 10 个 skill 文件
└── agents/
    ├── acceptor/instructions.md  # 验收者模板
    ├── designer/instructions.md  # 设计者模板
    ├── implementer/instructions.md
    ├── reviewer/instructions.md
    └── tester/instructions.md
```

**幂等**: 重复安装只覆盖 skills 和 agents 模板, 不会重复追加 rules。

## Project Initialization

在任何项目目录中执行 `/init`, Copilot 会读取 `agent-init` skill 并自动:
- 创建 `.copilot/agents/` 目录 (5 个角色, 含 workspace)
- 初始化 `state.json`, `inbox.json`, `task-board.json`
- **在项目 git root 创建 `AGENTS.md`** (Copilot 自动读取此文件)
- 继承全局模板并根据项目技术栈定制化

## Usage

```
"切换到验收者"    → 收集需求, 发布任务
"切换到设计者"    → 架构设计, 输出规格
"切换到实现者"    → TDD 开发, 按 goals 逐个实现
"切换到审查者"    → 代码审查
"切换到测试者"    → 测试, 报告问题
"查看 Agent 状态" → 状态面板
```

## Goals Checklist

每个任务包含功能目标清单 (goals):
- **Acceptor** 创建任务时定义 goals (每个 goal 是一个可独立验证的功能点)
- **Implementer** 逐个实现 goals, 标记为 `done`, 全部 done 才能提交审查
- **Acceptor** 验收时逐个验证 goals, 标记为 `verified`, 全部 verified 才能通过验收

## File Structure

```
~/.copilot/                      # 全局层 (安装后)
├── copilot-instructions.md      # 含 Agent 协作规则
├── skills/agent-*.md            # 10 个 skill
└── agents/<role>/instructions.md # 5 个角色模板

<project>/                       # 项目层 (/init 生成)
├── AGENTS.md                    # Copilot 自动读取的 Agent 指引
└── .copilot/
    ├── task-board.json / .md
    ├── tasks/T-NNN.json
    └── agents/<role>/
        ├── state.json / inbox.json
        ├── instructions.md      # 定制化版本
        └── workspace/           # 工作产出物
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
