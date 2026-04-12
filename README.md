<p align="center">
  <img src="blog/images/architecture.png" alt="CodeNook" width="680" />
</p>

<h1 align="center">🤖 CodeNook — Multi-Agent Development Framework</h1>

<p align="center">
  <a href="https://github.com/cintia09/CodeNook/releases"><img src="https://img.shields.io/github/v/release/cintia09/CodeNook?style=for-the-badge&color=6366f1" alt="Release"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge" alt="MIT License"></a>
  <a href="https://github.com/cintia09/CodeNook/stargazers"><img src="https://img.shields.io/github/stars/cintia09/CodeNook?style=for-the-badge&color=f59e0b" alt="Stars"></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Agents-5-6366f1?style=flat-square" alt="5 Agents">
  <img src="https://img.shields.io/badge/Skill-1-10b981?style=flat-square" alt="1 Skill">
  <img src="https://img.shields.io/badge/HITL_Scripts-6-f59e0b?style=flat-square" alt="6 HITL Scripts">
  <img src="https://img.shields.io/badge/Zero_Dependencies-✓-8b5cf6?style=flat-square" alt="Zero Dependencies">
</p>

<p align="center">
  <strong>5 AI agents, 1 skill, orchestrator-driven workflow — zero dependencies, HITL approval gates, DFMEA risk management</strong>
</p>

<p align="center">
  <a href="#installation">Installation</a> ·
  <a href="#quick-start">Quick Start</a> ·
  <a href="#architecture">Architecture</a> ·
  <a href="#hitl-multi-adapter-system">HITL</a> ·
  <a href="#agent-profiles">Agent Profiles</a> ·
  <a href="blog/vibe-coding-and-multi-agent.md">Blog</a>
</p>

---

Zero-dependency, orchestrator-driven multi-agent framework for Claude Code and GitHub Copilot CLI.

## Overview

Five specialized AI agents collaborate through an orchestrator that routes tasks, spawns subagents, and enforces human-in-the-loop gates between every phase.

| Role | Emoji | Responsibilities | Tools | Model (default) |
|------|-------|------------------|-------|-----------------|
| **Acceptor** | 🎯 | Requirements gathering, goal decomposition, acceptance testing | Read, Bash, Grep, Glob | claude-haiku-4.5 |
| **Designer** | 🏗️ | Architecture design (ADR format), API specs, test specifications | Read, Bash, Grep, Glob, WebFetch | claude-sonnet-4 |
| **Implementer** | 💻 | TDD development (red-green-refactor), DFMEA risk analysis | Read, Edit, Create, Bash, Grep, Glob | claude-sonnet-4 |
| **Reviewer** | 🔍 | Code review, OWASP security checklist, severity rating | Read, Bash, Grep, Glob | claude-sonnet-4 |
| **Tester** | 🧪 | Test execution, coverage analysis, issue reporting | Read, Bash, Grep, Glob, Edit | claude-haiku-4.5 |

## Core Features

- **1 Skill** — `codenook-init` installs agent system + deploys orchestration engine per-project
- **Subagent Architecture** — Each agent runs in a separate context window, spawned on demand
- **HITL After Every Phase** — 6 scripts (local-html, terminal, github-issue, confluence, verify, server)
- **Task Board** — Single JSON file as source of truth; 10 statuses with deterministic routing
- **Memory Chain** — Each phase writes a snapshot; downstream agents receive upstream context
- **DFMEA Risk Management** — Implementer outputs failure-mode analysis (S×O×D → RPN)
- **Tool-Based Boundaries** — `tools` / `disallowedTools` in agent frontmatter (no hooks needed)
- **Per-Agent Models** — Each role can use a different AI model
- **Zero Dependencies** — Pure Markdown profiles + JSON state files
- **Multi-Platform** — Copilot CLI (`.github/`) and Claude Code (`.claude/`)

## Installation

### Option 1: One-Line Install

```bash
curl -sL https://raw.githubusercontent.com/cintia09/CodeNook/main/install.sh | bash
```

Installs 1 skill globally. Auto-detects Claude Code / Copilot CLI.

### Option 2: Manual Install

Copy the skill directory to your platform's skills folder:

| Platform | Target |
|----------|--------|
| Copilot CLI | `~/.copilot/skills/codenook-init/` |
| Claude Code | `~/.claude/skills/codenook-init/` |

The skill directory contains `SKILL.md`, agent templates, HITL adapter scripts, and the orchestration engine template.

### Verify

```bash
bash install.sh --check
```

## Quick Start

### 1. Initialize the Agent System

In any project directory, tell your AI assistant:

> "Initialize the agent system"

The `codenook-init` skill walks you through 4 prompts:

| Prompt | Options |
|--------|---------|
| Platform | Copilot CLI · Claude Code · Both |
| Agent models | Use defaults · Custom per-agent |
| HITL adapter | Local HTML · Terminal · GitHub Issue · Confluence |
| Gitignore | Yes · No |

It then generates project-level files:

```
<root>/                          # .github/ or .claude/
├── agents/
│   ├── acceptor.agent.md
│   ├── designer.agent.md
│   ├── implementer.agent.md
│   ├── reviewer.agent.md
│   └── tester.agent.md
├── codenook/
│   ├── memory/
│   ├── task-board.json
│   ├── config.json
│   └── hitl-adapters/           # HITL scripts (auto-copied)
│       ├── terminal.sh
│       ├── local-html.sh
│       ├── github-issue.sh
│       ├── confluence.sh
│       ├── hitl-verify.sh
│       └── hitl-server.py
└── instructions/                # Copilot CLI only
    └── codenook.instructions.md # Orchestration engine (auto-loaded)
```

> For Claude Code, the orchestration engine is appended to the project-root `CLAUDE.md` instead.

### 2. Create a Task

> "Create task: Implement user authentication"

The orchestrator adds it to `codenook/task-board.json` with status `created`.

### 3. Run the Task

> "Run task T-001"

The orchestrator drives the task through the full pipeline:

```
created → designer → [HITL] → implementer → [HITL] → reviewer → [HITL] → tester → [HITL] → acceptor → [HITL] → done
```

You approve or provide feedback at each HITL gate. That's it.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    USER (You)                            │
│           "create task" · "run task T-001"               │
└─────────────────┬───────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────┐
│              ORCHESTRATOR (main session)                  │
│                                                          │
│  ┌───────────────────┐   ┌────────────┐   ┌───────────────┐  │
│  │ codenook/         │   │ codenook/  │   │ codenook/     │  │
│  │ task-board.json   │   │ config.json│   │ memory/*.md   │  │
│  │ (source of    │   │ (platform, │   │ (phase        │  │
│  │  truth)       │   │  models,   │   │  snapshots)   │  │
│  │              │   │  hitl)     │   │              │  │
│  └──────────────┘   └────────────┘   └───────────────┘  │
│                                                          │
│  Route by status → spawn subagent → collect result       │
│  → HITL gate → update status → next phase                │
└───┬─────────┬─────────┬─────────┬─────────┬─────────────┘
    │         │         │         │         │
    ▼         ▼         ▼         ▼         ▼
┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐
│🏗️ Des │ │💻 Imp │ │🔍 Rev │ │🧪 Tes │ │🎯 Acc │
│igner  │ │lemen- │ │iewer  │ │ter    │ │eptor  │
│       │ │ter    │ │       │ │       │ │       │
│Separate context windows — spawned on demand   │
└───────┘ └───────┘ └───────┘ └───────┘ └───────┘
```

**Key principle:** The orchestrator is the sole writer of `codenook/task-board.json`. Subagents receive context in their prompt and return results in their response — no file-based messaging.

## Task Lifecycle

### Status Routing Table

| Status | Handler | On Approve | On Reject |
|--------|---------|------------|-----------|
| `created` | → Designer | `designing_done` | *(agent retries)* |
| `designing_done` | → **[HITL]** | `implementing` | `created` |
| `implementing` | → Implementer | `implementing_done` | *(agent retries)* |
| `implementing_done` | → **[HITL]** | `reviewing` | `implementing` |
| `reviewing` | → Reviewer | `review_done` | *(agent retries)* |
| `review_done` | → **[HITL]** | `testing` | `implementing` |
| `testing` | → Tester | `test_done` | *(agent retries)* |
| `test_done` | → **[HITL]** | `accepting` | `implementing` |
| `accepting` | → Acceptor | `accepted` | *(agent retries)* |
| `accepted` | → **[HITL]** | `done` | `created` |

- HITL gates after every agent phase — no auto-advancement
- Rejection routes backward to the appropriate phase
- Subagent errors pause the loop and report to the user

### Task Board Schema

```json
{
  "version": "4.0",
  "tasks": [{
    "id": "T-001",
    "title": "Implement user authentication",
    "status": "created",
    "priority": "P0",
    "goals": [
      { "id": "G1", "description": "JWT login endpoint", "status": "pending" }
    ],
    "artifacts": {},
    "feedback_history": [],
    "created_at": "2025-01-15T10:00:00Z",
    "updated_at": "2025-01-15T10:00:00Z"
  }]
}
```

### Commands

| Command | Action |
|---------|--------|
| `create task <title>` | Add task with status `created` |
| `show task board` | Display all tasks with status |
| `run task T-XXX` | Start orchestration loop |
| `task status T-XXX` | Show detailed status + history |
| `add goal G3: <desc> to T-XXX` | Add goal to existing task |
| `delete task T-XXX` | Remove task (with confirmation) |
| `agent status` | Show framework config and state |

## HITL Multi-Adapter System

Every phase transition passes through a human review gate. The adapter is auto-detected or configured in `codenook/config.json`.

### Detection Priority

1. `codenook/config.json` → `hitl.adapter` (explicit setting)
2. `$SSH_TTY` set → terminal
3. `$DISPLAY` set or macOS → local-html
4. `/.dockerenv` exists → terminal
5. Default → terminal

### 4 Adapters

| Adapter | Environment | Publish | Feedback |
|---------|-------------|---------|----------|
| 🌐 **local-html** | Local dev (desktop) | HTTP server + browser UI | Web buttons + text input |
| 💻 **terminal** | SSH / Docker / CI | Formatted CLI summary | `ask_user()` prompt |
| 🐙 **github-issue** | GitHub projects | Create/update issue | Poll reactions (👍 = approve) |
| 📝 **confluence** | Enterprise intranet | Create/update Confluence page | Poll page comments |

Each adapter implements three operations:

```bash
adapter.sh publish  <task_id> <role> <file>   # Present output for review
adapter.sh poll     <task_id> <role>           # Check for response
adapter.sh get_feedback <task_id> <role>       # Return decision + comments
```

### Feedback Loop

```
Subagent produces output → Orchestrator publishes via adapter
→ Human reviews → Approve / Feedback / Reject
→ Orchestrator records in feedback_history → routes accordingly
```

Multi-round feedback is supported — reject with comments, agent revises, re-publish, review again.

## Agent Profiles

Each agent is defined in a Markdown file with YAML frontmatter. The `tools` and `disallowedTools` fields enforce role boundaries — **no hooks required**.

### Example: Implementer

```yaml
---
name: implementer
description: "Developer — implements goals via TDD, writes code and tests, produces DFMEA analysis."
tools: Read, Edit, Create, Bash, Grep, Glob
disallowedTools: Agent
---
```

### Role Boundaries

| Role | `tools` | `disallowedTools` | Effect |
|------|---------|-------------------|--------|
| 🎯 Acceptor | Read, Bash, Grep, Glob | Edit, Create, Agent | Read-only, no code changes |
| 🏗️ Designer | Read, Bash, Grep, Glob, WebFetch | Edit, Create, Agent | Read-only + web research |
| 💻 Implementer | Read, Edit, Create, Bash, Grep, Glob | Agent | Full code access, no sub-spawning |
| 🔍 Reviewer | Read, Bash, Grep, Glob | Edit, Create, Agent | Read-only, no code changes |
| 🧪 Tester | Read, Bash, Grep, Glob, Edit | Agent | Can edit test files, no sub-spawning |

All agents have `disallowedTools: Agent` — preventing sub-subagent spawning. Only the orchestrator can spawn subagents.

### Profile Structure

Each `.agent.md` file contains:

| Section | Purpose |
|---------|---------|
| **Identity** | Role description and behavioral contract |
| **Input Contract** | What the orchestrator provides |
| **Workflow** | Step-by-step execution process |
| **Output Contract** | Structured artifact format |
| **Quality Gates** | Completion checklist |
| **Constraints** | Hard rules (TDD, security, English-only, etc.) |

## Memory

Each phase writes a memory snapshot to `codenook/memory/<task_id>-<role>-memory.md`. The orchestrator manages the memory chain — each agent receives all upstream memories:

```
designer memory                                    → implementer
designer + implementer memory                      → reviewer
designer + implementer + reviewer memory           → tester
all memories                                       → acceptor
```

Memory snapshots include: input summary, key decisions, artifacts produced, issues & risks, and context for the next agent.

## Configuration

After initialization, `codenook/config.json` lives under the platform directory (`.github/codenook/` or `.claude/codenook/`):

```json
{
  "version": "4.0",
  "platform": "copilot-cli",
  "models": {
    "acceptor":    "claude-haiku-4.5",
    "designer":    "claude-sonnet-4",
    "implementer": "claude-sonnet-4",
    "reviewer":    "claude-sonnet-4",
    "tester":      "claude-haiku-4.5"
  },
  "hitl": {
    "enabled": true,
    "adapter": "local-html",
    "port": 8765,
    "auto_open_browser": true
  },
  "preferences": {
    "autoGitignore": true
  }
}
```

| Field | Description |
|-------|-------------|
| `platform` | `copilot-cli` or `claude-code` |
| `models.*` | AI model per agent role |
| `hitl.enabled` | Enable/disable HITL gates |
| `hitl.adapter` | `local-html` · `terminal` · `github-issue` · `confluence` |
| `hitl.port` | Port for local-html adapter (default: 8765) |

### Platform Directories

| Platform | Root | Agents | CodeNook Dir | Skills |
|----------|------|--------|--------------|--------|
| Copilot CLI | `.github/` | `.github/agents/` | `.github/codenook/` | `~/.copilot/skills/` |
| Claude Code | `.claude/` | `.claude/agents/` | `.claude/codenook/` | `~/.claude/skills/` |

## Error Handling

| Scenario | Action |
|----------|--------|
| Subagent timeout | Report to user; offer retry or skip |
| Subagent crash | Report error; offer retry with different model |
| HITL no response (10 min) | Reminder; 30 min → save state and pause |
| `codenook/task-board.json` corrupt | Recover from `.bak`; report if unrecoverable |
| Memory file missing | Warn and continue with reduced context |

The orchestrator backs up `codenook/task-board.json` to `codenook/task-board.json.bak` before every write. On restart, it reads the task board and resumes from the current status — no in-memory state needed.

## Migrating from v3.x

v4.0 is a ground-up simplification. Key changes:

| v3.x | v4.0 |
|------|------|
| 20 global skills | 1 global skill + project-level agents & engine |
| 13 shell hooks | `tools` / `disallowedTools` in frontmatter |
| Session-level role switching (`/agent`) | Subagent delegation via orchestrator |
| 11-state FSM | 10-status task-board routing |
| File-based messaging (`inbox.json`) | Orchestrator context passing |
| `agent-hitl-gate` skill | Multi-adapter HITL (4 adapters) |
| `events.db` SQLite audit | Feedback history in `codenook/task-board.json` |
| `.agents/` project directory | `.github/codenook/` or `.claude/codenook/` (platform-native) |

**Migration steps:**

1. Remove old global skills, hooks, and rules from `~/.claude/` or `~/.copilot/`
2. Install v4.0 (`curl` one-liner or manual copy)
3. In your project, run "initialize agent system" to generate new files
4. Migrate existing tasks manually if needed (copy goals to new `codenook/task-board.json`)

> 📖 See [MIGRATION.md](docs/MIGRATION.md) for a detailed migration guide.

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feat/my-feature`)
3. Commit changes (`git commit -m 'feat: add my feature'`)
4. Push to the branch (`git push origin feat/my-feature`)
5. Open a Pull Request

Please follow the existing code style and include tests for new features.

## License

MIT
