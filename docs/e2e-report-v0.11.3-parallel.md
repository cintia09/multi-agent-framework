# CodeNook v0.11.3 — Parallel Two-Task E2E

- **Date:** 2026-04-20
- **Workspace:** `/Users/mingdw/Documents/workspace/development`
- **Source SHA:** `082f221` (`v0.11.3`)
- **Sub-agents:** A = primes (`claude-opus-4.7`), B = strrev (`claude-opus-4.7`), dispatched in a single response (true parallel).
- **Verifier:** GitHub Copilot CLI (autonomous).

## Phase 0 — Workspace reset + fresh install

| # | Check | Result | Notes |
|---|-------|--------|-------|
| 0.1 | `install.sh` exit 0 | ✅ PASS | first install |
| 0.2 | `.codenook/bin/codenook` exists, executable, `--help` prints subcommand list | ✅ PASS | bash script, +x |
| 0.3 | `.codenook/memory/{knowledge,skills,history,_pending,config.yaml}` all present | ✅ PASS | all five entries |
| 0.4 | `.codenook/schemas/{task-state,installed}.schema.json` shipped | ✅ PASS | plus `hitl-entry`, `locks-entry`, `queue-entry` schemas |
| 0.5 | `state.example.md` shipped | ⚠️ PASS-with-note | located at `.codenook/state.example.md`, NOT under `schemas/` as the bootloader text suggests (`E2E-P-006`) |
| 0.6 | `state.json` `schema_version == "v1"` | ✅ PASS | |
| 0.7 | `state.json` `kernel_version == "0.11.3"` | ❌ **FAIL** | first install wrote `kernel_version: "0.5.0-m5.1"`. A second `install.sh` run later in Phase 2 corrected it to `0.11.3`. (`E2E-P-001`) |
| 0.8 | CLAUDE.md marker block present, user content outside markers byte-identical to baseline | ✅ PASS | marker block injected at EOF; `diff` of outside-marker portion → ZERO DIFF (sha 8981ced…) |
| 0.9 | install.log warns about legacy v4.x tokens but does not abort | ✅ PASS | warning text suggests `--migrate-claude-md` planned for v0.12 |

> Pre-install state: workspace already had a v4.9.5-style `CLAUDE.md` (no `.bak.preinstall` available). It was preserved verbatim and used as the user-true baseline for the outside-marker diff.

## Phase 1 — Parallel sub-agent trip reports (verbatim)

Both agents were dispatched in a single tool-call response and ran concurrently against the same `.codenook/` workspace. Each authored its own `src/*.py` + `tests/*.py` and walked the kernel-driven phases (the development plugin actually emits **8 phases** — clarify → design → plan → implement → test → accept → validate → ship — not the 6 named in the task spec).

### Sub-agent A (primes)

```
=== AGENT A TRIP REPORT ===
TASK_ID_PRIMARY: T-002
TASK_ID_SIBLING: T-003
FINAL_STATE: done (phase=complete)
FILES_CREATED: src/primes.py, tests/test_primes.py
PYTEST_RESULT: PASS 4/4 (test_primes_up_to_10, _1, _100, _0)
CHAIN_LINK_OK: yes — `chain link --child T-002 --parent T-003` returned
  {"child":"T-002","parent_id":"T-003","chain_root":"T-003"}
  and state.json now contains parent_id="T-003", chain_root="T-003".
MEMORY_ENTRIES_CREATED: 0 new files in .codenook/memory/knowledge/
  (only .gitkeep present; mock-LLM extractor produced extract_failed /
  below_threshold for every dispatch — see anomalies)
EXTRACTION_LOG_ENTRIES_FOR_THIS_TASK: 84 entries in
  .codenook/memory/history/extraction-log.jsonl mention T-002
  (router-noop + per-phase extractor_dispatched / extract_started /
  extract_failed / below_threshold rows for knowledge, skill,
  config extractors across each phase).
PARALLEL_HAZARDS_OBSERVED:
  - No file-locking / EAGAIN / lock errors observed against B.
  - No B-task content (T-001) leaked into T-002 directory or router-context.md.
  - No state.json / audit.jsonl JSON corruption (all reads parsed cleanly).
  - No task_id collision (kernel allocated T-001→B, T-002→me, T-003→sibling).
  - One *non-parallel* friction: kernel transition plan→implement silently
    failed because target_dir was missing from state (entry-questions for
    implement requires it); the wrapper swallowed the missing-field JSON,
    so the only visible signal was a `recover: re-dispatch (no in_flight)`
    warning in history. Worked around by editing state.json to add
    target_dir:"src" then re-supplying the planner output.
COMMAND_TRANSCRIPT_PATH: .scratch/parallel-e2e/agent-A-transcript.log
  (prompt requested /tmp/... but runtime hard-blocks /tmp writes; saved
  under workspace .scratch/ instead.)

=== PHASE WALKTHROUGH ===
Phase 1 (clarify):   tick exit 0 → clarifier; outputs/phase-1-clarifier.md (verdict ok); auto-advanced.
Phase 2 (design):    tick exit 0 → 2 parallel designers (dual_mode=parallel, dual_mode_compatible);
                     phase-2-designer.md (ok); decide approve →
                     {"id":"T-002-design_signoff","decision":"approve"}; tick → plan.
Phase 3 (plan):      tick exit 0 → planner; phase-3-planner.md (ok). Two re-dispatch loops
                     due to missing target_dir; manually patched, then tick → implement.
Phase 4 (implement): tick exit 0 → 2 parallel implementers; src/primes.py + tests/test_primes.py
                     + phase-4-implementer.md (ok); decide approve → pre_test_review approve;
                     tick → test.
Phase 5 (test):      tick exit 0 → tester; pytest 4 passed; phase-5-tester.md (ok); tick → accept.
Phase 6 (accept):    tick exit 0 → acceptor; phase-6-acceptor.md (ok); decide approve → acceptance approve;
                     tick → validate.
Phase 7 (validate):  tick exit 0 → validator; phase-7-validator.md (ok); tick → ship.
Phase 8 (ship):      tick exit 0 → reviewer; phase-8-reviewer.md (ok); tick → complete, status=done.

=== ANOMALIES ===
1. Mock-LLM extractor failures (per phase, per asset_type):
   {"event":"extract_failed","asset_type":"knowledge","task_id":"T-002",
    "reason":"parse: Expecting value: line 1 column 2 (char 1)"}
   skill / config: outcome="below_threshold" reason="max_count=0".
   Effect: 0 new entries in .codenook/memory/knowledge/.
2. Silent transition block on missing entry-question: tick exits 0 with no
   stdout/stderr, then logs `recover: re-dispatch (no in_flight)` instead
   of surfacing the target_dir missing-field response.
3. `codenook task new --priority` is rejected: `unknown arg: --priority`.
   The flag advertised in the task playbook does not exist in v0.11.3.
```

### Sub-agent B (strrev)

```
=== AGENT B TRIP REPORT ===
TASK_ID_PRIMARY: T-001
TASK_ID_SIBLING: T-004
FINAL_STATE: phase=complete, status=done
FILES_CREATED: src/strrev.py, tests/test_strrev.py
PYTEST_RESULT: PASS 4/4 (test_hello, test_mixed_case, test_empty, test_single)
CHAIN_LINK_OK: yes — state.json shows parent_id=T-004, chain_root=T-004
  (CLI returned {"child":"T-001","parent_id":"T-004","chain_root":"T-004"})
MEMORY_ENTRIES_CREATED: 0 in .codenook/memory/knowledge/ (only .gitkeep);
  1 pending stub at .codenook/memory/_pending/T-001.json. All extractor runs
  returned no_candidates / below_threshold because role outputs lacked an
  `extract:` frontmatter block.
EXTRACTION_LOG_ENTRIES_FOR_THIS_TASK: 84 lines in extraction-log.jsonl
  matching T-001 (8 phases × {dispatch + start + complete} for knowledge /
  skill / config extractors).
PARALLEL_HAZARDS_OBSERVED:
  - No race / lock / EAGAIN errors observed.
  - No memory-entry leakage from A — A's _pending/T-002.json is visible
    but never injected into my context.
  - No state.json / audit.jsonl corruption (all writes atomic).
  - No phase-ordering bug from shared global state — T-001 walked
    clarify → … → ship cleanly.
  - No task_id collision: kernel auto-assigned T-001, A got T-002 + T-003,
    sibling got T-004 (sequential allocation, no collisions).
  - Side observation (NOT a parallel hazard): plan re-entered a re-dispatch
    loop because implement's entry-question requires target_dir, which
    `task new` does not set and the plan-output verdict gets re-consumed
    each tick. Recovered by editing state.json directly (the recovery
    hint advertises `codenook task set --field …` but that subcommand
    does not exist: `codenook task: unknown subcommand: set`).

=== PHASE WALKTHROUGH ===
Phase 1 (clarify): clarifier on first tick → phase-1-clarifier.md (ok); tick → design.
Phase 2 (design): dual-mode parallel dispatched 2 designer agents; phase-2-designer.md;
                  tick parked at HITL gate design_signoff; decide approve; tick → plan.
Phase 3 (plan):   planner; phase-3-planner.md; failed to advance because implement requires
                  target_dir; 3 spurious recover/re-dispatch rows; patched state.json directly.
Phase 4 (implement): 2 parallel implementers; src/strrev.py (`s[::-1]`) + tests (4 cases);
                  phase-4-implementer.md; HITL gate pre_test_review; decide approve; tick → test.
Phase 5 (test):   tester; pytest -v → 4 passed; phase-5-tester.md; tick → accept.
Phase 6 (accept): acceptor; phase-6-acceptor.md; HITL acceptance; decide approve;
                  tick → validate → ship → complete (status=done, next_action=noop).

=== ANOMALIES ===
- `task new --priority` not supported (`unknown arg: --priority`).
- `task set` subcommand does not exist despite recovery hint advertising it.
- Plan-phase re-dispatch loop when implement's entry-questions are unsatisfied;
  previous phase's output file is never deleted and gets re-consumed each tick.
- Tick exit code 1 ("dispatched planner" while phase already==plan) appears benign —
  --json output reports status=advanced but wrapper exits 1.
- Knowledge extractors all return no_candidates because phase outputs do not
  include the `extract:` frontmatter block.
- No interference with sub-agent A observed.
```

## Phase 2 — Concurrency assertions

| # | Assertion | Result | Evidence |
|---|-----------|--------|----------|
| 2.1 | Both tasks reached `done` | ✅ PASS | `status --task T-002` and `--task T-001` both return `phase=complete, status=done` |
| 2.2 | Artefacts exist & no cross-overwrite | ✅ PASS | `src/primes.py` (475 B), `src/strrev.py` (102 B), `tests/test_primes.py` (431 B), `tests/test_strrev.py` (323 B) — distinct timestamps, distinct content |
| 2.3 | Pytest both pass | ✅ PASS | `pytest tests/test_primes.py tests/test_strrev.py -v` → **8 passed in 0.00 s** |
| 2.4 | State isolation (no cross-references) | ✅ PASS | `'T-001' in state(T-002)` → False; `'T-002' in state(T-001)` → False; only chain links to T-003 / T-004 siblings |
| 2.5 | Audit isolation per task | ⚠️ PASS-with-note | per-task `audit.jsonl` files do **not** exist — all events go to global `.codenook/history/dispatch.jsonl` and `.codenook/history/hitl.jsonl`. HITL log shows 3 entries each for T-001 and T-002 with no interleaving collisions. Per-task audit was a Phase-2 spec assumption; kernel uses global logs (`E2E-P-007`). |
| 2.6 | Memory knowledge YAML well-formed | ✅ PASS (vacuously) | `.codenook/memory/knowledge/` contains only `.gitkeep` — 0 entries to validate. No half-written / torn files. |
| 2.7 | Memory index JSON parseable | ✅ PASS | no `index.json` exists; both `.codenook/memory/_pending/T-001.json` and `T-002.json` parse cleanly. No `.lock` leftover. |
| 2.8 | No race-condition fingerprints in audit/history JSONLs | ✅ PASS | grep `lock_timeout\|parse_error\|partial_write\|EAGAIN\|EWOULDBLOCK` across all jsonl → 0 hits |
| 2.9 | CLAUDE.md outside-marker byte-identical to baseline | ✅ PASS | `diff` → ZERO DIFF |
| 2.10 | Idempotent re-install after parallel run | ✅ PASS | second `install.sh` exit 0; state.json `kernel_version` corrected from `0.5.0-m5.1` → `0.11.3` (see `E2E-P-001`) |

## Phase 3 — Round-1 regression sweep

| # | Round-1 fix | Result | Evidence |
|---|-------------|--------|----------|
| E2E-001 | `codenook --help` prints subcommand list | ✅ PASS | full help text emitted |
| E2E-002 | `router` falls through to host_driver when no Claude Code host | ✅ PASS | returns `{"action":"prompt","prompt_path":...,"reply_path":...}` (host_driver prompt-mode) |
| E2E-005 | Malformed YAML → tick reports parse error with file path | ⚠️ PASS-with-note | tick emits `WARNING: clarifier output present but unusable (no_frontmatter): outputs/phase-1-clarifier.md`. File path is included; the message says `no_frontmatter` rather than a strict `yaml_parse_error`, but the user-visible signal is correct. |
| E2E-006 | `task new` without `--dual-mode` → entry-question response w/ `allowed_values` | ❌ **FAIL** | `task new --title entry-q-test` silently writes `dual_mode: "serial"` and `phase: null` — no entry-question is surfaced, no `allowed_values` printed. (`E2E-P-002`) |
| E2E-009 | Extractor produces ≥ 1 knowledge entry from a valid role output | ❌ **FAIL** | 84 extraction-log entries each for T-001 and T-002, all `extract_failed` / `below_threshold` / `no_candidates`; 0 files in `memory/knowledge/`. (`E2E-P-003`) |
| E2E-016 | Double install → exit 0 | ✅ PASS | re-install in Phase 2.10 succeeded |
| E2E-017 | `claude_md_linter` on workspace CLAUDE.md → 0 errors in marker-only mode | ❌ **FAIL** | linter reports 5 errors **inside the install-injected marker block** (lines 2252, 2284 ×2, 2295 ×2): `forbidden domain token 'development'` / `'plugins/development'`. The bootloader text install.sh writes is itself non-conformant to the linter's default policy. (`E2E-P-004`) |
| E2E-018 | Memory skeleton present | ✅ PASS | `_pending`, `config.yaml`, `history`, `knowledge`, `skills` all present |
| E2E-019 | `state.json` has new schema | ⚠️ PASS-with-note | `schema_version: v1` ✅; `kernel_version` initially wrote stale `0.5.0-m5.1` (see Phase 0.7 / `E2E-P-001`) |

## Phase 5 — Findings (severity-ordered)

### CRITICAL
*(none — no data corruption, no concurrency races, no cross-task leakage.)*

### HIGH

**E2E-P-001 — Fresh `install.sh` writes stale `kernel_version` to `state.json`**
- **Where:** `.codenook/state.json` after first install of v0.11.3.
- **What:** `kernel_version` is `"0.5.0-m5.1"` despite `install.sh` banner advertising `v0.11.3` and `VERSION` file containing `0.11.3`. A second `install.sh` run subsequently writes the correct `0.11.3`.
- **User impact:** Telemetry, `codenook status`, schema-compatibility gates, and any tooling that reads `kernel_version` will report the wrong version on first install — undermining the v0.11.3 schema/version contract this verification is supposed to confirm.
- **Suggested fix:** In `install.sh` (or the kernel-version stamp helper), source the version from `VERSION` (or the kernel module) at install time and overwrite `kernel_version` unconditionally on every run; add a Bats test asserting `state.json.kernel_version == VERSION` immediately after `install.sh`.

**E2E-P-002 — `task new` swallows missing `--dual-mode` instead of surfacing an entry-question**
- **Where:** `.codenook/bin/codenook task new` (kernel `task_new.sh`).
- **What:** Calling `task new --title …` without `--dual-mode` silently produces a task with `dual_mode: "serial"` and `phase: null`, no entry-question stdout, no `allowed_values`. Round-1 fix was supposed to make this interactive/structured.
- **User impact:** Round-1 regression. Users get an opaque default instead of a discoverable choice; task playbooks and docs that promise an entry-question break.
- **Suggested fix:** Re-instate the entry-question gate (return JSON with `action:"entry_question", field:"dual_mode", allowed_values:["serial","parallel"]`) when the flag is absent and stdin is non-interactive; only default when explicitly opted-in via `--accept-defaults`.

**E2E-P-003 — Knowledge extractor produces zero entries even on well-formed role outputs**
- **Where:** Mock-LLM extractor pipeline; `extraction-log.jsonl` events `extract_failed: parse: Expecting value: line 1 column 2 (char 1)` (knowledge) and `outcome: below_threshold, reason: max_count=0` (skill / config).
- **What:** Across 16 fully-walked phase outputs (8 each for T-001 and T-002), zero `.codenook/memory/knowledge/*.md` files were materialized. The default mock LLM never returns valid extractor JSON, and threshold defaults are 0.
- **User impact:** The memory layer is effectively a no-op out of the box. Users walking the lifecycle see an empty `knowledge/` dir and have no signal that extraction is misconfigured vs. genuinely empty.
- **Suggested fix:** Either (a) ship a deterministic stub extractor that always emits one minimal entry per role output so the contract is observable, or (b) fail loudly when 100 % of extractions error out across a completed task, surfacing it in `codenook status`. Add a Bats test that walks one task and asserts ≥ 1 file in `memory/knowledge/`.

### MEDIUM

**E2E-P-004 — Install-injected CLAUDE.md marker block fails its own linter**
- **Where:** `claude_md_linter.py` against the bootloader block written by `install.sh`.
- **What:** Linter reports 5 `forbidden domain token` errors at lines 2252–2295 — every one of them is inside the `<!-- codenook:begin --> … <!-- codenook:end -->` block injected by the installer (mentions of `development` / `plugins/development`).
- **User impact:** Round-1 fix E2E-017 is contradicted: a fresh install + immediate lint is non-clean. Any CI gate that runs the linter post-install will fail.
- **Suggested fix:** Either (a) make the linter skip content **inside** the codenook marker block by default (it's installer-managed), or (b) rewrite the bootloader template to avoid the forbidden tokens (e.g., refer to "the installed plugin" generically and link to README for the name).

**E2E-P-005 — Plan→implement re-dispatch loop when `target_dir` is unset**
- **Where:** `tick.sh` transition logic.
- **What:** Both A and B independently hit the same loop: planner output `verdict: ok` is consumed each tick but `implement`'s entry-questions reject because `target_dir` is missing. The previous phase's output file is never moved/deleted, the missing-field JSON is swallowed, and the only visible signal is `_warning: recover: re-dispatch (no in_flight)`. Both agents had to manually edit `state.json` because the advertised recovery command (`codenook task set --field …`) does not exist (`unknown subcommand: set`).
- **User impact:** Lifecycle is not actually completable from the documented commands alone — every parallel-mode task hits this. Two independent expert agents both required out-of-band JSON editing.
- **Suggested fix:** (a) Implement the `codenook task set` subcommand (or a `task config --field … --value …`); (b) Have `task new --dual-mode parallel` prompt for `target_dir` (entry-question) instead of accepting it post-hoc; (c) Surface the missing-field JSON to stdout/stderr instead of swallowing it.

**E2E-P-006 — `state.example.md` location does not match bootloader description**
- **Where:** Bootloader marker text says "`.codenook/state.example.md` — annotated task `state.json` reference"; the file is indeed at `.codenook/state.example.md`. Original spec/comment hinted it should live under `schemas/`. Minor — the bootloader is consistent with reality, the spec was wrong.
- **User impact:** None observed; documentation-only inconsistency.
- **Suggested fix:** Reconcile the spec table; current layout is fine.

### LOW

**E2E-P-007 — No per-task `audit.jsonl`; events go to global history files**
- **Where:** `.codenook/tasks/<id>/audit.jsonl` is never created; events live in `.codenook/history/{dispatch,hitl}.jsonl` and `.codenook/memory/history/extraction-log.jsonl`.
- **What:** Audit isolation is enforced by `task_id` field rather than by separate files. Functionally correct (no interleaving collisions observed; each task's events parse back cleanly), but differs from the Phase-2 assertion's assumption.
- **User impact:** Anyone tailing per-task audit logs will be surprised. No correctness issue.
- **Suggested fix:** Either start writing `tasks/<id>/audit.jsonl` (mirror or split), or document the global-log model in CLAUDE.md / README.

**E2E-P-008 — `task new --priority` flag advertised but not implemented**
- **Where:** `task_new.sh`. Flag `--priority` is rejected (`unknown arg`).
- **User impact:** Playbook examples and the task spec used `--priority P1`; agents had to retry without it.
- **Suggested fix:** Either implement the flag (just stash priority into state) or remove it from docs / playbooks.

**E2E-P-009 — Tick exit code 1 on benign re-dispatch**
- **Where:** `tick.sh`. When the same phase is re-dispatched (e.g., during the plan→implement loop above), `--json` reports `status: advanced` but the wrapper exits 1.
- **User impact:** Misleading exit code → CI scripts may treat success as failure.
- **Suggested fix:** Reserve exit 1 for genuine runtime errors; use 0 for any state-machine transition (including re-dispatch).

## Phase 6 — Coverage gap analysis

The pre-existing 895 Bats + 21 pytest baseline did not catch any of the 9 findings above. Suggested additions:

1. **`bats/concurrency_state_isolation.bats`** — spawn two `task new` invocations in `&` background, assert distinct sequential `task_id`s, no shared `state.json` mutation, no `.lock` leftover.
2. **`bats/concurrency_history_interleave.bats`** — drive two tasks through HITL gates concurrently, parse `history/hitl.jsonl` and assert events for distinct tasks never have torn lines (each line valid JSON, `task_id` field always present).
3. **`bats/install_kernel_version_stamp.bats`** — assert `state.json.kernel_version == $(cat VERSION)` immediately after `install.sh` (catches `E2E-P-001`).
4. **`bats/install_idempotent_kernel_version.bats`** — re-run install, assert `kernel_version` not stale.
5. **`bats/task_new_entry_question_dual_mode.bats`** — call `task new --title …` without `--dual-mode`, assert JSON output contains `action: entry_question, field: dual_mode, allowed_values: [serial,parallel]` (catches `E2E-P-002`).
6. **`bats/lifecycle_full_walk.bats`** — walk a task from `task new` to `phase=complete` using ONLY the documented commands, assert no `recover: re-dispatch` warnings and ≥ 1 `memory/knowledge/*.md` file at the end (catches `E2E-P-003`, `E2E-P-005`).
7. **`bats/claude_md_linter_postinstall_clean.bats`** — fresh-install in a temp workspace, run the linter, assert 0 errors (catches `E2E-P-004`).
8. **`bats/task_set_subcommand_exists.bats`** — assert `codenook task set --help` exits 0 (catches the gap that `E2E-P-005` workaround relies on).
9. **`pytest test_extraction_pipeline_emits_entries.py`** — feed a fixture role-output containing an `extract:` frontmatter block to the extractor pipeline directly, assert ≥ 1 file appears in `memory/knowledge/`.
10. **`pytest test_tick_exit_code_contract.py`** — table-test of tick scenarios → assert exit codes match the documented contract (catches `E2E-P-009`).

## Phase 7 — Recommendation

**HOLD GA → ship patch v0.11.4** before tagging this as a stable parallel-tasks release.

Rationale:
- Concurrency itself is **healthy** — Phase 2 assertions 2.1–2.4, 2.6–2.10 are all PASS. There is no data corruption, no cross-task leakage, no race fingerprint, no torn write, and the parallel two-agent walk completed end-to-end with both pytests green.
- However, three Round-1 fixes regressed or were never wired up correctly:
  - `E2E-P-001` (kernel_version stamp) is a contract violation that affects every fresh install.
  - `E2E-P-002` (entry-question for dual_mode) is a Round-1 promise this release was supposed to deliver.
  - `E2E-P-003` (extractor produces 0 entries) means the memory layer is observably empty after a full lifecycle, undermining the marketing of the feature.
- `E2E-P-004` (linter ↔ installer self-conflict) is fixable in either component but should not ship unresolved.
- `E2E-P-005` (plan→implement loop) is the single biggest UX papercut: two independent expert agents both had to edit `state.json` by hand.

A tight v0.11.4 patch addressing P-001 / P-002 / P-003 / P-004 / P-005 + the suggested Bats coverage above would be ready for GA. P-006 / P-007 / P-008 / P-009 can roll into v0.12.

---

*Verification artefact only. No source code modified. Generated by GitHub Copilot CLI on 2026-04-20.*

---

## v0.11.4 follow-up — round-2 fix-pack (delivered 2026-04-20)

All 9 findings resolved. Tag `v0.11.4`. Bats 895 → 914, pytest 21 → 32.
Commit SHAs filled in post-push.

| ID         | Severity | Resolution                                                                                | Commit          |
|------------|----------|-------------------------------------------------------------------------------------------|-----------------|
| E2E-P-001  | HIGH     | install.sh exports CN_CORE_VERSION; post-install assertion verifies kernel_version == VERSION | _see git log_ |
| E2E-P-002  | HIGH     | wrapper `task new` returns entry-question JSON + exit 2 when --dual-mode missing          | _see git log_ |
| E2E-P-003  | HIGH     | extractor falls back to `summary` + body when no `extract:` block; integration test added | _see git log_ |
| E2E-P-004  | MEDIUM   | claude_md_linter learned per-token inside-marker allowlist for kernel references          | _see git log_ |
| E2E-P-005  | MEDIUM   | --target-dir flag (default src/); tick pins phase + status=blocked on entry-q for new phase | _see git log_ |
| E2E-P-006  | MEDIUM   | state.example.md moved to .codenook/schemas/; bootloader + installer aligned              | _see git log_ |
| E2E-P-007  | LOW      | dispatch-audit + hitl-adapter tee per-task audit.jsonl                                    | _see git log_ |
| E2E-P-008  | LOW      | --priority P0|P1|P2|P3 implemented (default P2); schema validates                          | _see git log_ |
| E2E-P-009  | LOW      | tick exit-code contract: 0=advanced/done, 2=entry-q, 3=hitl, 1=error                       | _see git log_ |

