# development plugin

A v6 CodeNook plugin that drives software-engineering tasks through a
**profile-aware** pipeline. The clarifier picks one of seven
`task_type` values and the orchestrator walks the matching chain over
the 12-phase catalogue: **clarify → design → plan → dfmea → implement
→ build → review → submit → test-plan → test → accept → ship**.

Built on the v6 plugin framework (see [`docs/architecture.md`](../../docs/architecture.md)).

## Install

Use the top-level installer:

```
python3 install.py --target <workspace> --plugin development --yes
```

The installer validates the manifest, schema, dependencies, secrets,
sizes, and paths, then atomically commits the staged tree to
`.codenook/plugins/development/`.

## Profiles

| `task_type`  | chain                                                                                            |
|--------------|--------------------------------------------------------------------------------------------------|
| `feature`    | clarify → design → plan → dfmea → implement → build → review → submit → test-plan → test → accept → ship |
| `hotfix`     | clarify → implement → build → review → test-plan → test → ship                                   |
| `refactor`   | clarify → design → plan → dfmea → implement → build → review → test-plan → test → ship           |
| `test-only`  | clarify → test-plan → test → accept                                                              |
| `docs`       | clarify → implement → review → ship                                                              |
| `review`     | clarify → review → ship                                                                          |
| `design`     | clarify → design → ship                                                                          |

The clarifier defaults to `feature` if it cannot infer the type. The
resolved profile is cached in `state.profile`.

## Layout

```
plugins/development/
├── plugin.yaml            # install manifest + router surface
├── config-defaults.yaml   # tier_* model defaults + hitl/concurrency
├── config-schema.yaml     # config-validate DSL fragment
├── phases.yaml            # 12-phase catalogue + 7 profile chains
├── transitions.yaml       # profile-keyed ok / needs_revision / blocked
├── entry-questions.yaml   # required state fields per phase
├── hitl-gates.yaml        # 11 gates (every non-implement phase)
├── roles/                 # 11 role profiles (clarifier..acceptor, dfmea-analyst)
├── manifest-templates/    # 12 phase-N-<role>.md dispatch templates
├── skills/test-runner/    # plugin-shipped pytest/npm/go wrapper
├── validators/            # post-{implement,build,submit,test-plan,test}.py
├── prompts/               # criteria-{implement,test,accept}.md
├── knowledge/             # pytest-conventions.md
└── examples/              # seed.json fixtures
```

## Verdict contract

Every role MUST emit a YAML frontmatter at the top of its output file:

```
---
verdict: ok                # or needs_revision / blocked
summary: <≤200 chars>
---
```

`orchestrator-tick.read_verdict` reads only this; the body is for humans.

## Submit → test E2E boundary

For profiles with a `submit` phase, the submitter must record
`submitted_ref` in its frontmatter. The downstream `test-plan` and
`test` phases must target that exact ref.

Local build/smoke/script syntax checks are not real E2E unless they
exercise a deployed/runtime endpoint or device and prove that target is
running the submitted ref. The plugin's post validators enforce this
contract mechanically:

- `post-submit.py` requires `submitted_ref` for real submissions.
- `post-test-plan.py` requires environment + submitted-ref planning.
- `post-test.py` requires submitted-ref-bound execution sections.

## Known gaps (M6 scope)

* The M6 DoD test "diff against v5 baseline" is **skipped** — v5 has
  been fully removed from the repo (see CHANGELOG v0.11.1); semantic
  equivalence is the v6 acceptance bar (§9.5 / decision #T-13).
* The plugin uninstall path is not exercised; M2 ships install only.
  An archive-on-uninstall flow is M7+.

## Task chains (M10 / E2E-008)

Tasks can be linked into parent/child chains for context propagation
and chain-summarized memory. The relevant `state.json` fields are:

| Field | Type | Set by | Purpose |
|---|---|---|---|
| `parent_id` | `T-XXX` \| `null` | `codenook chain link` / `codenook task new --parent` | Direct parent task id. |
| `chain_root` | `T-XXX` \| `null` | Auto-maintained by `task_chain.set_parent` | Cached terminal ancestor for O(1) root lookup. |

The bootloader CLI ships a helper:

```bash
.codenook/bin/codenook chain link  --child T-002 --parent T-001
.codenook/bin/codenook chain show  T-002
.codenook/bin/codenook chain detach T-002
```

The link command refuses cycles (`CycleError`, exit 2), refuses
overwrites without `--force` (`AlreadyAttachedError`, exit 3), and
echoes back `{child, parent_id, chain_root}` so callers can verify the
write took effect.

> **Common mistake.** The schema field is `parent_id`, not `parent`.
> A bare `parent:` key is rejected by `task-state.schema.json`
> (`additionalProperties: false`). Always use the `chain link` helper
> or set `parent_id` explicitly.
