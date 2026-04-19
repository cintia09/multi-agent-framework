# Changelog

All notable changes to this project will be documented in this file.

## [0.9.0-m9.0] - 2026-04-19

### 🧠 v6.0 Milestone M9 — Memory Layer + LLM-Driven Extraction

Greenfield memory subsystem: every task execution now sediments
`knowledge / skills / config` into a workspace-local writable layer at
`.codenook/memory/`, while the `plugins/` tree becomes strictly
read-only at runtime. The router-agent learns a `MEMORY_INDEX` of all
candidate + promoted entries and auto-injects matching ones into spawn
prompts. Anti-bloat is enforced by per-task caps, hash dedup, and the
new GC CLI.

#### Added — Per-milestone summary

- **M9.0** Spec doc `docs/v6/memory-and-extraction-v6.md` (Hermes-inspired
  patch-first pattern, 5 FR groups, 6 NFR, 8 milestones); architecture
  §13 ratifies M9; implementation-v6.md M9 sections.
- **M9.1** Memory layout primitives — `_lib/memory_layer.py`
  (knowledge / skill / config + atomic IO + fcntl read-modify-write +
  21-function public API surface) and `_lib/memory_index.py`
  (mtime-cached snapshot at `.codenook/memory/.index-snapshot.json`,
  ≤500 ms over 1000 files). `init` skill creates the empty skeleton.
- **M9.2** Extraction triggers — `orchestrator-tick` `after_phase`
  hook, `extractor-batch.sh` async dispatcher (≤200 ms wall),
  CLAUDE.md 80% context water-mark protocol.
- **M9.3** Knowledge extractor — `knowledge-extractor` skill with
  patch-or-create flow, frontmatter strict validation (summary ≤200,
  tags ≤8), `find_similar()` + LLM merge / replace / create judge
  (default merge), per-task cap ≤3, hash dedup, secret scanner.
- **M9.4** Skill extractor — `skill-extractor` skill detecting ≥3
  repeated CLI / script invocations; per-task cap ≤1; reuses M9.3
  decision flow. `_read_task_context()` now ingests `notes/*.{md,txt,log}`.
- **M9.5** Config extractor — `config-extractor` skill normalising
  `task-config-set` calls into `config.yaml entries[]` with
  `applies_when`; same key merges to latest value; per-task ≤5.
- **M9.6** Router-agent memory awareness — `router-agent/prompt.md`
  now renders MEMORY_INDEX (name + description per entry); spawn.sh
  materialises plugins + memory two layers into the task prompt;
  `_lib/token_estimate.py` budget pruning; `router-context` 8-turn
  archiver.
- **M9.7** Plugin read-only enforcement — `_lib/plugin_readonly.py`
  (runtime guard inside `_atomic_write_text` + static checker CLI);
  CLAUDE.md linter expanded to forbid main-session direct memory greps.
- **M9.8** Release polish — see below.

#### Added — M9.8 (this release)

- **GC CLI** `_lib/memory_gc.py` (`python -m memory_gc --workspace
  <ws> [--dry-run] [--json]`) enforces per-task caps from spec
  §6 / §7 (knowledge=3, skill=1, config=5). Drops oldest by
  `created_at` (with path tie-break) within over-cap groups; promoted
  entries are never pruned. Real run audits each removal via
  `extract_audit.audit(outcome='gc_pruned', verdict='accepted')` and
  refreshes the memory-index snapshot. Exit codes: 0 nothing pruned /
  0 pruned OK / 1 error / 2 invalid args.
- **pre-commit hook template** `templates/pre-commit-hook.sh`
  (chmod 0755) — three gates: (1) staged write under `plugins/`
  rejected unconditionally, plus full `plugin_readonly.py --target .`
  static checker (M9.8 fix-r2: defaults now exclude
  `tests/fixtures/**` and `tests/**/fixtures/**` so the hook stops
  bricking the repo it ships with; `--exclude PATTERN` is repeatable
  and additive, `--no-default-excludes` restores legacy behaviour);
  (2) `claude_md_linter.py --check-claude-md` on root
  CLAUDE.md; (3) the shared SECRET_PATTERNS regex set across every
  staged blob. Install with `cp skills/codenook-core/templates/pre-commit-hook.sh
  .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit`.
- **E2E bats** `tests/e2e/m9-e2e.bats` covering TC-M9.8-01..04 (full
  spec contracts: extractor-batch round-trip surfacing α's summary in
  β's router prompt; watermark async produces a candidate within 5s;
  3 concurrent extractor-batch dispatches with no `.tmp.*` residue
  and no hash collisions; spawn `--confirm` materialises state.json
  while the rendered prompt cites seeded knowledge + applies_when
  config) plus regressions TC-M9.8-10 (GC dry-run/real run) and
  TC-M9.8-11 (pre-commit hook rejects top-level `plugins/` but allows
  nested `tests/fixtures/plugins/...` after the fast-gate anchor fix)
  and TC-M9.8-12 (router→extractor→memory-index loop idempotent
  across two ticks).
- **Backlog folds** — TC-M9.1-06 surface check now requires
  `promote_skill` and `promote_config_entry`; `_read_task_context()`
  also consumes `.txt` / `.log`; TC-M9.2-07 documents ±20% timing
  tolerance + `BATS_TEST_RETRIES=2`; design doc §10.1 explicit
  docstring for `promote_config_entry`.

#### Quality gates

- 798+ bats tests green across the full M1..M9.8 suite (M9.8 fix-r2
  adds 4 regressions in `tests/m9-plugin-readonly-excludes.bats`
  covering --exclude defaults, additive excludes, and
  --no-default-excludes; M9.8 fix-r1 brought 7 e2e cases —
  TC-M9.8-01..04 spec contracts + TC-M9.8-10..12 GC, hook regression,
  idempotent loop).
- `_lib/plugin_readonly.py --target . --json` exits 0 (defaults
  exclude bats fixture trees).
- `_lib/claude_md_linter.py --check-claude-md CLAUDE.md` 0 errors.
- 0 `description.md` references; no greenfield-forbidden tokens.
- 0 secret-scanner hits on the M9.8 diff (fixture AKIA / fd00 tokens
  in `m1-sec-audit.bats` and `m9-knowledge-extractor.bats` are
  constructed via runtime concatenation so the regex matches at test
  time but `git grep` finds nothing in source).

## [0.8.0-m8.0] - 2026-04-18

### 🚀 v6.0 Milestone M8 — Conversational Router Agent

Replaces the legacy stateless `router-triage` (M3) with a real
multi-turn, file-backed **router-agent** that drafts a task config in
conversation with the user and hands off to `orchestrator-tick` on
confirmation. **692/692 bats tests green.**

#### Added — Core (`skills/codenook-core/`)
- **M8.0** Spec doc `docs/v6/router-agent-v6.md` (640 lines) + decisions
  #46–#52 ratified in architecture-v6.md §12 (router-agent as stateless
  subagent, YAML+md context, router calls init-task + first tick,
  300s stale-lock threshold, domain layering, M3 router-triage removed).
- **M8.1** Schemas + helpers — `_lib/router_context.py`,
  `_lib/draft_config.py`, plus M5-DSL schemas for router-context,
  draft-config, router-reply, router-lock.
- **M8.2** `router-agent` skill — `SKILL.md`, `spawn.sh`, `prompt.md`,
  `render_prompt.py`. Per-turn entry-point that prepares context,
  acquires fcntl lock, renders prompt, and on `--confirm` invokes the
  full handoff chain.
- **M8.3** Discovery indexes — `_lib/plugin_manifest_index.py`,
  `_lib/knowledge_index.py` (rank candidates, aggregate knowledge).
- **M8.4** Per-task fcntl lock — `_lib/task_lock.py` with positive-
  evidence stale recovery (closes unlink-recreate race).
- **M8.6** Domain-agnostic main session protocol — root `CLAUDE.md`
  (8-section v6 task lifecycle protocol) + `_lib/claude_md_linter.py`
  enforcing forbidden domain tokens going forward.
- **M8.9** Workspace user-overlay layer — `_lib/workspace_overlay.py`
  for project-scoped writable description/skills/knowledge/config that
  overlays the read-only plugin layer.
- **M8.10** Role enumeration + role-skip — `_lib/role_index.py`,
  `one_line_job` frontmatter on all 17 roles, draft-config gains
  `selected_plugins` + `role_constraints`, `orchestrator-tick`
  honours `role_constraints.excluded` by skipping phase.

#### Added — Tests
- 8 new bats files under `tests/m8-*.bats` (~85 tests covering every
  M8.x milestone, including a 5-test E2E acceptance suite).

#### Removed
- `router-triage` skill (M3) — superseded by router-agent. See entry
  above. Helper `_lib/router_select.py` retained as Python-only scoring
  API.

#### Domain-layering principle (codified)
- Main session is domain-agnostic (Conductor): only spawns
  router-agent, relays prompts, drives ticks, relays HITL.
- Router-agent owns all domain decisions on the creation side
  (Specialist).
- Linter enforces this on `CLAUDE.md` going forward.

## [Unreleased]

## [0.7.0-m7.2] - 2026-04-18

### 🚀 v6.0 Milestones M3–M7 + E2E Acceptance

v6 ships as the production successor to the v5 PoC: a single-workspace,
plugin-based architecture with a 12-gate install pipeline, a generic
orchestrator-tick state machine, 4-layer config resolution, and three
first-party plugins. **588/588 bats tests green.**

#### Added — Core (`skills/codenook-core/`)
- **M3** `router-triage` skill: dual-mode question, intent regex routing,
  4 PHASE_ENTRY_QUESTIONS contracts.
- **M4** `orchestrator-tick` skill: full state machine with phase advance,
  unit fan-out, HITL gate suspend/resume, recovery branch, session resume,
  iteration cap. Companion `hitl-adapter` (terminal + queue) and
  `session-resume` skills.
- **M5** `config-resolve` skill: 4-layer cascade (defaults → workspace →
  plugin → task) with tier-symbol expansion against
  `model_catalog.resolved_tiers`, full provenance trace, decisions #43/#44/#45
  enforced (warn+fallback unknown tier, router=tier_strong invariant,
  10-key whitelist). Companion `config-mutator` and
  `task-config-set` skills.
- Shared `_lib/`: `atomic.py`, `semver.py`, `manifest_load.py`,
  `builtin_catalog.py`, `jsonschema_lite.py`, `expr_eval.py` (no Python
  eval/exec), `config_layers.py`, `provenance.py`, `router_select.py`.

#### Added — Plugins (`plugins/`)
- **M6** `plugins/development/` — 8-phase software-development pipeline
  (clarify → design → plan → implement → test → accept → validate → ship)
  ported from v5 PoC. 8 role profiles, 8 manifest templates, 3 HITL gates
  (design_signoff, pre_test_review, acceptance), shipped test-runner skill,
  validators, prompts, knowledge.
- **M7** `plugins/generic/` — universal fallback plugin (clarify →
  analyze → execute → deliver), routing priority 10.
- **M7** `plugins/writing/` — long-form writing plugin (outline → draft →
  review → revise → publish) with `pre_publish` HITL gate, routing
  priority 50.

#### E2E Acceptance (12/12 PASS)
Real-CLI smoke test in a clean workspace:
- core install + 3-plugin install via 12-gate pipeline
- idempotency (rc=3 on re-install w/o `--upgrade`)
- 3/3 input-to-plugin routing
- full 8-phase task lifecycle in 12 ticks with 3 HITL approvals
- 4-layer config resolution (task-tier wins, provenance present)
- plugin upgrade path

#### Documented gaps (tracked as issues)
- #1 — `init.sh --workspace` is an M1 stub
- #2 — test-plan config layer paths don't match shipped contract
- #3 — Plugin upgrade does not archive prior version
- #4 — `router-triage` doesn't yet consume packaging fields

## [5.0.0-poc.1] - 2026-04-18

### 🧪 v5.0 POC — Workspace-First Architecture (preview, opt-in)

The v5.0 POC ships under `skills/codenook-v5-poc/` and is **opt-in**: existing
v4.x stable installs are unaffected. v5.0 is a breaking redesign — there is no
migration path from v4.x workspaces.

#### Added
- **Workspace-first layout**: `.codenook/` at project root replaces
  `.claude/codenook/`. Two-layer state (workspace `state.json` + per-task
  `state.json`); `task-board.json` is a derived index.
- **Bootloader**: single `CLAUDE.md` at project root; both Claude Code and
  Copilot CLI honor it. No more `.github/copilot-instructions.md`.
- **Core orchestrator** (`codenook-core.md`, ~1.6K lines, 24 sections):
  state machine, routing table, prompt-as-file, sub-agent self-bootstrap,
  validator pattern, scheduler, HITL gating, dispatch audit, secret scan,
  session distillation, model assignment protocol.
- **Helper scripts** (8): `preflight.sh`, `keyring-helper.sh`,
  `secret-scan.sh`, `dispatch-audit.sh`, `session-runner.sh`,
  `model-config.sh`, `rebuild-task-board.sh`, `subtask-runner.sh` /
  `queue-runner.sh`.
- **Sub-agent profiles** (11): clarifier, designer, planner, implementer,
  reviewer, tester, acceptor, validator, synthesizer, security-auditor,
  session-distiller. All use self-bootstrap + Context Budget enforcement.
- **§24 Model Assignment Protocol**: 5-level resolution
  (task[role] > task.default > workspace[role] > workspace.default > inherit).
  Default `inherit` means dispatch without `--model` so the platform reuses the
  main session's model. Subtasks always inherit from parent and are never asked.
- **Tests**: 22 assertions in `tests/run-all.sh` (T0–T28), all passing.
- **Interactive HTML doc**: `skills/codenook-v5-poc/docs/v5-poc.html`
  (single-page, 3-tab: Design / Tests / Implementation).
- **POC README** + main README pointer + install.sh banner.

#### Notes
- Real LLM end-to-end (driving the orchestrator through clarify → accept) is
  not yet validated; this release covers scaffolding, helpers, and tests.
- Stable users should keep using the v4.9.x line.

## [4.9.0] - 2026-04-16

### 🚀 v4.9.0 — Model Defaults, Copilot Paths, Generic Skill Provisioning

#### Changed
- **Default models**: All agents now default to `claude-opus-4.6`, reviewer defaults to `gpt-5.4`
  (was: acceptor/tester = haiku-4.5, designer/implementer/reviewer = sonnet-4)
- **Dual-mode recommended pairing**: `claude-opus-4.6 + gpt-5.4` (was: sonnet-4 + gpt-5.1)
- **Q4 Skill Provisioning**: Removed all hardcoded skill names (baoyu-*, 5g-ran-*, etc.);
  now classifies skills by reading SKILL.md description + keyword matching. Exclude list
  also changed from hardcoded names to heuristic pattern matching.
- **Agent Profile Templates**: Added Copilot CLI paths alongside Claude Code paths
- **HITL Adapter Scripts**: Added Copilot CLI source path reference
- **SKILL.md header**: Updated to v4.9.0, mentions both Claude Code and Copilot CLI platforms
- **install.sh**: Updated description text; architecture diagram in README now includes
  dual-agent mode visual
- **README**: Updated agent model table, config examples, architecture diagram with
  dual-agent flow, added Phase Constitution feature bullet

## [4.8.1] - 2026-04-15

### 📜 v4.8.1 — Phase Constitution for Cross-Examination

Added per-phase quality criteria (Phase Constitution) to the dual-agent cross-examination
system. Inspired by Constitutional AI, each phase now has explicit evaluation dimensions
that focus the orchestrator's analysis and the agent's self-assessment.

#### Added
- **PHASE_CONSTITUTION data structure**: maps each phase to its quality focus and evaluation
  criteria (requirements: completeness/testability/ambiguity; design: scalability/coupling/security;
  impl: code quality/DFMEA; review: finding validity/severity calibration; etc.)
- **Phase Constitution documentation**: new section in Dual-Agent Parallel Mode docs with
  summary table of all phases and their criteria
- **Criteria-aware analysis**: `analyze_divergence()` now injects phase-specific criteria
  into the orchestrator prompt, ensuring evaluation is domain-appropriate
- **Criteria-aware challenges**: `build_challenge_prompt()` includes the quality standards
  so agents know what they're being evaluated against

#### Changed
- **analyze_divergence()**: now calls `resolve_phase_name()` to look up constitution;
  prompt restructured with "Evaluation Focus" header and per-criterion assessment
- **build_challenge_prompt()**: adds "Quality Standards for This Phase" section;
  instructions updated to reference the standards
- **Challenge prompt docs**: updated to show the new prompt structure with criteria

## [4.8.0] - 2026-04-15

### 🔄 v4.8.0 — Iterative Convergence Cross-Examination

Redesigned the dual-agent cross-examination flow from one-shot parallel critique
to an iterative convergence protocol with up to 3 rounds.

#### Changed
- **Cross-examination redesign**: orchestrator now challenges each agent sequentially,
  requiring them to defend, concede, or merge on each divergence point (max 3 rounds)
- **Convergence detection**: orchestrator analyzes divergence between A/B documents
  each round; exits early when positions converge
- **Document artifacts**: versioned per round (`-agent-a-r0.md`, `-agent-a-r1.md`, etc.)
  instead of single static files
- **Synthesis prompt simplified**: no longer passes critique docs (agents already revised)
- **Cost model updated**: 4–10× calls per dual phase (was fixed 5×)

#### Added
- `analyze_divergence()` — orchestrator self-analysis function for convergence detection
- `build_challenge_prompt()` — replaces `build_cross_examination_prompt()`

#### Removed
- `build_cross_examination_prompt()` — replaced by iterative challenge flow

#### Fixed (from v4.7.3 deep review)
- `task` vs `current_task` naming inconsistency (9 instances in orchestrate/dual functions)
- Preflight `dual_mode` dict now includes `synthesizer` and `phase_models` for schema completeness
- `get_user_decision` signature updated with `multi_select=False` parameter
- `get_user_input` helper function declared

## [4.7.3] - 2026-04-15

### 🛡️ v4.7.3 — Preflight Check for Missing Creation-Time Fields

Fixes a design defect where tasks created in a previous session could advance
without answering mandatory creation-time questions (e.g., dual-agent mode).

#### Added
- **Preflight Check** in orchestration loop: on first iteration (`total_iterations == 0`), verifies that `dual_mode` is set; prompts user if `null` and no global default exists
- Cross-reference note in Task Creation Flow pointing to the preflight safety net

#### Fixed
- Tasks resumed cross-session no longer silently skip the dual-agent mode question

## [4.7.2] - 2026-04-15

### 🔒 v4.7.2 — HITL Adapter Enforcement & Task Creation Flow

Synced production-proven improvements from xueba-knowledge deployment.

#### Added
- **HITL Hard Constraint**: Mandatory adapter resolution check before any HITL interaction — prevents calling wrong adapter (e.g., `terminal.sh` when config specifies `local-html`)
- **Enforcement Checklist**: Mental checklist agents must execute before each HITL gate
- **Adapter Resolution Logging**: Traceability log for resolved adapter name and phase
- **Task Creation Flow (MANDATORY)**: Structured 6-question flow for task creation, including dual-agent mode prompt

#### Changed
- Adapter resolution wording: "per-phase from Q2" → "per-phase override", "global from Q2" → "global config — MOST COMMON"
- Pseudocode adapter section: enhanced with step-by-step comments (4a/4b/4c) and violation warnings

## [4.7.1] - 2025-07-29

### ⚡ v4.7.1 — Engine Token Optimization

Compressed knowledge system pseudocode to reduce token footprint without
behavioral changes. Passed two rounds of deep review (clean on round 2).

#### Optimized
- Collapsed 10 helper function implementations into compact signature table (-179 lines)
- Compressed `extract_knowledge()` prompt while preserving full format template
- Restored inline dedup algorithm in `load_knowledge()` for correctness
- Added parsing logic detail to `parse_knowledge_items` helper entry

#### Fixed (from optimization deep review)
- **CRITICAL:** Removed undefined function references (`extraction_prompt_with`, `deduplicate_by_item_headers`)
- **HIGH:** Added regex parsing logic to `parse_knowledge_items` table entry
- **MEDIUM:** Restored full extraction prompt format template with quality rules
- **LOW:** Restored Confidence field in index entry format

#### Metrics
- Engine size: 21.2K → 20.2K tokens (4.4% reduction)
- Lines: 1,785 → 1,645 (-140 lines)

## [4.7.0] - 2025-07-28

### 🧠 v4.7.0 — Knowledge Accumulation System

Agents now automatically extract and persist cross-task knowledge, becoming smarter
over time. New tasks benefit from accumulated experience — code conventions, pitfalls,
architecture decisions, and best practices are captured after each phase.

#### ✨ New Features
- **Automatic Knowledge Extraction**: After each HITL-approved phase, the orchestrator
  scans the phase document for reusable lessons and saves them to the knowledge base
- **Dual-Dimension Knowledge Base**: Knowledge indexed by role (`by-role/`) AND by
  topic (`by-topic/`) — 5 role files + 5 topic files + master index
- **Knowledge Loading**: Relevant knowledge automatically injected into agent prompts
  via `load_knowledge()` — agents see lessons from their own past tasks + relevant topics
- **Deduplication**: Knowledge items tracked by `[T-NNN]` headers to prevent duplicates
- **Confidence Threshold**: Configurable minimum confidence level for extracted items
  (HIGH/MEDIUM/LOW)
- **Capacity Management**: Per-role and per-topic max item limits with oldest-first rotation

#### 📁 New Directory Structure
```
codenook/knowledge/
├── by-role/          (implementer.md, reviewer.md, designer.md, tester.md, acceptor.md)
├── by-topic/         (code-conventions.md, architecture-decisions.md, pitfalls.md,
│                      best-practices.md, project-config.md)
└── index.md
```

#### 🔧 Config
```json
{ "knowledge": { "enabled": true, "auto_extract": true,
  "max_items_per_role": 100, "max_items_per_topic": 50,
  "max_chars": 8000, "confidence_threshold": "MEDIUM" } }
```

#### 📝 Agent Template Updates
- All 5 agent templates updated with Knowledge Base constraint — agents instructed
  to reference accumulated knowledge for conventions, pitfalls, and best practices

## [4.6.5] - 2025-07-28

### 🔧 v4.6.5 — Deep Review Round 5 (29 fixes) + Dual-Agent Mode

Comprehensive deep review sweep (29 issues: 3 CRITICAL, 7 HIGH, 11 MEDIUM, 8 LOW)
plus two new orchestration features.

#### ✨ New Features
- **Dual-Agent Parallel Mode**: Two agents (different models) execute same phase in parallel,
  cross-examine each other's work, and a third agent synthesizes the final document.
  Configurable per-task or globally via `dual_mode` config.
- **Per-Phase Model Configuration**: `phase_models` field allows different model pairs
  for each workflow phase (e.g., Opus+GPT for design, Sonnet+Codex for implementation).

#### 🐛 Bug Fixes

**Engine (17 fixes):**
- **[C1]** Circuit breaker "Continue" now resets retry_counts (prevents infinite loop)
- **[C1+H1]** Circuit breaker `break` saves task-board.json before breaking
- **[C2]** Rename `task` variable to `current_task` in orchestrate() (variable collision)
- **[H2]** Add `paused` status handler at top of while loop (resume or exit)
- **[H3]** Fix synthesis fallback comment (was misleading about heuristic)
- **[M1]** Remove duplicate PHASE_KEYS, reuse PHASE_NAME_MAP via resolve_phase_name()
- **[M2]** Add `abandoned` and lightweight dynamic statuses to exhaustive list
- **[M3]** Define prev_phase lookup using AGENT_PHASES backward walk
- **[M4]** Add `record_feedback` and `stop` to adapter interface table
- **[M5]** Add config.json complete schema example
- **[M6]** Add "develop+review" shortcut to commands table
- **[M7]** Add early check for `hitl.enabled = false` → auto-approve
- **[L2]** Add null validation for resolved agent_a/agent_b models
- **[L3]** Add retry-aware phase decisions re-ask prompt
- **[L4]** Add unknown decision value error handling
- Fix stale `<task.status>` reference → `<current_task.status>`
- Close else block for HITL enabled/disabled check

**Templates (12 fixes):**
- **[H4]** Acceptor: add `task_id` to all 3 phase input contracts
- **[H5]** Reviewer: add `task_id` to input contract
- **[H6]** Designer: add lightweight mode awareness note
- **[H7]** README: add Create to tester tools list
- **[M1]** install.sh: update version comment to v4.6.5
- **[M2]** SKILL.md: update title version to v4.6.5
- **[M3]** Acceptor: add lightweight mode note
- **[M4]** Seed version strings: update from 4.6 to 4.6.5
- **[L1]** CHANGELOG: fix v3.x dates (2026 → 2025 typos)
- **[L2]** Acceptor: output contract formatting consistency
- **[L3]** README: fix tester description to include "create"
- **[C3]** CHANGELOG: add missing entries for v4.4.0–v4.6.5

## [4.6.0] - 2025-07-28

### ⚡ v4.6 — Multi-Task Management, Phase Entry Decisions, Deep Review Round 2

Major orchestration improvements: multi-task management with parallel task support,
mandatory phase entry decisions, and conversation-triggered commands.

#### ✨ New Features
- **Multi-Task Management**: switch, pause, resume active tasks; `depends_on` for task dependencies
- **Any-Phase Entry**: `--start-at` flag to create tasks at any phase in the workflow
- **Phase Entry Decisions**: mandatory questions before each phase with config persistence
- **Conversation Triggers**: natural-language commands for task/framework operations

#### 🐛 Bug Fixes
- Deep review round 2: 10 critical/medium findings fixed
- Auto-persist phase entry decisions to config
- Fix pseudocode consistency (round 3 nits)

## [4.5.0] - 2025-07-28

### 🔧 v4.5 — Per-Phase Model & HITL Adapter Configuration

#### ✨ New Features
- Per-phase model configuration for fine-grained control
- Per-phase HITL adapter overrides

## [4.4.0] - 2025-07-28

### 🔧 v4.4 — Skill Provisioning

#### ✨ New Features
- **Project-Level Skill Auto-Loading**: project-level skills in `codenook/skills/` automatically loaded to sub-agents
- **Smart Skill Provisioning (Q4)**: skills provisioned based on agent role and task context

## [4.3.1] - 2025-07-28

### 🔧 v4.3.1 — Deep Review Rounds 3 & 4

Two additional rounds of deep code review, fixing 14 more issues (40 total across all 4 rounds).

#### 🐛 Bug Fixes

**Round 3 — Engine (6 fixes):**
- Bump version reference from v4.2 to v4.3 in engine title
- Add `mode`, `pipeline`, `retry_counts`, `total_iterations` to task-board schema example
- Record skip decision in `feedback_history` when agent fails (HITL audit trail)
- Quick Trigger now matches lightweight status names (agent_name prefix)
- Fix `build_lightweight_routing` acceptor filtering for duplicate pipeline entries
- Remove duplicate Circuit Breaker comment (edit leftover)

**Round 3 — Templates (3 fixes):**
- Designer and tester: upgrade to 4-backtick code fences for nested mermaid blocks
- Implementer: add lightweight mode guidance note (matches reviewer/tester)
- Implementer and tester: add `task_id` to input contract (matches designer)

**Round 4 — Engine (5 fixes):**
- Handle "Retry with different model" option in agent failure block (was falling through)
- Bump task-board schema version from 4.2 to 4.3 (new fields)
- Define `get_user_decision` helper and use consistently (replaces mixed `ask_user` usage)
- Add `"abandoned"` to while loop exit conditions for robustness
- Add routing lookup fallback with error message for unknown status

#### 📊 Deep Review Statistics (4 rounds total)
| Round | Issues | CRITICAL | HIGH | MEDIUM | LOW |
|-------|--------|----------|------|--------|-----|
| R1 | 19 | 2 | 6 | 5 | 6 |
| R2 | 7 | 1 | 1 | 2 | 3 |
| R3 | 9 | 0 | 1 | 7 | 1 |
| R4 | 5 | 0 | 1 | 1 | 3 |
| **Total** | **40** | **3** | **9** | **15** | **13** |

## [4.3.0] - 2025-07-28

### ⚡ v4.3 — Quick Trigger, Lightweight Mode & Deep Review Sweep

Three new orchestration features plus comprehensive quality fixes from two rounds of deep code review (26 issues total).

#### ✨ New Features
- **Quick Trigger Dispatch**: Keyword-based agent activation (ZH/EN) — say "测试" or "test" to invoke tester directly, with automatic task context detection
- **Mandatory Ask-User Rule**: Orchestrator MUST call `ask_user` at the end of every response with context-aware choices
- **Lightweight Task Mode**: Custom agent pipelines for focused workflows — predefined shortcuts (quick fix, develop, test only, review only) plus custom `--pipeline a,b,c` syntax
  - Dynamic routing via `build_lightweight_routing(pipeline)` — chains only specified agents
  - 6 predefined pipeline shortcuts with ZH/EN aliases
  - HITL gates enforced in both full and lightweight modes

#### 🐛 Bug Fixes (26 issues from 2 rounds of deep review)

**Round 1 — Engine (11 fixes):**
- Complete AGENT_PHASES table with all 5 agents and all phases
- Fix reject routing: plan phases → retry same status, execute phases → back to plan
- Adapt circuit breaker for lightweight mode with human-readable labels
- Merge redundant HITL enforcement sections
- Make verdict routing mode-aware (full vs lightweight)
- Add verdict → routing mapping table for clarity
- Update Agent Roles table with phase and document columns

**Round 1 — Agent Templates (8 fixes):**
- Tester/reviewer: upstream docs changed from required → 📎 recommended
- Implementer: fix all `.agents/docs/` paths → `codenook/docs/<task_id>/`
- Implementer: add verdict quality gate (COMPLETE only when all tests pass)
- All agents: explicit document save paths

**Round 2 — Engine (4 fixes):**
- Replace undefined `find_plan_status_for()` with inline logic + `find_status_for_agent()`
- Add global iteration counter (max 30) to circuit breaker
- Add lightweight mode note to document chain section
- Cross-reference Task Modes from Task Management Commands

**Round 2 — Agent Templates (3 fixes):**
- Standardize "📎 recommended" capitalization across reviewer template
- Clarify status name construction in lightweight routing comments
- Mark designer `task_id` as required in context table

#### 🔄 Changed
- Engine instructions: net change -20 lines after all features and fixes (683 lines)
- Task Management Commands: shortcut descriptions now reference Task Modes section
- Circuit breaker: dual trigger (per-status >3 OR global >30 iterations)

## [4.2.0] - 2025-07-27

### 🛡️ v4.2 — HITL Enforcement & Adapter Fixes

Systematic fix for HITL gate enforcement bugs and adapter architecture issues.

#### 🐛 Bug Fixes
- **Terminal adapter self-contained**: Added `record_feedback` command — terminal adapter no longer depends on `ask_user` or any LLM-specific tool
- **HITL status mismatch**: Fixed `hitl-verify.sh` status names to match actual routing table (`impl_planned`, `impl_done`, etc. instead of wrong `designing_done`, `implementing_done`)
- **Agent frontmatter**: Removed invalid `disallowedTools` field from all 5 agent `.agent.md` files (not a valid Copilot CLI YAML field)

#### ✨ New Features
- **Mandatory Bootstrap Rule**: Orchestrator MUST read `task-board.json` before ANY agent action
- **Agent Phase Summary table**: Quick-reference routing table in instructions
- **HITL Concrete Steps**: Exact bash command sequences for local-html and terminal adapters (replaces abstract pseudo-code)
- **"DO NOT substitute ask_user" guard**: Explicit prohibition against shortcutting local-html adapter

#### 🔄 Changed
- **All adapters now follow symmetric bash-based interface**: publish → poll → get_feedback (+ record_feedback for terminal)
- **`ask_user` downgraded to optional**: Referenced only as convenience for terminal adapter step 2, never as a requirement
- **Orchestration loop pseudo-code**: `ask_user()` calls replaced with `get_user_decision()` (environment-agnostic)

## [4.1.0] - 2025-07-26

### 📄 v4.1 — Document-Driven Workflow

Every agent now produces a planning document before execution. 10 HITL gates per task cycle (up from 5).

#### ✨ New Features
- **Document-driven workflow**: Plan → Approve → Execute → Report → Approve
- **10 HITL gates per task**: Every agent phase has a mandatory human approval gate
- **10 document artifacts per task**: requirement-doc, design-doc, implementation-doc, dfmea-doc, review-prep, review-report, test-plan, test-report, acceptance-plan, acceptance-report
- **Document storage**: All artifacts saved to `codenook/docs/T-NNN/` for traceability
- **Verdict-based routing**: Review/test/acceptance verdicts drive status transitions
- **Mandatory Mermaid diagrams**: All agent documents must include visual diagrams
- **HITL light theme**: Clean, minimal white UI replacing the dark theme
- **Init directory confirmation**: User confirms installation directory during setup

#### 🔄 Changed
- **Acceptor**: Now operates in 3 sub-phases (requirements, accept-plan, accept-exec)
- **Implementer**: Split into plan phase (implementation document) and execute phase (code + DFMEA)
- **Reviewer**: Split into plan phase (review prep with standards collection) and execute phase (review report)
- **Tester**: Split into plan phase (test plan document) and execute phase (test report)
- **Routing table**: 10 entries with unified agent → HITL pattern (was 10 entries with alternating agent/HITL)
- **Task board schema**: v4.1 with 10 artifact slots per task
- **Orchestration engine**: Updated loop with document storage, verdict routing, dual-phase invocation
- **SKILL.md**: v4.1 schema, docs/ directory, upgrade preserves docs/
- **highlight.js**: Switched from github-dark to github (light) theme
- **Mermaid**: Switched from dark to default theme

#### 📊 Phase Matrix
| Agent | Plan Phase | HITL | Execute Phase | HITL |
|-------|-----------|------|---------------|------|
| Acceptor (req) | Requirement Doc | ✅ | — | — |
| Designer | Design Doc | ✅ | — | — |
| Implementer | Implementation Doc | ✅ | Code + DFMEA | ✅ |
| Reviewer | Review Prep | ✅ | Review Report | ✅ |
| Tester | Test Plan | ✅ | Test Report | ✅ |
| Acceptor (accept) | Acceptance Plan | ✅ | Acceptance Report | ✅ |

#### 🔍 Deep Code Review (v4.0.1)
- Fixed 22 issues from 5-agent parallel code review
- XSS vulnerability patched (html.escape on all user content)
- Decision values aligned ("approve"/"feedback")
- Atomic writes with tempfile.mkstemp()
- install.sh integrity validation

## [4.0.0] - 2025-04-12

### 🚀 v4.0 — Subagent Architecture Redesign

Complete architectural overhaul: from 20 global skills + 13 hooks to 2 skills + subagent delegation.

#### ✨ New Architecture
- **2 skills** replace 20: `agent-init` (initialization + 5 templates) and `agent-orchestrator` (routing + HITL + memory)
- **Subagent delegation**: All agents run in separate context windows, spawned by the orchestrator
- **Project-level agents**: `agent-init` generates `.github/agents/` (Copilot) or `.claude/agents/` (Claude Code)
- **task-board.json**: Simple status-based routing replaces 11-state FSM
- **Multi-adapter HITL**: Auto-detects environment → local-html / terminal / confluence / github-issue
- **Hard constraints via frontmatter**: `tools`/`disallowedTools` in agent profiles replace hook enforcement
- **Memory management**: Orchestrator saves/loads markdown snapshots between phases

#### 🗑️ Removed (v3.x → v4.0)
- 18 global skills (agent-fsm, agent-switch, agent-messaging, agent-hooks, etc.)
- 13 shell hook scripts + hooks.json
- Session-level role switching (`/agent <name>` in main session)
- File-based messaging (inbox.json)
- `.agents/` runtime directory (events.db, state.json, workspace/)
- Global agent profiles (`~/.copilot/agents/`, `~/.claude/agents/`)
- Complex FSM state machine with guards

#### 📦 New File Structure
```
skills-v4/
├── agent-init/
│   ├── SKILL.md              — Initialization logic
│   └── templates/            — 5 agent profile templates
│       ├── acceptor.agent.md
│       ├── designer.agent.md
│       ├── implementer.agent.md
│       ├── reviewer.agent.md
│       └── tester.agent.md
└── agent-orchestrator/
    ├── SKILL.md              — Orchestration engine
    └── hitl-adapters/        — 4 HITL adapters
```

#### 📊 Size Comparison
| Metric | v3.x | v4.0 |
|--------|------|------|
| Skills | 20 | 2 |
| Hooks | 13 | 0 |
| Total lines | ~7,000 | ~1,200 |
| Install files | 40+ | 12 |
| Context per invocation | ~1,300 lines | ~200-350 lines |

#### 🔧 Updated
- `install.sh` rewritten for v4.0 (--install, --check, --uninstall, --clean-v3)
- HITL server `hitl-server.py` fixed: Python 3.13 regex compatibility + code block rendering

## [3.5.0] - 2025-07-24

### 🌐 Full English Internationalization (i18n)

- **Entire codebase translated from Chinese to English** — ~70 files, ~7000 lines
- All 20 skill docs (`skills/agent-*/SKILL.md`) — translated + optimized
- All 5 agent profiles (`agents/*.agent.md`) — fully translated
- All 11 documentation files (`docs/*.md`) — translated
- Global instructions (`copilot-instructions.md`, `CLAUDE.md`, `agent-rules.md`) — translated
- Task board descriptions (`.agents/task-board.json`) — 19 fields translated
- Project-level skills, DFMEA template, blog post, HITL server comments — translated
- 8 design docs and 10 review reports in runtime workspace — translated
- `agent-switch` preserves bilingual trigger keywords for Chinese-speaking users
- Zero Chinese characters remain in any active framework file

### 🔧 Maintenance

- Deduplicated `install.sh` guard logic + minimized global instructions (3712→46 lines)
- Fixed `install.sh` guard string to match both Chinese and English headers

## [3.4.1] - 2025-04-11

### 🔒 HITL Hook Enforcement

- **Hook hard constraint**: `agent-pre-tool-use.sh` now blocks FSM transitions in `task-board.json` when `hitl.enabled: true` and no approved feedback file exists
- **6 transitions enforced**: created→designing, designing→implementing, implementing→reviewing, reviewing→testing, testing→accepting, accepting→accepted
- **All 5 agent skills** updated with `🔒 Hook hard constraint` notice
- Backward transitions and property-only changes remain unrestricted
- HITL disabled (`hitl.enabled: false`) skips all gate checks

### 🧪 E2E Test Results
- 30/30 tests passed across 6 test groups
- Agent switching, role boundaries, HITL pipeline, mid-flow modifications, HITL disabled, memory isolation

## [3.4.0] - 2025-04-13

### 🚀 Agent Experience Enhancement

#### Unified FSM (T-039)
- Merged 18-state 3-Phase Engineering Closed Loop into **11-state unified FSM**
- Legacy 3-Phase states auto-migrate via 15-state mapping table
- Removed `workflow_mode` selection from `agent-init`

#### Human-in-the-Loop Review Gate (T-041, T-042)
- New `agent-hitl-gate` skill (20th skill)
- **All 5 agents** have HITL checkpoints before FSM transitions
- 4 platform adapters:
  - `local-html`: Interactive HTTP server with dark-themed Web UI + multi-round feedback
  - `terminal`: Pure CLI for Docker/SSH/headless environments
  - `github-issue`: GitHub Issue-based review via `gh` CLI
  - `confluence`: Confluence REST API integration with comment polling
- Docker auto-detection: binds `0.0.0.0`, skips browser open
- Atomic file writes (`os.rename`) for race condition prevention

#### DFMEA Integration (T-040)
- DFMEA template with **S×O×D→RPN** risk scoring
- Mandatory DFMEA analysis before coding (implementer Phase 1)
- FSM guard validates RPN ≥ 100 items have mitigation measures

#### Developer Experience
- **T-038**: Ask-next-step rule injection per agent role in `agent-init`
- **T-043**: Worktree prompt for feature isolation in acceptor workflow
- **T-044**: Role mismatch detection + switch prompt in all 5 agents

### 🔒 Security Hardening (3 rounds, 22 issues fixed)
- Command injection: Python `sys.argv` instead of `open('$file')` string embedding
- XSS defense: Pandoc `-raw_html` extension strips raw HTML blocks
- Path traversal: `^T-[0-9]+$` task ID validation
- Env var whitelist: only `CONFLUENCE_TOKEN/API_KEY/PAT/ATLASSIAN_TOKEN`
- Atomic file writes in `hitl-server.py` (tmp + `os.rename`)
- Port exhaustion: exit with error instead of silent fallback
- PID verification: `kill -0` check after server startup
- Dependency checks (`python3`, `gh`, `curl`) in all 4 adapters

### 🐛 Bug Fixes
- Hook false positive on role switch: now checks redirect targets individually, skips `active-agent`
- FSM auto-transition on switch: when target role has no matching tasks, offer batch transition
- 3-Phase deprecation notices in `agent-hooks` and `agent-orchestrator`

### 📊 Stats
- 16 commits since v3.3.6 | 31 files changed | ~2,600 lines added
- 7 tasks (T-038~T-044), 28 goals — all accepted
- 36/36 tests passing | 20 skills (was 19)

## [3.3.6] - 2025-04-11

### 🔒 Security Hardening — Hook Enforcement

**Virtual Event Enforcement via preToolUse:**
- **agentSwitch**: validates role names on write to `active-agent`; blocks empty/invalid writes and file deletion (`rm`, `mv`)
- **memoryWrite**: namespace isolation — agents can only write their own memory files; task memory (`T-NNN-*`) is shared
- **taskBoard**: JSON syntax validation for full `task-board.json` writes

**Security Vulnerabilities Fixed:**
- **False positive prevention**: strip quoted strings (`'...'`, `"..."`) before pattern matching — prevents `--notes "npm publish"` from triggering block
- **Active-agent bypass**: block `rm`/`mv` on `active-agent` file; default to `acceptor` (most restrictive) when file missing but framework initialized
- **Chained command bypass**: per-segment analysis (`has_dangerous_segment`) splits on `&&`, `||`, `;` to prevent danger hidden behind whitelist matches
- **Multi-line quote stripping**: collapse newlines with `tr '\n' ' '` before `sed` to handle multi-line commit messages
- **Cross-directory attacks**: Strategy 4 extracts absolute paths from bash commands to detect operations targeting projects from outside directories

**Hook Configuration Cleanup:**
- Removed 6 unsupported custom events from `hooks-copilot.json` (Copilot CLI only supports 6 built-in events)
- Retained: `sessionStart`, `preToolUse`, `postToolUse`

### Added
- `tests/test-false-positive.sh` — 15 false-positive test cases
- `tests/test-virtual-events.sh` — 31 virtual event + security test cases
- 4-strategy project root detection (cwd walk, file path walk, cd target, absolute path extraction)

### Verified
- 51/51 total tests: framework 5/5 ✅, false-positive 15/15 ✅, virtual events 31/31 ✅
- Live-tested cross-directory, chained command, and active-agent bypass scenarios

## [3.3.5] - 2025-04-11

### Added
- **Comprehensive hard constraints for all 5 agent roles** via `preToolUse` hook enforcement
  - **Tester**: blocked from `git commit/push`, `rm/mv/cp` on non-test files, redirects outside test directories; allowed: `.agents/`, `tests/`, `*.test.*`, `*.spec.*`
  - **Implementer**: blocked from `npm publish`, `docker push`; blocked redirects to other agents' workspaces
  - **Acceptor/Designer**: read-only except `.agents/`; blocked destructive commands and redirects
  - **Reviewer**: read-only except `.agents/reviewer/`, `docs/`, `task-board`; blocked destructive commands

### Fixed
- **Bash redirect bypass vulnerability**: detected `>`, `>>`, `tee`, `sed -i`, `patch`, `dd` patterns in bash commands to prevent write operations that bypassed edit/create restrictions
- Redirect whitelist for `.agents/` writes per-role and test directories for tester role

### Verified
- 44/44 hook enforcement test scenarios passed across all 5 roles
- 8/8 live enforcement tests passed in real Copilot CLI session (tester role)

## [3.3.4] - 2025-04-11

### Fixed
- **agent-pre-tool-use.sh**: Fixed project root detection that failed when Copilot CLI session started from a non-project directory (e.g., `~`). Now walks up directory tree from both `cwd` and file path to find `.agents/` directory.

### Verified
- **Copilot CLI hooks confirmed working** (v1.0.24): `preToolUse` hook with `permissionDecision: "deny"` successfully blocks tool execution
- Both `~/.copilot/hooks/hooks.json` and `config.json` inline hooks are executed
- All 6 hook events documented by GitHub are supported: `sessionStart`, `sessionEnd`, `userPromptSubmitted`, `preToolUse`, `postToolUse`, `errorOccurred`

## [3.2.0] - 2025-04-10

### 🚀 Skills Mechanism Optimization (T-SKILL-OPT)

**R2: Per-Agent Skill Isolation:**
- All 5 `.agent.md` profiles now declare `skills:` allowlist in frontmatter
- Each agent has explicit "Skill permissions" section with positive and negative constraints
- Shared skills (7): orchestrator, fsm, task-board, messaging, memory, switch, docs
- Role-specific skills (11): config, init, acceptor, designer, implementer, reviewer, tester, events, hooks, hypothesis, teams

**R1: Token Distribution Documentation Fix:**
- `docs/llm-message-structure.md`: Corrected token pie chart from "18 Skills full text 40%" to "Skills summary list 1%"
- Added explanation of two-level loading mechanism (summary ~1% + on-demand full text)
- Updated ASCII packet structure to reflect summary-only skill injection
- Corrected "Key Insights" section to describe two-level loading

**R4: Dual Installation Methods in README:**
- "Method 1: One-click Install" — `curl | bash` (script-driven)
- "Method 2: Prompt-based Install" — Tell AI assistant to install from repo (AI-guided)
- Added detailed manual install steps table (target directories per platform)
- Updated skill count from 15 to 18

## [3.1.5] - 2025-04-10

### 📝 Audit Round 10 — Convergence (2 doc fixes)

**Executable code: ZERO issues** — codebase converged ✅

**MEDIUM:**
- `agent-hooks/SKILL.md`: Fix Step→Agent table: `ci_monitoring` and `device_baseline` mapped to `tester` (was `implementer`)

**LOW:**
- `agent-hooks/SKILL.md`: Add 5 missing transitions to 3-Phase pseudocode (`design_review→test_scripting`, 4 hypothesis transitions)

## [3.1.4] - 2025-04-10

### 🔒 Security Audit Round 9 (16 issues fixed)

**HIGH:**
- `test-3phase-fsm.sh`: Fix `grep -q "LEGAL"` matching "ILLEGAL" — FSM test suite was non-functional
- `test-3phase-fsm.sh`: Add missing `design_review→test_scripting` in test FSM case statement
- `team-session.sh`: Escape agent names in tmux commands to prevent shell injection

**MEDIUM:**
- `install.sh`: Recreate TMP_DIR after cleanup — tarball install was falling through to git clone
- `agent-session-start.sh`: Use `PRAGMA busy_timeout=3000` instead of `.tables` for DB health check
- `auto-dispatch.sh`: Clear stale lock directories (>60s) to prevent permanent dispatch lockout
- `test-integration.sh`: Capture exit code before `set -e` masks staleness-check failures
- `install.sh`: Only backup hooks.json if `.bak` doesn't already exist (prevents overwriting user's original)
- `cron-scheduler.sh`: Document that `schedule` field is display-only, caller's crontab controls timing
- `agent-messaging/SKILL.md`: Clarify two `type` enum systems (auto-dispatch vs bidirectional)

**LOW:**
- `test-3phase-fsm.sh`: Fix label "26" → "27" legal transitions
- `test-integration.sh`: Remove dead `cp` immediately overwritten by `cat`
- `team-session.sh`: Validate `--agents/--task/--layout` have values (prevent `set -u` crash)
- `team-session.sh`: Portable `watch` fallback with `while sleep` loop for macOS
- `cron-scheduler.sh`: Fix file handle leak in Python `json.load(open(...))` → `with open()`
- `install.sh`: Add `trap 'rm -rf "$TMP_DIR"' EXIT` for cleanup on interrupt

## [3.1.3] - 2025-04-09

### 🚀 Strict Document Gate Mode

- `hooks/lib/fsm-validate.sh`: Document gate now supports `"strict"` mode — blocks transitions (`LEGAL=false`) when required docs are missing
- Configuration via `task-board.json` top-level field `"doc_gate_mode": "strict"` (default: `"warn"`)
- `skills/agent-docs/SKILL.md`: Updated with strict/warn mode documentation
- `skills/agent-fsm/SKILL.md`: Added document gate as guard #5 in FSM validation rules
- `tests/test-integration.sh`: 2 new tests (strict blocks, warn allows) — 25 total

## [3.1.2] - 2025-04-09

### 🔒 Security Audit Round 7 (10 issues fixed)

**HIGH:**
- `agent-before-memory-write.sh`: Block path traversal (`..`) in memory file paths

**MEDIUM:**
- `agent-before-compaction.sh`: Validate agent name against `[a-z_-]+` allowlist
- `agent-fsm/SKILL.md`: Document `design_review→test_scripting` transition (was in code but not docs)
- `test-integration.sh`: Fix hypothesis test field name `.path` (was `.file_path`, test was vacuous)
- `cron-scheduler.sh`: Use `project_dir` for task-board path in generate-report
- `team-session.sh`: Escape `PROJECT_DIR` in dashboard pane tmux command

**LOW:**
- `test-3phase-fsm.sh`: Add `design_review:test_scripting` to legal transitions test array
- `agent-pre-tool-use.sh`: Add tester bash restrictions (block git push, npm publish, docker run)
- `install.sh`: Narrow chmod +x to `agent-*.sh` + `security-scan.sh` only

## [3.1.1] - 2025-04-09

### 🔒 Security Audit Round 6 (16 issues fixed)

**HIGH:**
- `install.sh`: Fixed symlink attack — tarball now extracts directly to mktemp dir with `--strip-components=1`
- `webhook-handler.sh`: Added `|| true` to sqlite3 call; log previous agent on switch
- `verify-init.sh`: Replaced all python3 code injection vectors with jq; fixed shebang + `set -euo pipefail`
- `agent-pre-tool-use.sh`: Reviewer now allowed to write `.agents/docs/` (fixes doc gate/boundary conflict)

**MEDIUM:**
- `cron-scheduler.sh`: Pass shell vars via `os.environ` instead of interpolating into Python strings
- `fsm-validate.sh`: Convergence gate uses `$NEW_STATUS` (not `$NEW_STATUS_SQL`); escape PT_* in JSON
- `auto-dispatch.sh`: Moved duplicate check inside lock to prevent TOCTOU race condition
- `team-session.sh`: Escape single quotes in TASK_FILTER and PROJECT_DIR for tmux
- `test-integration.sh`: Fixed hypothesis test using wrong field names (was snake_case, now camelCase)
- `install.sh`: Removed `git config --global http.postBuffer` side effect

**LOW:**
- `agent-pre-tool-use.sh`: Quote `$CWD` in parameter expansion to prevent glob interpretation
- `team-dashboard.sh`: Fixed progress bar off-by-one at 0%
- `webhook-handler.sh`: Log previous agent name on webhook-triggered switch
- `test-3phase-fsm.sh`: Removed redundant rm -rf (EXIT trap handles cleanup)
- `fsm-validate.sh`: SQL-escape PT_* values in convergence gate JSON

## [3.1.0] - 2025-04-09

### 🚀 Agent Teams — Bidirectional Messaging, Parallel Execution, Competitive Hypothesis

**New Features:**
- **Bidirectional Messaging**: Added `thread_id`, `reply_to` fields to message schema; `broadcast` message type for team-wide announcements
- **tmux Team Session**: `scripts/team-session.sh` launches multi-agent split-pane session with auto-refresh dashboard
- **Team Dashboard**: `scripts/team-dashboard.sh` shows real-time agent status, inbox counts, pipeline progress bar, recent events
- **Competitive Hypothesis**: New `agent-hypothesis` skill (18th skill) — Fork/Evaluate/Promote pattern for parallel approach exploration
- **`hypothesizing` FSM state**: New state in both Simple and 3-Phase workflows; `designing→hypothesizing` and `implementing→hypothesizing` transitions
- **Inbox on Switch**: After-switch hook now shows unread message count with urgent priority highlighting

**Enhancements:**
- `agent-messaging/SKILL.md`: Added thread support, broadcast type, updated routing rules
- `agent-teams/SKILL.md`: Added tmux session architecture, competitive hypothesis pattern, workspace storage
- `agent-fsm/SKILL.md`: Added `hypothesizing` to universal transitions
- `auto-dispatch.sh`: `hypothesizing` status skips auto-dispatch (coordinator manages)
- README: Added "Agent Teams" section with architecture diagram, 3 features, usage scenarios
- Integration tests expanded 21→23 (hypothesis transition + team dashboard)

## [3.0.23] - 2025-04-09

### 🔒 Security Audit Round 5 (16 issues fixed)

**HIGH:**
- `agent-post-tool-use.sh`: Fixed ACTIVE_AGENT double-escaping — raw value now stored, escaped only at SQL use sites (H1)
- `agent-post-tool-use.sh`: All sqlite3 calls now have `2>/dev/null || true` to prevent hook crash on DB errors (H2)
- `auto-dispatch.sh`: `created` status now routes to acceptor in 3-phase mode (was always designer) (H3)

**MEDIUM:**
- `fsm-validate.sh`: Added `design_review→test_scripting` transition (M1)
- `agent-fsm/SKILL.md`: Fixed ci_monitoring/device_baseline agent assignment (implementer→tester) (M2)
- `fsm-validate.sh`: Document gate now covers 3-phase states + acceptance-criteria.md (M3)
- `agent-post-tool-use.sh`: Reordered modules — FSM validation runs BEFORE auto-dispatch (M4)
- `memory-capture.sh`: Skips FSM-violated tasks to avoid capturing illegal transitions (M5)
- `fsm-validate.sh`: Goal guard uses `$NEW_STATUS` instead of `$NEW_STATUS_SQL` for comparison (M6)
- `install.sh`: Uses `mktemp -d` instead of predictable `/tmp/multi-agent-framework` path (M7)
- `agent-pre-tool-use.sh`: grep pattern uses `(\s|$)` to catch commands at end of line (M8)

**LOW:**
- `test-3phase-fsm.sh`: Added trap for temp dir cleanup (L1)
- `install.sh`: Split `local` declarations from assignments to avoid masking exit codes (L2)
- `verify-install.sh`: Replaced python3 path-injection-prone JSON check with jq (L4)
- `cron-scheduler.sh`: Resolved subprocess paths relative to script directory (L5)

## [3.0.22] - 2025-04-09

### 🔒 Security Audit Round 4 (22 issues fixed)

**CRITICAL:**
- `install.sh`: Now copies `hooks/lib/` directory (auto-dispatch, fsm-validate, memory-capture modules were missing after install!)

**HIGH — SQL/Code Injection:**
- `session-start.sh`: TIMESTAMP numeric validation (missed in Round 1)
- `memory-search.sh`: escape QUERY, ROLE, LAYER params; validate LIMIT is numeric
- `security-scan.sh`: sanitize newlines in JSON output (was producing invalid JSON)

**MEDIUM — Correctness & Safety:**
- `memory-capture.sh`: use jq for memory file JSON (fixes title with double quotes)
- `post-tool-use.sh`: escape double quotes/backslashes in TOOL_ARGS detail JSON; fix TOCTOU race (snapshot from cache, not disk)
- `install.sh`: fix operator precedence in integrity check; consistent skill count (17)
- `fsm-validate.sh`: compare raw status (not sql-escaped) for blocked_from
- `staleness-check.sh`: fix Perl code injection via environment variable
- `auto-dispatch.sh`: use @tsv (tab) instead of pipe delimiter; fail-safe lock skip
- `verify-install.sh`: add agent-docs to skill check list; threshold 16→17
- `agent-after-switch.sh`: jq for JSON output; null-safety for assigned_to
- `agent-before-task-create.sh`: jq for JSON output

**LOW — Hardening:**
- `config.sh`: use escaped values in sed append; escape regex in tool removal
- Test schema aligned with production (created_at column)
- Test #14 validates exit code + output (no false pass on crash)
- Remove redundant staleness-check from PostToolUse hooks.json
- `memory-index.sh`: track + report actual indexed count
- `webhook-handler.sh`: validate CWD before writing files

## [3.0.21] - 2025-04-09

### 🔒 Security Audit Round 3 (12 issues fixed)

**HIGH — SQL Injection:**
- `webhook-handler.sh`: escape PAYLOAD before SQL insertion
- `memory-index.sh`: escape file paths and checksum in all SQL queries

**MEDIUM — Security & Correctness:**
- `auto-dispatch.sh`: escape ACTIVE_AGENT in SQL JSON detail
- `memory-capture.sh` + `fsm-validate.sh`: fix `||`/`&&` operator precedence bug (guard clause now uses explicit `if/fi`)
- `agent-after-switch.sh`: replace jq `first` (1.6+) with `.[0]` for older jq compat; add null-safety for `.assigned_to`
- `agent-post-tool-use.sh`: validate task-board.json with `jq empty` before processing
- `auto-dispatch.sh`: fail-safe lock timeout (skip instead of proceeding unprotected)
- `config.sh`: escape special chars in sed replacement patterns

**LOW — Hardening:**
- `agent-pre-tool-use.sh`: escape agent name in JSON error output
- `agent-after-switch.sh`: replace unsafe `ls *.md` with `find -name "*.md"`

## [3.0.20] - 2025-04-09

### ⚡ Performance Optimization

**`fsm-validate.sh`**: Reduced jq calls from O(10×N) to O(2) total per hook invocation:
- Pre-extract ALL task fields (id, status, workflow_mode, feedback_loops, blocked_from, goals, parallel_tracks) in ONE jq call using `@tsv`
- Pre-load snapshot statuses with single jq call + awk lookup
- Eliminated 4 consecutive parallel_tracks queries (→ pre-extracted)
- Deduplicated `blocked_from` extraction across simple/3phase validators

**`memory-capture.sh`**: Same pattern — single jq call for all task data.

**`agent-staleness-check.sh`**:
- Cache date tool detection at startup (try once, reuse) instead of 3-tool fallback per call
- Consolidate 3→1 jq calls per state.json file

### 🧪 Integration Tests Expanded (12 → 21)

New tests: pre-tool-use agent boundaries (acceptor/implementer/reviewer), before-memory-write (empty/wrong-path/valid), on-goal-verified event logging, session-start event, staleness-check execution.

### 📖 README

- Added "Known Limitations & Troubleshooting" section

## [3.0.19] - 2025-04-09

### 🔧 Hook Modularization

Split the 364-line `agent-post-tool-use.sh` monolith into a clean 79-line main hook + 3 focused modules:

- `hooks/lib/auto-dispatch.sh` (75 lines) — message routing on status change
- `hooks/lib/fsm-validate.sh` (171 lines) — FSM transitions, goal guard, doc gate, feedback limit
- `hooks/lib/memory-capture.sh` (49 lines) — status transition detection + memory init

### 🧪 Integration Tests

- New `tests/test-integration.sh` with 12 actual hook execution tests
- Covers: tool logging, auto-dispatch, FSM violation, doc gate, memory capture, after-switch, compaction, security scan, before-task-create, events DB
- Added to `tests/run-all.sh` — full suite now 5/5

### 📄 Other

- `agent-init` skill now auto-creates `.agents/docs/` directory
- README: added document pipeline section with flow diagram

## [3.0.18] - 2025-04-09

### 📄 New Feature: Document Pipeline (`agent-docs` skill)

**Core concept**: Each SDLC phase must produce standardized documents that serve as inputs to the next phase.

**Document flow matrix**:
| Phase | Agent | Input | Output |
|-------|-------|-------|--------|
| Requirements | Acceptor | user request | `requirements.md` + `acceptance-criteria.md` |
| Design | Designer | requirements.md | `design.md` |
| Implementation | Implementer | requirements + design | `implementation.md` |
| Review | Reviewer | requirements + design + implementation | `review-report.md` |
| Testing | Tester | requirements + design + implementation | `test-report.md` |
| Acceptance | Acceptor | acceptance-criteria + all docs | Accept/Reject |

**What's included**:
- New `agent-docs` skill with 6 document templates (requirements, acceptance-criteria, design, implementation, review-report, test-report)
- Storage convention: `.agents/docs/T-XXX/` per task
- FSM document gate: warns when transitioning without required output document
- After-switch hook: lists available input documents for the current task
- All 5 agent profiles updated with explicit document input/output requirements
- 3-Phase mode document mapping included

## [3.0.17] - 2025-04-09

### 🐛 Deep Audit Round 2 (20 issues fixed)

**Security & Robustness:**
- **CWD extraction** in `agent-before-task-create.sh` — duplicate check now works from any directory
- **Lock release safety** — jq/mv failures no longer leave stale tmp files
- **grep pattern portability** in `security-scan.sh` — single-quote matching works across all grep implementations
- **CWD validation** in `security-scan.sh` — graceful exit if directory invalid
- **Download integrity** in `install.sh` — verify key files exist after tarball extraction
- **Copilot rules write check** — warn if append to copilot-instructions.md fails

**Cross-Platform Compatibility:**
- **Portable sed** in `config.sh` — `_sed_i()` helper detects macOS vs Linux (fixes `sed -i ''` failure on Linux/CI)
- **Portable date parsing** in `agent-staleness-check.sh` — replaced python3 fallback with perl `Time::Piece` (faster, no timeout risk)

**FSM Logic & Safety:**
- **Simple mode feedback loop protection** — `reviewing→implementing`, `testing→fixing`, `accept_fail→designing` now capped at 10 loops
- **Convergence gate event logging** — gate failures now logged to events.db (audit trail)
- **Unblock warnings** — tasks unblocked without `blocked_from` record get visible warning

**Memory & State:**
- **Memory directory creation check** — explicit error if `mkdir -p` fails
- **Compaction hook guard** — skip diary flush if no active agent found

**Documentation:**
- **README skill count** — badge updated 15→16, added `agent-config` to skills table
- **Section anchor** — `#15-skills` → `#16-skills`

## [3.0.16] - 2025-04-09

### 🐛 Critical Bug Fixes (Security & Reliability Audit)
- **TIMESTAMP SQL injection** — validate timestamp is numeric before SQL insertion
- **Pipe subshell variable loss** — convert `| while` to `while ... done < <(...)` in agent-post-tool-use.sh and agent-staleness-check.sh; staleness detection was completely broken
- **macOS file locking** — replace Linux-only `flock` with portable `mkdir`-based atomic lock
- **JSON null validation** — guard TASK_ID/NEW_STATUS against null/empty before FSM processing
- **TOOL_ARGS truncation order** — truncate before SQL escaping (not after) to prevent broken escape sequences
- **CWD initialization** — add INPUT/CWD extraction to 5 hooks missing it (after-memory-write, after-task-status, before-compaction, on-goal-verified, after-switch)

## [3.0.15] - 2025-04-09

### ✨ New Skill: agent-config
- **CLI model configuration** — `config.sh model set <agent> <model>` to configure agent models
- **CLI tools management** — `config.sh tools set/add/rm/reset` to control per-agent tool access
- **Dynamic agent discovery** — auto-scans all `*.agent.md` files, no hardcoded list
- **Dynamic model discovery** — `config.sh models` queries platform CLIs for available models
- **Dual-platform sync** — all changes applied to `~/.claude/agents/` and `~/.copilot/agents/` simultaneously
- **Backward compatible** — old `config.sh set/reset` commands still work

### 🔔 Model Switch Hints
- **agent-after-switch hook** — reads agent's `model` field on switch, suggests `/model <id>` command
- If `model` configured → "📌 Use /model xxx to switch"
- If only `model_hint` → "💡 hint information"
- If neither → silent (no noise)

### 🔧 Fixes
- **verify-install.sh** — updated skill count 15→16 (added agent-config)
- **SKILL.md interactive workflow** — AI now mandated to run discovery commands first, not assume agent/model lists

## [3.0.14] - 2025-04-09

### 🤝 Copilot Parity
- **Full Copilot CLI support** — installer now detects `~/.copilot` and auto-installs agents + skills + hooks + rules (same as Claude Code)
- **Agent profiles for Copilot** — 5 `.agent.md` files installed to `~/.copilot/agents/` (Copilot CLI natively supports custom agents via `/agent`)
- **Dual-platform check_install** — `--check` reports status for both Claude Code and Copilot CLI
- **Dual-platform uninstall** — `--uninstall` cleans both `~/.claude` and `~/.copilot` agent files

### 📝 Documentation
- **Updated platform compatibility table** — README now shows full parity between Claude Code and Copilot CLI
- **English usage instructions** — installer Done message now in English

## [3.0.13] - 2025-04-09

### ✨ Features
- **Per-agent model config** — added `model` and `model_hint` fields to all 5 agent profiles
- **Project-type-aware init** — agent-init Step 1c classifies projects (ios/frontend/backend/systems/ai-ml/devops) and adapts skill generation per type
- **Model resolution in agent-switch** — priority: task override → agent model → project config → system default

## [3.0.12] - 2025-04-09

### ⚡ Performance
- **Task-board cache** — cached task-board.json content in variable (15→1 disk reads per hook invocation)

### 🛡️ Resilience
- **events.db auto-repair** — session-start validates schema with `.tables` check, auto-recreates corrupted DB

### 🔧 CI/CD
- **GitHub Actions CI** — added `.github/workflows/test.yml`, runs all tests on push/PR to main

## [3.0.11] - 2025-04-09

### 📝 Documentation
- **Add 3-Phase sections** to implementer, reviewer, tester SKILL.md — each role now documents its 3-Phase responsibilities, steps, and differences from Simple mode
- **Trim monitoring diagrams** — replaced 48-line ASCII flowcharts with concise 5-step numbered lists (implementer −22 lines, tester −21 lines)

## [3.0.10] - 2025-04-09

### 🐛 Critical Fix
- **Fix undefined variables in auto-memory-capture** — `OLD_STATUS_SQL`/`NEW_STATUS_SQL`/`TASK_ID_SQL` were from a separate pipe subshell; memory events were never logged

### 🔒 Security
- **Bash command boundary enforcement** — acceptor, designer, reviewer now blocked from destructive bash commands (`rm`, `mv`, `git push`, `npm publish`, `docker run`, etc.)

### 🔧 Improvements
- **Improved uninstall()** — now removes security-scan.sh, rules/ files, restores hooks.json from `.bak`, cleans up Copilot installation

## [3.0.9] - 2025-04-09

### 🔧 Improvements
- **Standardize hook paths** — all 7 hooks with bare `.agents/` paths now use `AGENTS_DIR="${CWD:-.}/.agents"` variable
- **Clarify flock portability** — Linux-only with graceful no-op on macOS
- **CONTRIBUTING.md** — added dual-platform hook format comparison table (PascalCase vs camelCase, command vs bash, timeout ms vs sec)

### 🧪 Tests
- **test-hooks.sh expanded** — JSON validity checks for both hooks.json files, event count parity, rules/ validation, shebang + pipefail enforcement

## [3.0.8] - 2025-04-09

### 🐛 Critical Fix
- **Fix variable use-before-define** in `agent-post-tool-use.sh` — `OLD_STATUS_SQL`/`NEW_STATUS_SQL` were referenced before assignment, causing FSM validation to silently skip; also fixed self-referencing `sql_escape()` calls

### 🔧 Improvements
- **Complete Copilot hooks.json**: Added 6 missing event types (agentSwitch, taskCreate, taskStatusChange, memoryWrite, compaction, goalVerified) — Copilot users now get full hook coverage
- **verify-install.sh hardened**: Shebang → `#!/usr/bin/env bash`, error handling → `set -euo pipefail`

## [3.0.7] - 2025-04-09

### 🐛 Bug Fixes
- **README.md**: Fixed unclosed code fence after task lifecycle diagram — headings and text were rendered inside code block
- **install.sh hook count**: Fixed glob pattern (`agent-*.sh` → `*.sh`) to include `security-scan.sh` (12/13 → 13/13)
- **install.sh threshold**: Raised completeness check from 12 to 13 hooks

### 🔧 Improvements
- **hooks.json backup+replace**: Install now backs up existing hooks.json before overwriting (creates `.bak`) instead of skipping — applies to both Claude and Copilot platforms

## [3.0.6] - 2025-04-08

### 🔒 Security
- **CRITICAL: Fix SQL injection** in 11 sqlite3 calls across 6 hooks — all variables now escaped via `sql_escape()` helper
- **Expanded secret scanning**: Add detection for Stripe keys, Slack tokens, database connection strings, JWT/Bearer tokens, webhook URLs

### 🔧 Improvements
- **python3→jq migration**: All 7 hooks now use jq for JSON parsing (consistent, lighter, portable)
- **Shebang standardization**: All 13 hooks now use `#!/usr/bin/env bash` (was mixed `#!/bin/bash`)
- **SQLite error handling**: All hooks now log warnings on insert failure instead of silent suppression
- **.gitignore hardened**: Add agent runtime files (events.db, state.json, inbox.json, snapshots, logs, backups)

## [3.0.5] - 2025-04-08

### ⚡ Performance
- **SKILL.md context reduction**: agent-init 680→173 (−75%), agent-switch 588→141 (−76%)
- Total across 4 files: 3654→1116 lines (−69%, ~10K tokens/session)

## [3.0.4] - 2025-04-08

### 📦 New Features
- **FSM unblock validation**: `blocked→X` now restricted to `blocked→blocked_from` state only (prevents state-skipping)
- **Goal guards**: Acceptance (`→accepted`) blocked unless ALL goals have `status=verified`
- **11 new behavioral tests**: Unblock validation (5 tests) + goal guard (6 tests) — total 31 FSM tests

### ⚡ Performance
- **SKILL.md context reduction**: agent-orchestrator 1394→500 lines (−64%), agent-memory 992→302 lines (−70%)

### 🔧 Improvements
- **Consolidated hooks**: Merged memory-index trigger from agent-after-task-status.sh into agent-post-tool-use.sh (single source of truth)
- **SQLite error handling**: agent-after-task-status.sh now logs warnings on failure

## [3.0.3] - 2025-04-08

### ⚡ Performance
- **jq loop optimization**: Auto-dispatch now uses pipe-delimited parsing (3 jq calls → 1 per task)
- **SQLite transactions**: `memory-index.sh` wraps all inserts in a single transaction (atomicity + ~10x speed)

### 🐛 Bug Fixes
- **File locking**: Add `flock`-based locking on inbox.json writes to prevent race conditions
- **Cross-platform dates**: Add python3 fallback for ISO date parsing (macOS + Linux + containers)
- **SQLite error logging**: Replace silent `2>/dev/null || true` with proper warning on failure
- **Shell safety**: Standardize `set -euo pipefail` across all 6 hook scripts

### 📦 New Features
- **Orphan task detection**: Staleness check now flags blocked tasks with no activity >48h (🔴 warning)

## [3.0.2] - 2025-04-08

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
- Fix duplicate "Claude Code, Claude Code" → "Claude Code, GitHub Copilot"
- Fix "15+ Hook" → "13 Hook" in skills table and roadmap
- Fix staleness-check event type: SessionStart → PostToolUse (matches hooks.json)
- Update docs/agent-rules.md with 3-Phase workflow rules
- Update install.sh to install modular rules to `~/.claude/rules/`
- Update AGENTS.md: fix chmod for security-scan.sh, fix hook count verification
- Add rules/ directory structure to README file tree

### 🧪 Tests
- Expand test-hooks.sh from 5 to 13 hooks (full v2.0 coverage)

## [3.0.0] - 2025-04-12

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

## [2.0.0] - 2025-04-07

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

## [1.0.0] - 2025-04-06

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

## v3.2.1

### R3: Architecture Docs Update
- Rewrote `docs/skills-mechanism.md` with 5 updated Mermaid diagrams
- New: Two-level loading sequence diagram (summary ~1% + on-demand full text)
- New: Skill discovery paths comparison (Claude Code vs Copilot CLI)
- New: Per-Agent skill isolation flowchart with shared/role-specific allocation
- Updated: Three-layer behavior control (added skill constraints)
- Updated: Request lifecycle (reflects two-level loading + doc gate)

### R5: Conditional Activation (Partial)
- Added `paths:` frontmatter to `agent-hooks` skill (`hooks/**`, `**/*.sh`, config files)
- Documented `paths:` feature in skills-mechanism.md platform comparison table
- Role skills (tester, implementer) excluded to avoid breaking agent workflow

## v3.2.2

### Documentation Cleanup
- Fix stale references: skill count 14/15/17→18 across README, USAGE_GUIDE, badges
- Update claude-code-flow.md: two-level Skill loading + per-agent isolation diagram
- Update agent-rules.md: remove stale state.json, add skills: isolation mention
- Simplify README: condense issue tracking + memory sections, collapsible narrative
- Fix doc gate limitation entry: strict mode now exists (was listed as planned)
- README: 734→682 lines (−7%)

## v3.2.3

### agent-init Rework
- Step 1b: Scan both CLAUDE.md and .github/copilot-instructions.md
- Step 1e: Scan all 18 global skills (was only 7), read agent profiles with skills: isolation
- Step 1f: NEW — detect platform (Claude Code / Copilot CLI / both)
- Step 3: Remove stale state.json references
- Step 6: Fix .gitignore (remove state.json)
- Step 7: NEW — generate/update CLAUDE.md + copilot-instructions.md with framework refs
- Step 7c: NEW — auto-append .agents runtime paths to project .gitignore
- Step 8: Updated summary with platform + global skill count

## v3.2.4

### Skills Loading Animation
- Interactive HTML animation (8 steps, keyboard/auto-play)
- GIF (378KB) + MP4 (152KB) versions for sharing
- Visualizes two-level loading, per-agent isolation, token efficiency

### Audit Round 11
- 1 doc-only issue fixed (stale version in USAGE_GUIDE)
- Executable code: ZERO issues for 3rd consecutive round

## v3.3.0

### Worktree-Based Parallel Tasks
- NEW `agent-worktree` skill: create/list/merge/status commands
- Each task gets isolated worktree + branch (task/T-XXX)
- Shared task-board.json + events.db via symlink
- Isolated runtime (inbox, memory, docs) per worktree
- Auto-copy memory/docs back to main on merge

### Framework Updates
- Skill count: 18 → 19 (agent-worktree added as shared skill)
- Shared skills: 7 → 8 (all agents get worktree access)
- Updated all 5 agent profiles + skills-mechanism diagram
- Design doc: `.agents/docs/T-WORKTREE/design.md`

## v3.3.1

### Worktree P2-P5 Implementation
- P2: `team-session.sh --worktree --tasks T-042,T-043` (one tmux window per task)
- P3: auto-dispatch cross-worktree message routing
- P4: task-board.json `worktree` field (path/branch/created_at)
- P5: USAGE_GUIDE §3.4 + 5 new integration tests (30 total)

## v3.3.2

### Forced Natural Language Agent Switch
- agent-switch SKILL.md: expanded description with 7 trigger patterns (CN+EN)
- Added mandatory trigger rules section with name mapping table
- agent-rules.md: new "Forced Role Switch" top-priority section
- agent-init Step 7a: CLAUDE.md template now includes switch trigger rules
- Supports: "switch to acceptor" (CN), "switch to tester", "/agent acceptor", "I am implementer" (CN), etc.

## v3.3.3

### Role Permission Enforcement
- agent-rules.md: new "Role Permission Enforcement" section with permission matrix
- Self-check before every file operation: read active-agent → check matrix → block violations
- Violation response template: shows role, blocked action, and switch suggestion
- agent-init Step 7a: CLAUDE.md template includes enforcement rules
- Works in both Claude Code (hook-enforced) and Copilot CLI (self-check enforced)
