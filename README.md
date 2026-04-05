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
- **Optimistic locking** — Concurrent modification protection via version fields

## Task Lifecycle

```
created → designing → implementing → reviewing → testing → accepting → accepted ✅
                         ▲                          ▲  │
                         └── reviewing (reject) ────┘  └── fixing ──┘
```

## Quick Start

### 1. Install skills globally

Simply tell Copilot CLI (while in this repo):
> "帮我将这个 repo 里的 agents 安装到我本地"

Copilot will read the install.sh and execute it, or you can run manually:
```bash
./install.sh
```

This copies 10 skill files to `~/.copilot/skills/` and appends agent collaboration rules to `~/.copilot/copilot-instructions.md`.

### 2. Initialize a project

```bash
cd your-project/
# Tell Copilot CLI: "初始化 Agent 系统" or "/init agents"
```

### 3. Start working

```bash
# Switch to acceptor role
"/agent acceptor"  →  Create requirements and publish tasks

# Switch to designer role
"/agent designer"  →  Design architecture, output specs

# Switch to implementer role
"/agent implementer"  →  TDD implementation

# Switch to reviewer role
"/agent reviewer"  →  Code review

# Switch to tester role
"/agent tester"  →  Testing and issue reporting

# Check all agent status
"/agent status"
```

## File Structure

```
~/.copilot/
├── instructions.md          # Global rules (append agent rules)
└── skills/
    ├── agent-fsm.md         # State machine engine
    ├── agent-task-board.md   # Task CRUD + optimistic locking
    ├── agent-messaging.md   # Inter-agent inbox messaging
    ├── agent-switch.md      # Role switching controller
    ├── agent-init.md        # Project initialization
    ├── agent-acceptor.md    # Acceptor role definition
    ├── agent-designer.md    # Designer role definition
    ├── agent-implementer.md # Implementer role definition
    ├── agent-reviewer.md    # Reviewer role definition
    └── agent-tester.md      # Tester role definition

<project>/.copilot/          # Created by /init
├── task-board.json          # Machine-readable task board
├── task-board.md            # Human-readable task board
├── tasks/                   # Individual task details
└── agents/
    └── <role>/
        ├── state.json       # Agent FSM state
        ├── inbox.json       # Message inbox
        ├── instructions.md  # Project-specific instructions
        └── workspace/       # Work artifacts
```

## Design Inspirations

| Project | Stars | Key Insight Adopted |
|---------|-------|-------------------|
| [MetaGPT](https://github.com/geekan/MetaGPT) | 66K | `Code = SOP(Team)` — Embed standard processes into agents |
| [NTCoding/autonomous-claude-agent-team](https://github.com/NTCoding/autonomous-claude-agent-team) | 36 | Hook enforcement, RESPAWN pattern, event sourcing |
| [dragonghy/agents](https://github.com/dragonghy/agents) | — | YAML config, MCP messaging, staleness detection |
| [TaskGuild](https://github.com/kazz187/taskguild) | 3 | Status-driven agent triggering, Kanban automation |

## Roadmap

- **Phase 1** ✅ Manual role switching + FSM + task board (current)
- **Phase 2** — events.db (SQLite audit log) + enhanced /init
- **Phase 3** — Auto-dispatch, staleness detection, scheduled prompts

## License

MIT
