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

---

## Team Session — tmux Split-Pane Mode

### Overview
Launch a multi-agent team session where each agent gets its own tmux pane. Agents share the task-board and communicate via inbox messages in real-time.

### Launch
```bash
bash scripts/team-session.sh [--agents <roles>] [--task <T-XXX>] [--layout <tiled|even-horizontal>]
```

### Examples
```bash
# Launch all 5 agents
bash scripts/team-session.sh

# Launch specific agents for a task
bash scripts/team-session.sh --agents implementer,tester,reviewer --task T-042

# Horizontal layout
bash scripts/team-session.sh --layout even-horizontal
```

### Architecture
```
┌──────────────────────────────────────────────┐
│  tmux session: agent-team                     │
├──────────────┬──────────────┬────────────────┤
│  acceptor    │  designer    │  implementer   │
│  (pane 0)    │  (pane 1)    │  (pane 2)      │
├──────────────┴──────┬───────┴────────────────┤
│  reviewer           │  tester                │
│  (pane 3)           │  (pane 4)              │
├─────────────────────┴────────────────────────┤
│  📊 Dashboard (pane 5) — auto-refresh 10s    │
└──────────────────────────────────────────────┘
```

### Dashboard Pane
The bottom pane runs `watch -n10 bash scripts/team-dashboard.sh` showing:
- Active agents and their current tasks
- Inbox message counts per agent
- Recent FSM transitions
- Pipeline progress bar

### Shared Resources
- **task-board.json**: Atomic access via mkdir-based locks
- **events.db**: SQLite WAL mode for concurrent writes
- **inbox.json**: Per-agent, locked during write

### Session Management
| Command | Action |
|---------|--------|
| `tmux attach -t agent-team` | Reconnect to team session |
| `tmux kill-session -t agent-team` | Terminate all agents |
| Ctrl+B then arrow key | Navigate between panes |
| Ctrl+B then z | Zoom into a pane (toggle) |

---

## Competitive Hypothesis Pattern

### Overview
When facing a design or implementation challenge with multiple valid approaches, fork the task into N parallel hypotheses. Each hypothesis is explored independently, then evaluated and the best one is promoted.

### When to Use
- Architecture decisions with trade-offs (e.g., monolith vs microservice)
- Algorithm choices (e.g., BFS vs DFS for graph traversal)
- Debugging with multiple suspected root causes
- Performance optimization with competing strategies

### Hypothesis Lifecycle

```
task (designing/implementing)
    │
    ▼ fork_hypothesis
┌─────────────────────┐
│  hypothesizing       │ ← new FSM state
├──────┬──────┬───────┤
│ H-1  │ H-2  │ H-3   │ ← parallel exploration
│ BFS  │ DFS  │ A*    │
└──────┴──────┴───────┘
    │
    ▼ evaluate_hypotheses
┌─────────────────────┐
│  Winner: H-3 (A*)    │
│  Reason: best perf   │
└─────────────────────┘
    │
    ▼ promote_hypothesis
task continues (designing/implementing)
```

### Storage
```
.agents/hypotheses/T-XXX/
├── manifest.json          # Hypothesis metadata
├── H-1/
│   ├── approach.md        # Description of approach
│   ├── workspace/         # Working files
│   └── evaluation.json    # Metrics and assessment
├── H-2/
│   ├── approach.md
│   ├── workspace/
│   └── evaluation.json
└── H-3/
    ├── approach.md
    ├── workspace/
    └── evaluation.json
```

### manifest.json Schema
```json
{
  "task_id": "T-042",
  "created_at": "2026-04-09T10:00:00Z",
  "created_by": "designer",
  "challenge": "Choose optimal search algorithm for memory indexing",
  "evaluation_criteria": [
    {"name": "performance", "weight": 0.4},
    {"name": "memory_usage", "weight": 0.3},
    {"name": "code_complexity", "weight": 0.3}
  ],
  "hypotheses": [
    {
      "id": "H-1",
      "title": "BFS with memoization",
      "status": "exploring | evaluated | promoted | rejected",
      "agent": "implementer",
      "scores": {}
    }
  ],
  "winner": null,
  "promoted_at": null
}
```

### Workflow

#### 1. Fork Hypotheses
```
User/Agent: "Explore 3 approaches for T-042 search algorithm"
→ Creates .agents/hypotheses/T-042/manifest.json
→ Creates H-1/, H-2/, H-3/ directories
→ Each hypothesis gets an approach.md describing the strategy
```

#### 2. Parallel Exploration
Each hypothesis can be explored by:
- **Same agent sequentially** — one agent tries each approach
- **Multiple agents in parallel** — via tmux team session
- **Sub-agents** — coordinator spawns per-hypothesis sub-agents

#### 3. Evaluate
```json
// H-1/evaluation.json
{
  "hypothesis_id": "H-1",
  "scores": {
    "performance": 7,
    "memory_usage": 8,
    "code_complexity": 9
  },
  "weighted_score": 7.9,
  "notes": "Simple but O(n²) for large graphs",
  "evaluator": "reviewer"
}
```

#### 4. Promote Winner
- Copy winning hypothesis workspace to main project
- Update manifest.json with winner
- Log to events.db: `hypothesis_promoted`
- Continue task in original FSM state

### Integration with FSM
New transitions for `hypothesizing` state:
```
designing     → hypothesizing    (fork to explore approaches)
implementing  → hypothesizing    (fork to explore implementations)
hypothesizing → designing        (winner promoted, back to design)
hypothesizing → implementing     (winner promoted, back to implementation)
```
