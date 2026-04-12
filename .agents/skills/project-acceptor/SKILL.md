---
name: project-acceptor
description: "Project acceptance criteria and business context. Loaded when the Acceptor agent works."
---

# Project Acceptance Guide

## Business Context
Multi-Agent Framework is an AI software engineering pipeline. Target users are developers using Claude Code / GitHub Copilot, collaborating through 5 specialized Agent roles to complete the SDLC (Requirements → Design → Implementation → Review → Testing → Acceptance). Core value: solving AI context window limitations via cross-Agent memory and FSM state machine.

## Acceptance Baseline
- **Functional tests**: `bash tests/run-all.sh` — all pass
- **Build check**: N/A (no compilation; all shell/markdown)
- **Lint check**: No auto-linter; manually verify SKILL.md frontmatter format
- **Coverage**: Test suite covers skills/agents/hooks format validation

## Acceptance Process
1. Read the task's goals list
2. Verify each goal's `description` is reflected in code
3. Run `bash tests/run-all.sh` — confirm all pass
4. Check SKILL.md files have YAML frontmatter
5. Check hooks have `+x` permission
6. Mark goals `met: true`, task status → `accepted`

## Quality Red Lines
- Never delete existing skill content (append/enhance only)
- Never break FSM state transition logic
- Commit messages must be in English
- No hardcoded absolute paths in `.agents/`
