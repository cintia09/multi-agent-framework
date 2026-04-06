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
2. Add shebang: `#!/usr/bin/env bash`
3. Make it executable: `chmod +x hooks/my-hook.sh`
4. Register in `hooks/hooks.json`
5. Document the trigger conditions and behavior

### Modifying an Agent Profile

1. Agent profiles are in `agents/*.agent.md`
2. Each profile defines: core responsibilities, startup procedure, skill dependencies, behavior limits
3. Keep the profile focused on WHAT the agent does, not HOW (that's in skills)

## Guidelines

- **English commit messages** with descriptive titles
- **Preserve zero-dependency principle** — no npm/pip/cargo dependencies
- **File-driven** — all state in JSON/Markdown files, no databases (except events.db)
- **Test your changes** — run `tests/run-all.sh` before submitting
- **Update docs** — if you change a skill, update the skill's documentation

## Pull Request Process

1. Fork the repository
2. Create a feature branch: `git checkout -b feat/my-feature`
3. Make your changes
4. Run tests: `bash tests/run-all.sh`
5. Commit with descriptive message
6. Open a PR with the template filled out

## Code of Conduct

Be respectful, constructive, and collaborative. We welcome contributors of all skill levels.
