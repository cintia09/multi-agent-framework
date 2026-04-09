---
name: agent-hypothesis
description: "Competitive hypothesis exploration. Fork a task into parallel approaches, evaluate, and promote winner."
---

# Agent Hypothesis — Competitive Exploration

## Overview
When a task has multiple valid approaches, fork into parallel hypotheses. Each is explored independently, then evaluated and the best one promoted.

## When to Use
- Architecture decisions with trade-offs
- Algorithm choices (performance vs simplicity)
- Debugging with multiple suspected root causes
- Design alternatives needing prototyping

## Commands

| Command | Action |
|---------|--------|
| `/hypothesis fork T-XXX` | Fork task into hypotheses |
| `/hypothesis list T-XXX` | List hypotheses for a task |
| `/hypothesis eval T-XXX` | Evaluate and score hypotheses |
| `/hypothesis promote T-XXX H-N` | Promote winning hypothesis |
| `/hypothesis cancel T-XXX` | Cancel hypothesis exploration |

## Workflow

### 1. Fork — Create Hypotheses

```
User: "Explore 3 approaches for T-042 search algorithm"
```

**Steps:**
1. Create `.agents/hypotheses/T-042/` directory
2. Create `manifest.json` with challenge description and evaluation criteria
3. Create `H-1/`, `H-2/`, `H-3/` subdirectories
4. Write `approach.md` in each with strategy description
5. Update task status to `hypothesizing` in task-board.json
6. Log `hypothesis_forked` event to events.db

**manifest.json:**
```json
{
  "task_id": "T-042",
  "created_at": "2026-04-09T10:00:00Z",
  "created_by": "designer",
  "previous_status": "designing",
  "challenge": "Choose optimal search algorithm for memory indexing",
  "evaluation_criteria": [
    {"name": "performance", "weight": 0.4, "description": "Execution time on 1000+ entries"},
    {"name": "memory_usage", "weight": 0.3, "description": "Peak memory consumption"},
    {"name": "code_complexity", "weight": 0.3, "description": "Lines of code, cyclomatic complexity"}
  ],
  "hypotheses": [
    {"id": "H-1", "title": "BFS with memoization", "status": "exploring", "agent": "implementer"},
    {"id": "H-2", "title": "DFS with pruning", "status": "exploring", "agent": "implementer"},
    {"id": "H-3", "title": "A* with heuristic", "status": "exploring", "agent": "implementer"}
  ],
  "winner": null,
  "promoted_at": null
}
```

**approach.md Template:**
```markdown
# Hypothesis H-1: BFS with Memoization

## Strategy
Use breadth-first search with a hash map cache for visited nodes.

## Expected Pros
- Simple implementation
- Guaranteed shortest path

## Expected Cons
- High memory usage for large graphs
- O(V+E) time complexity

## Implementation Plan
1. Create BFS traversal function
2. Add memoization layer
3. Benchmark against test dataset

## Files to Create/Modify
- `scripts/memory-search-bfs.sh`
- `tests/test-search-bfs.sh`
```

### 2. Explore — Parallel Investigation

Each hypothesis can be explored by:

| Mode | Description | When to Use |
|------|-------------|-------------|
| **Sequential** | Same agent tries each approach one by one | Simple tasks, 2 hypotheses |
| **Parallel tmux** | Team session with one agent per hypothesis | Complex tasks, need real implementation |
| **Sub-agents** | Coordinator spawns per-hypothesis sub-agents | Available in Claude Code / Copilot CLI |

Each hypothesis workspace is isolated:
```
.agents/hypotheses/T-042/H-1/
├── approach.md           # Strategy document
├── workspace/            # Working files (code, configs)
│   ├── memory-search.sh
│   └── benchmark.log
└── evaluation.json       # Filled after evaluation
```

### 3. Evaluate — Score and Compare

Run evaluation against defined criteria:

```json
// H-1/evaluation.json
{
  "hypothesis_id": "H-1",
  "evaluated_at": "2026-04-09T14:00:00Z",
  "evaluator": "reviewer",
  "scores": {
    "performance": {"value": 7, "max": 10, "notes": "120ms for 1000 entries"},
    "memory_usage": {"value": 8, "max": 10, "notes": "45MB peak"},
    "code_complexity": {"value": 9, "max": 10, "notes": "42 lines, CC=3"}
  },
  "weighted_score": 7.9,
  "recommendation": "Good baseline but O(n²) for large datasets",
  "verdict": "viable"
}
```

**Comparison Output:**
```
🔬 Hypothesis Evaluation — T-042: Search Algorithm
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  H-1: BFS with memoization       Score: 7.9  ⭐⭐⭐
  H-2: DFS with pruning           Score: 7.2  ⭐⭐⭐
  H-3: A* with heuristic          Score: 9.1  ⭐⭐⭐⭐⭐  ← WINNER
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Recommendation: Promote H-3 (A* with heuristic)
  Reason: Best performance (9/10) with acceptable complexity
```

### 4. Promote — Apply Winner

1. Copy `H-3/workspace/` contents to project source tree
2. Update manifest.json: `winner: "H-3"`, `promoted_at: "..."`
3. Update task status from `hypothesizing` back to `previous_status` (designing/implementing)
4. Log `hypothesis_promoted` event with scores
5. Archive non-winning hypotheses (keep for reference, mark as `rejected`)
6. Send broadcast message: "T-042 hypothesis resolved: A* approach promoted"

## FSM Integration

### New State: `hypothesizing`

**Transitions:**
```
designing     → hypothesizing    (fork to explore design approaches)
implementing  → hypothesizing    (fork to explore implementation approaches)
hypothesizing → designing        (winner promoted, design continues)
hypothesizing → implementing     (winner promoted, implementation continues)
```

### FSM Validation Rules
- Only `designer` or `implementer` can fork hypotheses
- `hypothesizing` cannot transition directly to `reviewing` or `testing`
- Return transition goes to `previous_status` stored in manifest.json
- Hypothesis forking counts as a feedback loop iteration

## Events
| Event | Description |
|-------|-------------|
| `hypothesis_forked` | Task forked into N hypotheses |
| `hypothesis_evaluated` | Hypothesis scores computed |
| `hypothesis_promoted` | Winning hypothesis applied |
| `hypothesis_cancelled` | Exploration cancelled |

## Best Practices
1. **Limit hypotheses to 2-4** — more than 4 rarely adds value
2. **Define criteria FIRST** — before exploring, agree on what "better" means
3. **Time-box exploration** — set a deadline to prevent infinite exploration
4. **Keep workspace minimal** — hypothesis workspaces should contain only the delta
5. **Document trade-offs** — even losing hypotheses contain valuable insights
