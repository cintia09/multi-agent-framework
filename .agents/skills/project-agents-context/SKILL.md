---
name: project-agents-context
description: "Project context loaded by all agents. Includes tech stack, build commands, and deployment info."
---

# Project Context

## Project Info
- **Name**: multi-agent-framework
- **Description**: AI software engineering pipeline — 5 AI Agents collaborating through the full SDLC
- **Repository**: git@github.com:cintia09/multi-agent-framework.git
- **Branch strategy**: `main` (direct push, no PR workflow)

## Tech Stack
- **Languages**: Bash (shell scripts), Markdown (skills/docs), JSON (state/config)
- **Framework**: Custom Agent collaboration (FSM + Task Board + Memory + Messaging)
- **UI**: N/A (CLI framework, no frontend)
- **Database**: SQLite (events.db audit log)
- **Testing**: Custom bash test suite (`tests/run-all.sh`)
- **CI**: N/A (local development)
- **Deployment**: `install.sh` one-click install to `~/.claude/`

## Common Commands
| Action | Command |
|--------|---------|
| Run tests | `bash tests/run-all.sh` |
| Check install | `bash install.sh --check` |
| Install framework | `bash install.sh --full` |
| Uninstall framework | `bash install.sh --uninstall` |
| Verify scripts | `bash scripts/verify-install.sh` |

## Directory Structure
| Directory | Purpose |
|-----------|---------|
| `skills/` | 12 global Agent Skills (SKILL.md defines behavior) |
| `agents/` | 5 Agent Profiles (role definitions) |
| `hooks/` | Shell hooks (boundary enforcement, audit, security scan) |
| `scripts/` | Utility scripts (install verification, etc.) |
| `tests/` | Test suite (skills/agents/hooks format validation) |
| `docs/` | Project-level living docs (requirements, design, test, implementation, review, acceptance) |
| `.agents/` | Runtime directory (task board, state, memory, project-level skills) |
| `blog/` | Architecture diagrams and resources |

## Project Conventions
- All commit messages must be in English
- Commits must include `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`
- Skills start with YAML frontmatter
- Agent profiles use `.agent.md` suffix
- Hook scripts must have `+x` permission
