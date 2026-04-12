---
name: agent-task-board
description: "Task Board operations: create/update/view tasks. Trigger: 'create task', 'task list', 'update task status'."
---

# Task Board Operations

## File Locations
- JSON (machine-readable): `<project>/.agents/task-board.json`
- Markdown (human-readable): `<project>/.agents/task-board.md`
- Task details: `<project>/.agents/tasks/T-NNN.json`

## task-board.json Format

```json
{
  "version": 1,
  "tasks": [
    {
      "id": "T-001",
      "title": "User Auth System",
      "status": "created",
      "assigned_to": "designer",
      "priority": "P0",
      "created_by": "acceptor",
      "created_at": "2026-04-05T08:00:00Z",
      "updated_at": "2026-04-05T08:00:00Z",
      "worktree": null
    }
  ]
}
```

### worktree Field (Optional)

When a task has an independent worktree created via `agent-worktree create`:

```json
{
  "worktree": {
    "path": "../project--T-001",
    "branch": "task/T-001",
    "created_at": "2026-04-05T10:00:00Z"
  }
}
```

- `worktree: null` means the task is developed in the main working directory (default)
- After merge (`agent-worktree merge`), worktree field is cleared to null
- Auto-dispatch routes messages to the corresponding worktree's inbox based on this field

## Operations

### Create Task (Acceptor Only)
1. Read task-board.json
2. Generate new ID: T-{max_id + 1}, zero-padded to 3 digits
3. Create task entry, status = "created", assigned_to = "designer"
4. Create tasks/T-NNN.json detail file
5. Write task-board.json (version + 1)
6. Sync task-board.md
7. Write to designer's inbox.json: "New task T-NNN: <title>"

### View Task List
Read task-board.json and format output:
```
📋 Task Board (version: N)
ID      Status         Assignee      Priority  Title
T-001   implementing   Implementer   P0        User Auth System
T-002   designing      Designer      P1        Question Bank Module
```

### Update Task Status
Delegates to agent-fsm skill for state transition logic.

**⚡ Memory save required after state transition**:
After each successful task state transition, the current agent must invoke agent-memory skill to save a context snapshot:
```
FSM validation passed → write task-board.json → sync Markdown → 💾 save memory → notify downstream agent
```
Memory includes: work summary, key decisions, artifacts, modified files, handoff notes.
See agent-memory skill for details.

### Block Task
When any agent encounters an unresolvable issue:
1. Set task status to `blocked`
2. Record `blocked_reason` and `blocked_from` (previous status) on the task
3. Send message to acceptor's inbox: "⚠️ T-NNN blocked: <reason>"

### Unblock Task
Triggered by "unblock T-NNN":
1. Read task's `blocked_from` field to get previous status
2. Restore status to the `blocked_from` value
3. Clear `blocked_reason` and `blocked_from`
4. Send message to the responsible agent's inbox: "✅ T-NNN unblocked, restored to <status>"

```json
// Blocked task example
{
  "id": "T-003",
  "status": "blocked",
  "blocked_from": "implementing",
  "blocked_reason": "Dependent API not ready",
  "assigned_to": "implementer"
}
```

### Sync Markdown
Auto-generate task-board.md after every task-board.json modification.

## Task Detail File (tasks/T-NNN.json)

```json
{
  "id": "T-001",
  "title": "User Auth System",
  "description": "Implement cookie-based user authentication system...",
  "status": "created",
  "assigned_to": "designer",
  "priority": "P0",
  "created_by": "acceptor",
  "created_at": "2026-04-05T08:00:00Z",
  "updated_at": "2026-04-05T08:00:00Z",
  "history": [],
  "goals": [
    {"id": "G-001", "title": "Goal description", "status": "pending", "completed_at": null, "verified_at": null}
  ],
  "artifacts": {
    "requirement": null,
    "acceptance_doc": null,
    "design": null,
    "test_spec": null,
    "test_cases": null,
    "issues_report": null,
    "fix_tracking": null,
    "review_report": null,
    "acceptance_report": null
  }
}
```

## Important Notes
- All writes use optimistic lock (read version → verify version unchanged on write → version + 1)
- Every JSON modification must sync the Markdown counterpart
- Only acceptor can create and delete tasks
- Status changes must pass agent-fsm validation

## Goals

### goals Field Schema
```json
{
  "id": "G-001",
  "title": "Implement user login endpoint",
  "status": "pending|done|verified|failed",
  "completed_at": null,
  "verified_at": null,
  "note": ""
}
```

### Goal Statuses
| Status | Meaning | Set By |
|--------|---------|--------|
| `pending` | Not yet implemented | Acceptor (on task creation) |
| `done` | Marked complete | Implementer |
| `verified` | Acceptance confirmed | Acceptor |
| `failed` | Acceptance rejected | Acceptor |

---

## Grouped View

### Trigger

Show when user says `/board --grouped` or "group by status".

### Status Group Definitions

| Group | Included Statuses | Icon |
|-------|------------------|------|
| 🔴 Blocked | `blocked` | ⛔ |
| 🟡 In Progress | `created`, `designing`, `implementing`, `reviewing`, `testing`, `accepting`, `fixing` | ⏳ |
| 🟢 Completed | `accepted` | ✅ |
| ❌ Accept Failed | `accept_fail` | 🔄 |

### Output Format

```
📋 Task Board — Grouped View (version: N)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔴 Blocked (1)
  ⛔ T-004  P0  implementing  💻 Implementer  Dependency API Module
     Reason: Dependent API not ready

🟡 In Progress (3)
  ⏳ T-001  P0  reviewing     🔍 Reviewer     User Auth System
  ⏳ T-003  P1  implementing  💻 Implementer  Question Bank Module
  ⏳ T-005  P2  designing     🏗️ Designer     Theme System

🟢 Completed (2)
  ✅ T-002  P0  accepted      —         Database Init
  ✅ T-006  P1  accepted      —         Logging System

❌ Accept Failed (1)
  🔄 T-007  P1  accept_fail   🏗️ Designer     Search Feature

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total: 7 tasks | Blocked: 1 | In Progress: 3 | Completed: 2 | Failed: 1
```

### Implementation Steps

1. Read `task-board.json`
2. Group tasks by `status` into corresponding groups
3. Sort each group by `priority` (P0 > P1 > P2)
4. Show `blocked_reason` for blocked tasks
5. Hide empty groups

---

## Project Stats Panel

### Trigger

Show when user says `/board --stats` or "project stats".

### Output Format

```
📊 Project Stats Panel
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 Completion Rate
  ████████████░░░░░░░░  60% (6/10 tasks completed)

⏱️ Avg Cycle Time
  Overall avg: 5.2h
  Fastest: T-006 (2.1h)
  Slowest: T-001 (9.8h)

🐢 Slowest Stage (Bottleneck Analysis)
  implementing  avg 2.8h  ← bottleneck
  designing     avg 1.2h
  testing       avg 0.9h
  reviewing     avg 0.5h
  accepting     avg 0.3h

📈 Throughput
  This week: 4 tasks
  Last week: 2 tasks
  Trend: ↑ +100%

🔄 Rejection Rate
  Review rejected: 2/8 (25%)
  Test rejected: 1/8 (12.5%)
  Acceptance rejected: 0/6 (0%)

⛔ Block Stats
  Currently blocked: 1 task
  Avg block duration: 2.5h
  Most blocked stage: implementing

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### Data Sources

| Metric | Source | Formula |
|--------|--------|---------|
| Completion rate | `task-board.json` | `count(status=accepted) / count(all)` |
| Avg cycle time | `tasks/T-NNN.json` `cycle_time` | `avg(total_elapsed_minutes)` (accepted tasks only) |
| Slowest stage | `tasks/T-NNN.json` `cycle_time.stages` | Group by stage, `avg(duration_minutes)`, find max |
| Throughput | `task-board.json` + `tasks/T-NNN.json` | Count `accepted` tasks this week vs last week |
| Rejection rate | `tasks/T-NNN.json` `history` | Count reviewing→implementing, testing→fixing transitions |
| Block stats | `task-board.json` + `cycle_time.blocked_time` | Current blocked count, avg block duration |

### Implementation Steps

1. Read `task-board.json` for all tasks
2. Read each `tasks/T-NNN.json` for `cycle_time` data
3. Calculate metrics per formulas above
4. Format output (progress bars use `█` and `░` characters)
5. Trends use arrows: ↑ up / ↓ down / → flat

---

## Progress Tracking

### Overview

Calculate completion percentage for each task and the overall project based on goals status.

### Task-Level Progress

In **task list** and **grouped view**, each task shows goals completion progress:

```
📋 Task Board (version: N)
ID      Status         Assignee      Priority  Progress    Title
T-001   implementing   Implementer   P0        ██░░░ 2/5   User Auth System
T-002   accepted       —            P0        █████ 3/3   Database Init
T-003   reviewing      Reviewer      P1        ███░░ 3/5   Question Bank Module
```

### Progress Formula

```
Task progress = count(goals where status in ["done", "verified"]) / count(goals)

Overall project progress = sum(completed goals across all tasks) / sum(total goals across all tasks)
```

### Progress Bar Rendering

| Completion | Bar | Semantics |
|-----------|-----|-----------|
| 0% | `░░░░░` | Not started |
| 1-25% | `█░░░░` | Just started |
| 26-50% | `██░░░` | In progress |
| 51-75% | `███░░` | Past halfway |
| 76-99% | `████░` | Near completion |
| 100% | `█████` | Complete |

### Implementation Steps

1. Read `tasks/T-NNN.json` goals array
2. Count goals by status
3. Calculate percentage: `done + verified` count as completed
4. Render 5-block progress bar + numbers (e.g., `███░░ 3/5`)
5. Insert progress column in task list output

### Project Progress in Stats Panel

```
📋 Overall Project Progress
  Goals: ████████████████░░░░  32/40 (80%)
  Verified: 28/40 (70%)  Pending verify: 4/40 (10%)  Not implemented: 8/40 (20%)
```

---

## Filter & Sort

### Trigger

User appends filter/sort parameters when viewing task list:

| Command | Description |
|---------|-------------|
| `/board --assignee implementer` | Show only tasks assigned to implementer |
| `/board --assignee designer,reviewer` | Show tasks for multiple roles |
| `/board --sort age` | Sort by task age (oldest first) |
| `/board --sort priority` | Sort by priority (P0 > P1 > P2) |
| `/board --sort progress` | Sort by completion (lowest first) |
| `/board --priority P0` | Show only P0 tasks |
| `/board --priority P0,P1` | Show P0 and P1 |
| `/board --status implementing,fixing` | Show only specific statuses |
| `/board --age ">2h"` | Show tasks older than 2 hours |
| Combined | Parameters stack: `/board --assignee implementer --sort age --priority P0` |

### Filter Rules

| Filter | Field | Match |
|--------|-------|-------|
| `--assignee <role>` | `assigned_to` | Exact, comma-separated multi-value |
| `--priority <level>` | `priority` | Exact, comma-separated multi-value |
| `--status <status>` | `status` | Exact, comma-separated multi-value |
| `--age "<op><duration>"` | `created_at` | Supports `>2h`, `<1d`, `>30m`, etc. |

### Sort Rules

| Sort By | Field | Default Direction |
|---------|-------|-------------------|
| `priority` | `priority` | P0 > P1 > P2 (desc) |
| `age` | `created_at` | Oldest first (asc) |
| `updated` | `updated_at` | Most recent first (desc) |
| `progress` | goals completion % | Lowest first (asc) |
| `cycle` | `cycle_time.total_elapsed_minutes` | Slowest first (desc) |

### Default Sort

When no sort specified, use **compound sort**:
1. Primary: `priority` desc (P0 first)
2. Secondary: `updated_at` desc (most recent first)

### Implementation Steps

1. Read `task-board.json` for all tasks
2. Apply filters sequentially (AND logic — all filters must match)
3. If goals or cycle_time data needed, read corresponding `tasks/T-NNN.json`
4. Sort by specified method
5. Format output (same column format as standard list, with filter summary at bottom)

```
📋 Task Board — Filtered (version: N)
Filter: assignee=implementer, priority=P0 | Sort: age ↑
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ID      Status         Assignee      Priority  Progress    Age     Title
T-001   implementing   Implementer   P0        ██░░░ 2/5   3.2h   User Auth System
T-004   fixing         Implementer   P0        ███░░ 3/5   1.5h   API Error Handling
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Showing 2/7 tasks
```
