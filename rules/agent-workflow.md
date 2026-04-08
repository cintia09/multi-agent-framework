---
paths:
  - ".agents/**"
  - "hooks/**"
  - "skills/**"
  - "agents/**"
---

# Agent Collaboration Rules

## Role System
5 Agent roles collaborate through skills:
- `agent-acceptor` — 🎯 Acceptor (requirements, acceptance testing)
- `agent-designer` — 🏗️ Designer (architecture, ADR, TDD design)
- `agent-implementer` — 💻 Implementer (TDD development, build fixes)
- `agent-reviewer` — 🔍 Reviewer (design + code review, OWASP)
- `agent-tester` — 🧪 Tester (coverage, flaky detection, E2E)

## Role Switching
When user invokes an agent-* skill or says "/agent <name>":
1. Read the corresponding agent skill (agent-<name>.md)
2. Execute the startup procedure defined in that skill
3. Act within that role's scope — never exceed authority

## State Management
- All state changes MUST go through `agent-task-board` and `agent-fsm` skills
- Direct editing of task-board.json is forbidden
- Every state change must record history

## Task Flow (Simple Mode)
```
created → designing → implementing → reviewing → testing → accepting → accepted
```
No skipping. Loops: reviewing → implementing, testing → fixing → testing, accepting → accept_fail → designing.

## Task Flow (3-Phase Mode)
- Phase 1: requirements → architecture → tdd_design → dfmea → design_review
- Phase 2: implementing + test_scripting + code_reviewing (parallel) → ci_monitoring → device_baseline
- Phase 3: deploying → regression_testing → feature_testing → log_analysis → documentation → accepted
- Convergence gate: all parallel tracks must complete before device_baseline
- Feedback loops: max 10 per task, auto-block when exceeded
