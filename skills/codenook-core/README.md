# codenook-core (v6 kernel skeleton)

This package is the **v6 internal kernel** for CodeNook: shell loader, builtin
agents/skills, and the `init.sh` installer/plugin-manager dispatcher.

It is **not** a drop-in replacement for the v5 PoC (`skills/codenook-v5-poc/`).
v5 remains the working end-to-end reference until v6 reaches feature parity
(see `docs/v6/implementation-v6.md` milestones M1–M7).

## Layout (M1)

```
init.sh                     command dispatcher (--install-plugin, --refresh-models, …)
VERSION                     semver of the core skeleton
core/shell.md               main session loader (≤3K hard limit)
skills/builtin/
  config-resolve/           4-layer deep-merge + model symbol expansion
  model-probe/              capability discovery + tier resolution
tests/                      bats-core test suites (run: `bats tests/`)
```

## Status

- M1.1 — init.sh skeleton, shell.md, config-resolve, model-probe (this drop)
- M1.2+ — pending (see implementation doc §M1)

## Running tests

```bash
cd skills/codenook-core
bats tests/
```

Requires: bash, jq, python3 (with PyYAML), bats-core ≥ 1.5.
