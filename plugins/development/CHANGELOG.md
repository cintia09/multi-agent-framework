# development plugin — changelog

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
