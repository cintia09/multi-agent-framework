# Contributing to Multi-Agent Framework

Thank you for your interest in contributing! This guide explains how to add new capabilities to the framework.

## How to Contribute

### Adding a New Skill

1. Create a directory under `skills/` (e.g., `skills/agent-my-skill/`)
2. Add `SKILL.md` with YAML frontmatter:
   ```yaml
   ---
   name: agent-my-skill
   description: "Brief description of what this skill does"
   ---
   ```
3. Document the workflow, inputs, outputs, and integration points
4. Update `README.md` skills table

### Adding a New Hook

1. Create a shell script under `hooks/` (e.g., `hooks/my-hook.sh`)
2. Add shebang: `#!/usr/bin/env bash` and `set -euo pipefail`
3. Use `AGENTS_DIR="${CWD:-.}/.agents"` for project paths (not bare `.agents/`)
4. Make it executable: `chmod +x hooks/my-hook.sh`
5. Register in **both** JSON configs (see format differences below)
6. Document the trigger conditions and behavior

**Dual-platform hook format:**

| Field | Claude Code (`hooks.json`) | Copilot (`hooks-copilot.json`) |
|-------|---------------------------|-------------------------------|
| Event keys | `PascalCase` (SessionStart) | `camelCase` (sessionStart) |
| Script field | `"command": "path"` | `"bash": "path"` |
| Timeout | `"timeout": 5000` (ms) | `"timeoutSec": 5` (sec) |
| Routing | `"matcher": "*"` | N/A |
| Description | N/A | `"comment": "..."` |
| Script path | `~/.claude/hooks/` | `~/.copilot/hooks/` |

### Adding a Rule

1. Create a markdown file under `rules/` (e.g., `rules/my-rule.md`)
2. Optionally add YAML frontmatter with `paths:` to scope the rule:
   ```yaml
   ---
   paths:
     - "src/**/*.ts"
   ---
   ```
3. Rules without `paths:` apply globally; rules with `paths:` only load when matching files are accessed
4. Keep rules concise — they consume context tokens

### Modifying an Agent Profile

1. Agent profiles are in `agents/*.agent.md`
2. Each profile defines: core responsibilities, startup procedure, skill dependencies, behavior limits
3. Keep the profile focused on WHAT the agent does, not HOW (that's in skills)

## Project Structure

```
skills/             # 15 Skill definitions (YAML frontmatter + Markdown)
agents/             # 5 Agent profiles (.agent.md)
hooks/              # 13 shell scripts + hooks.json (Claude) + hooks-copilot.json (Copilot)
rules/              # Modular rules (path-scoped, Claude Code native .claude/rules/)
scripts/            # Utility scripts (verify, memory, cron, webhook)
tests/              # Test suite (4 tests)
docs/               # Project documentation templates + agent-rules.md
```

## Guidelines

- **English commit messages** with descriptive titles
- **Preserve zero-dependency principle** — no npm/pip/cargo dependencies
- **File-driven** — all state in JSON/Markdown files, no databases (except events.db)
- **macOS compatible** — no GNU-only flags (`grep -P`, etc.), use POSIX/BSD alternatives
- **Test your changes** — run `tests/run-all.sh` before submitting
- **Update docs** — if you change a skill/hook/rule, update the corresponding documentation
- **Dual-platform** — consider both Claude Code and GitHub Copilot compatibility

## Pull Request Process

1. Fork the repository
2. Create a feature branch: `git checkout -b feat/my-feature`
3. Make your changes
4. Run tests: `bash tests/run-all.sh`
5. Commit with descriptive message
6. Open a PR with the template filled out

## Code of Conduct

Be respectful, constructive, and collaborative. We welcome contributors of all skill levels.
