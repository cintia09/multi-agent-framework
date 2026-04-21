# CodeNook Pipeline — v0.14 / development v0.2.0

End-to-end walkthrough of how a CodeNook task moves from "user has an
idea" to "ship_signoff approved", using the development plugin's
**`feature` profile** (the longest chain — 11 phases) as the example.

The kernel is `<ws>/.codenook/codenook-core/`. The plugin is
`<ws>/.codenook/plugins/development/`. All runtime state is under
`<ws>/.codenook/tasks/<T-NNN>/`.

---

## 1. The conductor protocol

The CLI session you are using (Claude Code, Copilot CLI) is a **pure
protocol conductor**. Its loop on every user turn is exactly four
steps:

1. **Classify.** Decide whether the user's turn is a CodeNook task
   trigger ("use codenook to …", "open a codenook task", "走
   codenook 流程", …). If not, answer normally — do nothing else.
2. **Invoke `codenook tick`.** Allocate (or reuse) a `T-NNN` id and
   call:
   ```bash
   codenook tick --task T-NNN --json
   ```
   Read the `status` field. Treat its value as opaque: only the
   four branches `advanced`, `waiting`, `done`, `blocked` matter to
   the conductor.
3. **Handle HITL.** When `status == waiting`, list the queue with
   `codenook hitl list` (or read `<ws>/.codenook/hitl-queue/*.json`
   directly), surface each pending entry's `prompt` verbatim, collect
   the user's decision, and call:
   ```bash
   codenook decide --task T-NNN --phase <phase-id-or-gate-id> \
                   --decision <approve|reject|needs_changes> \
                   [--comment "…"]
   ```
4. **Loop.** Tick again. Repeat until `status` is `done` (success)
   or `blocked` (something needs operator action; surface the
   `message_for_user` field verbatim and stop).

The conductor never reads role files, never interprets phase
outputs, never picks a plugin or profile. All of that lives behind
the kernel.

---

## 2. Catalogue + profiles

The development plugin's `phases.yaml` has **two top-level keys**:

- `phases:` — the **catalogue**. A map keyed by phase id; each entry
  defines the role, the expected output path, the gate (if any),
  and feature flags (`supports_iteration`, `allows_fanout`,
  `dual_mode_compatible`, `post_validate`).
- `profiles:` — a map of `task_type → [phase id, …]`. The clarifier
  emits a `task_type` in its frontmatter; the orchestrator caches
  the resolved profile in `state.profile` after the first dispatch
  and walks that ordered list.

The `feature` profile uses every phase in the catalogue:

```
clarify → design → plan → implement → build → review →
submit → test-plan → test → accept → ship
```

### Catalogue table

| # | Phase | Role file | Produces (under `tasks/<T>/`) | Gate | Flags |
|---|-------|-----------|-------------------------------|------|-------|
| 1 | `clarify` | `roles/clarifier.md` | `outputs/phase-1-clarifier.md` | `requirements_signoff` | — |
| 2 | `design` | `roles/designer.md` | `outputs/phase-2-designer.md` | `design_signoff` | `dual_mode_compatible` |
| 3 | `plan` | `roles/planner.md` | `outputs/phase-3-planner.md` | `plan_signoff` | `allows_fanout` |
| 4 | `implement` | `roles/implementer.md` | `outputs/phase-4-implementer.md` | *(none)* | `supports_iteration`, `allows_fanout`, `dual_mode_compatible`, `post_validate` |
| 5 | `build` | `roles/builder.md` | `outputs/phase-5-builder.md` | `build_signoff` | `post_validate` |
| 6 | `review` | `roles/reviewer.md` | `outputs/phase-6-reviewer.md` | `local_review_signoff` | — |
| 7 | `submit` | `roles/submitter.md` | `outputs/phase-7-submitter.md` | `submit_signoff` | — |
| 8 | `test-plan` | `roles/test-planner.md` | `outputs/phase-8-test-planner.md` | `test_plan_signoff` | — |
| 9 | `test` | `roles/tester.md` | `outputs/phase-9-tester.md` | `test_signoff` | `supports_iteration`, `post_validate` |
| 10 | `accept` | `roles/acceptor.md` | `outputs/phase-10-acceptor.md` | `acceptance` | — |
| 11 | `ship` | `roles/reviewer.md` (mode: ship) | `outputs/phase-11-reviewer.md` | `ship_signoff` | — |

`implement` is the only gate-less phase by design — it is the one
phase where rapid iteration is worth more than human approval, and
the downstream `build`, `review`, and `test` gates catch what
matters anyway.

### Phase-by-phase

**1. `clarify` (clarifier).** Turns a vague user request into a
testable spec: ≤3-bullet goal restatement, ≥3 acceptance criteria,
explicit non-goals, numbered ambiguities. Critically, it also emits a
`task_type` frontmatter field — `feature | hotfix | refactor |
test-only | docs | review | design` — that selects the profile. Gate:
`requirements_signoff`. Default profile when ambiguous: `feature`.

**2. `design` (designer).** Drafts the architecture / ADR for the
change. `dual_mode_compatible` means that when the task is started
with `state.dual_mode = parallel`, the orchestrator dispatches `N`
designer agents in parallel and the verdict is the consensus of
their outputs. Gate: `design_signoff`.

**3. `plan` (planner).** Decomposes the design into a concrete
sequenced task list. With `allows_fanout`, the planner may emit
`decomposed: true` in its frontmatter; orchestrator-tick then seeds
child tasks (one per subtask) and pauses the parent until they
complete. Gate: `plan_signoff`.

**4. `implement` (implementer).** Writes the actual code (red →
green → refactor). `supports_iteration` enables loop-back from a
failed `post_validate` (capped by `state.max_iterations`).
`post_validate: validators/post-implement.sh` runs after the agent
returns; failure bumps `state.iteration` and re-dispatches. **No
gate** — the next phase (`build`) catches mechanical breakage.

**5. `build` (builder).** Executes the project's build / lint /
smoke command. Caches the command in `state` for reuse. Pure
mechanical gate: `build_signoff` confirms the build is green and
the cached command still applies.

**6. `review` (reviewer, mode: review).** Local code-review critique
before any external submission. Gate: `local_review_signoff`.

**7. `submit` (submitter).** Records the external review-submission
decision (Gerrit / GitHub PR / skip) and the resulting URL. The
external LGTM is out of orchestrator scope — operator resumes the
tick once it lands. Gate: `submit_signoff`.

**8. `test-plan` (test-planner).** Writes the test document (cases,
fixtures, pass criteria) **before** tests run, so missing scenarios
are caught up front. Gate: `test_plan_signoff`.

**9. `test` (tester).** Runs the tests using the shipped
`test-runner` skill. `supports_iteration` lets a failed
`post_validate` (e.g. tests still red) loop back. Gate:
`test_signoff` is the operator spot-check before user acceptance.

**10. `accept` (acceptor).** Final user acceptance — confirms the
change actually solves the reported problem. Gate: `acceptance`.

**11. `ship` (reviewer, mode: ship).** Final deliver-mode sign-off
checklist. Reuses the reviewer role file but with
`mode: ship` set in the manifest template (`phase-11-reviewer.md`),
so the role file is one source of truth for both review modes.
Gate: `ship_signoff`. Approval transitions the task to
`status: done`.

---

## 3. The 7 profiles

| Profile | Length | Phases | Skips |
|---------|-------:|--------|-------|
| `feature` | 11 | clarify, design, plan, implement, build, review, submit, test-plan, test, accept, ship | — |
| `refactor` | 9 | clarify, design, plan, implement, build, review, test-plan, test, ship | submit, accept |
| `hotfix` | 7 | clarify, implement, build, review, test-plan, test, ship | design, plan, submit, accept |
| `test-only` | 4 | clarify, test-plan, test, accept | design, plan, implement, build, review, submit, ship |
| `docs` | 4 | clarify, implement, review, ship | design, plan, build, submit, test-plan, test, accept |
| `design` | 3 | clarify, design, ship | everything between |
| `review` | 3 | clarify, review, ship | everything between |

The catalogue is the **single source of truth** for phase metadata
(role, gate, flags); the profiles only choose which subset and in
which order.

---

## 4. HITL semantics

Every gate ships in `plugins/development/hitl-gates.yaml` with three
fields: `trigger` (the phase id that opens it), `required_reviewers`
(currently always `[human]`), and a human-readable `description`.
When tick reaches a gated phase and the role's output is consumed,
it materialises an entry in `<ws>/.codenook/hitl-queue/<task>-<gate>.json`
and parks the task with `status: waiting`.

The conductor resolves the gate via:

```bash
codenook decide --task T-NNN --phase <phase-id-or-gate-id> \
                --decision <verb> [--comment "…"]
```

`--phase` accepts either the phase id (e.g. `clarify`) or the gate
id (e.g. `requirements_signoff`) — the CLI resolves either form by
consulting the plugin's `phases.yaml`.

Decision verbs recognised by the orchestrator:

- **`approve`** — the gate passes; tick advances to the next phase
  in the profile.
- **`reject`** — the gate fails terminally; task transitions to
  `status: blocked` with the operator comment recorded in
  `state.history`.
- **`needs_changes`** — the gate fails recoverably; tick re-dispatches
  the same phase (subject to `max_iterations`) so the role can rework
  its output. Equivalent to verdict `needs_revision`.

---

## 5. Memory & extraction at phase boundaries

After every phase output is consumed and `post_validate` (if any)
passes, tick fires
`extractor-batch.sh --task-id T-NNN --phase <phase> --reason after_phase`.
The dispatcher fans out three sub-extractors:

- **`skill-extractor`** — looks for repeated script / CLI invocations
  (≥3 in the phase) and proposes one reusable skill candidate
  written to `memory/skills/<name>/SKILL.md`.
- **`knowledge-extractor`** — pulls declarative findings (decisions,
  conventions, environment notes) into `memory/knowledge/<topic>.md`.
- **`config-extractor`** — captures config decisions into
  `memory/configs/` (when applicable).

All writes are hash-keyed (dedupe via `.index-snapshot.json`) and
recorded line-by-line in `<ws>/.codenook/extraction-log.jsonl`.
Each successful write also regenerates the human-readable
`<ws>/.codenook/memory/index.yaml`, which is what the conductor and
future role agents consult to inventory available memory.

The same dispatcher is invoked with `--reason context-pressure` when
the conductor's local token estimate hits the 80 % watermark; it
returns a non-blocking JSON envelope within ≤200 ms so the
conductor can decide whether to `/clear` or `/compact` without losing
the task's accumulated knowledge.

Full reference: [`docs/memory-and-extraction.md`](docs/memory-and-extraction.md).

---

## 6. Troubleshooting

When a task does not behave as expected, three commands and one file
cover almost every diagnostic question:

```bash
# What does tick think the next step is?
codenook tick --task T-001 --json

# What is the canonical state?
cat .codenook/tasks/T-001/state.json | python3 -m json.tool

# What gates are still open?
codenook hitl list
```

### `status: blocked`

The state machine has stopped advancing. Inspect
`state.history[-1]` (the rejection comment, the failed verdict, or
the `post_validate` exit code is logged there). To resume after
fixing the underlying problem, re-tick. To abandon, `codenook task
set --task T-001 --field status --value cancelled`.

### Gate stuck (`status: waiting` forever)

Either the gate entry was never opened (check
`<ws>/.codenook/hitl-queue/`) or the operator's `decide` call
referenced the wrong `--phase`. List with `codenook hitl list`,
inspect `cat .codenook/hitl-queue/T-001-<gate>.json`, and decide
again with the exact gate id.

### Sub-agent failure

The role agent returned without a valid `verdict` frontmatter, the
expected output file was missing, or `post_validate` exited
non-zero. `tick --json` will surface a `status: blocked` envelope
with `message_for_user` explaining the failure. The dispatched
manifest is at `.codenook/tasks/T-001/prompts/phase-N-<role>.md`
and the (partial) output at `.codenook/tasks/T-001/outputs/phase-N-<role>.md`
— hand-fix the output, re-tick, and the orchestrator will pick up
where it stopped.

### Iteration cap exhausted

`state.iteration >= state.max_iterations` on a `supports_iteration`
phase. Bump the cap with
`codenook task set --task T-001 --field max_iterations --value 6`
and re-tick.
