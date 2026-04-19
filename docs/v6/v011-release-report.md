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

Detailed per-item rationale: `docs/v6/m11-decisions.md`.

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
`fcntl.flock`), AT-REL-1, AT-LLM-2.1, AT-COMPAT-1, AT-COMPAT-3.

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
| **MEDIUM-04** | True `fcntl.flock` on snapshot rebuild | Cross-lock ordering with per-task `task_lock`; bundle with multi-process orchestration design |
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
