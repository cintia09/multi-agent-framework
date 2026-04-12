---
name: project-tester
description: "Project test framework and testing strategy. Loaded when the Tester agent works."
---

# Project Testing Guide

## Test Framework
- **Unit tests**: Bash test scripts (`tests/test-*.sh`)
- **Integration tests**: `tests/run-all.sh` runs all
- **E2E tests**: N/A (CLI framework, no UI)

## Test Commands
| Action | Command |
|--------|---------|
| All tests | `bash tests/run-all.sh` |
| Skills format | `bash tests/test-skills.sh` |
| Agents format | `bash tests/test-agents.sh` |
| Hooks format | `bash tests/test-hooks.sh` |
| Install verify | `bash install.sh --check` |

## Test File Organization
- **Location**: `tests/`
- **Naming**: `test-*.sh`
- **Runner**: `run-all.sh` (aggregates all test-*.sh)
- **Output**: `✅` pass / `❌` fail; non-zero exit code on failure

## Testing Strategy
- **New Skill**: Verify SKILL.md has frontmatter and non-empty content
- **New Hook**: Verify `+x` permission and executability
- **New Agent Profile**: Verify `.agent.md` suffix and non-empty content
- **Goal validation**: Read task-board.json goals, verify against actual files
- **Regression**: Re-run all tests after modifying existing skills

## Validation Rules
| Target | Validation Method |
|--------|-------------------|
| SKILL.md format | Check `---` frontmatter exists |
| JSON validity | `python3 -m json.tool < file.json` |
| Hook permissions | `test -x hooks/*.sh` |
| Agent profile | Check `.agent.md` file exists and is non-empty |
| Task board | JSON has `version` and `tasks` fields |
