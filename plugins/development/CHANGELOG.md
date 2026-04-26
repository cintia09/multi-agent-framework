# development plugin — changelog

## 0.4.0 — memory-first generic skills

Plugin pivot away from hard-coded device / remote-review knowledge:
specifics now live in workspace memory or come from the user via HITL.

### Post-review hardening (same release)

- `acceptor/role.md` — fixed wrong manifest / prompt / output
  references (was `phase-6-acceptor.md`, should be
  `phase-10-acceptor.md` per `phases.yaml`).
- All 10 roles — boilerplate skill descriptor path corrected from
  `skills/<name>/index.md` (which is the *knowledge* convention)
  to the actual skill convention `skills/<name>/SKILL.md`.
- `remote-watch/watch.sh` — failed probes now report
  `status: unknown` and `exit 2` instead of being silently
  classified as `pending` via the catch-all regex.
- `device-detect/detect.sh`, `remote-watch/watch.sh`,
  `test-runner/runner.sh` — argv parsing now arity-checks `$2`
  before dereferencing, so a missing value produces the
  documented `exit 2` instead of a `set -u` unbound-variable
  trap.
- `remote-watch/SKILL.md`, `test-runner/SKILL.md` — added a
  Security / threat-model section documenting that `--config` is
  sourced as shell and is the caller's trust boundary.
- `device-detect/SKILL.md` — `*.yaml` added to `unknown-config`
  detection (matches code); `primary` documented as
  first-seen non-`unknown` bucket (matches code).

### New skills

- `device-detect/` — enumerate generic execution-environment buckets
  (`local-python`, `local-node`, `local-go`, `recorded-env`,
  `custom-runner`, `unknown-config`, `unknown`) under `<target_dir>`
  and emit a `memory_search_hint` so the calling role can do a
  workspace memory lookup before asking the user.
- `remote-watch/` — generic three-tier remote review/CI poller.
  Tier 1 ships defaults for GitHub PR (`gh pr view`) and Gerrit
  (`ssh <host> gerrit query`). Tier 2 sources a `--config <path>`
  shell snippet (typically extracted from a memory entry under
  `memory/knowledge/remote-watch-config-*/`) defining `PROBE_CMD`
  + `STATUS_REGEX_*`. Tier 3 exits with `needs_user_config:true`
  + exit code 3 so the conductor asks the user.

### Changed skills

- `test-runner/runner.sh` — rewritten to a generic three-tier
  dispatcher (markers → `--config <path>` → `needs_user_config:true`
  + exit 3). Previous hard-coded ADB / QEMU semantics removed.

### Changed roles

- `submitter` — step 2 now emits `verdict: blocked` +
  `submission_decision_needed: true` when no remote is detected, so
  the conductor asks the user (manual paste URL / skip / abort) at
  the `submit_signoff` HITL gate. Step 6 invokes the new
  `remote-watch` skill via the same memory-first → ask-user flow
  (single snapshot only — no daemons / continuous tailing).
- `test-planner` — new step 1 asks the user for test scope
  (`smoke` / `new-feature` / `regression` / `full-regression`); new
  step 2 calls `device-detect`, then memory-searches the returned
  hint, then asks the user only when both miss. Output frontmatter
  gains `scope:`, `environment:`, and `environment_source:` fields.

## 0.2.2 — frontmatter fix

- Add missing `name: test-runner` field to `skills/test-runner/SKILL.md` frontmatter so `memory doctor` no longer emits a warning during install.

## 0.2.0 — profile-aware pipeline

Major redesign: the 8-phase serial pipeline is now an 11-phase
**catalogue** that the orchestrator walks via one of seven **profiles**
selected by the clarifier's `task_type` frontmatter.

### Profiles (design §3)

| `task_type`  | chain                                                                                     |
|--------------|-------------------------------------------------------------------------------------------|
| `feature`    | clarify → design → plan → implement → build → review → submit → test-plan → test → accept → ship |
| `hotfix`     | clarify → plan → implement → build → review → submit → test → accept → ship               |
| `refactor`   | clarify → design → plan → implement → build → review → submit → test-plan → test → accept → ship |
| `test-only`  | clarify → test-plan → implement → build → test → accept → ship                            |
| `docs`       | clarify → plan → implement → review → submit → ship                                       |
| `review`     | clarify → review → submit                                                                 |
| `design`     | clarify → design                                                                          |

The clarifier defaults to `feature` when uncertain.

### New phases

* **build** (role: `builder`) — first runtime verification (compile,
  lint, type-check, unit-smoke). HITL ask-once for the project's build
  command, cached at `.codenook/config/build-cmd.yaml`.
* **submit** (role: `submitter`) — git/PR housekeeping (commit, push,
  open PR). Cached PR template and base branch.
* **test-plan** (role: `test-planner`) — plans the integration / e2e
  tests *before* the `test` phase runs them.

### Renamed / repurposed phases

* `validator` is gone; the dual-mode reviewer that used to live there
  now lives inside the `implement` phase as a structured handshake.
* `reviewer` now serves two distinct phases:
  * **review** — local code review (post-build, pre-submit).
  * **ship** — final deliver checklist (post-acceptance).

### HITL gates (10, every non-implement phase)

`requirements_signoff`, `design_signoff`, `plan_signoff`,
`build_signoff`, `local_review_signoff`, `submit_signoff`,
`test_plan_signoff`, `test_signoff`, `acceptance`, `ship_signoff`.
The legacy `pre_test_review` gate is removed.

### Failure routing (design §3)

* Most `needs_revision` / `blocked` verdicts route back to `implement`
  (the canonical fix point).
* In `test-only`, failures route back to `test-plan` (no implement
  phase preceeds the failing test).
* In `design` and `review` profiles, failures self-loop or bounce to
  `clarify` (no code to fix).

### Schema / state

* `state.json` gains optional `task_type` (clarifier hint) and
  `profile` (resolved + cached) fields.
* `phases.yaml` now ships a `phases:` *map* (catalogue) plus a
  `profiles:` map. Backward-compatible: plugins with a flat
  `phases:` list (e.g. `generic`, `writing`) still load via the
  legacy code path.
* `transitions.yaml` is profile-keyed with a `default:` table that
  any profile may inherit from.

### Tests

* New `m2-profiles.bats` — end-to-end smoke for all 6 non-feature
  profiles.
* New `m3-tick-profiles.bats` — unit-level coverage for
  `_resolve_profile`, `_load_pipeline`, and profile-keyed
  `lookup_transition`.
* `m6-development-*.bats` updated for the new catalogue + profiles.
* The `m6-development-e2e.bats` DoD test now drives the full
  `feature` chain (clarify…ship) with HITL approve at every gate.

### Migration

* In-flight tasks pinned to the v0.1.0 8-phase layout continue to run
  unchanged: only plugins whose `phases.yaml` declares a `profiles:`
  map activate the v0.2.0 code path.
* New tasks may seed `task_type` directly in `state.json`; otherwise
  the clarifier's frontmatter pins the profile on its first output.

## 0.1.0 — initial release (M6, built on v6 plugin framework)

* 8-phase pipeline materialised as `phases.yaml`, `transitions.yaml`,
  `entry-questions.yaml`, `hitl-gates.yaml`.
* 8 role profiles in `roles/` authored against the v6 single-workspace
  model (no `~/.codenook/`, no `templates/` paths).
* Plugin-shipped `test-runner` skill + `post-implement` /
  `post-test` validators.
* `criteria-{implement,test,accept}.md` plugin-shipped acceptance rubrics.
* `pytest-conventions.md` plugin-shipped knowledge.
* Manifest exposes both the M2 install-pipeline contract and the v6
  router surface (impl-v6 §M6.2).
