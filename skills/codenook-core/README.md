# codenook-core (v6 kernel skeleton)

This package is the **v6 internal kernel** for CodeNook: shell loader, builtin
agents/skills, and the `init.sh` installer/plugin-manager dispatcher.

It is **not** a drop-in replacement for the v5 PoC (`skills/codenook-v5-poc/`).
v5 remains the working end-to-end reference until v6 reaches feature parity
(see `docs/v6/implementation-v6.md` milestones M1–M7).

## Layout (M1 + M2 + M3)

```
install.sh                  M2 plugin install CLI (12-gate pipeline)
init.sh                     M1 command dispatcher (--install-plugin, --refresh-models, …)
VERSION                     semver of the core skeleton
core/shell.md               main session loader (≤3K hard limit)
agents/                     builtin agent profiles (router, distiller, security-auditor, hitl-adapter, config-mutator)
skills/builtin/
  _lib/                     shared helpers (atomic.py, semver.py)
  config-resolve/           4-layer deep-merge + model symbol expansion
  config-validate/          field-level type/range validation of merged configs
  model-probe/              capability discovery + tier resolution
  secrets-resolve/          ${env:...} / ${file:...} placeholder resolution
  sec-audit/                pre-tick workspace security scanner (also gate G08)
  dispatch-audit/           redacted append-only dispatch logger (500-char cap)
  preflight/                pre-tick sanity check (dual_mode, phase, HITL queue, config overrides)
  task-config-set/          Layer-4 override writer (task-level model config)
  queue-runner/             generic FIFO queue with file locking
  orchestrator-tick/        task state machine advancement
  session-resume/           session state summary (≤1KB)
  # M2 install-pipeline gate skills:
  plugin-format/            G01  well-formedness + escaping-symlink check
  plugin-schema/            G02  declarative plugin.yaml schema validator
  plugin-id-validate/       G03  id regex + reserved + already-installed
  plugin-version-check/     G04  semver + --upgrade strict-greater
  plugin-signature/         G05  optional sha256 sig (CODENOOK_REQUIRE_SIG)
  plugin-deps-check/        G06  requires.core_version comparator
  plugin-subsystem-claim/   G07  declared_subsystems collision detection
  plugin-shebang-scan/      G10  shebang allowlist for +x files
  plugin-path-normalize/    G11  no symlinks; no abs/~/.. in YAML paths
  install-orchestrator/     12-gate runner (invokes G01-G07, G10-G11 +
                            sec-audit (G08) + inline G09/G12)
  # M3 router subsystem:
  router/                   self-bootstrap loader (bootstrap.sh)
  router-context-scan/      ≤2KB workspace inventory consumed every triage
  router-dispatch-build/    500-char dispatch payload assembler + auto-audit
  router-agent/             conversational task-creation router (M8.2 — supersedes
                            M3 router-triage, removed in M8.7)
tests/                      bats-core test suites (run: `bats tests/`)
tests/fixtures/plugins/     static plugin fixtures (one per gate failure mode)
```

## Status

- M1.1–M1.4 — kernel skeleton, config/model subsystem, agent profiles, post-review fixes
- M2.1–M2.2 — Plugin install pipeline (12-gate `install.sh`)
- **M3.1 — Router + self-scan (this drop):**
  - `router/bootstrap.sh` — first sub-agent dispatched by main session;
    self-bootstraps from agents/router.md + core/shell.md + state.json +
    each installed `plugin.yaml`; resolves model to `tier_strong` (#44)
  - `router-context-scan/scan.sh` — ≤2KB workspace inventory (installed
    plugins, active tasks, HITL queue, fan-out subtasks, size warnings);
    bounded walks short-circuit at 10K files / 100MB
  - `router-triage/triage.sh` — decision: chat / skill / plugin / hitl,
    with priority builtin > plugin > chat > hitl; tied plugin matches
    escalate to hitl  *(removed in M8.7; see router-agent skill / M8.2)*
  - `router-dispatch-build/build.sh` — assembles the ≤500-char dispatch
    payload (decision #T-3), truncates user_input to 200 chars + ellipsis,
    auto-invokes dispatch-audit
  - Extended `agents/router.md` with Self-bootstrap / Triage rules /
    Dispatch contract sections
  - 48 new bats cases (total 343)
- M4+ — pending (orchestrator-tick, session-resume, HITL adapter)

## ⚠️ Plugin-author note — SemVer pre-release precedence during M2

Per [SemVer §11.4](https://semver.org/#spec-item-11), `0.2.0-m2.1` sorts
**before** `0.2.0` (a pre-release version is *less than* the same version
without a pre-release tag). While core is on `0.2.0-m2.x`, plugins that
need "M2 or newer" must declare their floor with an explicit pre-release:

```yaml
# plugin.yaml
requires:
  core_version: '>=0.2.0-m2'     # ✅ matches 0.2.0-m2.1, 0.2.0-m2.2, 0.2.0, ...
  # core_version: '>=0.2.0'      # ❌ rejects every M2 pre-release build
```

See `skills/builtin/plugin-deps-check/SKILL.md` for the full constraint
syntax. Plain `>=0.2.0` becomes correct once core ships final `0.2.0`.

## Running tests

```bash
cd skills/codenook-core
bats tests/
```

Requires: bash, jq, python3 (with PyYAML), bats-core ≥ 1.5.
