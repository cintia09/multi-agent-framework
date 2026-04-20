# CodeNook v0.11.1 Deep Review

**Reviewer**: Copilot CLI (autonomous deep-review agent)
**Date**: 2026-04-20
**Source**: `cintia09/CodeNook` @ `a7bb309` (tag `v0.11.1`)
**Bats baseline**: 851 / 851 PASS (re-confirmed in this review)
**Workspace under test**: `/Users/mingdw/Documents/workspace/development`

---

## 1. Install Verification

### 1.1 What was actually run

The task spec asked for `bash install.sh /Users/mingdw/Documents/workspace/development`. The
top-level `install.sh` (v0.11.1) **does not accept a workspace path**; the positional
argument falls through to the `*)` branch of its case statement and prints
`Unknown option: /Users/mingdw/...` to stderr (see DR-002). This is a UX regression
relative to the documented Quick-Start flow.

The plugin install therefore had to be performed via the **kernel installer**
(`skills/codenook-core/install.sh`):

```
bash skills/codenook-core/install.sh \
     --src plugins/development \
     --workspace /Users/mingdw/Documents/workspace/development
→ ✓ INSTALLED: plugin development 0.1.0   (exit 0)
```

A `--dry-run` first run was clean (`✓ DRY-RUN OK`).

### 1.2 Post-install workspace layout

```
/Users/mingdw/Documents/workspace/development/.codenook/
├── memory/                        # (pre-existed from prior usage)
│   ├── config.yaml
│   ├── history/                   (empty — no extraction-log.jsonl yet)
│   ├── knowledge/                 (~1000 k-*.md files — from earlier run, not from install)
│   ├── skills/                    (empty)
│   ├── .index-snapshot.json + .lock
│   └── .gitignore
├── plugins/development/           ← created by this install (0700, read-only intent)
│   ├── plugin.yaml, phases.yaml, transitions.yaml, hitl-gates.yaml, …
│   ├── roles/{clarifier,designer,implementer,tester,acceptor,validator,reviewer}.md
│   ├── skills/, validators/, prompts/, knowledge/, examples/
│   └── manifest-templates/
├── state.json                     # {"installed_plugins":[{"id":"development","version":"0.1.0"}]}
└── tasks/                         (1000+ tasks T-0000..T-099x, pre-existing)
```

VERSION verification: source repo `cat VERSION` → `0.11.1`. The workspace has no
`.codenook/VERSION` file (kernel doesn't write one); only `state.json` records
the installed plugin version (`0.1.0`).

### 1.3 Idempotency

| Probe | Result |
|---|---|
| 2nd `install.sh --src plugins/development --workspace …` (no flag) | `[G03] id 'development' already installed; use --upgrade` (gate fires; no clobber). Exit 0 from `tail` pipeline; orchestrator returns 3 internally. |
| 3rd run with `--upgrade` (same version) | `[G04] --upgrade rejected: would downgrade or no-op (installed=0.1.0, new=0.1.0)` |

Idempotency is **enforced** by the install-orchestrator's G03/G04 gates. ✅

### 1.4 User-file safety

`mtime` snapshot before/after the install for the four user-authored paths:

| Path | mtime | Touched by install? |
|---|---|---|
| `CLAUDE.md` | `Apr 18 07:55:30` (unchanged) | **No** |
| `scratch/` | `Apr 18 09:13:27` (unchanged) | No |
| `src/` | `Apr 18 09:02:59` (unchanged) | No |
| `tests/` | `Apr 18 09:07:53` (unchanged) | No |

The kernel installer is correctly scoped to `.codenook/plugins/<id>/` and
`.codenook/state.json`. **No user file was modified.** ✅

The task expectation that *"the workspace CLAUDE.md should have been augmented
with the codenook router-agent block"* is **not what the v0.11.1 installers do**:
neither `install.sh` nor `skills/codenook-core/install.sh` writes or augments
`CLAUDE.md`. The user's existing `CLAUDE.md` still references v5.0 POC bootloader
content (see DR-006).

### 1.5 Quality-gate spot checks (executed in this review)

| Gate | Probe | Result |
|---|---|---|
| `secret_scan.scan_secrets` | AWS, OpenAI, ghp_, postgres URI, 10.x | All flagged ✅ |
| Same | JWT (`eyJ…`), Google API (`AIza…`), Slack (`xoxb-`) | **All MISSED** — see DR-005 |
| `plugin_readonly.assert_writable_path` | `/tmp/.codenook/plugins/foo/x.md` (no ws) | Raises `PluginReadOnlyViolation` ✅ |
| Same | `/Users/me/plugins-monorepo/.codenook/state.json` (no ws) | Correctly **NOT** raised (segment match is exact) ✅ |
| `plugin_readonly.py --target _lib --json` | static scan of kernel | 26 files, 0 hits ✅ |
| `claude_md_linter.py` on workspace `CLAUDE.md` | | 0 errors / 0 warnings ✅ |
| `bats skills/codenook-core/tests/` | full sweep | **851 / 851 PASS** ✅ |

---

## 2. Findings (severity-ordered)

### CRITICAL

*(none — no security holes or data-loss bugs found in v0.11.1)*

### HIGH

#### DR-001 — `plugin_readonly.assert_writable_path` over-blocks when called with `workspace_root=None`
- **Where**: `skills/codenook-core/skills/builtin/_lib/plugin_readonly.py:100-153` (callers: `_lib/router_context.py:221`, `_lib/draft_config.py:153`)
- **What**: Two production call sites pass `workspace_root=None`. In that mode the guard scans **every** segment of the *absolute* resolved path for the literal name `plugins`. Any contributor whose workspace lives somewhere under a directory named `plugins` (e.g. `/home/me/code/plugins/myproj/.codenook/...`, or this very repo's `/.../CodeNook/plugins/...` source tree being used as a workspace) will have **every router-context and draft-config write rejected** with `PluginReadOnlyViolation`.
- **Why it matters**: Silent fail-closed in a code-path that runs every router turn → router-agent prep crashes; reproducible only on certain absolute paths, so it will be missed in CI.
- **Suggested fix**: Both call sites already know their workspace; thread `workspace_root` through and treat the un-rooted call as deprecated (raise `ValueError` when neither `workspace_root` nor an explicit opt-out is given).

#### DR-002 — Top-level `install.sh` quietly rejects positional workspace path documented in README
- **Where**: `install.sh:253-261` and `README.md:107-129`.
- **What**: `install.sh`'s `case "${1:-}"` falls through to `*) echo "Unknown option: $1"; usage; exit 1`. README §"Quick Start" tells users to pipe the script via curl into `bash`, which works, but the deep-review task spec, several internal docs, and intuition all suggest `bash install.sh <workspace>`. There is no `--workspace` flag and the script silently delegates plugin install to the *kernel* `init.sh --install-plugin …` — which is itself a stub (DR-003).
- **Why it matters**: First-time users following the README will experience two confusing failures back-to-back (positional rejected, then `init.sh --install-plugin → "TODO: not implemented in M1 skeleton"`).
- **Suggested fix**: Either (a) accept `--workspace <dir>` and shell out to `skills/codenook-core/install.sh`, or (b) update README to point users directly at the kernel installer and remove the misleading `init.sh --install-plugin` example.

#### DR-003 — `skills/codenook-core/init.sh` is documented as the workspace seeder/plugin manager but every non-meta subcommand is still a stub
- **Where**: `skills/codenook-core/init.sh:42-88`; doc claims in `README.md:115-127`, `docs/architecture.md` (multiple), `docs/release-report-v0.11.md`.
- **What**: `init.sh` (no args) prints USAGE and exits 0; it does **not** create `.codenook/`. `--install-plugin`, `--uninstall-plugin`, `--scaffold-plugin`, `--pack-plugin`, `--upgrade-core` all do `stub "<name>"` → `exit 2`. Only `--version`, `--help`, `--refresh-models` are real. README §1 nonetheless presents them as the canonical install path.
- **Why it matters**: The shipped onboarding flow does not work as documented. Reviewers/users will hit `TODO: --install-plugin not implemented in M1 skeleton` on the very first command.
- **Suggested fix**: Either implement `--install-plugin` as a thin wrapper around `skills/codenook-core/install.sh` (single-line `exec`), or aggressively prune the stubs from the help text and docs and point at the working installer.

#### DR-004 — Source-tree docstrings still reference `docs/v6/...` paths after the v0.11.1 docs flatten
- **Where**: 14+ `_lib` modules — `chain_summarize.py:10,43`, `claude_md_linter.py:6,9`, `draft_config.py:9`, `knowledge_index.py:6`, `memory_gc.py:5,217`, `memory_layer.py:13`, `parent_suggester.py:3`, `plugin_manifest_index.py:9`, `plugin_readonly.py:23`, `router_context.py:12`, `task_chain.py:3,135`. Also `workspace_overlay.py:18`.
- **What**: Commit `a7bb309` ("flatten docs/v6 → docs/") removed the `docs/v6/` directory but module docstrings still cite `docs/v6/router-agent-v6.md`, `docs/v6/memory-and-extraction-v6.md`, `docs/v6/task-chains-v6.md`. The paths and the `-v6` suffixed filenames no longer exist in the repo.
- **Why it matters**: Every contributor following a docstring breadcrumb hits a 404. Static doc-link checkers would also flag these once they are extended to scan source comments.
- **Suggested fix**: Repo-wide rewrite `docs/v6/<name>-v6.md → docs/<name>.md` in all `*.py` and `SKILL.md` files. Single sed pass.

#### DR-005 — `secret_scan` ruleset is too narrow to satisfy its own README claim
- **Where**: `skills/codenook-core/skills/builtin/_lib/secret_scan.py:18-34`; advertised by `README.md:105` ("`secret_scan` enforce[s] that nothing outside `tasks/` and `memory/` is mutated by the kernel").
- **What**: The 9 rules cover AWS keys, OpenAI keys, GitHub PATs (only `ghp_`), RSA private-key headers, RFC1918 IPs, and DB connection strings. Verified misses: **JWTs (`eyJ…`), Google API keys (`AIza…`), Slack tokens (`xoxb-/xoxa-/xoxp-`), generic Bearer tokens, GitHub fine-grained PATs (`github_pat_…`), Azure storage keys, `password=` / `secret=` k=v patterns, SSH private keys without the BEGIN header line.** Extractors that ingest user-pasted text into `.codenook/memory/knowledge/` will silently let any of these through.
- **Why it matters**: This is a fail-close gate in the extraction pipeline; narrow coverage gives a false sense of security for the most common modern leak shapes.
- **Suggested fix**: Add the missing patterns above (most are <10 LOC) and split the rule set into "high-confidence" (refuse) vs. "advisory" (warn) tiers so additions don't have to be perfectly low-FP.

### MEDIUM

#### DR-006 — Workspace `CLAUDE.md` is left in a v5-POC state; no v0.11.1 installer touches it
- **Where**: `/Users/mingdw/Documents/workspace/development/CLAUDE.md` (header: *"Bootloader (CodeNook v5.0 POC)"*) — `install.sh` and `skills/codenook-core/install.sh` do not modify any user file.
- **What**: The deep-review task spec, the README onboarding text, and `docs/architecture.md` §3.1 all imply that a v0.11.1 workspace should be driven by a router-agent / shell.md bootloader. After install, the v0.11.1 router/orchestrator stack is on disk but nothing tells the user's main session about it. The user's bootloader still references the obsolete `security-auditor` and "load and embody the CodeNook Orchestrator" v5 protocol, which no longer matches the v0.11.1 dispatch model.
- **Why it matters**: First-turn UX is broken: claude/copilot will boot the v5 protocol, look for v5 paths, and silently drift.
- **Suggested fix**: Ship a `claude_md_template.md` snippet plus an opt-in flag (`install.sh … --augment-claude-md`) that appends a clearly delimited `<!-- codenook:bootloader vX.Y -->` block; refuse if a non-matching block already exists.

#### DR-007 — Dual-mode preflight enforcement diverges between modern and legacy paths
- **Where**: `skills/codenook-core/skills/builtin/preflight/_preflight.py:33` (legacy) vs. `skills/codenook-core/skills/builtin/orchestrator-tick/_tick.py:411-414` + `plugins/development/entry-questions.yaml`.
- **What**: The user's previously-flagged "task created with `dual_mode: null` should be re-prompted before first advancement" is **fixed in the modern path**: `tick()` calls `check_entry_questions()` for the `clarify` phase, which lists `dual_mode` as required; the task is correctly blocked with `Please answer first: dual_mode`. **However**, in `_tick.py:411-414` `state.get("dual_mode") == "parallel"` falls through to serial dispatch when the value is `None`, so any code path that bypasses `check_entry_questions` (e.g. a phase that does not list `dual_mode` in its required set, like `implement` for a re-entered task whose state was edited by hand) silently treats the task as serial. Subtask seeding at line 358 also defaults to `"serial"` without preflight on the child.
- **Why it matters**: The fix relies on a plugin-level YAML stanza, not a structural invariant. Future plugins or hand-edited state can re-introduce the bug.
- **Suggested fix**: Add a structural guard inside `dispatch_role` / `seed_subtasks` that raises if `state.get("dual_mode") not in ("serial","parallel")`. Make `dual_mode is None` an explicit blocked status, not a silent serial.

#### DR-008 — `preflight._preflight.KNOWN_PHASES` is hard-coded and inconsistent with the development plugin's actual phases
- **Where**: `skills/codenook-core/skills/builtin/preflight/_preflight.py:37`; phases in `plugins/development/phases.yaml`.
- **What**: `KNOWN_PHASES = ["start","implement","test","review","distill","accept","done"]`. Development plugin phases are `clarify, design, plan, implement, test, accept, validate, ship`. Five of those eight are not in the whitelist (`clarify`, `design`, `plan`, `validate`, `ship`) and `review`/`distill` in the whitelist correspond to no plugin phase. Today the legacy preflight is only reached when `state["plugin"]` is missing (`_tick.py:799`), so plugin-aware tasks dodge it; but the script is exposed as `preflight.sh` and is documented in `docs/requirements.md:785` as the universal six-check gate.
- **Why it matters**: Anyone running the documented `preflight.sh --task T-NNN` against a development-plugin task will get bogus `unknown_phase: clarify` errors.
- **Suggested fix**: Read the phase whitelist from the plugin's `phases.yaml` instead of hard-coding it.

#### DR-009 — `router-agent/render_prompt.py` first-tick subprocess uses a fragile JSON-parse fallback
- **Where**: `skills/codenook-core/skills/builtin/router-agent/render_prompt.py:567-587`.
- **What**: `tick.sh --json` stdout is parsed by `json.loads(proc.stdout.strip().splitlines()[-1])`. When `tick.sh` prints any diagnostic before the JSON line (it does: `tick.sh: dry-run mode, …` etc.), the last line is the JSON, so this works for the happy path. But on `splitlines() == []` (empty stdout, common on early `tick.sh: state.json not found` exit) we get `IndexError → Exception` → `tick_status = "ok"` because `proc.returncode == 0` is falsy. Wait — returncode is 2 in that case → `"rc=2"`. Acceptable. Real risk: a future `--json` change that wraps the payload in trailing whitespace lines will silently flip the status to `rc=0`-derived strings.
- **Why it matters**: Status reporting on the user-visible router output silently drifts from reality.
- **Suggested fix**: Parse only lines that look like JSON objects (`startswith("{")`); if none, surface `tick_status = "no_json"` explicitly rather than falling back to returncode.

#### DR-010 — `extract_audit.audit()` writes plain-JSONL with no hash chain or sequence number
- **Where**: `skills/codenook-core/skills/builtin/_lib/extract_audit.py:38-55`; consumed by `memory_layer.append_audit`.
- **What**: The audit log is the canonical record of every secret-rejection, plugin-readonly violation, and extraction-pipeline outcome (FR-RO-1, FR-RO-2). It is appended in plaintext with no hash-chained `prev_sha256`, no per-entry sequence, no fsync barrier between entries, and no out-of-band "I just truncated this log" record. Anyone with FS access (which is anyone running the agent) can rewrite history undetectably.
- **Why it matters**: Tamper-evidence is a stated goal of the read-only / fail-closed design; without a chain, the audit log cannot be relied on as evidence.
- **Suggested fix**: Add a `prev_sha256` field computed over the canonical JSON form of the previous record, plus a one-time `seq=0` genesis entry written by `init_memory_skeleton`. Verifier ships as `extract_audit.py --verify`.

#### DR-011 — `memory_index._write_snapshot` leaves a `.lock` file in the workspace memory dir forever
- **Where**: `skills/codenook-core/skills/builtin/_lib/memory_index.py:112-119`.
- **What**: The lock file (`.index-snapshot.json.lock`) is created with `os.O_CREAT` and `flock`-locked, but never `os.unlink`-ed. Confirmed in the live workspace: `/Users/mingdw/Documents/workspace/development/.codenook/memory/.index-snapshot.json.lock` has size 0 and persists across runs. This is also the reason `MEDIUM-04` in the v0.11 release report is listed as "deferred to v0.12" — but the *flock itself is now implemented*; the deferred work is the cross-lock ordering with `task_lock`. The release-report wording undersells the current state.
- **Why it matters**: Cosmetic-but-confusing: contributors investigating "what is this dot-file" will look for a write-side bug. Also clutters `memory_gc` walks if not explicitly skipped.
- **Suggested fix**: Either unlink the lockfile on success in a `finally`, or document its presence in `memory_layer.README` and ensure GC walks treat `.lock` as a normal hidden file.

### LOW

#### DR-012 — `workspace_overlay.discover_overlay_skills` resolves symlinks without containment check
- **Where**: `skills/codenook-core/skills/builtin/_lib/workspace_overlay.py:71-84`.
- **What**: `entry.resolve()` returns the symlink target without verifying it stays under `overlay_root`. A workspace owner who symlinks `user-overlay/skills/X` to `/etc` would have `discover_overlay_skills` happily return `Path('/etc')`. The threat model is intra-tenant (workspace owner = attacker against themself), so impact is bounded, but the function shouldn't promise containment without enforcing it.
- **Suggested fix**: After resolve, assert `resolved.is_relative_to(overlay_root.resolve())`; skip with a warning when not.

#### DR-013 — `_legacy_tick` writes `state` after a preflight failure even when `--dry-run` was the user's intent in some paths
- **Where**: `skills/codenook-core/skills/builtin/orchestrator-tick/_tick.py:669-672` & `685-692`.
- **What**: `if not dry_run: atomic_write_json(state_file, state)` is correct, but the code mutates `state` (via `_legacy_log`) before the dry-run check happens at the call site, so a developer using `_legacy_tick` programmatically with `dry_run=False` (the default) gets state mutation as a side effect of *failed* preflight. Mostly cosmetic in production because legacy-tick is only triggered by missing `plugin` field, but worth noting.
- **Suggested fix**: Defer the `_legacy_log` mutation until *after* the dry-run gate.

#### DR-014 — `cleanup-report-v0.11.1.md` and `release-report-v0.11.md` still describe MEDIUM-04 as fully deferred even though `_write_snapshot` now uses `fcntl.flock`
- **Where**: `docs/release-report-v0.11.md:43` and §7 ("MEDIUM-04 | True `fcntl.flock` on snapshot rebuild").
- **What**: The flock IS implemented (DR-011 above). The remaining v0.12 work is *cross-lock ordering with `task_lock`*, not "implement flock". The two-line description in §7 is misleading.
- **Suggested fix**: Re-word the §7 entry to "MEDIUM-04 — design cross-lock ordering between `_write_snapshot` flock and per-task `task_lock`".

---

## 3. Strengths

- **Atomic-write hygiene** (`_lib/atomic.py` + `memory_layer._atomic_write_text` + `memory_index._write_snapshot`) is consistent across writers: tempfile in same dir → fsync → `os.replace`. No partial-write race observed.
- **Install-orchestrator gate set** (G01–G12) is genuinely fail-closed: idempotency probes (G03, G04) work as advertised; subsystem-claim collisions (G07) prevent silent overwrite.
- **`plugin_readonly` static + runtime layering** is a real two-layer defence (CLI scanner caught zero false positives on the live `_lib`; runtime guard correctly distinguishes exact `plugins` segment from substrings like `plugins-monorepo`).
- **Bats discipline** — 851 / 851 in <90 s; `[v0.11] MINOR-04/06` cases lock in the recent diagnostic additions, evidence of test-first regression discipline.
- **C4 architecture diagram** in `docs/architecture.md` (added in `a7bb309`) is the clearest single artifact for a new contributor.

---

## 4. Defer-to-v0.12 confirmations

| ID | Status after this review | Note |
|---|---|---|
| **A1-6** (session-resume schema v2) | ✅ Confirm defer | Touches 10 bats asserts; out of v0.11.1 scope. |
| **MEDIUM-04** (snapshot `fcntl.flock`) | ⚠ **Refine** | Flock is *implemented* (`memory_index.py:115`). Remaining work is cross-lock ordering with `task_lock`. See DR-011 / DR-014. |
| **AT-REL-1** (manual SIGTERM reviewer) | ✅ Confirm defer | Human-in-the-loop, not a code item. |
| **AT-LLM-2.1** (real-mode LLM guard bats) | ✅ Confirm defer | Needs network or fixture infra. |
| **AT-COMPAT-1** (Linux CI matrix) | ✅ Confirm defer | Pure infra. |
| **AT-COMPAT-3** (`jq`-missing diag bats) | ✅ Confirm defer | Trivial when picked up. |
| **NEW: DR-001** (plugin_readonly over-block) | Recommend **add to v0.12** | High-impact regression bait when developers run codenook on a path containing `plugins`. |
| **NEW: DR-005** (secret_scan ruleset) | Recommend **add to v0.12** | Easy wins; the omissions are notable. |
| **NEW: DR-006** (CLAUDE.md augmentation) | Recommend **add to v0.12** | UX gap that turns the kernel-only install into orphan code on disk. |

---

## 5. Recommendation

**Ship v0.11.1 as-is** — none of the findings are CRITICAL or release-blocking and
the bats baseline is green. **However**, schedule a focused v0.11.2 docs/UX
patch to address DR-002, DR-003, DR-004, DR-006 (all docs/install-UX, no code
risk) and a v0.12 code patch to address DR-001, DR-005, DR-007/008, DR-010.
The kernel itself is sound; the rough edges are concentrated in the
onboarding boundary (top-level installer, README, CLAUDE.md story) where they
will hurt every new user the most.
