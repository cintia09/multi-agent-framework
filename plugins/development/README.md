# development plugin

A v6 CodeNook plugin that drives software-engineering tasks through an
8-phase pipeline: **clarify → design → plan → implement → test →
accept → validate → ship**.

Built on the v6 plugin framework (`docs/implementation.md` §M6).

## Install

```
init.sh --install-plugin dist/development-0.1.0.tar.gz
```

The M2 12-gate pipeline (`install-orchestrator`) validates the manifest,
schema, dependencies, secrets, sizes, paths, shebangs, and atomically
commits the staged tree to `.codenook/plugins/development/`.

## Layout

```
plugins/development/
├── plugin.yaml            # M2 install manifest + v6 router surface
├── config-defaults.yaml   # tier_* model defaults + hitl/concurrency
├── config-schema.yaml     # M5 config-validate DSL fragment
├── phases.yaml            # 8 phase entries (id/role/produces/gates)
├── transitions.yaml       # ok / needs_revision / blocked table
├── entry-questions.yaml   # required state fields per phase
├── hitl-gates.yaml        # design_signoff, pre_test_review, acceptance
├── roles/                 # 8 role profiles (clarifier..validator)
├── manifest-templates/    # 8 phase-N-<role>.md dispatch templates
├── skills/test-runner/    # plugin-shipped pytest/npm/go wrapper
├── validators/            # post-implement.sh, post-test.sh
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
