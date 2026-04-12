---
name: agent-fsm
description: "FSM Engine: Manages state machines for agents and tasks. Trigger: 'FSM state transition' or 'update task status'."
---

# Agent FSM Engine

## FSM Mode

The framework uses a **unified linear workflow** for all tasks. Each task follows the same state machine:

```
created → designing → implementing → reviewing → testing → accepting → accepted
```

With feedback loops for quality control and a blocked state for manual intervention.

---

## Simple Linear FSM

## Agent State Definitions

Agents have 3 states:
- `idle` — Available, can accept new tasks
- `busy` — Working on a task
- `blocked` — Stuck, requires manual intervention

## Task State Definitions & Transition Rules

Legal task state transitions (from → to):

```
created      → designing                 (designer picks up)
designing    → implementing              (design complete)
implementing → reviewing                 (submit for code review)
reviewing    → implementing              (review rejected)
reviewing    → testing                   (review approved)
testing      → fixing                    (issues found)
testing      → accepting                 (all tests passed)
fixing       → testing                   (fix complete, re-test)
accepting    → accepted                  (acceptance passed ✅)
accepting    → accept_fail               (acceptance failed)
accept_fail  → designing                 (re-enter pipeline)
ANY          → blocked                   (unresolvable issue)
blocked      → [previous_state]          (manual unblock)
designing    → hypothesizing             (fork competing approaches)
implementing → hypothesizing             (fork competing approaches)
hypothesizing → designing                (winner → design)
hypothesizing → implementing             (winner → implement)
```

## Operations

### Read Agent State
```bash
cat <project>/.agents/runtime/<agent>/state.json
```

### Update Agent State
Read → check version → modify → write (version + 1)

state.json format:
```json
{
  "agent": "<agent_name>",
  "status": "idle|busy|blocked",
  "current_task": null,
  "sub_state": null,
  "queue": [],
  "last_activity": "<ISO 8601>",
  "version": 0,
  "error": null
}
```

### Task State Transition
1. Read task-board.json
2. Find target task
3. Validate transition is legal (per rules above)
4. If illegal, **reject with reason** — never execute an invalid transition
5. If legal:
   a. Update task status
   b. Update assigned_to (determine next responsible agent by new status)
   c. Record history entry: `{"from": "old", "to": "new", "by": "agent", "at": "ISO8601", "note": "..."}`
   d. Write to target agent's inbox.json (notification)
   e. Increment task-board.json version
   f. Sync task-board.md

### Status → Agent Mapping
| New Status | Assigned To |
|-----------|-------------|
| created | designer |
| designing | designer |
| implementing | implementer |
| reviewing | reviewer |
| testing | tester |
| fixing | implementer |
| accepting | acceptor |
| accepted | — (completed) |
| accept_fail | designer |
| blocked | — (awaiting manual) |

### Guard Rules
Before executing a transition, check:
1. Current → target state is in the legal transition list
2. Executing agent is the task's current assigned_to
3. task-board.json version matches the read version (optimistic lock)
4. **Goals guard**:
   - `implementing → reviewing`: All goals must have status `done` — reject if any `pending`, prompt implementer about unfinished goals
   - `accepting → accepted`: All goals must have status `verified` — reject if any `pending`/`done`/`failed`, prompt acceptor about unverified goals
5. **Document gate**:
   - Before transition, check required output documents exist in `.agents/docs/T-XXX/`
   - Mode controlled by `task-board.json` top-level `"doc_gate_mode"` field:
     - `"warn"` (default): ⚠️ Warn but allow transition
     - `"strict"`: ⛔ Block transition (`LEGAL=false`), documents must be written first

6. **DFMEA gate (implementing → reviewing)**:
   - Check `.agents/runtime/implementer/workspace/T-NNN-dfmea.md` exists
   - **Content validation**: Failure modes with RPN ≥ 100 must have mitigations (Mitigation column non-empty)
   - Check method: Parse DFMEA markdown table, find rows with RPN ≥ 100, verify last column has content
   - Mode same as document gate (`doc_gate_mode`: warn / strict)
   - Strict mode: Missing DFMEA or unmitigated high-RPN → reject transition
7. **Feedback loop guard**: On feedback transitions, check `feedback_loops < MAX_FEEDBACK_LOOPS`
8. **HITL approval guard** (only when `hitl.enabled == true`):
   - Check task's `hitl_status.status == "approved"`
   - Not approved → reject: "⛔ HITL approval required. Complete manual approval first."
   - Config source: `hitl` block in `.agents/config.json`

If any guard fails, abort transition and report reason.

### Safety Limit: Feedback Loops

**MAX_FEEDBACK_LOOPS = 10** per task.

Feedback transitions (reviewing → implementing, testing → fixing, accept_fail → designing) increment the `feedback_loops` counter:
```json
{
  "id": "T-005",
  "feedback_loops": 3,
  "feedback_history": [
    {"from": "reviewing", "to": "implementing", "at": "2026-04-10T14:00:00Z", "reason": "Security issue found"},
    {"from": "testing", "to": "fixing", "at": "2026-04-10T16:00:00Z", "reason": "2 test failures"},
    {"from": "accept_fail", "to": "designing", "at": "2026-04-11T09:00:00Z", "reason": "Missing requirement"}
  ]
}
```

When `feedback_loops >= MAX_FEEDBACK_LOOPS`:
1. Task automatically transitions to `blocked`
2. Reason: "Feedback loop safety limit reached (10/10). Manual intervention required."
3. Event logged to events.db: `fsm_feedback_limit`
4. Human must review, resolve root cause, reset counter, and unblock

---

## Legacy 3-Phase State Migration

> The 3-Phase Engineering workflow (18 states) has been unified into the linear workflow above.
> Existing tasks with `workflow_mode: "3phase"` or legacy states are automatically mapped:

| Legacy State (3-Phase) | Maps To (Unified) |
|------------------------|-------------------|
| `requirements` | `designing` |
| `architecture` | `designing` |
| `tdd_design` | `designing` |
| `dfmea` | `designing` |
| `design_review` | `reviewing` |
| `test_scripting` | `implementing` |
| `code_reviewing` | `reviewing` |
| `ci_monitoring` | `testing` |
| `ci_fixing` | `fixing` |
| `device_baseline` | `testing` |
| `deploying` | `implementing` |
| `regression_testing` | `testing` |
| `feature_testing` | `testing` |
| `log_analysis` | `testing` |
| `documentation` | `designing` |

When encountering a legacy state:
1. Map to unified state using the table above
2. Update task's `status` to the mapped state
3. Remove `workflow_mode`, `phase`, `step`, `parallel_tracks` fields
4. Preserve `feedback_loops` and `feedback_history` (these are now in unified FSM)
