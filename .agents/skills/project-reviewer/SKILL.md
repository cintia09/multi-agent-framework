---
name: project-reviewer
description: "Project review standards and code quality requirements. Loaded when the Reviewer agent works."
---

# Project Review Guide

## Review Checklist
- [ ] Tests pass: `bash tests/run-all.sh`
- [ ] SKILL.md has YAML frontmatter (`name` + `description`)
- [ ] Hook scripts have `+x` permission
- [ ] JSON files are valid (`python3 -m json.tool`)
- [ ] No hardcoded absolute paths (use relative paths or `$HOME`)
- [ ] No security vulnerabilities (hardcoded secrets, unescaped user input)
- [ ] Commit messages in English
- [ ] New features have corresponding goal descriptions
- [ ] Existing skill content not removed (append/enhance only)

## Project-Specific Rules
- All SKILL.md files must remain backward-compatible (no deleting existing sections)
- FSM transitions: Changes to agent-fsm/SKILL.md require extra review of transition table completeness
- Task Board: Changes to task-board.json must verify `version` field increment
- Memory: Changes to agent-memory/SKILL.md must ensure capture/load symmetry

## Severity Levels
| Level | Description | Examples |
|-------|-------------|----------|
| CRITICAL | Breaks core workflow | Missing FSM states, invalid task-board structure |
| HIGH | Missing functionality | Skill missing required sections, hook missing permissions |
| MEDIUM | Quality issues | Unclear docs, hardcoded paths |
| LOW | Style suggestions | Naming inconsistency, minor formatting |

## Review Report Template
Output to `.agents/runtime/reviewer/workspace/review-reports/review-T-NNN-<date>.md`:
- **Critical issues** (must fix)
- **Suggestions** (optional fix)
- **Verdict**: PASS / FAIL (FAIL if any CRITICAL/HIGH issues exist)
