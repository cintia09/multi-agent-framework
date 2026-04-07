---
name: agent-teams
description: "Multi-agent parallel execution. Spawn sub-agents for parallel tasks."
---

# Agent Teams — Parallel Execution

## Overview
Agent Teams enables multiple agents to work on different tasks simultaneously, leveraging Claude Code's sub-agent capabilities.

## Subagent Spawn Protocol

### When to Use Parallel Execution
- Multiple independent tasks in the same FSM state (e.g., 3 tasks all in "implementing")
- Large task that can be decomposed into independent sub-tasks
- Review of multiple unrelated files

### Spawn Pattern
```
Main Agent (Coordinator)
├── Sub-Agent 1: T-024 (implementing)
├── Sub-Agent 2: T-025 (implementing)
└── Sub-Agent 3: T-026 (implementing)
```

### Spawn Protocol
1. Coordinator identifies parallelizable tasks
2. For each task, spawn a sub-agent with:
   - Task ID and goals
   - Relevant memory (Top-6 search results)
   - Project context
   - Role-specific SKILL.md
3. Sub-agents work independently
4. On completion, sub-agent writes results to:
   - `.agents/runtime/{role}/workspace/` (artifacts)
   - `.agents/memory/{role}/diary/YYYY-MM-DD.md` (observations)
5. Coordinator collects results and advances pipeline

### Multi-Implementer Pattern
```
Coordinator (Implementer)
├── Task Agent: "Implement T-024 memory indexing"
│   └── Works on: scripts/memory-index.sh, skills/agent-memory/SKILL.md
├── Task Agent: "Implement T-025 search"
│   └── Works on: scripts/memory-search.sh
└── Task Agent: "Implement T-026 lifecycle"
    └── Works on: skills/agent-memory/SKILL.md (different section)
```

**Conflict Prevention:**
- Each sub-agent works on different files (coordinator assigns)
- If files overlap, use sequential execution for those tasks
- Sub-agents MUST NOT modify task-board.json (coordinator only)

### Parallel Review Pattern
```
Coordinator (Reviewer)
├── Review Agent: "Review T-024 memory changes"
│   └── Reads: skills/agent-memory/SKILL.md, scripts/memory-*.sh
├── Review Agent: "Review T-025 hook changes"
│   └── Reads: hooks/*.sh, hooks/hooks.json
└── Review Agent: "Review T-026 scheduling"
    └── Reads: scripts/cron-scheduler.sh, .agents/jobs.json
```

### Constraints
- Max parallel agents: 5 (one per role, or multiple same-role)
- Sub-agents inherit project context but NOT conversation history
- Sub-agents cannot switch roles (fixed to spawned role)
- Coordinator must validate all sub-agent outputs before committing

### Integration with FSM
- Parallel execution only within a single FSM state
- All sub-agents must complete before state transition
- If any sub-agent fails, coordinator decides: retry, fix, or escalate

## Limitations (Current)
- Requires Claude Code Agent Teams feature
- Sub-agent context is isolated (no shared memory during execution)
- Results are merged manually by coordinator
- Not yet integrated with cron scheduler

## 3-Phase Parallel Tracks

In the 3-Phase Engineering Closed Loop workflow, Phase 2 (Implementation) uses a structured parallel execution model managed by the orchestrator daemon.

### Track Layout

```
design_review (PASS)
    │
    ├─── Track A: implementing      (implementer)  — feature coding
    ├─── Track B: test_scripting    (tester)       — test automation
    └─── Track C: code_reviewing    (reviewer)     — continuous review
                │
                ▼
         ┌─────────────────┐
         │ Convergence Gate │  ← all 3 tracks + CI must be complete
         └─────────────────┘
                │
                ▼
         ci_monitoring → ci_fixing (loop) → device_baseline
```

### Track Responsibilities

| Track | Agent | Input | Output | Completion Signal |
|-------|-------|-------|--------|-------------------|
| **A** | implementer | design doc, TDD plan | source code, unit tests | All goals marked `done` |
| **B** | tester | test spec, TDD plan | test scripts, fixtures | Test suite runnable |
| **C** | reviewer | code from A + B | review report | Review PASS (no CRITICAL) |

### Convergence Gate at `device_baseline`

The FSM will **not** allow transition to `device_baseline` unless all parallel tracks report complete. This is enforced by:

1. **task-board.json** — each task has a `parallel_tracks` object:
   ```json
   {
     "parallel_tracks": {
       "implementing": "complete",
       "test_scripting": "complete",
       "code_reviewing": "complete",
       "ci_monitoring": "green"
     }
   }
   ```
2. **Hook validation** — `agent-post-tool-use.sh` checks the convergence gate before allowing `ci_monitoring → device_baseline`
3. **Orchestrator** — the daemon polls track status and only advances when all conditions are met

### Orchestrator-Managed Parallel Spawning

The orchestrator daemon handles the complexity of parallel agent invocation:

1. **Launch Phase**: On entering `implementing` state, the orchestrator:
   - Spawns Track A (implementer) as a background agent
   - Spawns Track B (tester) as a background agent
   - Waits for initial artifacts (configurable delay), then spawns Track C (reviewer)

2. **Monitoring Phase**: The orchestrator:
   - Polls `.agents/task-board.json` for track completion signals
   - Monitors agent logs in `.agents/orchestrator/logs/`
   - Handles early failures (if Track A fails, Track B/C may be suspended)

3. **Convergence Phase**: When all tracks complete:
   - Updates `parallel_tracks` status
   - Triggers CI pipeline (`{CI_TRIGGER_CMD}`)
   - Advances to `ci_monitoring`

### Conflict Prevention in 3-Phase Parallel

The same conflict prevention rules from simple parallel execution apply, with additional constraints:
- Track A (implementer) owns source code files
- Track B (tester) owns test files and fixtures
- Track C (reviewer) is read-only (produces review reports only)
- The orchestrator assigns file boundaries at launch
- task-board.json modifications are orchestrator-only during Phase 2 parallel

## Future
- Automatic task decomposition
- Shared memory bus between sub-agents
- Auto-merge of non-conflicting changes
- Parallel pipeline (different tasks in different FSM states simultaneously)
