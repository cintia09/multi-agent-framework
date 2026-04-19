# CodeNook v0.11 — Backlog Decisions (M11.0)

> Source inputs:
> - `docs/v6/requirements-v0.10.md` §A.1 (8 inconsistencies) + §A.2 (10 omissions)
> - `docs/v6/acceptance-execution-report-v0.10.md` (13 PARTIAL + 4 SKIP)
> - `CHANGELOG.md` v0.10.0-m10.0 → Known limitations (MEDIUM-04, MINOR-04, MINOR-06)
>
> Decision tags: **[SPEC-PATCH]** = update docs to match correct code behaviour;
> **[CODE-FIX]** = code is wrong, change source + add bats lock-in;
> **[DELETE-DEAD-CODE]** = unused code/keys to remove;
> **[DEFER-v0.12]** = risk too high or constitutes its own epic.

---

## A. v0.10 §A.1 — Spec/Code Inconsistencies (8)

| ID | Topic | Decision | Rationale |
|----|-------|----------|-----------|
| A1-1 | `dual_mode` default = `serial` | **[SPEC-PATCH]** | Code behaviour (preflight only enforces field when `total_iterations > 1`) is correct & ergonomic; clarify spec to say "optional, default `serial`". |
| A1-2 | Chain `max_depth` library default `None` vs. spec "default 10" | **[SPEC-PATCH]** | Library staying unbounded is the intended composable default; the protective bound (100) lives at the router-call site per `task-chains-v6.md` §6. Reconcile §3.5 + §7.3 wording. |
| A1-3 | `plugin.yaml.sig` "first non-blank token" lenient compare | **[SPEC-PATCH]** | Lenient compare is intentional (allows comments). Document the rule in FR-PLUGIN-G05 + §6.5. |
| A1-4 | extractor "24h idempotency" actually permanent (no rotation) | **[SPEC-PATCH]** | Spec wording rewritten: "idempotent on (task,phase,reason) until trigger-key file is rotated by the operator (no automatic 24h expiry in v0.10/v0.11)". Issue tracked as v0.12 candidate (key rotation). |
| A1-5 | secret_scan = 9 patterns (spec mentions "10") | **[SPEC-PATCH]** | Code is the source of truth; correct the count to 9 in all spec/AT references. |
| A1-6 | session-resume M1-compat keys retained | **[DEFER-v0.12]** | Removal requires rewriting `m1-session-resume.bats` (10 asserts on legacy keys). Treat as a separate "session-resume schema v2" epic to keep this release surgical. Documented in §C below. |
| A1-7 | router-agent `--confirm` exit 4 covers parse + validation errors | **[SPEC-PATCH]** | Code's broader exit-4 mapping is the operationally useful behaviour. Spec FR-ROUTER-2 + §6.5 row clarified to enumerate "draft missing / parse error / required-field validation / parent_attach_failed → 4". |
| A1-8 | G01 vs G11 symlink policy differ | **[SPEC-PATCH]** | Two-gate split is intentional defence-in-depth. Spec FR-PLUGIN-G01/G11 + NFR-SEC-5 wording made explicit. |

---

## B. v0.10 §A.2 — Spec Omissions (10)

All ten are existing, deliberate code behaviours not yet documented. **All decision = [SPEC-PATCH]**: add a one-paragraph "Implementation note" under the appropriate FR.

| ID | Topic | Spec landing site |
|----|-------|-------------------|
| A2-1 | `plugin_readonly` static CLI mode + default test-fixture exclusion | FR-SKILL-2 implementation note |
| A2-2 | `parent_suggester` EN+ZH stopword list | FR-CHAIN-5 implementation note |
| A2-3 | `task_lock` 300 s stale-PID threshold + "unparsable payload never unlinked" | FR-ROUTER-3 (already half-spec'd; add 300 s explicit) |
| A2-4 | `memory_gc` skips `promoted=true` entries | FR-MEM-4 implementation note |
| A2-5 | `config-resolve` fallback chain `strong→balanced→cheap→opus-4.7` | FR-LLM-1 implementation note |
| A2-6 | `dispatch-audit` redaction = 9 patterns from `secret_scan` | FR-EXTRACT-5 implementation note |
| A2-7 | router-agent `--user-turn-file -` reads stdin | FR-ROUTER-2 + CLI table footnote |
| A2-8 | distiller `expr_eval` sandbox blocks `__` and `import` | FR-DIST-1 implementation note |
| A2-9 | `extractor-batch` uses `nohup` for detached fan-out | FR-EXTRACT-4 implementation note |
| A2-10 | `plugin_manifest_index.DEFAULT_PRIORITY = 100` | FR-PLUGIN-MANIFEST + §5.6 row |

---

## C. M10 Known Limitations (CHANGELOG)

| ID | Topic | Decision |
|----|-------|----------|
| MEDIUM-04 | Snapshot rebuild TOCTOU | **[SPEC-PATCH]** + small contract hardening. Adding `fcntl.flock` on `.chain-snapshot.json` rebuild paths is feasible (~30 LOC) but requires careful interaction with the per-task `task_lock` already held by callers; risk of cross-lock ordering. **Decision**: strengthen documentation of the single-process contract + add an explicit `chain_snapshot_rebuild_locked` audit hook around the rebuild, but defer real `flock` to v0.12 along with multi-process orchestration support. |
| MINOR-04 | `chain_summarize` substitution recursion | **[CODE-FIX]** | Add 1-line guard: post-substitution, scan rendered output for residual `{{TASK_CHAIN}}` token; emit `chain_render_residual_slot` diagnostic audit. |
| MINOR-06 | `cmd_prepare` vs `cmd_confirm` parent-suggestion staleness | **[CODE-FIX]** | At `cmd_confirm` time, if `draft.parent_id` resolves to a task whose `status ∈ {done, cancelled}`, emit `chain_parent_stale` diagnostic audit before proceeding. Behaviour stays permissive (no exit-4) to match existing "stale suggestion" semantics. |

---

## D. Dead-code candidates (M11.3)

| Candidate | Decision | Notes |
|-----------|----------|-------|
| `_lib/secret_scan._SECRET_PATTERNS` underscore alias | **[DELETE-DEAD-CODE]** if 0 callers | grep first |
| `_resume.py` M1-compat keys (A1-6) | **[DEFER-v0.12]** | See A1-6 |
| Commented-out blocks | scan during M11.3 | |
| `now_safe_iso` in `_resume.py` (defined, never called) | **[DELETE-DEAD-CODE]** if 0 callers | grep first |
| Other `_lib` helpers with 0 callers | scan during M11.3 | |

---

## E. Acceptance-report SKIP items

| ID | Decision |
|----|----------|
| AT-REL-1 (manual SIGTERM) | **[DEFER-v0.12]** — needs reviewer manual procedure. |
| AT-LLM-2.1 (real-mode guard bats) | **[DEFER-v0.12]** — out of v0.11 scope. |
| AT-COMPAT-1 (Linux CI matrix) | **[DEFER-v0.12]** — infra change. |
| AT-COMPAT-3 (jq-missing diagnostic bats) | **[DEFER-v0.12]** — out of v0.11 scope. |

---

## F. Counts

| Tag | Count |
|-----|-------|
| SPEC-PATCH | 16 (A1: 7, A.2: 10 — note A1-2 is also a spec-only fix; MEDIUM-04 partial spec) − overlap |
| CODE-FIX | 2 (MINOR-04, MINOR-06) |
| DELETE-DEAD-CODE | 2 candidates pending grep verification |
| DEFER-v0.12 | 6 (A1-6, MEDIUM-04 lock impl, AT-REL-1, AT-LLM-2.1, AT-COMPAT-1, AT-COMPAT-3) |

Final tallies will be reported in `v011-release-report.md` after execution.
