---
name: project-implementer
description: "Project coding standards and dev commands. Loaded when the Implementer agent works."
---

# Project Development Guide

## Dev Commands
| Action | Command | Notes |
|--------|---------|-------|
| Run tests | `bash tests/run-all.sh` | 3 tests (skills/agents/hooks) |
| Single test | `bash tests/test-skills.sh` | Verify SKILL.md format |
| Check install | `bash install.sh --check` | Verify install status in ~/.claude/ |
| Install locally | `bash install.sh --full` | Clone from GitHub and install |

## Coding Standards
- **Shell**: Start with `set -euo pipefail`; encapsulate logic in functions
- **Markdown**: YAML frontmatter must have `name` and `description`
- **JSON**: 2-space indent, `ensure_ascii=False`
- **Naming**: kebab-case (files/dirs), snake_case (JSON fields)
- **Commits**: English commit messages + Co-authored-by trailer

## File Type Guide
| File Type | Location | Rules |
|-----------|----------|-------|
| Skill | `skills/agent-*/SKILL.md` | YAML frontmatter + step-based Markdown |
| Agent Profile | `agents/*.agent.md` | Role persona definition |
| Hook | `hooks/*.sh` | Bash script, needs `+x`, reads stdin JSON |
| Test | `tests/test-*.sh` | Bash, outputs ✅/❌, non-zero exit on failure |
| Doc | `docs/*.md` | Project-level living docs, append mode |

## TDD Workflow
1. Test files: `tests/test-*.sh`
2. Write new test case → `bash tests/run-all.sh` to confirm red
3. Implement feature
4. `bash tests/run-all.sh` to confirm green
5. Refactor (keep green)

## Dependencies
- **No package manager**: Zero external dependencies
- All tools: bash, sqlite3, python3 (system-provided)
- New skills/hooks only require creating files — no install steps
