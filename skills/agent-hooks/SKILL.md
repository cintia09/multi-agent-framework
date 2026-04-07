---
name: agent-hooks
description: "Hook lifecycle management. Shell scripts triggered at lifecycle points to enforce boundaries, validate operations, and coordinate agents."
---

# Skill: Agent Hooks

## Description
Manages the hook lifecycle for the multi-agent framework. Hooks are shell scripts triggered at specific lifecycle points to enforce boundaries, log events, validate operations, and coordinate agents.

## Trigger
- Agent switch, task creation/status change, memory write, context compaction, goal verification
- Pre/post tool usage, session start

## Hook Inventory

### Existing Hooks (5 — v1.0 Core)
| Hook | File | Event | Purpose |
|------|------|-------|---------|
| Security Scan | `security-scan.sh` | PreToolUse | Block secrets from being committed |
| Session Start | `agent-session-start.sh` | SessionStart | Initialize events.db, check pending work |
| Pre-Tool-Use | `agent-pre-tool-use.sh` | PreToolUse | Enforce agent role boundaries |
| Post-Tool-Use | `agent-post-tool-use.sh` | PostToolUse | Audit logging, auto-dispatch |
| Staleness Check | `agent-staleness-check.sh` | SessionStart | Warn about inactive tasks/agents |

### New Hooks (8 — v2.0 Lifecycle)
| Hook | File | Event | Purpose |
|------|------|-------|---------|
| Before Switch | `agent-before-switch.sh` | AgentSwitch | Validate agent role switch is allowed |
| After Switch | `agent-after-switch.sh` | AgentSwitch | Log switch event, inject role context |
| Before Task Create | `agent-before-task-create.sh` | TaskCreate | Validate task (title, duplicate check) |
| After Task Status | `agent-after-task-status.sh` | TaskStatusChange | Log status change, trigger memory capture |
| Before Memory Write | `agent-before-memory-write.sh` | MemoryWrite | Validate memory content and path |
| After Memory Write | `agent-after-memory-write.sh` | MemoryWrite | Update FTS5 search index |
| Before Compaction | `agent-before-compaction.sh` | Compaction | Flush session memories before context compression |
| On Goal Verified | `agent-on-goal-verified.sh` | GoalVerified | Log goal verification to events.db |

## Hook Control Semantics

### Block Semantics
Any `before-*` hook can return a block response to prevent the operation:
```json
{"block": true, "reason": "Reviewer cannot modify source files"}
```
When blocked:
- The operation is **cancelled**
- The reason is displayed to the agent
- An event is logged to `events.db`

### Approval Semantics
Hooks can request human confirmation:
```json
{"requireApproval": true, "message": "Task has unmet goals, confirm acceptance?"}
```
When approval requested:
- The operation is **paused**
- The message is displayed to the user
- User must confirm or deny before proceeding

### Priority Chain
Multiple hooks for the same event execute in priority order:
- Priority 1 (highest) → Priority N (lowest)
- If any hook returns `block: true`, remaining hooks are **skipped**
- Default priority: **50** (configurable in `hooks.json`)

### Hook Response Protocol
```json
// Allow (default if no output)
{"allow": true}

// Block (terminal — stops operation and remaining hooks)
{"block": true, "reason": "..."}

// Approval (pauses for human confirmation)
{"requireApproval": true, "message": "..."}

// Status (informational, for after-* hooks)
{"status": "ok"}

// Permission decision (for PreToolUse hooks specifically)
{"permissionDecision": "deny", "permissionDecisionReason": "..."}
```

## Role Tool Profiles

Tool profiles are defined in `.agents/tool-profiles.json` and control what each agent role is allowed to do:

| Role | Tools | Write Access | Restrictions |
|------|-------|-------------|--------------|
| **acceptor** | Read, Bash, Grep, Glob, View | None (read-only) | No `rm`, `mv`, `cp`, redirect |
| **designer** | All | `.agents/runtime/designer/`, design docs | Cannot modify skills, hooks, scripts, tests |
| **implementer** | All | All source code | Cannot modify `task-board.json` |
| **reviewer** | All | `.agents/runtime/reviewer/`, review docs | Cannot modify skills, hooks, scripts |
| **tester** | All | `tests/`, `.agents/runtime/tester/` | Cannot modify skills, hooks, agents |

Enforcement is done by `agent-pre-tool-use.sh` which reads the active agent from `.agents/runtime/active-agent` and applies the corresponding profile restrictions.

## Configuration

All hooks are registered in `hooks/hooks.json`. Each entry specifies:
- **matcher**: glob pattern for which tools/events trigger the hook
- **hooks**: array of hook definitions with `type`, `command`, and `timeout`

## Input/Output Contract

**Input**: Hooks receive JSON on stdin with context-specific fields:
- Agent switch: `{from_agent, to_agent, task_id}`
- Task operations: `{task_id, title, new_status, agent}`
- Memory operations: `{file_path, content}`
- Goal verification: `{task_id}`
- Tool use: `{toolName, toolArgs, cwd}`

**Output**: Hooks write JSON to stdout (see Response Protocol above).

## Steps
1. Hook scripts are installed to `hooks/` and made executable
2. `hooks.json` maps lifecycle events to hook scripts
3. The runtime calls hooks at the appropriate lifecycle point
4. `before-*` hooks can block operations; `after-*` hooks are informational
5. Tool profiles in `.agents/tool-profiles.json` define per-role boundaries
