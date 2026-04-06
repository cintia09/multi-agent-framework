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

## Future
- Automatic task decomposition
- Shared memory bus between sub-agents
- Auto-merge of non-conflicting changes
- Parallel pipeline (different tasks in different FSM states simultaneously)
