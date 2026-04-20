# CodeNook v0.11.0 — Release Report

> **Release**: v0.11.0 · Spec Consolidation & Cleanup
> **Date**: 2026-04-19
> **Push timestamp (UTC)**: 2026-04-19T22:20:57Z
> **Tag SHA (commit)**: `77fe05758e85f87e9b97a8147d715cdc1e006ce6`
> **Annotated tag SHA**: `da295ccc1708493be4e050ff8a8ba454ce31ddeb`
> **Base**: v0.10.0-m10.0 (`dcd9fed`)
> **Branch**: `main`

---

## 1. Decision-list summary (M11.0)

| Tag | Count |
|-----|------:|
| **SPEC-PATCH** | 16 |
| **CODE-FIX** (with bats lock-in) | 2 |
| **DELETE-DEAD-CODE** | 2 |
| **DEFER-v0.12** | 6 |
| **No-op** (already specified) | 1 (A2-5) |
| **Total backlog items addressed** | 21 |

Detailed per-item rationale: `docs/m11-decisions.md`.

### SPEC-PATCH IDs (16)

A1-1, A1-2, A1-3, A1-4, A1-5, A1-7, A1-8 (7 from §A.1) +
A2-1, A2-2, A2-3, A2-4, A2-6, A2-7, A2-8, A2-9, A2-10 (9 from §A.2).

### CODE-FIX IDs (2)

MINOR-04 (`chain_render_residual_slot` diagnostic),
MINOR-06 (`chain_parent_stale` diagnostic).

### DELETE-DEAD-CODE (2)

`_SECRET_PATTERNS` alias, `now_safe_iso` stub (10 LOC removed across 2
files, all 0-caller verified by repo-wide grep).

### DEFER-v0.12 (6)

A1-6 (session-resume schema v2 epic), MEDIUM-04 (snapshot
`fcntl.flock` *cross-lock ordering* — flock itself is implemented in
`memory_index._write_snapshot`; the deferred work is the per-task
`task_lock` ordering), AT-REL-1, AT-LLM-2.1, AT-COMPAT-1, AT-COMPAT-3.

---

## 2. Commits (in order, base → tag)

| SHA | Subject |
|-----|---------|
| `c5907c4` | docs(v0.11) · M11.0 backlog decisions |
| `e1632f9` | docs(v0.11) · M11.1 spec patches (8 inconsistencies + 10 omissions) |
| `26bdea1` | refactor(v0.11) · drop dead code (`_SECRET_PATTERNS` alias + `now_safe_iso` stub) |
| `3611e93` | fix(v0.11) · MINOR-04 + MINOR-06 known-limitation hardening |
| `77fe057` | chore(release) · v0.11.0 |

All 5 commits include
`Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`.

### Push confirmation

```
$ git push --follow-tags origin main
To github.com:cintia09/CodeNook.git
   893af99..77fe057  main -> main
 * [new tag]         v0.11.0 -> v0.11.0
```

Push timestamp (UTC): **2026-04-19T22:20:57Z**.

---

## 3. Tag verification

```
$ git ls-remote --tags origin | grep v0.11.0
da295ccc1708493be4e050ff8a8ba454ce31ddeb	refs/tags/v0.11.0
77fe05758e85f87e9b97a8147d715cdc1e006ce6	refs/tags/v0.11.0^{}
```

Annotated tag object `da295cc` resolves to commit
`77fe057` (`chore(release) · v0.11.0`).

---

## 4. bats sweep counts

| Stage | Total | PASS | FAIL | SKIP |
|-------|------:|-----:|-----:|-----:|
| Baseline (`893af99`, pre-M11) | 847 | 847 | 0 | (existing skips counted as PASS) |
| Post-M11.3 (dead-code removed) | 847 | 847 | 0 | – |
| Post-M11.4 (lock-ins added) | **851** | **851** | **0** | – |

Net delta: **+4 PASS** (4 new lock-in cases under
`tests/v011-known-limitations.bats`):

- `[v0.11] MINOR-04 residual {{SLOT}} after substitution → chain_render_residual_slot diag`
- `[v0.11] MINOR-04 clean prompt → no residual diag emitted`
- `[v0.11] MINOR-06 confirm with stale (done) parent → chain_parent_stale diag, attach proceeds`
- `[v0.11] MINOR-06 confirm with active parent → no stale diag`

---

## 5. Dead-code removal

| File | LOC removed | Lines |
|------|------------:|-------|
| `skills/codenook-core/skills/builtin/_lib/secret_scan.py` | 6 | drop docstring paragraph + module-level `_SECRET_PATTERNS = SECRET_PATTERNS` alias |
| `skills/codenook-core/skills/builtin/session-resume/_resume.py` | 4 | drop unused `now_safe_iso(default="")` stub helper |
| **Total** | **10** | |

Grep verification (run before each deletion, repo-wide, all source
plus tests/fixtures) confirmed 0 active callers.

---

## 6. Real-workspace regression (M11.5)

**Workspace**: `/Users/mingdw/Documents/workspace/development`
(~1000 active tasks: T-0000 .. T-0999, plus production CLAUDE.md).

| Probe | Result |
|-------|--------|
| `install.sh --install` from local source | ✅ exit 0, banner reports v0.11.0 |
| `init.sh .` (idempotent re-init) | ✅ exit 0, no destructive churn |
| `session-resume/resume.sh --workspace . --json` | ✅ exit 0, JSON well-formed; correctly reports `1000 active tasks — pick one?` and active_tasks[0..3] sample |
| `plugin_readonly.py --target <repo> --json` | ✅ exit 0, `writes_to_plugins: []` |
| `claude_md_linter` on `CLAUDE.md` | ✅ exit 0 (19 demonstrative warnings about quoted forbidden tokens — false-positive class, content is *describing* the rule not violating it; no behaviour change vs. v0.10) |
| Re-install after push (latest tag) | ✅ "Downloaded v0.11.0" / "Installed! v0.11.0" |

---

## 7. Open items deferred to v0.12

| ID | Topic | Why deferred |
|----|-------|--------------|
| **A1-6** | session-resume M1-compat key removal | Requires rewriting `m1-session-resume.bats` (10 asserts on legacy keys); packaged as separate "session-resume schema v2" epic |
| **MEDIUM-04** | Cross-lock ordering between snapshot `fcntl.flock` and per-task `task_lock` | Per-call `fcntl.flock` IS implemented in `memory_index._write_snapshot` (since v0.10) and `.lock` cleanup landed in v0.11.2 (DR-011); remaining work is designing the global ordering between the snapshot lock and per-task `task_lock` so concurrent task ticks cannot deadlock against an in-flight memory rebuild. Bundle with multi-process orchestration design. |
| **AT-REL-1** | Manual SIGTERM reviewer procedure | Needs human reviewer manual; out of v0.11 scope |
| **AT-LLM-2.1** | Real-mode LLM guard bats | Out of v0.11 scope |
| **AT-COMPAT-1** | Linux CI matrix | Infra change |
| **AT-COMPAT-3** | `jq`-missing diagnostic bats | Out of v0.11 scope |

---

## 8. Blockers

**None.** All planned M11 work landed within budget. Sweep stayed
green throughout. Push + tag verified end-to-end against
`git@github.com:cintia09/CodeNook.git`.

---

## 9. Verification commands (replayable)

```bash
# Tag in remote:
git ls-remote --tags origin | grep v0.11.0

# Bats sweep:
bats skills/codenook-core/tests/*.bats 2>&1 | tail -5

# Real-workspace probes:
cd /Users/mingdw/Documents/workspace/development
bash $REPO/skills/codenook-core/skills/builtin/session-resume/resume.sh \
  --workspace . --json | jq '.active_tasks | length'
PYTHONPATH=$REPO/skills/codenook-core/skills/builtin/_lib \
  python3 $REPO/skills/codenook-core/skills/builtin/_lib/plugin_readonly.py \
  --target $REPO --json | jq '.writes_to_plugins | length'
```

---

## v0.11.2 follow-up (fix-pack)

Date: 2026-04-20 · Tag: `v0.11.2` · Bats: ≥ 878 / 878 PASS

The deep-review report (`docs/deep-review-v0.11.1.md`) catalogued 14
findings (DR-001 .. DR-014). v0.11.2 lands the high-impact
docs/UX/code-correctness subset; the remainder stays on the v0.12
queue.

### Applied in v0.11.2

| ID | Subject | Fix |
|---|---|---|
| **DR-001** | `plugin_readonly.assert_writable_path` over-blocked when `workspace_root=None` | When `None`, fall back to CWD as the implicit workspace; absolute paths containing a `plugins/` segment but living outside CWD are no longer rejected. New bats lock the contract (4 tests). |
| **DR-002** | Top-level `install.sh` silently rejected positional `<workspace_path>` | Rewrote `install.sh` to accept `bash install.sh <workspace_path>` and delegate to `skills/codenook-core/install.sh`. Idempotent; supports `--dry-run`, `--upgrade`, `--check`, `--no-claude-md`, `--plugin`. |
| **DR-003** | `init.sh` subcommands sold as live in docs but still stubs | Added a status banner + per-subcommand 🚧/✅ table to README, PIPELINE, `docs/architecture.md`, `docs/implementation.md`. Quick-start now points at the live `bash install.sh <ws>` flow. |
| **DR-004** | Source-tree docstrings still cited the removed `docs/v6/...` paths | Repo-wide `sed` over `skills/` + `plugins/` rewrote `docs/v6/<name>-v6.md → docs/<name>.md`. `grep -r docs/v6 skills/ plugins/` now returns 0 matches. |
| **DR-005** | `secret_scan` ruleset too narrow | Added detection for JWT (`eyJ…`), Google API keys (`AIza…`), Slack tokens (`xox[baprs]-…`), generic `Authorization: Bearer …` (≥ 20-char token), and modern GitHub PATs (`ghp_/ghs_/gho_/ghu_/ghr_`, `github_pat_`). 11 new bats (positive + negative). Also added a thin CLI to `secret_scan.py`. |
| **DR-006** | Workspace `CLAUDE.md` left in v5-POC state by installer | New helper `skills/codenook-core/skills/builtin/_lib/claude_md_sync.py` writes/replaces a `<!-- codenook:begin --> … <!-- codenook:end -->` bootloader block in the workspace `CLAUDE.md`. Idempotent (second run = zero diff); user content outside the markers is never touched. Wired into `install.sh`; opt-out via `--no-claude-md`. 5 new bats. |
| **DR-008** | `preflight._preflight.KNOWN_PHASES` hard-coded | `_discover_known_phases()` reads phase ids from the active plugin's `phases.yaml` (resolved via `state["plugin"]` or the single entry in workspace `state.json`). Falls back to a generic superset (legacy + development plugin) when no plugin can be resolved. 3 new bats. |
| **DR-011** | `memory_index._write_snapshot` left a `.lock` file forever | After flock release, `os.unlink(lock_path)`; tolerates the race where another writer recreates it. 1 new bats locks the cleanup. |
| **DR-014** | Reports said MEDIUM-04 fully deferred even though `fcntl.flock` was implemented | Re-worded both the §1 DEFER list and the §7 row to clarify that flock is **implemented** and only the cross-lock ordering with `task_lock` is on the v0.12 queue. |

Also in v0.11.2:

* `skills/codenook-init/` (v4.9.5 legacy initialiser) **deleted** —
  it was missed during the v0.11.1 v5-poc cleanup. Top-level
  `sync-skills.sh` (which only existed to push that legacy skill) is
  removed. Cross-references purged from README, PIPELINE, requirements,
  architecture/implementation docs (historical reports left as-is).
* Architecture diagram (`blog/images/architecture-v0.11.{svg,png}` +
  hero `architecture.png`) redrawn as a strict 4-layer C4 view with
  no module duplicated between Kernel and "Router Agent" layer. The
  router-agent / orchestrator-tick / spawn / dispatch_subagent tiles
  now appear once, inside the Kernel container, alongside the other
  builtin skills and the `_lib/` utilities row.
* Two new bats files: `tests/v011_2-fix-pack.bats` (19 cases),
  `tests/v011_2-install-claude-md.bats` (8 cases). Three legacy
  `m9-plugin-readonly.bats` tests (TC-M9.7-03, -22, -23) updated to
  match the DR-001 contract (chdir to ws; CWD-fallback applies).

### Residual DEFER-v0.12

Out of the original deep-review backlog, these remain on the v0.12
queue (no code changes in v0.11.2):

* **DR-007** — dual-mode preflight enforcement structural guard.
* **DR-009** — `render_prompt.py` JSON-parse fallback hardening.
* **DR-010** — `extract_audit.audit()` hash-chained tamper-evidence.
* **DR-012** — `workspace_overlay` symlink containment check.
* **DR-013** — `_legacy_tick` dry-run state-mutation ordering.
* **A1-6**, **AT-REL-1**, **AT-LLM-2.1**, **AT-COMPAT-1**,
  **AT-COMPAT-3** — unchanged from v0.11.1 release report.
* **MEDIUM-04 (cross-lock ordering only)** — flock + lock cleanup
  shipped; remaining work is the snapshot ↔ task_lock ordering design.

### Verification (v0.11.2)

```bash
cd <repo>
bats skills/codenook-core/tests/                 # 878 / 878 PASS
python3 skills/codenook-core/skills/builtin/_lib/claude_md_linter.py \
  --check-claude-md CLAUDE.md
python3 skills/codenook-core/skills/builtin/_lib/plugin_readonly.py \
  --target . --json
grep -rEn "docs/v6|skills/codenook-init" . \
  --include="*.md" --include="*.sh" --include="*.py" --include="*.yaml" \
  | grep -v 'docs/.*-v0\.11\.1\.md\|docs/.*report\|docs/deep-review'   # 0 hits
python3 skills/codenook-core/skills/builtin/_lib/secret_scan.py \
  README.md PIPELINE.md docs/*.md
```
