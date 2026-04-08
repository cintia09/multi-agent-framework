# Changelog

All notable changes to this project will be documented in this file.

## [3.0.1] - 2026-04-08

### 🐛 Bug Fixes
- **CRITICAL**: Fix missing `accepting→accept_fail` FSM transition in Simple mode validation — previously blocked all acceptance failure flows
- **macOS compatibility**: Replace `grep -P` (GNU-only) with `sed` in agent-post-tool-use.sh — fixes silent failure on macOS
- **Shell injection**: Fix unsanitized `$TASK_ID` in agent-before-task-create.sh — now passed via env var
- **Broken paths**: Fix `scripts/memory-index.sh` references in hooks — now searches `.agents/scripts/` and `scripts/` with fallback
- **3-Phase auto-dispatch**: Add all 15 3-Phase state→agent mappings to post-tool-use dispatch — previously only Simple mode states were dispatched

### 📦 New Features
- **Modular rules** (`rules/`): Leverage Claude Code's native `.claude/rules/` system with path-scoped rules
  - `agent-workflow.md` — Role + FSM rules (scoped to `.agents/**`, `hooks/**`, `skills/**`)
  - `security.md` — Secret scanning rules (scoped to code files)
  - `commit-standards.md` — Conventional commit format
- **Platform compatibility table**: Document Claude Code vs GitHub Copilot support matrix

### 📝 Documentation
- Fix README lifecycle diagram: add missing `accepting → accept_fail → designing` path
- Fix duplicate "Claude Code、Claude Code" → "Claude Code、GitHub Copilot"
- Fix "15+ Hook" → "13 Hook" in skills table and roadmap
- Fix staleness-check event type: SessionStart → PostToolUse (matches hooks.json)
- Update docs/agent-rules.md with 3-Phase workflow rules
- Update install.sh to install modular rules to `~/.claude/rules/`
- Update AGENTS.md: fix chmod for security-scan.sh, fix hook count verification
- Add rules/ directory structure to README file tree

### 🧪 Tests
- Expand test-hooks.sh from 5 to 13 hooks (full v2.0 coverage)

## [3.0.0] - 2026-04-12

### 🚀 Major Release — 3-Phase Engineering Closed Loop

#### Phase 13: 3-Phase Engineering Closed Loop
- **Dual-mode FSM**: Tasks now support `workflow_mode: "simple"` (default, backward compatible) or `"3phase"` (new)
- **18 new FSM states** across 3 phases for the 3-Phase workflow:
  - Phase 1 — Design: requirements → architecture → tdd_design → dfmea → design_review
  - Phase 2 — Implementation: implementing + test_scripting (parallel) → code_reviewing → ci_monitoring/ci_fixing → device_baseline
  - Phase 3 — Testing & Verification: deploying → regression_testing → feature_testing → log_analysis → documentation
- **Orchestrator daemon**: Background shell script that autonomously drives 3-Phase tasks end-to-end
- **Parallel tracks**: Phase 2 runs 3 concurrent tracks (implementer, tester, reviewer) with convergence gate
- **Feedback loops**: Phase 3 → Phase 2 (test failure), Phase 2 → Phase 1 (design gap), with MAX_FEEDBACK_LOOPS=10 safety limit
- **Pluggable external systems**: CI (GitHub Actions/Jenkins/GitLab CI), Code Review (GitHub PR/Gerrit/GitLab MR), Device/Test environment — all configurable via `{PLACEHOLDER}` tokens
- **16 prompt templates**: Step-specific prompts for autonomous agent invocation, generated during project init
- **Convergence gate**: All parallel tracks must complete before device_baseline
- **Feedback safety**: Auto-block tasks that exceed 10 feedback loops
- **New skill**: `agent-orchestrator` (3-Phase daemon management + prompt templates)
- Extended `agent-fsm` with 3-Phase state definitions, transitions, and guard rules
- Extended `agent-hooks` with 3-Phase dispatch logic, convergence validation, feedback counting
- Extended `agent-init` with workflow mode selection and 3-Phase initialization (orchestrator + prompts)
- Extended `agent-teams` with Phase 2 parallel track documentation
- Extended `agent-post-tool-use.sh` with dual-mode FSM validation (simple + 3-phase)
- Extended `task-board.json` schema with `workflow_mode`, `phase`, `step`, `parallel_tracks`, `feedback_loops`, `feedback_history` fields

### 📊 Stats
- Skills: 14 → **15** (+agent-orchestrator)
- FSM States: 10 (simple) + **18** (3-phase)
- Prompt Templates: **16** (generated per project)
- Workflow Modes: **2** (simple + 3-phase)
- Feedback Safety Limit: 10 loops per task

## [2.0.0] - 2026-04-07

### 🚀 Major Release — 5 New Phases

#### Phase 8: Memory 2.0
- Three-layer memory architecture (MEMORY.md long-term + diary/YYYY-MM-DD.md + PROJECT_MEMORY.md shared)
- SQLite FTS5 full-text indexing with unicode61 tokenizer (`scripts/memory-index.sh`)
- Hybrid search CLI with role/layer/limit filters (`scripts/memory-search.sh`)
- Memory lifecycle: 30-day temporal decay, 6-signal auto-promotion scoring
- Compaction-safe memory flush

#### Phase 9: Hook System 2.0
- Expanded from 5 hooks to **13 scripts** across **9 event types**
- New lifecycle hooks: AgentSwitch, TaskCreate, TaskStatusChange, MemoryWrite, Compaction, GoalVerified
- Block/Approval semantics — hooks can return `{"block": true}` to prevent operations
- Priority chains — multiple hooks execute in order, block stops chain
- Per-role tool profiles in `.agents/tool-profiles.json`
- New skill: `agent-hooks` (hook lifecycle management)

#### Phase 10: Scheduling & Automation
- Cron scheduler (`scripts/cron-scheduler.sh`) with `jobs.json` configuration
- Webhook handler (`scripts/webhook-handler.sh`) for GitHub push/PR/CI events
- FSM auto-advance — task completion auto-triggers next agent switch

#### Phase 11: Context Engine
- Token budget allocation per agent role
- Role-aware bootstrap injection (global skill + project skill + task + memory Top-6)
- Intelligent compression preserving key decisions

#### Phase 12: Agent Teams
- Subagent spawn protocol for parallel task execution
- Multi-implementer parallel pattern
- Parallel review coordination
- New skill: `agent-teams` (team orchestration)

### 📊 Stats
- Skills: 12 → **14** (+agent-hooks, +agent-teams)
- Hooks: 5 scripts / 3 events → **13 scripts / 9 events**
- Scripts: 2 → **6** (+memory-index, memory-search, cron-scheduler, webhook-handler)

## [1.0.0] - 2026-04-06

### 🎉 Initial Release

#### Phase 1: Core Framework
- 5 Agent roles: Acceptor, Designer, Implementer, Reviewer, Tester
- FSM state machine with 10 states and guard rules
- Task board with optimistic locking
- Goals-based task tracking (pending → done → verified)
- Agent messaging via inbox.json

#### Phase 2: Enforcement & Auditing
- Shell hooks for agent boundary enforcement
- Pre-tool-use boundary checking
- Post-tool-use audit logging
- SQLite events.db for activity tracking
- Security scan (pre-commit secret detection)

#### Phase 3: Automation
- Auto-dispatch: task state changes trigger downstream agent notification
- Staleness detection: warn on tasks idle > 24 hours
- Batch processing mode: agents process all pending tasks in a loop
- Monitor mode: Tester ↔ Implementer auto fix-verify cycle
- Structured issue tracking (JSON + optimistic locking)

#### Phase 4: Memory & Visualization
- Auto memory capture on FSM stage transitions
- Smart memory loading (role-based field filtering)
- ASCII pipeline visualization in agent status panel
- Project-level living documents (6 docs in docs/)
- Event summary in status panel (24h activity per agent)

#### Phase 5: Best Practices Integration
- Implementer: TDD discipline (RED/GREEN/REFACTOR + git checkpoints + 80% coverage gate)
- Implementer: Build fix workflow (one error at a time)
- Implementer: Pre-review verification (typecheck → build → lint → test → security)
- Reviewer: Severity levels (CRITICAL/HIGH/MEDIUM/LOW) with approval rules
- Reviewer: OWASP Top 10 security checklist
- Reviewer: Code quality thresholds (function >50 lines, file >800 lines, nesting >4)
- Reviewer: Confidence-based filtering (≥80% confidence)
- Reviewer: Design + code review (can route back to designer)
- Tester: Coverage analysis workflow
- Tester: Flaky test detection and quarantine
- Tester: E2E testing with Playwright Page Object Model
- Designer: Architecture Decision Records (ADR)
- Designer: Goal coverage self-check
- Acceptor: User story format for goals
