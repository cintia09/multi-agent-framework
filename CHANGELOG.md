## v0.29.3 — Plugin entry-questions persistability (P0 fix)

### Fixed

Plugin entry-questions were broken end-to-end before this release:
plugin authors could declare `entry-questions.yaml :: <phase>.required`
fields, but users had no way to actually answer them — `codenook
task set --field <plugin_field> --value <answer>` was rejected as
"not writable", and even if you bypassed that, the next tick would
crash with a `task-state.schema.json` violation because the top-level
schema was `additionalProperties: false`. The recovery message the
kernel emitted (`rerun: codenook task set …`) was therefore a dead
end.

- **EQ-1 (schema)**: `task-state.schema.json` gains a top-level
  `entry_answers` object property (`additionalProperties: true`).
  Plugin-defined entry-question answers live here so the kernel's
  strict top-level `additionalProperties: false` contract still
  catches typos in well-known fields.
- **EQ-2 (kernel)**: `check_entry_questions()` now reads required
  fields from `state["entry_answers"]` first, then falls back to the
  top-level state dict (back-compat for any pre-v0.29.3 caller that
  wrote there directly).
- **EQ-3 (CLI)**: `codenook task set --field <key>` auto-routes
  unknown fields under `state["entry_answers"][<key>]` whenever
  `<key>` is declared by the active plugin's `entry-questions.yaml`
  (in any phase's `required:` or `questions:` map). Truly unknown
  fields are still rejected with the existing "not writable" error.
  The successful response JSON now includes `stored_under` so callers
  can see where the value landed.

### Tests

- New `test_entry_questions.py` (8 cases): covers schema acceptance
  of arbitrary `entry_answers` keys, schema rejection of unknown
  top-level fields, `check_entry_questions` reading from
  `entry_answers`, top-level back-compat, plugin-field auto-routing
  via `task set` against an installed kernel + synthetic plugin,
  and continued rejection of truly unknown fields.

## v0.29.2 — Knowledge discovery robustness

### Fixed

- **KO-1**: `discover_knowledge` now emits a stderr warning when a
  knowledge file's frontmatter looks malformed (starts with `---`
  but parse fails — e.g. closing `---` missing or YAML invalid).
  Previously such files were silently dropped from the index with
  no diagnostic, which made debugging "missing knowledge entry"
  symptoms painful. The file is still excluded from results
  (preserving prior behaviour), but the operator now sees a clear
  warning naming the offending path.
- **KO-4**: top-level `knowledge/README.md` is now filtered from
  discovery alongside `INDEX.yaml` / `INDEX.md`. README files are
  documentation, not knowledge entries; previously they surfaced
  as spurious "README" entries in `knowledge search` results.

### Tests

- Added `test_v0_29_2_knowledge_discovery_robustness.py` with 3
  cases covering README filtering, malformed-frontmatter warning
  emission, and silent pass-through for files without frontmatter.
- Total: 378 passed / 2 skipped.

## v0.29.1 — Notes/ removal + extraction-source docs

### Removed

- `tasks/<T-NNN>/notes/` directory creation (`cmd_task.py`). The
  legacy "extractor input drop" is obsolete since v0.29.0; per-task
  history snapshots under `tasks/<T-NNN>/history/<ts>/` and per-phase
  outputs under `tasks/<T-NNN>/outputs/` cover all manual-extraction
  source needs. Existing `notes/` dirs in old tasks are left as-is.

### Changed

- Bootloader (`init/bootloader.md`): added an **Extraction sources**
  paragraph that explicitly enumerates what to read when promoting
  task findings into `memory/knowledge/<slug>/` or
  `memory/skills/<slug>/` — `tasks/<T-NNN>/outputs/phase-*.md`,
  `tasks/<T-NNN>/history/<ts>/`, `memory/history/<ts>/` — and what
  is NOT a source (`audit.jsonl`, `prompts/`, `state.json`).

### Tests

- 375 passed / 2 skipped (unchanged).

## v0.29.0 (2026-04-26) — Memory simplification + manual knowledge

**Breaking change**: collapses the workspace memory layout and removes
the auto-extraction pipeline. Knowledge entries are now written by hand;
the kernel discovers them live each call.

### Removed

- `.codenook/memory/_pending/` (extractor staging area).
- `.codenook/memory/config.yaml` (per-memory knobs — `knowledge_hits.top_n`
  was the only honoured key; now the kernel default applies).
- `.codenook/memory/index.yaml` (auto-rebuilt index — never written
  again; `knowledge_index._load_entries` walks the disk live).
- Auto-extraction skills: `knowledge-extractor/`, `skill-extractor/`,
  `extractor-batch/`, `distiller/`, `config-extractor/`, plus
  `_lib/extraction_router.py`.
- `codenook extract` CLI subcommand.
- `orchestrator-tick.after_phase` no longer fans out to extractor-batch.
- `templates/memory-config.yaml`.

### Added

- `codenook history save --description "<text>" [--content-file P]`
  — manual session-history snapshot under
  `.codenook/memory/history/<ISO>-<slug>/`.
- `codenook history list [--scope memory|tasks|all]` — list snapshots.
- `codenook history prune [--days N] [--scope ...] --yes`
  — retention sweep (default 10 days). `--yes` is mandatory.
- Auto per-phase task snapshots under
  `.codenook/tasks/<T-NNN>/history/<ISO>-<phase>-<slug>/` written by
  the tick hook. Best-effort; never blocks.
- `_lib/history.py` — save / snapshot / list / prune helpers.
- `_lib/cli/cmd_history.py` — argparse dispatcher.

### Changed

- `codenook knowledge search` walks plugins + memory directories live
  each call (no on-disk index).
- `codenook knowledge reindex` is now a no-op with a deprecation
  message — kept for backward compatibility.
- `seed_workspace.seed_memory()` only creates `knowledge/`, `skills/`,
  `history/`. The post-install reindex hook is gone.
- Bootloader template (CLAUDE.md `<!-- codenook:begin -->...end -->`):
  references to `index.yaml` / `_pending/` removed; new §History
  snapshots section added; manual-knowledge path documented as
  "write to memory/knowledge/<slug>/index.md — discovery is live".

### Migration notes

- After upgrading, existing `.codenook/memory/index.yaml`,
  `config.yaml`, and `_pending/` files are NOT deleted (the installer
  is non-destructive). Operators may remove them by hand:
  ```bash
  rm -f .codenook/memory/index.yaml .codenook/memory/config.yaml
  rm -rf .codenook/memory/_pending
  ```
- Custom knowledge entries previously promoted from `_pending/` should
  be moved into `memory/knowledge/<slug>/index.md` (sub-dir form) by
  hand.
- `.codenook/config.yaml` (workspace-level model resolution chain) is
  unaffected.

## v0.28.0 (2026-04-25) — T-004 unified plugin+memory discovery

**Breaking change**: introduces unified sub-directory drop-in discovery
for plugins and workspace memory. Every discoverable entity
(skill / knowledge / role / case / playbook / error) is now a
self-contained directory with a required `index.md` carrying YAML
frontmatter (`id, type, title, summary, keywords` REQUIRED).

- New module `_lib/discovery/scan.py` — filesystem scanner with
  process-scoped mtime cache; discovery is live (no reindex required).
- New CLI `codenook discover plugins|memory|--all [--json]`.
- Plugin role files migrate from flat `roles/<role>.md` to sub-dir
  `roles/<role>/role.md` (+ `index.md`). Dispatcher + validator accept
  both during the migration window.
- `available_skills:` key in `plugin.yaml` is removed from all bundled
  plugins (now derived from scan).
- Memory layout restructured: topic sub-dirs
  `cases/ playbooks/ errors/ skills/ knowledge/` each with
  `<slug>/index.md` entities.

See task `T-004-统一-plugin-memory` for full design + migration plan.

## v0.27.24 (2026-04-24)

Bootloader hardening — fixes 10 issues found by deep review of the
v0.27.23 rendered CLAUDE.md. No CLI surface changes; template-only.

### Changed (bootloader template, `claude_md_sync.py`)

- **#1 Workflow ordering fixed in 3 places** (Auto-engagement flow,
  §Duplicate / parent check, §Pre-creation config ask). The canonical
  order is now unambiguous: interview → Pick plugin → Pick profile →
  Duplicate / parent check → Pre-creation config ask → `task new`.
  Previous template had two anchors that contradicted each other.
- **#4 `.codenook/` detection** is now spelled out: read
  `.codenook/state.json` to decide whether the workspace is
  CodeNook-enabled, instead of leaving the test implicit.
- **#5 Unknown tick status** — added explicit "any other value → stop,
  surface the JSON, ask the user" fallback so future kernel statuses
  do not silently no-op.
- **#6 Missing / empty / unparseable `index.yaml`** — ritual step 3
  now says treat as "no memory yet", continue, and note once. Avoids
  the previous "abort on missing inventory" trap.
- **#7 "you" ambiguity in role/phase prompt restriction** — added an
  explicit Exception clause: when the conductor IS the phase worker
  (clarifier inline, or `inline` exec mode), role-file "you MUST"
  text DOES bind it. The v0.27.23 blanket rule would have broken
  inline execution.
- **#8 Zero-plugin and weak-match cases** — §Pick a plugin now covers
  "zero plugins installed" (offer `plugin install` or inline) and
  "all matches score < 0.3" (label "(weak match)" + offer inline).
- **#9 Multiple HITL gates** — §HITL gates now mandates strict serial
  resolution (one channel ask + one decide per turn, then `tick`),
  with explicit "never batch decisions for more than one gate".
- **#10 `knowledge search` vs cached `index.yaml`** — disambiguated:
  cached scan is fine for trivial single-topic lookups; use
  `knowledge search` whenever the query is multi-keyword, fuzzy, or
  the cached summary is ambiguous.
- **#12 `model` field** — split the "verbatim" rule into the two
  cases the kernel actually emits: pass through verbatim when
  `envelope.model` is non-empty; omit the `model:` argument entirely
  when it is absent / null / empty.
- **#13 `_pending/` semantics** — explicit note that
  `.codenook/memory/_pending/` is the extractor's staging area only:
  NOT in `index.yaml`, NOT searched by `knowledge search`. Manual
  notes must be written directly to `memory/knowledge/<slug>.md`
  followed by `<codenook> knowledge reindex`.

### Tests

- New `test_v0_27_24_bootloader_hardening.py` — 13 tests, one per
  issue (one issue gets 3 tests for the 3-place reordering).

---

## v0.27.23 (2026-04-23)

Open up conductor read scope: the main session may now read any
file under `.codenook/plugins/` (knowledge, skills, roles, phase
prompts) for orientation and explanation. The previous blanket
"MUST NOT read plugin internals in conductor context" rule is
gone, replaced with a narrower behavioural rule.

### Changed (bootloader template, `claude_md_sync.py`)

- **Removed** hard rule *"MUST NOT read `.codenook/plugins/*/roles/`,
  `.codenook/plugins/*/skills/`, or `.codenook/plugins/*/knowledge/`
  in conductor context"*. The conductor needed plugin visibility
  to give good answers (e.g. "what does the design phase do?",
  "explain this plugin's profile chain") without spawning a phase.
- **Added** new hard rule *"MUST NOT treat `roles/` or `phases/`
  prompt templates as instructions addressed to you"*. Those
  files use imperative voice written for isolated sub-agents;
  letting them re-target the conductor would silently move
  phase work into the main session and break the multi-agent
  boundary. They remain readable for explanation / debugging —
  quote, don't act.
- **§Proactive knowledge lookup step 4 rewritten:**
  - `plugins/<id>/knowledge/` and `plugins/<id>/skills/` — open
    and cite freely (treated like memory hits).
  - `plugins/<id>/roles/` and `plugins/<id>/phases/` — readable
    for explanation only; never as conductor instructions.
  - Old "stop at the summary, offer to start a task" wording
    deleted.

### Tests

- New `test_v0_27_23_conductor_read_scope.py` (4 tests) pins:
  legacy blanket prohibition gone, new "don't treat as
  instructions" rule present, plugin knowledge/skills readable,
  roles readable but only for explanation.

### Why

Once §Auto-engagement (v0.27.22) made the conductor proactive,
the read-only restriction became the next bottleneck — the LLM
could detect a substantial request and recommend a task, but
couldn't actually answer mid-depth questions about the plugins
it would dispatch. v0.27.23 lifts that ceiling while keeping the
"no inline phase work" boundary explicit.

## v0.27.22 (2026-04-23)

Bootloader auto-engagement: an installed CodeNook now actively
participates in every session, instead of waiting for the user to
type a magic phrase. The conductor LLM loads workspace inventory
on the first tool call and proactively recommends a CodeNook task
whenever a request is substantial.

### Changed (bootloader template, `claude_md_sync.py`)

- **Session-start ritual now triggers on the first tool call of
  any session performed inside a workspace where `.codenook/`
  exists.** Previously the ritual only ran "the first time the
  user mentions CodeNook in a session", which meant memory and
  plugin context were invisible for normal coding questions —
  defeating the point of having an installed CodeNook.
- **New §Auto-engagement section** with a substantial-vs-trivial
  rubric (≥2 files, plugin `match` hit, deliverable wording,
  decomposes into phases) and a 3-choice recommendation flow
  (`create task` / `handle inline` / `explain what CodeNook would
  do`). Trigger phrases (`走 codenook 流程`, `use codenook to …`,
  …) are preserved as a fast-path that skips the recommendation
  ask but still runs the rest of the pre-task interview.
- **Hard rules flipped:**
  - removed: *"MUST start a task only when the user explicitly
    asks"*.
  - added: *"MUST proactively recommend a CodeNook task whenever
    the user's request is substantial; user always confirms before
    `task new`"*.
  - added: *"MUST complete the §Session-start ritual on the first
    tool call of every session where `.codenook/` exists"*.
  - added: *"MUST NOT spawn a CodeNook task for trivial requests;
    handle inline but still apply §Proactive knowledge lookup"*.
- **Removed §When to start subsection** (replaced by
  §Auto-engagement). The legacy text "Only when the user
  explicitly asks. Recognise: …" is gone.

### Tests

- New `test_v0_27_22_bootloader_auto_engagement.py` (9 tests)
  pins the four-layer auto-engagement model: awareness fires on
  first tool call, §Auto-engagement section exists with the
  substantial / trivial rubric and 3-choice recommendation flow,
  trivial-inline path keeps proactive knowledge lookup, old
  explicit-only wording removed, trigger phrases preserved as
  fast-path.
- `test_claude_md_contract.py::test_contract_02_no_self_initiated_tasks`
  updated for the new contract (LLM may *recommend* a task but
  never silently creates one) — still asserts user-confirmation
  invariant.

### Non-goals

- No CLI changes (no new kernel subcommands).
- No phase-agent or dispatch-protocol changes.
- No cross-host discoverability work — Copilot CLI is confirmed
  to read `CLAUDE.md` already, so a separate
  `.github/copilot-instructions.md` shim is unnecessary.

## v0.27.21 (2026-04-23)

Memory-layer reliability: unblock `knowledge search` / `index.yaml`
from crashing on common frontmatter mistakes, extend search to cover
skills, and ship a new `memory doctor` CLI + auto-repair hook.

### Fixed
- **`memory_index.build_index` no longer crashes on `datetime.date`
  frontmatter values** (e.g. `created: 2026-04-22`). The atomic
  snapshot writer now serialises via `json.dumps(..., default=str)`
  so YAML-native dates round-trip as ISO strings instead of aborting
  the write. Prior to this fix, `full_index._scan_memory` silently
  swallowed the `TypeError` and returned `([], [])`, which meant
  the entire `memory/knowledge/` and `memory/skills/` layer was
  invisible to `knowledge search` and to the unified
  `.codenook/memory/index.yaml` (`skills/builtin/_lib/memory_index.py`).
- **`knowledge search` no longer crashes on non-string tags.** YAML
  parses bare literals like `0x2c2000` or `2026-01-01` into int /
  date objects; the aggregator now coerces every tag with
  `[str(t) for t in ...]` before handing it to `find_relevant`
  (`_lib/cli/cmd_knowledge.py`).

### Added
- **`knowledge search` now searches skills too.** Memory-extracted
  and plugin-shipped skills entries go into the same scoring pool as
  knowledge; the output line tags each hit with `[K]` or `[S]` so
  users can tell the two apart (`_lib/cli/cmd_knowledge.py`).
- **New `codenook memory doctor [--repair] [--json]` command**
  (`_lib/cli/cmd_memory.py` + `skills/builtin/_lib/memory_doctor.py`).
  Diagnoses common frontmatter issues in
  `<ws>/.codenook/memory/knowledge/*.md` and
  `memory/skills/<name>/SKILL.md`:
  - missing `title` / `name`  derive from first H1 or filename
  - missing `summary`  derive via `_summary_from_body`
  - `tags` not a list (string / null / scalar)  split / coerce
  - `tags` contains non-string items  `str()` each
  - `created:` / `updated:` as `datetime.date` / `datetime`
     rewrite as ISO string
  - stray `memory/skills/SKILL.md` at the wrong level  warn only
  - no frontmatter block  warn only (never synthesise a stub)
  `--repair` applies all safe fixes in place and writes a backup of
  every modified file to
  `<ws>/.codenook/memory/.repair-backup/<ISO-timestamp>/` (Windows-
  safe timestamp: `:` replaced by `-`). Plugin files under
  `<ws>/.codenook/plugins/<id>/{knowledge,skills}/` are scanned
  read-only and surfaced in a separate report section for upstream
  filing. `--json` emits the full report as structured JSON.
- **`install.py` post-install hook auto-runs `memory doctor --repair`**
  after `sync_claude_md`. Repaired files are listed inline; plugin-
  side issues print as warnings and do not abort install. Skipped for
  `--check` and `--dry-run` (`_lib/install/cli.py`).
- **Top-level `codenook --help` and subcommand wiring for
  `memory doctor`** (`_lib/cli/app.py`).

### Bootloader (CLAUDE.md)
- v0.27.21 bootloader (already synced in this release branch) makes
  plugin picking require explicit confirmation, makes profile picking
  require an explicit choice when a plugin has >1 profile, adds a new
  Proactive knowledge lookup section, documents `task show` and
  `plugin list` in the CLI reference, and prefers
  `task show --json` for HITL gate discovery.

### Tests
- **Windows path-separator tolerance** in
  `test_index_yaml_export.py`  the two `.endswith(...)` assertions
  now `.replace("\\", "/")` first so they also pass on Windows where
  paths contain backslashes.
- **UTF-8 write fix** in `test_extractor_real_role_output.py`  the
  test now writes role outputs with `encoding="utf-8"` so Windows
  default-codepage does not corrupt the `'` in "Python's".
- **New regression tests** under `tests/python/`:
  - `test_v0_27_21_memory_index_date_fix.py` 
    `memory_index.build_index` tolerates `created: 2026-04-22`.
  - `test_v0_27_21_cmd_knowledge_tag_coerce.py`  `knowledge search`
    renders entries with hex-literal tags without crashing.
  - `test_v0_27_21_knowledge_search_skills.py`  `knowledge search`
    finds a skill by name / summary / tags.
  - `test_v0_27_21_memory_doctor.py`  full-surface tests for the
    new doctor (missing summary, non-list tags, `--repair` writes
    backups, plugin files stay read-only, `--json` parseable).
  - `test_v0_27_21_install_post_repair.py`  `install.py` invokes
    doctor and prints the summary line.

---
## v0.27.20 (2026-04-23)

`codenook task show` — quick single-task detail view.

### Added
- **`codenook task show <T-NNN> [--json] [--history-limit N]`**
  (`_lib/cli/cmd_task.py::_task_show`). Renders all the fields a
  conductor would usually reconstruct by `cat .codenook/tasks/<id>/
  state.json | jq`, plus the pending-HITL count and a readable
  history tail.

  Human output includes:
  - identity: task_id, title, summary, plugin, profile, phase,
    status, priority, dual_mode, exec_mode, max_iterations,
    schema_version, created_at, updated_at
  - optional: model_override, parent_id, chain_root, target_dir
  - in-flight agent block (role / expected_output / dispatched_at)
    when the task is currently dispatched
  - first 10 lines of `task_input` under an "Input:" header
  - "Pending HITL (N):" list when hitl-queue has matches
  - "History (last N of M):" with `[ts] phase → verdict (note)`
    rows; the `note` column surfaces `history[].note` and the
    orchestrator's `_warning` flag (e.g. `hitl_approved`)

  `--json` emits `state.json` augmented with ``_resolved_task``
  (slugged dir name) and ``pending_hitl`` (list of gate filenames).

  `--history-limit N`:
    * positive → show last N, collapse rest into "… hidden"
    * 0 → hide history entirely
    * negative → show all

- Top-level `codenook --help` and `codenook task` help updated.

### Tests
- **8 new regression tests** in
  `tests/python/test_v0_27_20_task_show.py`:
  - missing id → exit 2
  - unknown id → exit 1 + "no such task"
  - basic human render shows every core field
  - `--history-limit` default / 0 / -1 branches
  - pending HITL line appears when queue has matching entries
  - `--json` structure (includes `_resolved_task`, `pending_hitl`)
  - tolerates non-dict history entries without crashing
  - unknown flag → exit 2
- Full suite: 305 passed / 2 skipped (was 297 / 2).

### Verification
- Live-verified against `/Users/mingdw/Documents/nook`: renders T-001
  (done, 4 history rows, 1 pending HITL), T-016 (complete, 45 history
  entries — shows last 5 with "40 earlier hidden"), Input Q/A block
  with CJK.

---

## v0.27.19 (2026-04-23)

Follow-up to v0.27.18: `task new` now renders a **Summary + confirm**
page after the interactive plugin/profile selection (mirroring the
`--interactive` wizard's pattern). Keeps scripted flows unblocked.

### Added
- **Summary + Y/n confirmation** in `_task_new` (`_lib/cli/cmd_task.py`)
  — shown only when ALL three conditions hold:
  - the user was actually prompted for plugin and/or profile
    (not just `--title` with single-plugin auto-pick), AND
  - stdin is a TTY (pipes / CI skip the confirm to avoid hangs), AND
  - `--accept-defaults` is not set.
  Summary includes title, plugin, profile, priority, parent (if
  any), model override, exec mode, dual-mode, and a 60-char input
  preview. On a non-"y" answer, task creation is aborted with
  exit 1 and no directory is created.

### Tests
- **1 new PTY-based regression test** in the same v0.27.18 file,
  using `pty.fork()` to drive a real terminal and assert that:
  - the Plugin menu appears and accepts `\n` (default)
  - the Profile menu appears and accepts `\n` (default)
  - the "Create? [Y/n]" confirm appears and accepts `Y`
  - a task dir with the expected slug gets created afterwards
  Skipped on Windows (pty is POSIX-only).
- Full suite: 297 passed / 2 skipped (was 296 / 2).

### Verification
- Live-installed into `/Users/mingdw/Documents/nook`: non-TTY
  pipeline still auto-selects without prompting for confirmation;
  `--accept-defaults` skips confirm; new probe tasks cleaned up.

---

## v0.27.18 (2026-04-23)

`plugin list` subcommand + interactive plugin/profile selection in
`task new`. Removes the "which plugin/workflow do I pick?" guesswork
for workspaces that host more than one plugin or profiles-heavy
plugins like ``development`` (which ships 7 profiles).

### Added
- **`codenook plugin list [--json]`** (`_lib/cli/cmd_plugin.py`)
  lists every plugin installed under ``.codenook/plugins/`` with:
  - id + version
  - declared profiles with their full phase chain
    (``feature: clarify → design → plan → … → ship``)
  - the raw phase catalogue
  Text mode is human-friendly (tree-style); ``--json`` emits one
  object per plugin with keys ``id`` / ``version`` / ``path`` /
  ``profiles[]`` / ``phases[]`` for tool piping.
- **Interactive plugin + profile selection in `task new`**
  (`_lib/cli/cmd_task.py`):
  - `--plugin` omitted with multiple installed: numbered menu
    prompt; user picks by number OR name; 3 invalid attempts aborts.
  - `--plugin` omitted with exactly one installed: auto-use with a
    transparency line (``only one plugin installed — using 'X'``).
  - `--plugin` omitted with ``--accept-defaults``: silent auto-pick
    of the first installed plugin (preserves CI / scripted flows).
  - `--profile` omitted and plugin advertises profiles: numbered
    menu with "default" highlighted (or first profile if none named
    "default"). Same 3-strike abort.
  - Non-TTY stdin (pipes / CI): menu is still echoed to stdout so
    the choice is visible in the log, then the default is
    auto-selected. No infinite prompt hangs.
  - Explicit `--plugin <unknown>` now rejected with exit 2 and the
    list of available ids (previously silently proceeded to a
    mkdir race later in the pipeline).
  - Helper ``_prompt_choice`` generalized for reuse by future
    wizards that need a menu-style picker.

### Changed
- `codenook plugin --help` now lists ``list`` as the first
  subcommand; top-level ``--help`` USAGE block updated to match.
- `task new --help` rewrites the ``--plugin`` and ``--profile``
  descriptions to document the new interactive behavior and the
  ``--accept-defaults`` escape hatch.

### Tests
- **7 new regression tests** in
  ``tests/python/test_v0_27_18_plugin_list_prompts.py``:
  - `plugin list` human output includes every installed plugin id
  - `plugin list --json` parses and has the expected structure
  - `plugin list --bogus` rejected with exit 2
  - `task new --plugin does-not-exist` rejected with exit 2 +
    "available: …" list
  - `--accept-defaults` with multiple plugins does NOT render the
    menu (silent auto-pick)
  - Non-TTY stdin renders the menu + auto-selects default
  - `task new --profile <invalid>` rejected with exit 2 + valid list
- Full suite: 296 passed / 2 skipped (was 289 / 2).

### Verification
- Live-installed into `/Users/mingdw/Documents/nook`; the workspace
  has 3 plugins (``development`` with 7 profiles, plus ``generic`` /
  ``writing``). `plugin list` renders all three with chains;
  non-TTY ``task new`` prints both menus and picks defaults
  visibly; ``--plugin bogus`` rejected as designed.

---

## v0.27.17 (2026-04-23)

Multi-angle audit fixpack (security + resilience + concurrency).
Three parallel code-reviews (security / resilience / concurrency)
surfaced 9 findings; this release lands the recommended top-5 subset.

### Fixed
- **[Critical] Path traversal in `chain link --child` / `--parent`**
  (`_lib/cli/cmd_chain.py:50`) — the command interpolated its
  `--child` argument straight into `ctx.workspace / ".codenook" /
  "tasks" / child / "state.json"`. A value like `../../.ssh/id_rsa`
  escaped the tasks sandbox. Both `--child` and `--parent` are now
  rejected with exit 2 when they fail the shared `is_safe_task_component`
  guard (rejects `..`, `/`, `\`, NUL, leading `.` or `_`, and
  multi-component paths).
- **[High] Path traversal in `task new --id`** (`_lib/cli/cmd_task.py`)
  — `--id` fed directly into `tdir = ws/.codenook/tasks/<id>` with
  `mkdir(parents=True, exist_ok=False)`, which could create arbitrary
  directories and a rogue `state.json` anywhere inside the workspace.
  Now validated at argument-parse time with the same
  `is_safe_task_component` guard.
- **[Medium] `codenook tick` crashes on corrupt `state.json`**
  (`_lib/cli/cmd_tick.py:107`) — the envelope-augmentation pass did a
  raw `json.loads(state_p.read_text(...))` outside of any try/except.
  A malformed or hand-edited state.json raised `JSONDecodeError` and
  dumped a stack trace instead of degrading. Now wrapped; tick output
  is returned unaugmented on parse failure, matching the existing
  "skip-on-parse-fail" pattern elsewhere in the kernel.
- **[Low] `hitl notify` re-POSTs decided entries during a decide × scan
  race** (`_lib/cli/cmd_hitl_notify.py:192`) — the daemon's pending
  scan didn't inspect the `decision` field, so an entry that had just
  been decided in-place (before it moved to `_consumed/`) would still
  be sent to the webhook. Pending set is now filtered to drop any
  entry whose `decision` field is truthy, preserving the
  "notify once per queued entry" contract.
- **[Low] `task new` ID-allocation retry cap raised 16 → 128**
  (`_lib/cli/cmd_task.py`) — the collision-retry ceiling was too low
  for bursty concurrent `task new` invocations (e.g. CI parallelism).
  Raised to 128; error message and comment updated.

### Added
- **`is_safe_task_component(name)`** helper in `_lib/cli/config.py` —
  canonical path-traversal guard for every CLI surface that accepts
  a task id from user input. `resolve_task_id` now calls it at the
  top, so the existence-check against the real filesystem is never
  performed on a malicious path.

### Tests
- **23 new regression tests** in `tests/python/test_v017_2_fixes.py`:
  - 7 params × `chain link --child` traversal rejection
  - 4 params × `chain link --parent` traversal rejection
  - 9 params × `task new --id` traversal rejection (plus a
    post-condition that confirms no rogue dirs were created outside
    `.codenook/tasks/`)
  - Corrupt-state.json tolerance in `_augment_envelope`
  - `hitl notify --once` skips an entry with `decision:"approve"`,
    using an in-process `http.server` to capture POSTs
  - Pin-test for the `128 attempts` retry-cap message

### Tests (full suite)
- 289 passed / 2 skipped (was 266 passed / 2 skipped in v0.27.16).

### Known deferrals (from the same audit)
- **[Medium] `atomic_write_json_validated` has no OS-level lock**
  (`skills/builtin/_lib/atomic.py`) — rename-based atomicity only.
  Two concurrent writers to the same `state.json` can lose an update
  under last-writer-wins. CodeNook's single-tick-per-task model makes
  this rare in practice; a proper `fcntl.flock` upgrade will be
  scoped as a standalone RFC.
- **[Medium] Install pipeline lacks cross-invocation locking**
  (`_lib/installer/_orchestrator.py`) — two concurrent `install.py`
  runs against the same workspace can both read the pre-mutation
  `state.json` and lose one plugin's entry in the append-then-write
  pass. Same RFC as above.
- **[Low] Chain link parent+child two-file write is non-atomic**,
  **[Low] `codenook upgrade` × `tick` interleaving on the same task**
  — both need a lock or a documented "quiesce" protocol. Filed for
  later.

### Verification
- Live-installed into `/Users/mingdw/Documents/nook`; re-ran a
  smoke tick → envelope + chain commands. Traversal rejects with
  clear error; normal flow unchanged.

---

## v0.27.16 (2026-04-23)

Phase C deep-review fixpack. One real bug surfaced + one defensive
hardening.

### Fixed
- **`int(None)` crash in migration walker** — `migrations.upgrade()`
  and `cmd_upgrade._load_state` both did
  `int(state.get("schema_version", 1))`. The `.get(..., 1)` default
  only fires when the key is missing, NOT when it's present with an
  explicit `null` value. A hand-edited or buggy state.json
  containing `"schema_version": null` therefore raised an uncaught
  `TypeError` from `int(None)`. Now both call sites read the raw
  value first and substitute `1` whenever the value is `None`.
  Same fix applied to the post-migration validation check that
  reads `new_state["schema_version"]`.

### Hardening
- The migration walker also now tolerates `"schema_version": "1"`
  (string form). Some external tooling stringifies ints; rather
  than fail validation, we coerce.

### Tests
- `test_migrations.py` (+2 regression tests):
  - `test_upgrade_handles_null_schema_version`
  - `test_upgrade_handles_string_schema_version`

### Verification
- 266 pytest passing / 2 skipped (was 264).

### Review credit
Issue surfaced by Phase C code-review pass (gpt code-review agent,
deep audit of v0.27.12 → v0.27.15 commits). Other issues
investigated and ruled out as false positives: hitl serve path
traversal (double-defended via `_safe_id` + helper-side
`_check_eid`), POST validation (decision whitelist + helper-side
state check), env-var injection (subprocess invoked as list, no
shell), notify mid-write race (json parse errors caught and
skipped), notify webhook persistence ordering (documented
at-least-once semantics), plugin diff symlink loops (`Path.rglob`
does not follow symlinks), plugin diff size cap (chunked read,
will not OOM), `_resolve_repo_root` walk (bounded to 20
iterations), priority-default change (no callers depended on
absence).

---

## v0.27.15 (2026-04-23)

Phase C4 of the v0.27.9 follow-up plan: HTTP UI + webhook fan-out for
the HITL queue. Stdlib only — no new runtime dependency.

### Added
- **`codenook hitl serve [--port N] [--bind addr]`** — single-process
  stdlib HTTP server with a tiny review UI:
    - `GET  /` — pending + recently-decided entries
    - `GET  /entry/<id>` — prompt + decision form
    - `GET  /entry/<id>/raw` — raw JSON
    - `POST /entry/<id>/decide` — form action; mutation is delegated
      to the same `hitl-adapter/_hitl.py` helper the CLI
      `hitl decide` path uses (single source of truth)
  Defaults to `127.0.0.1:8765`. Intentionally minimal — no auth, no
  CSRF, no TLS. Bind to localhost and tunnel via SSH if you need
  remote access. Entry-id whitelist protects against path traversal.
- **`codenook hitl notify --webhook <url>`** — polls
  `.codenook/hitl-queue/` and POSTs a JSON envelope per new entry:
  ```
  {"event": "hitl.queued", "workspace": "/abs",
   "entry": { …raw queue JSON… }}
  ```
  Flags: `--once`, `--interval N`, `--header K=V` (repeatable for
  e.g. `Authorization=Bearer …`), `--state-file <path>` for
  cross-restart at-least-once durability, `--user-agent <s>`.
  Stale ids (decided / archived) are evicted from the
  already-notified set so future re-queues with the same id do
  re-notify.

### Changed
- `cmd_hitl.HELP` and `app.USAGE` now list `serve` + `notify`
  alongside `list/show/decide`.

### Tests
- `tests/python/test_cli_smoke.py` (+2):
  - `hitl notify --once` against a stdlib HTTP test server fires
    one envelope per pending entry, exit 0.
  - `hitl serve --port <free>` binds, returns the index HTML
    containing "codenook hitl", terminates cleanly on SIGTERM.

### Verification
- 264 pytest passing / 2 skipped.

### Phase C summary
v0.27.12 (C1 schema migrations) → v0.27.13 (C2 bats→pytest first
batch) → v0.27.14 (C3 plugin diff/update) → v0.27.15 (C4 hitl
serve/notify). All four phase-C items shipped as separate
versions, each with its own tests and changelog. Skipped item #9
(sub-agent dispatch protocolisation) remains as a future design
ticket — needs RFC, not just code.

---

## v0.27.14 (2026-04-23)

Phase C3 of the v0.27.9 follow-up plan: per-plugin diff + update.
Closes the loop on "I edited a plugin under `plugins/` — what
exactly is different from what the workspace has installed, and how
do I push it out?" without forcing a full `python install.py`.

### Added
- **`codenook plugin diff <id>`** — file-level comparison between
  `<ws>/.codenook/plugins/<id>/` and the source tree. Walks both
  recursively (skipping `__pycache__`, dotfiles, `*.pyc`),
  sha256-hashes every file, and emits unified text diffs for
  modified UTF-8 files. Source resolution ladder: `--src` >
  `--repo` > `$CODENOOK_REPO` > walk-up from workspace/cwd
  looking for an `install.py`+`plugins/` sibling pair.
  `--json` for machine output. Exit 1 when changes exist
  (informational, scriptable as "needs update?"); 0 when clean.
- **`codenook plugin update <id>`** — thin wrapper that
  re-invokes `install.py --target <ws> --plugin <id> --upgrade`,
  using the same source-resolution ladder. Forwards
  `--dry-run` / `--yes`.

### Changed
- `cmd_plugin.HELP` now lists all four subcommands
  (`info`/`lint`/`diff`/`update`).
- `app.USAGE` mirrors the new lines under `plugin …`.

### Known limitation
`install.py` short-circuits when source `plugin.yaml.version`
matches the installed version (idempotent path: only refreshes
state.json, does NOT re-stage files). To re-stage local edits
without bumping the source version, run install.py manually after
incrementing `plugin.yaml.version`. Documented in `HELP_UPDATE`.

### Tests
- `tests/python/test_cli_smoke.py` (+3):
  - `plugin diff` clean against source = exit 0, empty changes
  - `plugin diff` after mutating one installed file surfaces
    `{"path": "phases.yaml", "status": "modified"}` and exit 1
  - `plugin update` on same-version install = exit 0, state.json
    still records the plugin

### Verification
- `python install.py --target /Users/mingdw/Documents/nook --yes`
  then `.codenook/bin/codenook plugin diff development --repo
  $REPO --json` returns `"changes": []`.

---

## v0.27.13 (2026-04-23)

Phase C2 of the v0.27.9 follow-up plan: bats → pytest first batch.
Both the bats and pytest implementations stay green during the
transition so contributors can opt into the python toolchain
without breaking CI.

### Tests
- **`tests/python/test_m1_task_config_set.py`** — 13 tests
  (parametrised) covering `task-config-set/set.sh` (M1 Unit 10):
  arg validation, allowlist enforcement, tier symbols, idempotent
  re-set, `--unset`, nested-not-dotted persistence.
- **`tests/python/test_m2_plugin_id_validate.py`** — 15 tests
  (parametrised) covering `plugin-id-validate/id-validate.sh` (M2
  Unit 3 / G03): id pattern, reserved-set, already-installed
  conflict, `--upgrade` bypass, `--json` envelope shape and
  `code: already_installed` discriminator.

### Changed
- No production code changes — tests-only commit.

### Migration plan
The bats counterparts (`m1-task-config-set.bats`,
`m2-plugin-id-validate.bats`) remain in `tests/` for now. They will
be deleted in a later patch once a few weeks of parallel runs
confirm the python tests catch every regression the bats tests
historically did. Subsequent batches will continue picking
CLI-surface bats files (no LLM, no claude-md) one milestone group
at a time.

### Verification
- 259 pytest passing / 2 skipped (was 231 in v0.27.12).
- Original `bats m1-task-config-set.bats m2-plugin-id-validate.bats`
  also still green (26 ok).

---

## v0.27.12 (2026-04-23)

Phase C1 of the v0.27.9 follow-up plan: schema migrations + an
operator-facing `codenook upgrade` command. Establishes the
infrastructure for future schema bumps so we never again ship a
breaking change without a migration path.

### Added
- **`_lib/migrations/`** — versioned migration registry keyed by
  source schema_version. Each migration is a pure function with
  three contracts: idempotent, gracefully degrades on missing
  optional fields, and MUST advance `state["schema_version"]`. The
  `upgrade(state)` walker chains them until current.
- **`v1_to_v2.py`** — first concrete migration. Normalises two
  conventionally-present-but-optional fields:
  - `priority` defaults to `"P2"` when missing/empty (matches
    `task new --accept-defaults`)
  - `history` defaults to `[]` when absent
- **`codenook upgrade`** subcommand. Walks every active task under
  `.codenook/tasks/`, applies pending migrations through the
  registry, and writes via `_persist_state` (atomic + schema-
  validated). Flags: `--task T-NNN`, `--dry-run`, `--yes`,
  `--json`. Exit 1 on any per-task migration failure (others still
  attempted); 0 when all selected tasks reach the current
  schema_version.

### Changed
- `_M4_STATE_VERSION` (in `draft_config.py`) bumped 1 → 2.
- `task new` now writes `schema_version: 2` and includes
  `priority` even when neither `--accept-defaults` nor an
  explicit value were supplied (defaults to `"P2"`).
- `freeze_to_state_json` now sets `priority` from
  `draft.priority` falling back to `"P2"` so router-driven task
  creation lands at the v2 convention.

### Tests
- `tests/python/test_migrations.py` — round-trip on a synthetic
  v1 state (priority + history filled, schema_version → 2;
  re-running the migration is a no-op).
- `tests/python/test_cli_smoke.py` — `codenook upgrade --json`
  on a workspace with one v1 + one v2 task: v1 reported in
  `upgraded`, v2 in `skipped`, exit 0.

### Verification
- `python install.py --target .` against a fresh workspace seeded
  with a hand-edited v1 state.json:
  - `codenook upgrade --dry-run --json` lists the v1 task with
    `from_version: 1`, `to_version: 2`, no file mutated.
  - `codenook upgrade --yes` writes; re-running prints
    "no migrations needed".

---

## v0.27.11 (2026-04-23)

Phase B of the v0.27.9 follow-up plan: observability + static
validation. Adds three subcommands that close visibility gaps every
operator hits eventually.

### Added
- **`codenook config show --task T-NNN [--phase P]`** — explains the
  4-layer model resolution chain (C task override > B phase model >
  A plugin default > D workspace default), showing every layer's
  contribution and which one won. Mirrors `models.resolve_model`'s
  walk without re-importing it (so a corrupt models module never
  takes the debug command down). `--json` for machine output.
- **`codenook plugin lint <id|path>`** — static validator catching
  the most common authoring mistakes:
    - `E_PLUGIN_YAML` / `E_PHASES_YAML` / `E_HITL_YAML` — missing
      or malformed top-level YAML
    - `E_ROLE_MISSING` — phase references a role with no
      `roles/<role>.md`
    - `E_GATE_UNDECLARED` — phase references a gate not in
      `hitl-gates.yaml`
    - `E_PROFILE_UNKNOWN_PHASE` — profile references a phase id
      missing from the catalogue
    - `W_TEMPLATE_UNKNOWN_VAR` — manifest template uses a `{var}`
      not in the canonical render allowlist
  Resolves the target as either an installed plugin id (looks
  under `.codenook/plugins/`) or a filesystem path (so you can
  lint `plugins/my-domain/` straight from a checkout). Exit
  nonzero on any violation; `--json` for machine output.
- **`codenook task list --tree`** — render parent → child
  hierarchy from `state.json :: parent_id`. Roots first; each
  child indented 2 spaces. Status filters still apply but
  filtered-out parents stay reachable (their children re-anchor as
  visible roots), and `parent_id` cycles emit a `↻ <id>  (cycle)`
  marker instead of recursing forever.

### Changed
- `_collect_task_records` row shape — adds `parent_id` (read from
  `state.json`) so `--tree` doesn't have to re-read each state.json.
- `_lib/cli/app.py` USAGE — documents `plugin lint` and `config
  show` alongside `plugin info`.

### Tests
- `tests/python/test_cli_smoke.py`: three new smoke tests
  (`test_config_show_human_and_json` for the resolution chain
  walker, `test_plugin_lint_clean_and_broken` covering both the
  shipped clean plugin and a corrupted copy, and
  `test_task_list_tree` covering parent/child indentation).

### Verification
- 224 pytest passing / 2 skipped (was 221 / 2 — the +3 are the
  new Phase B smoke tests).

---

## v0.27.10 (2026-04-23)

Operational follow-ups to v0.27.9 (`task list` / `task delete`): a
restore command, a real fix for an HITL queue matching bug, and a
status/list refactor that removes duplicated row-building code.

### Added
- **`codenook task restore`** — reverse of `task delete`. Moves
  archived snapshots from `.codenook/tasks/_archive/<orig>-<UTC-ts>/`
  back to `.codenook/tasks/<orig>/` and (best-effort) re-promotes
  any *undecided* HITL queue entries from
  `.codenook/hitl-queue/_consumed/` to the active queue. Decided
  entries stay in `_consumed/` as audit history. Refuses to
  overwrite an existing active dir. Supports `--list` (just show
  what's in `_archive/`), `--from <archived-name>` for
  disambiguation when multiple snapshots share a prefix,
  `--no-hitl-restore`, `--yes`, `--dry-run`, `--json`.

### Fixed
- **HITL queue prefix-matching false positives**
  (`_lib/cli/cmd_task.py :: _hitl_pending_for`). The previous
  implementation matched queue files by `filename.startswith(task_id + "-")`,
  which would mis-claim `T-10-foo_signoff.json` when the operator
  ran `task delete T-1`. The current numbering scheme uses
  zero-padded `T-NNN` ids and so happened to be safe, but the
  fragility was real and would surface on any plugin that allowed
  custom ids. Now reads each queue JSON and matches by the body's
  `task_id` field — the same source of truth the kernel uses to
  write the entry. Regression test included
  (`test_hitl_pending_uses_json_task_id_not_prefix`).

### Changed
- **`codenook status` task table** now reuses
  `cmd_task._collect_task_records` instead of duplicating the
  task-walking + state.json parsing. The output shape is unchanged
  (`test_status` continues to pass) but the model column is still
  resolved here (kept `cmd_task` decoupled from `models`).
- **`_collect_task_records` row shape**: renamed `short_id` → `task_id`
  (now sourced from the state.json `task_id` field) and added a
  `dir_name` field (the on-disk directory name). Both `task list`
  and `task delete` updated to use the new fields. JSON consumers
  may need to update if they relied on the removed `short_id`.
- **`_lib/cli/app.py` USAGE** — adds the `task restore` synopsis
  alongside `task delete`.
- **README.md** — adds a "Special directories under `.codenook/`"
  table documenting `_archive/`, `_consumed/`, and the legacy
  `.archive/` so operators understand where deleted tasks go and
  how restore works.
- **`cmd_task.py` module docstring** — formal definition of the
  archive contract (paths, lifecycle, who manages them).

### Tests
- `tests/python/test_cli_smoke.py`: two new smoke tests
  (`test_task_restore_round_trip` for the delete→restore cycle and
  `test_hitl_pending_uses_json_task_id_not_prefix` for the queue
  matching regression).

### Verification
- 221 pytest passing / 2 skipped (was 219 / 2 — the +2 are the
  new restore + HITL regression tests).

---

## v0.27.9 (2026-04-23)

Adds two long-missing built-in subcommands so operators no longer
need to `rm -rf .codenook/tasks/T-NNN` by hand or eyeball
`codenook status` JSON to figure out what's stuck.

### Added
- **`codenook task list`** — group active tasks by status
  (`in_progress` / `waiting` / `done` / other), surface per-task
  HITL queue counts (`⚠ HITL pending: N`), and support
  `--status` / `--phase` / `--plugin` filters plus `--json` for
  machine consumption. `done` tasks are hidden by default; pass
  `--include-done` to show them. Implemented in
  `_lib/cli/cmd_task.py :: _task_list` on top of the existing
  `iter_active_task_dirs` helper.
- **`codenook task delete`** — archive (default) or `--purge`
  tasks plus their HITL queue files. Accepts bare positional
  `T-NNN` ids or `--task` flags (repeatable), plus `--status` for
  bulk selection (e.g. `--status waiting`). Default behaviour is
  non-destructive: each task dir is moved to
  `.codenook/tasks/_archive/<orig>-<UTC-ts>/` and matching HITL
  queue `.json` entries are moved into
  `.codenook/hitl-queue/_consumed/` so the audit trail survives.
  Refuses `status=in_progress` tasks unless `--force`. Supports
  `--dry-run`, `--yes`, and `--json`.

### Changed
- `_lib/cli/app.py` USAGE — documents the two new subcommands
  alongside `task new` / `task set*`.
- `_lib/cli/cmd_task.py` HELP_TASK — lists `list` and `delete` in
  the per-`task` help dispatcher.

### Tests
- `tests/python/test_cli_smoke.py`: three new smoke tests
  (`test_task_list_human_and_json`,
  `test_task_delete_archive_and_purge`,
  `test_task_delete_unknown_task`) covering the human + JSON
  outputs of `task list`, archive vs `--purge` semantics of
  `task delete`, and the unresolved-id error path.

### Verification
- 219 pytest passing / 2 skipped (was 216 / 2 — the +3 are the
  new smoke tests).

---

## v0.27.8 (2026-04-22)

Fixes a real kernel bug discovered while investigating an HITL
verdict mismatch in a live workspace: HITL `needs_changes`
hard-looped the same phase, ignoring `transitions.yaml`, even
though `docs/task-chains.md` §3 explicitly defines it as
equivalent to verdict `needs_revision`.

### Fixed
- **HITL `needs_changes` ignored `transitions.yaml`**
  (`orchestrator-tick/_tick.py`). The HITL gate consumer at
  step 3.5 used to call `dispatch_or_skip(... cur ...)` directly
  with `iteration++`, regardless of what `transitions.yaml`
  declared for `<phase>.needs_revision`. This contradicted the
  documented equivalence with verdict `needs_revision`, and meant
  cross-phase bounces such as `review.needs_revision: implement`
  were silently downgraded to a same-phase loop on `review`.
  The HITL path now simply sets `verdict_for_transition =
  "needs_revision"` and falls through to the existing transition
  step 5, which already correctly handles same-phase loops
  (iteration++ + cap), cross-phase bounces (transition without
  iteration bump), and `complete` terminal targets — yielding a
  single audit-trail shape for both verdict-routed and HITL
  `needs_revision`/`needs_changes`.

### Documentation
- `docs/task-chains.md` §3: clarified that `needs_changes` is
  routed through `transitions.yaml`. Same-phase target →
  iteration++; different phase → fresh transition.

### Tests
- `tests/m4-e2e-tick.bats`: added a regression
  (`needs_changes routes via transitions.yaml (cross-phase bounce)`)
  that patches the generic fixture so `clarify.needs_revision:
  analyze`, then asserts an HITL `needs_changes` decision on the
  clarify gate transitions the task to `analyze`. The pre-existing
  same-phase test (`needs_changes → iteration incremented, same
  phase`) continues to pass because `clarify.needs_revision: clarify`
  in the fixture still resolves to a same-phase loop under the new
  routing path.

### Verification
- 216 pytest passing / 2 skipped
- 931 bats ok / 0 fail (the 931-vs-932 bats counter warning is
  pre-existing and unrelated to this change)

---

## v0.27.7 (2026-04-22)

Continuation of the v0.27.6 deep-audit pass — recovers all 15
remaining-out-of-scope bats failures. Two more real kernel bugs
(both visible from existing-test investigation), four stale tests
brought back in line with current behavior, and two tests
explicitly skipped because the feature they covered was removed
on purpose in earlier releases.

### Fixed
- **`.write.lock` leaked into the knowledge content directory**
  (`memory_layer.py`). The directory-level merge-vs-merge sentinel
  added in the post-D+E review (Change-E lock) was placed at
  `<memory>/knowledge/.write.lock` and `<memory>/skills/.write.lock`.
  Any caller that did a plain `os.listdir(.codenook/memory/knowledge/)`
  after the first write saw the lock file alongside real entries.
  Relocated under `<memory>/.locks/` so content directories stay pure.
  Surfaces as TC-M9.1-05 ("same topic prefers patch") rejecting the
  unexpected `.write.lock` in its expected listing.

- **`CN_EXTRACTOR_BATCH` override silently swallowed non-zero
  exits** (`orchestrator-tick/_tick.py`). The override path called
  `_sh_run([...], capture_output=True)` (a thin `subprocess.run`
  wrapper without `check=True`) and only logged when an *exception*
  was raised — but a stub that exits 7 returns a `CompletedProcess`
  cleanly, so the failure was completely invisible. Now inspects
  `returncode` and prints `"extractor batch failed: override=...
  exit=N"` on non-zero, while still letting the tick proceed
  (best-effort hook contract: TC-M9.2-05 asserts failure does not
  block the tick). **User-visible**: any operator using a custom
  extractor-batch override saw silent failures.

### Tests
- **6 tests rescued from a single helper bug** — `m9_seed_n_knowledge`
  in `tests/helpers/m9_memory.bash` seeded N entries with identical
  body `"x" * 1024`. With Change-E `fuzzy_merge=True` (default since
  v0.21.0+), every entry after the first matched the prior one's
  body fingerprint and merged into it instead of becoming its own
  topic, so callers that asked for 1000 / 30 / 3 distinct topics
  got 1. Helper now produces a unique body per index.
  Recovers TC-M9.1-08, TC-M9.1-12, M9.1 invalidate, TC-M9.3-07,
  M9.6 cap-20, M9.6 applies_when-split.

- **`m9-router-memory.bats`** — `seed_knowledge_aw` was test-only
  scaffolding for routing/match assertions, not for fuzzy-merge
  semantics. Pass `fuzzy_merge=False` so distinct topics with
  identical bodies stay separate.

- **`m9-knowledge-extractor.bats` TC-M9.3-07** — extractor cap test
  used candidate bodies `"Body N unique content N"` (≈25 chars)
  which still tripped the substring-overlap branch of
  `is_fuzzy_match`. Replaced with longer, structurally-distinct
  bodies so the cap-3 / dropped-by-2 assertion measures cap logic
  rather than fuzzy-merge collateral.

- **`m7-generic-manifest.bats` / `m7-writing-manifest.bats`** —
  pinned `version == "0.1.0"` while the actual manifests are now
  generic 0.1.2 / writing 0.1.1. Updated pins.

- **`m8-discovery.bats` M8.3 plain-file fallback** — `_summary_from_body`
  added in v0.21.0 now derives an implicit summary from the first
  non-empty paragraph for files without frontmatter. Test still
  expected an empty summary; updated to expect the actual paragraph.

- **`m9-extractor-batch.bats` TC-M9.2-06** — asserted the M9.2
  watermark protocol is documented in the repo-root CLAUDE.md, but
  that file was deleted in commit 08964fb (template now lives in
  `claude_md_sync.py` and renders into each workspace). The current
  bootloader template intentionally does not carry the watermark
  protocol section; the `extract --reason context-pressure`
  affordance still exists but the operator-facing docs were
  consolidated. Test now `skip`s with a pointer to the commit so
  the gap is auditable. Re-introducing the documentation is a
  separate decision.

- **`m9-extraction-router.bats` TC-ROUTE-03** — asserted
  `route_fallback=true` after a simulated LLM error. v0.25.0
  rewrote `extraction_router.route_artefacts()` to short-circuit
  to the cross_task fallback dict and never call the LLM (the LLM
  hop was pure overhead since cross_task is the only legal route).
  With no LLM call there is nothing to fall back from, so
  `route_fallback` is permanently false. Sibling TC-ROUTE-02
  (asserts cross_task lands) covers the surviving behavior. Test
  `skip`s with the rationale.

### Regression
216 pytest / 930 bats ok / 8 skips / 0 fail.

## v0.27.6 (2026-04-22)

Deep audit pass — fixes 5 latent bugs surfaced during the v0.27.5
review. Three are real kernel bugs (one production-impacting), two
are test-only drift.

### Fixed
- **`emit_summary` produced invalid JSON when `conductor_instruction`
  was present** (`orchestrator-tick/_tick.py`). The 500-byte
  output cap originally targeted terse status fragments; the
  multi-step HITL ritual added in M4 (~700-800 bytes of literal
  guidance the conductor must execute verbatim) blew through the
  cap, the trimmer didn't know about the field so trimmed
  nothing, and `_utf8_safe_truncate` then sliced the JSON string
  mid-string-value. The conductor saw `{"...":"...approve/reject/n\n`
  (literal LF after a backslash, no closing brace) and JSON-
  parsed it to a `JSONDecodeError` — every HITL gate hit on every
  workspace was failing this way. **Production-impacting**: any
  conductor that JSON-parsed `tick --json` would crash on the
  first HITL gate. Fix: when `conductor_instruction` is in the
  payload, raise the cap to 4 KiB so the value is never sliced.

- **`lookup_transition` didn't fall back to the `default` profile
  when called with `profile=None`** (`orchestrator-tick/_tick.py`).
  The v0.2.0+ profile-keyed transitions layout (`{default: {...}, feature: {...}, ...}`) silently returned `None` for any
  task created without an explicit `--profile`, because no
  top-level `clarify` / `plan` / etc. key existed. Fix: detect
  the profile-keyed layout structurally; when the caller didn't
  pin a profile, route through `default`. **Production-impacting**:
  every default-profile task previously errored out at the first
  `tick` after any verdict with `"no transition from <phase>/<verdict>"`.

- **`claude_md_linter` rejected the v0.27+ bootloader** with
  errors on `clarifier`, `designer`, `implementer`, etc.
  (`skills/builtin/_lib/claude_md_linter.py`). Two coupled drifts:
  (a) the linter's "Hard rules" section-exemption regex required
  the literal "(forbidden)" suffix, but the bootloader uses
  "(zero domain budget)"; (b) the heading regex was hard-coded to
  level-2 (`##`), while the bootloader's section is level-3
  (`###`). Also: the JSON dispatch-envelope example and the
  §Special cases / §Dispatch envelope sections (which by design
  must name the clarifier role since they document the protocol's
  domain-aware exceptions) were not exempt. Fix: relax the
  Hard-rules pattern to accept any parenthetical suffix at any
  heading level, exempt JSON / YAML / TOML data-fences, and add
  a `_ALLOWED_SECTION_RE` for the documented exception sections.

- **`install.py` first-line banner showed the wrong version**
  on every fresh install of v0.27.5 — `VERSION = "0.27.4"` was
  not bumped together with the two `VERSION` files. Aligned to
  0.27.6.

### Tests
- 6 of 11 legacy bats files using `$REPO_ROOT/install.sh` (which
  was retired in v0.14.0 → `install.sh.legacy`) were silently
  failing with exit-127. Replaced by a `codenook_install` shell
  helper in `helpers/load.bash` that translates the old
  `bash $INSTALL_SH --plugin <id> <ws>` shape to
  `python3 install.py --target <ws> --yes [extra]`. The helper
  intentionally does NOT add `--upgrade` (some tests verify
  exit-3 mismatch behavior without it).

- **`task_new_entry_question_target_dir.bats` E2E-P-005** —
  pre-pin state to `phase=implement` directly. The original test
  expected verdict-driven plan→implement advancement to land in
  implement, but the plan phase later acquired a `plan_signoff`
  HITL gate that pauses verdict-driven advancement. The test's
  scope is the implement entry-question, not the plan→implement
  transition — direct pinning preserves the intent.

- **`v011_3-fix-pack.bats` E2E-001 `codenook --help`** — relax
  the assertion to grep each canonical subcommand at line-start
  rather than as `"codenook <cmd>"` substring (the help format
  intentionally omits the `codenook` prefix on each line, since
  it's already implied under `Subcommands:`).

### Regression
216 pytest / 36 contract / 11 install-bats — all green.

## v0.27.5 (2026-04-22)

### Added
- `.github/workflows/release.yml`  auto-create GitHub Release when a
  `v*` tag is pushed. Release body is extracted from the matching
  `CHANGELOG.md` section; falls back to a minimal placeholder when no
  section is found.

### Why
Previously, every tag had to be promoted to a Release manually via the
GitHub UI. v0.27.2 / v0.27.3 / v0.27.4 were all left without releases as
a result. This workflow closes that gap going forward.
## v0.27.4 (2026-04-22)

Boot-ritual hardening + parent-task aggregation CLI.

### Added
- **`<codenook> task suggest-parent` CLI subcommand**
  (`_lib/cli/cmd_task.py`) — thin wrapper around the existing
  `parent_suggester.suggest_parents()` Jaccard-ranking library
  in `skills/builtin/_lib/`, which until now was only reachable
  internally from `router-agent`. Now any conductor can call:
  ```
  <codenook> task suggest-parent --brief "<text>" --threshold 0.10 --json
  ```
  to get a ranked list of open tasks that look like duplicates
  or siblings of the candidate brief, and offer the user a
  three-way choice (continue existing / chain as child via
  `--parent T-NNN` / create independently). The wrapper pins
  `--workspace` to the active CodeNook workspace and rejects
  any user-supplied `--workspace` to prevent ambiguity.
- **Bootloader §Duplicate / parent check** — new mandatory
  step inserted between the pre-task interview and the
  pre-creation config ask, instructing the conductor to call
  `task suggest-parent` and surface results as a single
  `ask_user` choice. Recommends `--threshold 0.10` (instead of
  the kernel default 0.15) to catch cross-language Chinese↔
  English title pairs that share only one token. Backed by a
  hard-rule MUST line.
- **Behavioural scenario s6** — exercises the §Session-start
  ritual under a natural prompt ("帮我给 nook 写个 README"),
  asserting that `memory/index.yaml` is among the agent's
  initial Reads. Currently RED in the wild (see Known issues).
- **Contract tests `test_contract_13_session_start_ritual_…`
  and `test_contract_14_duplicate_parent_check_is_mandatory`** —
  pin the new MUST + heading + three-way choice wording.
  Total contract suite: 36 tests, all green.

### Changed
- **§Session-start ritual heading** marked
  `(MANDATORY, do once per session)` with explicit
  "all four reads as one atomic batch" wording, and a fourth
  hard-rule MUST line was added forbidding partial / lazy
  reads of `memory/index.yaml`. Driven by an observed failure
  mode where agents finished `state.json` + plugin reads,
  noticed they "didn't need" memory yet, and skipped it —
  only to realise mid-flow that they had to backfill.

### Known issues
- Behavioural `s6` (memory-in-natural-prompt) still fails
  intermittently against `claude -p` even with the new MUST
  + MANDATORY wording. Markdown-only enforcement appears to
  have a ceiling for ritual atomicity; structural defenses
  (e.g. kernel-side preflight assertion) are tracked for a
  future release.

## v0.27.3 (2026-04-22)

CLAUDE.md bootloader content refactor — accuracy + dedup + structure.

### Added
- **Behavioural regression suite** at
  `skills/codenook-core/tests/behavioral/`. Drives a real
  `claude -p` agent inside an installed CodeNook workspace and
  asserts the agent's first action matches the rules encoded in
  the rendered `CLAUDE.md`. 5 scenarios cover (s1) bare-task
  interview, (s2) interview-done → exec-mode ask, (s3) "你自己
  决定" exemption-scoping, (s4) sub-agent → model ask
  (historical regression), and (s5) §Session-start ritual reads
  `memory/index.yaml` (verified via stream-json tool trace).
  Not wired into default CI — opt-in run, ~$1 / 5min per full
  suite. `README.md` documents cost, gating, and how to add a
  scenario.

### Changed
- **Removed the auto-generated "Workspace has plugins installed:
  ..." seed line** at the top of the bootloader. The session-start
  ritual already mandates reading `state.json` + each plugin's
  `plugin.yaml`, so the seed line was redundant and added noise.
  `render_block(version, plugin)` keeps its signature for API
  stability but no longer emits the line; `_render_seed_line`
  remains as dead code marked with `# noqa: F841` until the next
  major version. Bats test 11 inverted to assert the seed line
  is absent.
- **Model + execution mode are now task-creation decisions, not
  per-dispatch ones.** Added a new §Pre-creation config ask
  subsection that requires the conductor to ask exec mode first
  (always), then ask model only when exec mode is `sub-agent`
  (skipped under `inline` because the conductor cannot switch its
  own model mid-conversation, so model is informational only).
  Both choices are passed to `task new` as `--exec` and
  `--model`. Removed the per-dispatch model pre-flight ask from
  §Model field — it now explicitly says "do NOT issue a per-
  dispatch ask; the choice was already made at task creation".
  New contract tests
  (`test_contract_11_model_asked_at_task_creation_not_per_dispatch`,
  `test_contract_12_exec_mode_asked_at_task_creation`,
  `test_contract_12_model_skipped_when_inline`) lock this.
- **Restructured the rendered bootloader.** Reordered into a clean
  skeleton: Identity → Hard rules → Workspace layout → Session-start
  ritual → Task lifecycle (when / pick / interview / create / tick /
  envelope / HITL) → Special cases (clarifier / model / exec mode) →
  Conventions (wrapper + CLI quick-ref) → See also. Hard rules and
  workspace layout now lead the document so constraints and
  orientation come first.
- **Cut size by ~39%** (23,728 → 14,376 bytes; 509 → 338 lines)
  with no functional regression. Every conductor-facing contract is
  preserved and pinned by 27 new wording-agnostic invariant tests
  in `tests/python/test_claude_md_contract.py`.

### Fixed
- **`你自己决定` / "just go" exemption was being over-applied.** A
  follow-up agent trace showed the conductor skipping the model
  ask after the user said "你自己决定" to the interview. Spec is
  now explicit (in both the §Hard rules MUST line and inside
  §Pre-creation config ask) that the exemption only skips the
  pre-task interview — it does NOT exempt the exec-mode or
  model ask. New contract test
  (`test_contract_12_just_go_does_not_skip_exec_or_model_ask`).
- **Agents literal-passed `--model "<default>"` as a string.**
  Discovered via behavioural audit (T-014's `state.json` had
  `model_override = "<default>"`). The §Create-the-task block
  now shows two concrete `task new` examples — one with a real
  model, one omitting `--model` entirely for the platform-
  default case — plus an explicit anti-example list of common
  hallucinated placeholders to never pass.
- **HITL channel-choice ask was being skipped by some agents,
  even when the kernel emitted `conductor_instruction` saying
  "do NOT skip steps".** Three reinforcements landed:
  (1) bootloader step labelled `**Channel-choice ask (MANDATORY).**`
  with explicit "do not skip / do not pick `terminal` on the
  user's behalf" guidance;
  (2) hard-rule line that any `conductor_instruction` field
  returned by `tick --json` is authoritative and every numbered
  step must be executed in order, even when one feels redundant;
  (3) hard-rule line forbidding silent default to `terminal`.
  Two new contract tests
  (`test_contract_09_channel_choice_ask_is_mandatory`,
  `test_contract_09_conductor_instruction_is_authoritative`)
  lock the wording.
- **Slug-derivation rule was self-contradictory.** An early one-liner
  said the slug is auto-derived from `--input` (empty → `T-NNN`),
  while the bash-comment block correctly stated the priority is
  `--title` → single-line `--input` → `--summary`. Removed the early
  wrong wording and kept the canonical form.
- **Internal kernel script names leaked into the bootloader.** The
  hard-rules block named `tick.py`, `tick.sh`, `_tick.py`,
  `terminal.py`, and `terminal.sh` — but the same section explicitly
  forbids the conductor from calling kernel scripts directly. These
  parenthetical leaks are gone; only the public `<codenook>` wrapper
  surface remains.
- **Stale wording.** Removed "the script is a plain bash CLI" and
  "expects bash on PATH" (no longer accurate; the wrapper is
  Python-driven on every host).
- **Version-pinned justifications.** Removed dangling references to
  `v0.13.22 latency optimisation`, `unchanged from v0.18.x`, and
  `tasks created before v0.19` — none of these explain anything an
  LLM at v0.27.3 needs to know.

### Removed (deduplicated)
- "What conductor reads when picking a plugin" (separate section)
  merged into the unified Session-start ritual.
- "Discovering existing tasks" (separate section) merged into the
  Session-start ritual + status-as-discovery note.
- Duplicate `<codenook> decide` example (was shown twice).
- Duplicate `Resume the tick loop when all gates resolve` sentence.
- Repeated reminders that `installed_plugins` is authoritative
  (was stated in 4 places, now once).
- "Task creation entry points" subsection — the relevant facts
  (`--interactive`, `--accept-defaults`, defaults) are folded into
  the Create-the-task subsection.
- "Plugin knowledge discovery" — implementation detail moved to a
  one-line pointer in §See also (covered fully by
  `docs/memory-and-extraction.md`).
- "Task-chain fields" 4-line orphan section — folded into the
  workspace-layout table.
- "CLI is the ONLY sanctioned entry point" subsection — same point
  is now made once in Hard rules + once in §Conventions.

### Added
- **27 contract tests** in `tests/python/test_claude_md_contract.py`
  encode the conductor-facing invariants (identity, EN/ZH triggers,
  wrapper subcommands, boot-ritual files, plugin seed line variants,
  `--input` + slug semantics, tick JSON envelope fields, HITL gate
  flow, clarifier-inline rule, model verbatim handling,
  `execution_mode`, workspace layout, hard-rules section, control-
  byte freedom, multiline continuations). The refactor was driven
  red→green by this baseline.



CLAUDE.md bootloader rendering fixes. Three findings, one regression net.

### Fixed
- **High — Windows wrapper path was rendered with a stray backspace byte
  (`\b` → `0x08`).** `claude_md_sync.render_block` used `f"""..."""`
  for the bootloader template body. Inside a cooked f-string the
  literal `\b` in the line `<ws>\.codenook\bin\codenook.cmd` was
  interpreted as the backspace control character, so the rendered
  CLAUDE.md byte stream actually contained `<ws>\.codenook\x08in\codenook.cmd`.
  Most viewers either swallow the byte (showing `\.codenookin\codenook.cmd`)
  or render a glyph; either way Windows users copying the path got an
  invalid one. Switched the body to `rf"""..."""` (raw + f-string) and
  collapsed the now-redundant `\\bin` double-escape in the same template.
  (`skills/codenook-core/skills/builtin/_lib/claude_md_sync.py:21-91`)

- **Medium — multi-line shell snippets in the bootloader collapsed
  onto a single line.** Same root cause: in a cooked triple-quoted
  string `\<newline>` is a Python source-level line continuation that
  joins the lines and strips both characters, so `task new --title …
  \\\n        --summary …` rendered as `task new --title …                --summary …`
  with a blob of spaces. The raw-string switch makes `\<newline>` a
  literal two-character sequence — exactly what bash wants for line
  continuation. Three snippets restored (`task new`, `decide`, the HITL
  `decide` example).

- **Low — bootloader claimed only one plugin was installed.** The
  template received the single `--plugin` argument from the most-
  recent install command (e.g. "Workspace seeded with plugin:
  **writing**") even when `state.json` listed three. `sync()` now reads
  `.codenook/state.json` and surfaces the full sorted set
  ("Workspace has plugins installed: **development**, **generic**,
  **writing**"); falls back to the CLI flag when state.json is absent
  (preserving the long-standing first-install / unit-test code path).
  (`skills/codenook-core/skills/builtin/_lib/claude_md_sync.py:97-145`)

### Tests
- Added three regression tests in
  `tests/v011_2-install-claude-md.bats`:
  1. The rendered file contains no `\b`/`\t`/`\f`/`\v`/`\a` control
     bytes and the literal Windows path is intact.
  2. `task new` renders with at least four indented `--flag`
     continuation lines (would be one if the join bug came back).
  3. When `state.json` lists multiple plugins the seed line names all
     of them, regardless of which single id was passed via `--plugin`.

`bats tests/v011_2-install-claude-md.bats` 5/8 → 8/11 (the unrelated
pre-existing `install.sh` failures, tests 1-3, are still red because
that file was replaced by `install.py` in v0.14.0; out of scope here).
`pytest tests/python/` 180 passed / 2 skipped, unchanged.

---

## v0.27.1 (2026-04-21)

Code-review follow-up on v0.27.0. Two findings.

### Fixed
- **High — `tests/m9-skill-extractor.bats::TC-M9.4-02` realigned to
  the new `MIN_REPEAT_THRESHOLD = 2`.** The test was pinned against
  the old `>=3` gate via `phase-log-2x.txt` (two `bash scripts/build.sh`
  calls). With the new gate the 2× fixture *meets* threshold and the
  test would flip from "no skill dir + below_threshold" to "skill
  proposed". Renamed the fixture to `phase-log-1x.txt` (a single
  invocation) so the test still proves the gate refuses sub-threshold
  inputs. (`tests/fixtures/m9-skill-extractor/phase-log-1x.txt`,
  `tests/m9-skill-extractor.bats:59`)

- **Low — `knowledge-extractor._parse_json_payload` now refuses
  top-level arrays.** When the slow path was hit on a prose-wrapped
  array response (`Sure: [{"a":1},{"b":2}]`), the brace-counter found
  the `{` inside the array and returned only the first element —
  silent partial parse against a `-> dict` contract. Now checks
  whether `[` precedes the first `{` and raises so the caller's
  existing `judge-parse-failed` fallback runs.
  (`skills/builtin/knowledge-extractor/extract.py`)

---

## v0.27.0 (2026-04-21)

Extraction tuning sweep — addresses two pain points seen on the live
nook workspace where `memory/skills/` and `memory/config.yaml` stayed
empty across 7 tasks while `memory/knowledge/` filled up normally.

### Changed
- **`skill-extractor`: `MIN_REPEAT_THRESHOLD` lowered from 3 → 2.**
  Earlier threshold rejected any task with fewer than three identical
  shell-invocation tokens, which excluded all "write HTML training
  page" / "rewrite copy" / "explore project" task families
  (`max_count=0` in the audit log). Two repeats is still strong
  evidence the operator is leaning on a tool worth saving.
  (`skills/builtin/skill-extractor/extract.py`)

- **`config-extractor`: `MIN_DISTINCT_SIGNALS` lowered from 2 → 1.**
  Same family of tasks emit at most one distinct `KEY=VAL` token (an
  output path, a model id) and were noop'd as `distinct_signals=0`.
  Letting one signal through still gates on the LLM judge that
  follows. (`skills/builtin/config-extractor/extract.py`)

### Fixed
- **`knowledge-extractor._parse_json_payload` tolerates prose-wrapped
  JSON.** Previously only stripped `\`\`\`json` fences and crashed on
  responses like `Sure, here is the result: { ... }` (audit log
  showed three `parse: Expecting value: line 1 column 2 (char 1)`
  failures across T-005/T-006/T-007). The parser now: (1) tries the
  raw payload, (2) if that fails, scans for the first balanced
  top-level `{...}` object using a string-aware brace counter, (3)
  parses the extracted slice. Falls back through the existing
  `judge-parse-failed` path when no balanced object is found.
  (`skills/builtin/knowledge-extractor/extract.py`)

---

## v0.26.0 (2026-04-21)

Code-review sweep on top of v0.25.5. Eight findings (1 high, 6 medium,
1 low) all addressed. Pure hardening — no surface-level behaviour
changes for happy-path users.

### Fixed
- **High — atomic `task set*`.** All four mutators (`task set`,
  `task set-model`, `task set-exec`, `task set-profile`) used a bare
  `sf.write_text(json.dumps(...))`. A SIGINT or crash mid-write would
  truncate `state.json` and brick every subsequent `tick`/`status`
  for that task. Centralised in a new `_persist_state(sf, state)`
  helper that routes through `atomic_write_json_validated` (same as
  `task new` since v0.25.0). (`_lib/cli/cmd_task.py`)

- **Medium — `task new --id` no longer clobbers existing tasks.** The
  explicit-id branch did `tdir.mkdir(parents=True, exist_ok=True)`
  which silently reused a populated dir; the subsequent atomic state
  write would then wipe history/model_override/parent. Now refuses
  with stderr if `state.json` already exists, tolerates an empty
  pre-existing dir. (`_lib/cli/cmd_task.py`)

- **Medium — TOCTOU loop catches `OSError`.** The slot-reservation
  retry loop in `task new` only caught `FileExistsError`; a permission
  error or read-only mount would surface as an uncaught traceback.
  Now reports a clean stderr + exit 1. (`_lib/cli/cmd_task.py`)

- **Medium — `status --task <id>` now prints `model=<x>`.** Single-task
  status returned the raw `state.json` and stopped, while the
  multi-task table (since v0.25.0) appends a model column. Now both
  paths surface the resolved model. (`_lib/cli/cmd_status.py`)

- **Medium — `decide` validates `--decision` client-side.** Passing
  a typo (`--decision approv`) used to round-trip through the HITL
  adapter and fail with a less useful schema error. Added
  `VALID_DECISIONS = ("approve","reject","needs_changes")` check
  immediately after argparse. (`_lib/cli/cmd_decide.py`)

- **Medium — slug + HITL id ranges cover Hangul / kana / CJK Ext A.**
  v0.25.4 added `\u4e00-\u9fff` (CJK Unified) but tasks titled with
  hiragana, katakana, Hangul Syllables, or CJK Ext A were still
  squashed to `-`. Introduced shared `_SLUG_KEEP_RANGES` covering
  `\u3040-\u309f` (hiragana), `\u30a0-\u30ff` (katakana),
  `\u3400-\u4dbf` (Ext A), `\u4e00-\u9fff` (Unified), `\uac00-\ud7af`
  (Hangul Syllables). Mirrored in `hitl-adapter/_hitl.py::_EID_RE`.
  (`_lib/cli/config.py`, `skills/builtin/hitl-adapter/_hitl.py`)

- **Medium — `resolve_task_id` flags exact-AND-prefix collisions.**
  When both `T-003/` (empty stub) and `T-003-real-task/` existed, the
  exact match won silently and routed all commands to the empty stub.
  Now returns ambiguous with both candidates. (`_lib/cli/config.py`)

- **Low — `route_fallback` default flipped to `False`.** Vestigial
  field set to `True` even though the router itself short-circuits to
  `False` since v0.25.0. Field kept for forward-compat; will be
  removed in v0.27 along with the dead extraction_router LLM call.
  (`skills/builtin/extractor-batch/_extractor_batch.py`)

---

## v0.25.5 (2026-04-21)

### Changed
- **HITL `waiting` envelope now carries an inline `conductor_instruction`.**
  When `tick --json` returns `status:waiting` because a HITL gate
  was just enqueued, the JSON also includes:
  - `hitl_entry_id` — the queue entry id
  - `conductor_instruction` — a multi-line, MANDATORY ritual the
    conductor must execute before doing anything else: (1) ask_user
    `terminal | html`; (2a) terminal → render gate inline + ask_user
    for decision; (2b) html → write `.codenook/hitl-queue/<eid>.html`,
    open it, then ask_user; (3) submit via canonical
    `codenook decide --task --phase --decision`.

  Rationale: the same instruction has been in the bootloader since
  v0.18, but conductors routinely skipped the channel-choice ask
  and went straight to a text approval. Embedding the ritual in
  the kernel's own JSON output (which the conductor *just ran*)
  makes it impossible to miss. The bootloader text remains as
  reference. (`orchestrator-tick/_tick.py:1107-1136`)

## v0.25.4 (2026-04-21)

### Fixed
- **HITL adapter rejected CJK characters in entry ids.** The
  `_EID_RE` regex in `hitl-adapter/_hitl.py` was
  `^[A-Za-z0-9._-]+$`, but v0.23+ task ids include the slug — and
  slugs preserve CJK Unified Ideographs. Any task created with a
  Chinese title (`T-NNN-写blog`, `T-003-数据来源-...`) could not
  pass through `decide` / `hitl decide` / `hitl show` etc. — every
  call returned `terminal.sh: invalid --id`. Regex now allows
  `\u4e00-\u9fff` in addition to ASCII alphanum / dot / dash /
  underscore. Path-traversal guards (`startswith('.')`, `'..' in`)
  remain in place. (`skills/builtin/hitl-adapter/_hitl.py:27-32`)

## v0.25.3 (2026-04-21)

### Changed
- **`--task T-NNN` now resolves to its slugged dir.** Previously
  every CLI subcommand that took `--task` required the *exact* dir
  name (e.g. `T-003-写blog`), so when `task new` returned
  `T-003-foo` the conductor's natural follow-up
  `tick --task T-003` failed with `state.json not found`. The
  resolver now walks `.codenook/tasks/`: exact match wins, else
  a unique `T-NNN-*` directory wins, else the user gets either
  `no such task` or an `ambiguous` error listing candidates.
  Wired into `tick`, `status`, `decide`, `task set`, `task set-model`,
  `task set-exec`, `task set-profile` (7 sites) via a single
  `resolve_task_id()` helper in `_lib/cli/config.py`.

## v0.25.2 (2026-04-21)

### Fixed
- **Meaningless task slugs from multi-line `--input`.** v0.25.0
  set slug source preference to `--input → --title → --summary`,
  but `--input` is the multi-line interview answers (one Q+A per
  line) — using its first 24 chars produced gibberish slugs like
  `T-003-数据来源-题库本地路径-volumes`. Slug source preference is
  now `--title → --input (single-line only) → --summary`. Multi-line
  `--input` falls through to `--summary`. `--title` (the
  human-curated short label) wins by design. Bootloader doc string
  updated to match. (`_lib/cli/cmd_task.py:296-307`,
  `skills/builtin/_lib/claude_md_sync.py:186`)

## v0.25.1 (2026-04-21)

### Changed
- **Bootloader: dispatch pre-flight ask when model is unresolved.**
  Before dispatching a sub-agent for any envelope where `model` is
  absent / null / empty (or `codenook status` shows
  `model=<default>` / `model=<unknown>` for the task), the
  conductor MUST now issue exactly one `ask_user` to confirm the
  model. The user can pick a name, accept the platform default,
  or abort the dispatch. When the envelope already carries an
  explicit non-empty `model` field, no ask is required — the
  kernel has already resolved it through the priority chain
  (task > phase > plugin > workspace) and the conductor passes
  it through verbatim. Bootloader-only change; no kernel logic
  affected. (`skills/builtin/_lib/claude_md_sync.py`)

## v0.25.0 (2026-04-21)

Sweep of code-review fixes — 11 issues across the kernel surface
(2 High, 6 Medium, 3 Low). No schema breaks; bootloader template
gains a couple of cosmetic improvements.

### Fixed (High)
- **`_find_core_root` infinite loop on Windows.** The terminator
  checked `cur != "/"`, but `os.path.dirname("C:\\") == "C:\\"`
  on Windows, so the walk never converged. Now uses
  `dirname(cur) == cur` — works on both POSIX and Windows.
  (`orchestrator-tick/_tick.py:1301-1314`)
- **`task new` wrote `state.json` non-atomically.** A crash mid-write
  (or two concurrent writers) could leave a half-written or
  schema-invalid state file, which then poisons every subsequent
  `tick`/`status`. Now uses `atomic_write_json_validated` against
  `schemas/task-state.schema.json`. (`_lib/cli/cmd_task.py:337-341`)

### Fixed (Medium)
- **TOCTOU race in `task new` slot reservation.** Two concurrent
  invocations could both pass the `next_task_id` check and
  `mkdir(exist_ok=True)`, with the second silently clobbering the
  first's task. Reservation now uses `mkdir(exist_ok=False)` in a
  16-attempt retry loop, recomputing `next_task_id` each pass.
  (`_lib/cli/cmd_task.py:290-314`)
- **`extraction_router.route_artefacts` invoked an LLM subprocess on
  every `after_phase` tick** — only to ratify a constant value
  (`task_specific` had been collapsed to `cross_task` in v0.24).
  Short-circuited to return `(FALLBACK_ROUTES, False)` directly.
  Removes a multi-second hang from the hot path; helpers retained
  for follow-up cleanup. (`skills/builtin/_lib/extraction_router.py:128-153`)
- **`codenook status` did not surface the resolved model** despite
  the bootloader telling conductors to read it from there. Each
  task row now ends with `model=<resolved>` (graceful `<unknown>` /
  `<default>` fallbacks if the models module is missing or empty).
  (`_lib/cli/cmd_status.py`)
- **USAGE drift: `hitl <list|show|render|decide>` advertised the
  long-removed `render` subcommand.** Bootloader / `--help` now
  list `<list|show|decide>`, matching `cmd_hitl.py`.
  (`_lib/cli/app.py:37`)
- **Test coverage gap on `cmd_decide` two-pass gate resolution.**
  Added `test_cmd_decide_resolution.py` exercising the
  `--phase <gate_id>` fallback documented in the bootloader.
- **Test coverage gap on `next_task_id` slug coexistence.**
  Added `test_next_task_id_slug.py` covering legacy `T-NNN`,
  v0.23+ `T-NNN-<slug>`, and CJK slugs sharing one tasks dir
  without slot collisions.

### Fixed (Low)
- **`_legacy_tick` could not honour `CODENOOK_DISPATCH_CMD` with
  arguments** because it passed the env var as a single argv
  element. Now uses `shlex.split` (POSIX-aware), so
  `CODENOOK_DISPATCH_CMD="python my_hook.py --foo"` works.
  (`orchestrator-tick/_tick.py:1219-1238`)
- **Dead `state["keywords"]` reads** in `_tick.py` (~L501) and
  `cmd_tick.py` (~L186) — no writer has populated this key since
  v0.20.0. Removed (with a code comment so the next reader knows).
- **Duplicated HITL paragraph in the bootloader template** (two
  near-identical lead-ins). Collapsed to one.
  (`skills/builtin/_lib/claude_md_sync.py:282-285`)

### Changed
- Bootloader's `decide` step now recommends the canonical
  `<codenook> decide --task --phase` form. The legacy
  `hitl decide --id` is still wired in `cmd_hitl.py` and continues
  to work; it's just no longer the recommended surface.
  (`skills/builtin/_lib/claude_md_sync.py:314-323`)
- `claude_md_sync.render_block(version, plugin)` now actually
  interpolates the `plugin` argument, rendering
  *Workspace seeded with plugin: **<id>*** when present (was
  silently discarded). (`skills/builtin/_lib/claude_md_sync.py:21-32`)

### Known coverage debt
- The `{{TASK_CONTEXT}}` slot + per-task `extracted/` API surface is
  no longer fed by any writer (route was collapsed in v0.24).
  Reads return empty strings — harmless but dead code. Slated for
  removal alongside the `extraction_router` LLM helpers in v0.26
  once the manifest templates that reference `{{TASK_CONTEXT}}`
  are reviewed.

## v0.24.2 (2026-04-21)

### Fixed
- **Task IDs missing slug suffix on the most common entrypoint**
  (`task new --title X --summary Y --accept-defaults`, no `--input`).
  v0.23 only consulted `task_input` when composing the slug, so any
  invocation that did not pass `--input` silently produced bare
  `T-NNN` ids — defeating the whole point of v0.23. Slug source
  preference is now `--input` → `--title` → `--summary` (first
  non-empty wins). CJK and ASCII titles both yield slugs.
  (`cmd_task.py:286-294`)

### Changed
- Bootloader now mandates a **pre-task interview**: 2-4 short
  clarifying questions via `ask_user` before `task new`, with the
  answers concatenated into `--input`. The task is created with
  rich first-phase context instead of the role having to ask
  basic questions post-dispatch (which felt jarring — outliner
  asking "what's the topic?" right after task creation). Plugin
  selection still drives the question set: look at the first
  phase's role and ask what it would otherwise ask.

## v0.24.1 (2026-04-21)

### Added
- Bootloader gained a **mandatory boot ritual** preamble: on
  first CodeNook invocation per session, the conductor MUST read
  `state.json` + every `plugins/<id>/plugin.yaml` + `memory/index.yaml`
  + `codenook status` in one batch (~15 KB total) before doing
  anything. Cached for the rest of the session. Eliminates the
  failure mode where the conductor invents tasks that already
  exist or picks the wrong plugin because it never loaded the
  workspace inventory.

## v0.24.0 (2026-04-21)  Eliminate kernel bash dependency (Windows-native)

### Rationale
v0.23.1 was a tactical hotfix: it auto-discovered bash on Windows so
`codenook tick` would stop crashing on hosts where bash was installed
but not on PATH (PortableGit / MSYS2 / per-user Git installs). It
worked, but the kernel still **required** bash to be present somewhere
— anyone without Git Bash at all (clean Windows installs, locked-down
corp images, CI runners without bash) still saw `FileNotFoundError
[WinError 2]`.

v0.24.0 is the strategic fix: **the kernel internals never invoke
`.sh` scripts under any circumstances.** The 36 `.sh` wrappers in
`skills/builtin/*/` remain on disk for Linux/Mac users who script
against them; the kernel's own code paths route around them entirely.

### Strategy
1. **Eliminate kernel-internal subprocess to `.sh`.** Every site in
   `_tick.py`, `_bootstrap.py`, `_build.py`, `_orchestrator.py`, and
   `cmd_extract.py` that previously spawned a `.sh` wrapper now either
   imports the helper module directly (`_preflight.run`, `_emit.run`,
   `_extractor_batch.run`) or invokes the sibling `_<name>.py` with
   `[sys.executable, ...]`. No bash is involved.
2. **Provide Python siblings for external entries.** Eight skills
   gain a `.py` sibling that mirrors the `.sh` argv contract, so
   callers (router agents, the conductor, operators) on Windows can
   simply use `python <entry>.py …`. Linux/macOS users may continue
   using `.sh`; both are equivalent.
3. **Retain `.sh` files for Linux/Mac.** No `.sh` file is deleted.
   Plugin-shipped scripts and the user-set `CN_DISPATCH_CMD` hook
   are explicitly out of scope — those remain `sh_run`-routed and
   benefit from v0.23.1's bash auto-discovery when they happen to be
   `.sh`.

### New Python sibling entry points
- `skills/builtin/router-agent/spawn.py`
- `skills/builtin/orchestrator-tick/tick.py`
- `skills/builtin/preflight/preflight.py`
- `skills/builtin/hitl-adapter/terminal.py`
- `skills/builtin/dispatch-audit/emit.py`
- `skills/builtin/extractor-batch/extractor_batch.py`
- `skills/builtin/router/bootstrap.py`
- `skills/builtin/session-resume/resume.py`

Each sibling parses its own args (`argparse`), discovers the workspace
(via `--workspace`, `$CODENOOK_WORKSPACE`, or upward search for
`.codenook/`), sets the historical `CN_*` env vars, and either calls
the helper module directly or `runpy`-executes the sibling `_<name>.py`.

### New helper modules / public APIs
- `extractor-batch/_extractor_batch.py` (new) — pure-Python port of
  `extractor-batch.sh`. Exposes `run(task_id, reason, workspace,
  phase, lookup_root)`. Idempotent on `(task_id, phase, reason)`,
  spawns extractor `.py` files (not `.sh`) detached so it never
  blocks the tick.
- `preflight/_preflight.py` — added `run(task, state_file, workspace,
  json_out)` callable; the existing env-var `main()` is now a thin
  shim around it.
- `dispatch-audit/_emit.py` — added `run(role, payload, workspace)`
  callable; same shim pattern.

### Kernel-internal call-site refactors
- `orchestrator-tick/_tick.py`:
  - `append_dispatch_log()` → in-process `_emit.run(...)`.
  - Legacy `_legacy_tick()` preflight + audit hops → in-process
    `_preflight.run(...)` + `_emit.run(...)`.
  - `after_phase()` extractor batch → in-process
    `_extractor_batch.run(...)`. Honours `CN_EXTRACTOR_BATCH`
    override (still routes through `sh_run` for test-injected stubs).
- `router/_bootstrap.py`: `config-resolve` invocation switched from
  `resolve.sh` (`_sh_run`) to `[sys.executable, _resolve.py]` with
  the same CN_* env contract.
- `router-dispatch-build/_build.py`: dispatch-audit emit switched
  from `emit.sh` (`_sh_run`) to in-process `_emit.run(...)`.
- `install-orchestrator/_orchestrator.py`: 11-gate pipeline now
  invokes each gate's `_<name>.py` via `[sys.executable, ...]` with
  the historical CN_* env contract; same for `sec-audit`.
- `router-agent/render_prompt.py`: handoff first-tick switched from
  `tick.sh` (bash) to `[sys.executable, _tick.py]`.
- `_lib/cli/cmd_extract.py`: rewritten to call
  `_extractor_batch.run(...)` directly. The `_resolve_bash()` helper
  is gone; bash is no longer needed for `codenook extract`.

### Justified exceptions (NOT kernel-internal)
- `_tick.run_post_validate()` invokes the plugin-provided post-validate
  script (.sh / .py / .exe / anything). Plugin script languages are
  out of scope for the v0.24.0 "no kernel bash" guarantee; the call
  site uses `sh_run` and benefits from v0.23.1's auto-discovery if
  the plugin happens to ship a `.sh`.
- `_legacy_tick()` external `dispatch_cmd` (set via
  `CODENOOK_DISPATCH_CMD`) is operator-defined. Same `sh_run` rationale.

### Bootloader & docs
- `skills/builtin/_lib/claude_md_sync.py`: bootloader template now
  references `tick.py` / `terminal.py` alongside `tick.sh` /
  `terminal.sh`, noting the Python entries as preferred on hosts
  without bash.
- `docs/router-agent.md` §2 §6: updated handoff instructions to
  show both Python and bash entry points and to note that the
  kernel itself never requires bash.

### Tests
- `tests/python/test_no_bash_dependency.py` (new, 7 tests):
  monkey-patches `shutil.which("bash")` to `None` and verifies that
  `_preflight.run`, `_emit.run`, `_extractor_batch.run`, and
  `_tick.after_phase` all complete without raising
  `FileNotFoundError`.
- `tests/python/test_python_entries.py` (new, 17 tests): parametrises
  over the 8 new `.py` siblings; asserts each is importable, exposes
  `main`, and that `python <entry>.py --help` exits 0 with help text.
  Includes a smoke that runs `tick.py --task X --workspace Y --json`
  end-to-end on a fresh workspace.
- Pytest baseline now: **168 passed, 4 failed** (was 144/4 in v0.23.1
  — all 4 pre-existing path-separator failures are unrelated to
  this change and remain on the v0.25.x backlog).

### Acceptance grep
```
grep -r 'subprocess.*\.sh"\|\["bash' skills/codenook-core/_lib \
                                     skills/codenook-core/skills/builtin/*/_*.py
# → ZERO non-comment hits.
```

### Note on v0.23.1
v0.23.1's `find_bash()` helper and well-known-locations scan in
`_lib/sh_run.py` remain in place. They are still useful for:
- Plugin-shipped `.sh` scripts that the kernel transitively invokes
  (post-validate hooks, custom dispatch commands).
- Linux/Mac users who continue to drive the kernel via the `.sh`
  entries.

What changed in v0.24.0 is that **none of the kernel's own code
paths depend on those helpers any more.** Even on a Windows host
with `find_bash() == None`, every kernel command — `codenook task
new`, `codenook tick`, `codenook hitl …`, `codenook plugin install`
— runs cleanly.

---

## v0.23.1 (2026-04-21)  Windows bash auto-discovery hotfix


### Critical bug fix
On Windows hosts where `bash` is installed but **not on system PATH**
(typical PortableGit / Git for Windows / MSYS2 setups), every
`codenook tick` raised `FileNotFoundError [WinError 2]`:

- `skills/builtin/_lib/sh_run.py` resolved bash with
  `shutil.which("bash") or os.environ.get("CN_BASH", "bash")` and
  passed the literal `"bash"` string through to `subprocess` when
  both lookups missed.
- `skills/builtin/orchestrator-tick/_tick.py` (extractor-batch
  dispatch) bypassed `sh_run` entirely with `cmd = ["bash", batch, ]`
  and crashed the whole tick instead of skipping a best-effort hop.

Real-world impact: tasks T-012 and T-015 stuck in production on a
Windows machine with bash at
`C:\openclaw-pro\PortableGit\bin\bash.exe`.

### Fix
- New `find_bash() -> str | None` helper in `sh_run.py` with a
  cached priority chain:
  1. `` if it points to an existing file.
  2. `shutil.which("bash")`.
  3. Scan well-known Windows install locations (PortableGit,
     `Program Files\Git`, `Program Files (x86)\Git`,
     `Git\usr\bin`, `msys64`, `cygwin64`, `System32\bash.exe`
     for WSL) plus a glob over per-user
     `C:\Users\*\AppData\Local\Programs\Git\bin\bash.exe` installs.
- `sh_run` raises a clear `RuntimeError` listing every location
  tried when no interpreter is found, instead of letting
  `subprocess` raise an opaque `FileNotFoundError`.
- `orchestrator-tick` extractor-batch dispatch now uses
  `find_bash()` and **logs-and-skips** when bash is unavailable
  (extraction is best-effort; ticks no longer crash).
- `codenook extract` and `router-agent` `render_prompt` tick
  dispatch routed through `find_bash()` for the same reason.

### Workaround for hosts still on v0.23.0
Either install Git for Windows (https://git-scm.com/download/win) so
`bash` is on PATH, or set `CN_BASH` to an absolute `bash.exe`
path before invoking the CLI.

### Tests
- New `tests/python/test_sh_run_discovery.py` (8 cases) covering
  the priority chain, glob scan, `RuntimeError` message, cache
  behaviour, and POSIX passthrough.

## v0.23.0 (2026-04-21) — auto-derived slug suffix on task IDs

### Added
- **`slugify(text, max_len=24)` helper** in
  `skills/codenook-core/_lib/cli/config.py`. Derives a short
  filesystem-safe slug from the task input. ASCII inputs are
  lowercased and squashed to `[a-z0-9-]+`; CJK inputs preserve the
  CJK characters and squash everything else; Windows reserved names
  (`CON`/`PRN`/`AUX`/`NUL`/`COM1`-`COM9`/`LPT1`-`LPT9`)
  are guarded with a `task-` prefix; the result is truncated to
  `max_len` and snapped back to the last `-` boundary if a
  trailing partial word would otherwise be emitted.
- **`compose_task_id(n, slug)` helper** in the same module. Returns
  `T-NNN` when the slug is empty, `T-NNN-<slug>` otherwise.
- **`codenook task new` auto-formats the task id** as
  `T-NNN-<slug-from-input>`. The slug is derived from the user's
  `--input` (or wizard-collected input). When the input is empty,
  the legacy `T-NNN` form is preserved. `--id <T-NNN[-anything]>`
  still overrides the generated id verbatim — no re-slugging.
- **Tests** — new `tests/python/test_slug.py` (12 cases) covering
  ASCII slugging, CJK preservation, empty input, Windows-reserved
  guard, max-len truncation, dash-boundary snap, and the
  `next_task_id` / `compose_task_id` integration. Pytest:
  136 passed (+12 over v0.22.0), 4 pre-existing path-separator
  failures unchanged.

### Changed
- **`next_task_id(workspace)` returns an `int`** (the next free
  slot number) instead of the formatted `T-NNN` string. The
  directory scan now treats both `T-NNN/` and `T-NNN-<slug>/`
  as occupying slot `N`, so legacy unsuffixed ids and v0.23 slugged
  ids coexist without colliding.
- **`--id` help text** in `cmd_task.py` now documents the
  auto-format default.
- **Task-id regexes** in `task_lock.py`, `router_context.py`,
  `orchestrator-tick/_tick.py`, `task_chain.py`, and
  `draft_config.py` widened to accept lowercase ASCII and the CJK
  range `\u4e00-\u9fff` so slugged ids round-trip through every
  validator.
- **Bootloader template** (`claude_md_sync.py`) gains a one-line
  note about the slug suffix in the task creation section.

### Backward compatibility
- No schema bump. `state.json.task_id` is still an opaque string.
- Existing `T-001`/`T-002` directories continue to work; the
  iterator skips them, the lock holder accepts them, and the regex
  tolerates the old uppercase form. Mixing old + new ids in the
  same workspace works (e.g. `T-001/` plus `T-002-foo-bar/`);
  no renaming required.
- `--id` flag is unchanged. `attach`, `set`, `set-model`,
  `set-exec`, `set-profile`, `tick`, and `decide` all accept
  the full task id verbatim — no parsing.

## v0.22.0 (2026-04-21) — kernel-side `{{KNOWLEDGE_HITS}}` substitution + `find_relevant()` API

### Added
- **`find_relevant(workspace, query, role=None, phase_id=None, plugin=None, top_n=8)`**
  in `skills/codenook-core/skills/builtin/_lib/knowledge_query.py`. Reads
  `<ws>/.codenook/memory/index.yaml` (built by v0.21.0); falls back to a
  transient in-memory `aggregate_knowledge` scan when the index file is
  missing. Pure read, idempotent, never raises. Returns a list of
  `{path, summary, tags, plugin, score, reason}` hits.
- **TF-style scoring**: tokens overlap against tag (×3) + summary (×1)
  + path segment (×0.5). Plugin pin (`plugin=` arg matching entry's
  `plugin`) adds a +1 bias to break ties. Each hit carries a
  human-readable `reason` string ("tag match: …; summary keyword: …;
  plugin pin: …").
- **`{{KNOWLEDGE_HITS}}` template placeholder** auto-injected from
  `cmd_tick._augment_envelope` and from the orchestrator's
  `_render_phase_prompt`. Backward-compat: templates without the
  placeholder are unchanged.
- **Config key** `knowledge_hits.top_n` in `<ws>/.codenook/config.yaml`
  overrides the default cap of 8.
- **Tests** — new `tests/python/test_knowledge_query.py` (15 cases)
  covering ranking, plugin bias, top-N cap, fallback scan, render
  formatting, placeholder substitution, config key resolution, and an
  end-to-end check via `_tick._render_phase_prompt`. Pytest:
  124 passed (+15 over v0.21.0), 4 pre-existing path-separator
  failures unchanged.

### Changed
- `cmd_tick._augment_envelope` now substitutes `{{KNOWLEDGE_HITS}}`
  after `{{TASK_CONTEXT}}` so the dispatched prompt the conductor
  loads has both placeholders resolved.
- Orchestrator-tick `_render_phase_prompt` (the parity write that
  fires inside `dispatch_agent`) does the same substitution so direct
  callers / tests see consistent output.

### Notes / TODO
- The optional post-validator (warn when a phase output declares
  `confidence: HIGH` without citing any auto-injected hit) was
  deferred to keep the release small. Logged for v0.23.x.
- Plugin manifests / schemas unchanged — no `schema_version` bump.

### Backward compat
- Plugins whose templates do not contain `{{KNOWLEDGE_HITS}}` (i.e.
  every plugin except prnook ≥ 0.2.3) see no behaviour change.
- Workspaces without `index.yaml` still get hits via a fallback scan
  of `<ws>/.codenook/plugins/*/knowledge/`.

---

## v0.21.0 (2026-04-25) — recursive knowledge discovery + INDEX overrides + `codenook knowledge` CLI

### Fixed
- **CRIT  plugin knowledge under subdirectories was invisible to the
  router and phase agents.** The kernel's `discover_knowledge` did a
  flat scan of `<plugin>/knowledge/*.md` only, so prnook's 50+
  baselines / cases / fingerprints / port-mappings (all nested two
  levels deep) never reached `memory/index.yaml`. Probes saw 5
  prnook items where there should have been 25+.

### Added  Block A: recursive scan
- `knowledge_index.discover_knowledge` now walks
  `<plugin>/knowledge/**/*.md` and skips dot-directories plus
  `__pycache__` / `node_modules` / `.git` / etc. via a
  `_SKIP_DIRS` constant.
- **Implicit-frontmatter fallback** when fields are missing:
  `title`  filename stem (unchanged); `tags`  parent directory
  names relative to `knowledge/` (e.g.
  `baselines/APHA/startup.md`  `[baselines, APHA]`); `summary`
   first H1/H2 or first non-empty paragraph of the body, Markdown
  link/image syntax stripped, truncated to ~200 chars.
- Existing frontmatter `tags` win and are NOT merged with directory
  tags  explicit always overrides implicit.

### Added  Block B: INDEX.yaml / INDEX.md overrides
- Plugins may ship `knowledge/INDEX.yaml` (preferred, machine
  readable) with `entries: [{path, title, summary, tags}]`. When
  `path` ends in `/` (or names a directory), the entry applies to
  the directory's primary md file (`<dirname>.md` 
  `README.md`  first `*.md` alphabetically).
- Or ship `knowledge/INDEX.md` (fallback, markdown-linked) with
  bullets of shape `- [Title](relative/path.md)  summary`.
- Resolution order per file (highest wins): file frontmatter 
  INDEX.yaml entry  INDEX.md entry  implicit-from-path defaults.

### Added  Block C: `codenook knowledge` CLI
- `codenook knowledge reindex`  rebuild
  `<ws>/.codenook/memory/index.yaml` from every installed plugin's
  `knowledge/` and `skills/<name>/SKILL.md` plus any memory-
  extracted entries already present. Reports plugin / knowledge /
  skill counts. Idempotent (two back-to-back runs match modulo
  `generated_at`). Atomic write via tempfile + `os.replace`.
- `codenook knowledge list [--plugin <id>] [--limit N]`  print the
  indexed knowledge grouped by plugin.
- `codenook knowledge search <query> [--limit N]`  rank entries
  via the existing `find_relevant` substring scorer.
- The new `full_index` kernel module composes the unified payload;
  `cmd_knowledge` is the CLI front.

### Installer
- Post-install / post-upgrade hook now auto-runs the new reindex so
  `memory/index.yaml` is never an empty stub after install. Failure
  is best-effort: a warning is printed and the empty stub from
  `seed_memory` is left in place rather than aborting the install.

### Tests
- New `tests/python/test_knowledge_recursive.py` (10 tests):
  recursion, implicit tags-from-path, body summary extraction,
  INDEX.yaml override, INDEX.md override, frontmatter beating both
  INDEX files, dot-dir / `__pycache__` skip, real-prnook reindex
  (10 entries), reindex idempotence, and a CLI `knowledge search`
  smoke test.

### Bootloader
- `CLAUDE.md` gains a "Plugin knowledge discovery" section pointing
  conductors at `codenook knowledge {reindex,list,search}` and
  documenting the implicit / INDEX / frontmatter precedence.

### Backward compatibility
- Files with explicit frontmatter behave exactly as before
  (frontmatter still wins for every field). All existing knowledge-
  index tests pass unchanged. The 4 known-baseline failures from
  prior shipments are unchanged.
## v0.20.1 (2026-04-25) — hotfix: schema accepts new fields, tests no longer mask tick failures

### Fixed
- **CRIT-1 — task-state schema rejected new fields → first tick crashed.**
  `schemas/task-state.schema.json` declares
  `"additionalProperties": false`, but v0.19's `execution_mode` and
  v0.20's `task_input` were never added to the schema. The result:
  *every* task created with `--exec`, `--input`, `--input-file`, or
  via `--interactive` (the wizard always writes `task_input`) crashed
  the very first `tick` with
  `$: unexpected properties ['execution_mode']` (or `['task_input']`)
  and exited 1. Schema now lists `execution_mode`, `task_input`,
  `model_override`, and `profile` explicitly. Pure additive — no
  `schema_version` bump required.
- **CRIT-2 — tests masked the schema crash.**
  `tests/python/test_task_wizard.py::test_input_persists_and_in_envelope`
  ran `tick` with `check=False` and then guarded every assertion
  behind `if cp.returncode == 0: ...`, so the crash slipped past
  green CI. Replaced with hard
  `assert cp.returncode == 0, f"stderr={...}"` and added a new
  end-to-end regression test
  (`test_v0201_new_flags_tick_without_schema_violation`) that
  exercises `--profile` + `--input` + `--exec inline` + `--model`
  together and asserts `tick` exits cleanly with no schema error.
- **HIGH-1 — `task new --interactive` infinite-looped on stdin EOF
  for the required title prompt.** When the wizard's stdin closed
  while the user was at the "Title (required)" prompt, the loop
  spammed "title cannot be empty." forever because `_prompt` could
  not distinguish "user pressed enter" from "stdin at EOF". `_prompt`
  now returns a sentinel on EOF; the wizard checks for it at every
  prompt and aborts with a clear `stdin closed; aborting wizard`
  message and `rc=1`. Wizard top level also catches `KeyboardInterrupt`
  for graceful Ctrl+C.

### Known issues — queued for v0.20.2 / v0.21.0
The deep code review surfaced four additional items that are NOT
fixed in this hotfix because they are benign or low-frequency. They
are tracked for the next release:

- **HIGH-2** — augmentation transactional gap (idempotent / benign).
- **MED-1** — inline envelope omits `prior_outputs`.
- **MED-2** — `task set-profile` allowed while `in_flight_agent` is set.
- **MED-3** — `task new --input ""` silently dropped (empty string).



## v0.20.0 (2026-04-25) — task-creation entry points

### Added
- **`task new --profile <name>`** — pin a per-task profile up front.
  Validated against the chosen plugin's `phases.yaml :: profiles`
  keys; rejected with a helpful list of valid choices when invalid.
  Persisted to `state.json` as `profile: <name>`. The kernel's
  existing `_resolve_profile()` already honours `state['profile']` as
  the highest-priority resolution source, so the field flows through
  to dispatch with no other changes.
- **`task new --input <text>` / `--input-file <path>`** — seed the
  initial task description without going through the clarify phase.
  Mutually exclusive. Persisted to `state.json` as
  `task_input: <str>` and surfaced in the `tick --json` dispatch
  envelope under the same key, so phase agents and the inline
  conductor can use the seed verbatim.
- **`task new --interactive`** — wizard mode. Walks the user through
  plugin → profile → title → input (multi-line) → model → exec mode
  via plain stdin/stdout (no TUI library, no readline dependency;
  works in PowerShell, cmd, bash, zsh). Validates as it goes
  (rejects empty title; validates profile against the chosen plugin)
  and asks "Create? [Y/n]" before writing state.json. Mutually
  exclusive with `--accept-defaults`.
- **`task set-profile --task <T-NNN> --profile <name>`** — switch
  profile post-hoc. Conservative: rejects when the task's history
  already records a phase verdict (i.e. the pipeline is "in flight").
- **`plugin info <id>`** — print the chosen plugin's profiles +
  phases catalogue summary. Discovery helper for users of
  `--interactive` and for anyone trying to remember the available
  profile names.
- `task status` now surfaces the per-task `profile` column.
- Bootloader gained a "Task creation entry points" section
  documenting the three modes (one-shot, interactive, minimal).

### Schema
- `state.json` accepts two new optional fields:
  - `profile: <str>` — pinned profile, sourced from `--profile`,
    `--interactive`, or `set-profile`.
  - `task_input: <str>` — seed description, sourced from `--input`
    or `--input-file`.

  Absence of either field ⇒ v0.19.1 behaviour exactly.

### Backward compatibility
Every flag absence equals v0.19.1 behaviour. `task new` with no
new flags creates state.json with the same key set as v0.19.1.



## v0.19.1 (2026-04-21)

### Added
- Bootloader gained an explicit "Discovering existing tasks"
  paragraph instructing the conductor to use `codenook status`
  for task enumeration, NOT `glob .codenook/tasks/*/state.json`.
  Many host runtimes (Claude Code in particular) skip
  dot-directories in their default glob filter and silently
  return zero results, leading the conductor to falsely conclude
  "no active tasks". The CLI is the only reliable surface.

## v0.19.0 (2026-04-24) — per-task execution mode

### Added
- **`execution_mode` per task.** Each task's `state.json` now accepts
  an optional `execution_mode` field with two valid values:
  - `sub-agent` (default) — each phase is dispatched as a separate
    sub-agent via the conductor's task tool. Historical v0.17/v0.18
    behaviour. Best for heavy / parallelisable / context-isolated work.
  - `inline` — the conductor reads `role.md` inline in its own
    session, produces the phase output file itself, then calls `tick`
    again to advance. No sub-agent spawn. Best for short / chatty /
    serial phases (clarifier-style, doc review).

  Backward compat: tasks without the field — i.e. every task created
  before v0.19 — behave exactly as v0.18.x. Anything other than the
  two valid mode strings is coerced to `sub-agent`.

- **`_lib/exec_mode.py`** — `resolve_exec_mode(state) -> "sub-agent"
  | "inline"`. v0.19.0 reads only the per-task field; the helper
  documents a future extension hook for plugin- and workspace-default
  fall-throughs (`plugin.yaml :: default_exec_mode`,
  `config.yaml :: default_exec_mode`).

- **CLI: `task new --exec {sub-agent,inline}`** — set the execution
  mode at task creation time. Omit to keep the default.
- **CLI: `task set-exec --task <T-NNN> --mode {sub-agent,inline}`** —
  change the execution mode of an existing task.
- **CLI: `status`** — per-task summary line now includes
  `exec=<mode>` (defaults to `sub-agent` when the field is absent).

- **Dispatch envelope: new `inline_dispatch` action.** When the
  resolved execution mode is `inline`, `tick --json` returns an
  envelope with `action: "inline_dispatch"` (instead of the existing
  `phase_prompt`) and adds the fields `execution_mode: "inline"`,
  `role_path` (alias of `system_prompt_path`), and `output_path`
  (alias of `reply_path`) so the conductor has every path it needs
  to do the work in-session without re-querying the kernel. The
  optional `model` field from v0.18 is still emitted in inline mode
  but is informational only — the conductor cannot switch models
  mid-conversation.

- **Bootloader (`claude_md_sync`)** — added an "Execution mode in
  dispatch envelope" section after the v0.18 model-selection section,
  documenting the two `action` values and the inline-mode protocol.

### Tests
- New `tests/python/test_exec_mode.py` (17 cases) covering the
  resolver, both CLI subcommands, envelope wiring for both modes,
  the model-field passthrough in inline mode, and the simulated
  conductor-writes-output-then-tick contract.



### Fixed
- **Transactional state mutation in `orchestrator-tick`.** Previously,
  a single `tick` invocation could mutate the in-memory state dict
  (clear `in_flight_agent`, append a verdict to `history`) and then
  hit a downstream branch that returned an error envelope (typically
  `lookup_transition` returning `None` because `transitions.yaml` was
  missing or malformed). The mutated dict was still persisted to
  `state.json`, so the next `tick` saw `in_flight_agent=None` +
  `status=in_progress` + `phase` unchanged → recovery branch →
  re-dispatched the same phase, overwriting the completed output and
  losing the verdict. The result was an infinite re-dispatch loop on
  any tick that errored after consuming a verdict.
- `tick(workspace, state_file)` now operates transactionally:
  1. The on-disk state is read once at entry and snapshotted.
  2. All algorithm body work runs against a `copy.deepcopy` working
     copy.
  3. On the success path the working copy is returned to the caller
     for persistence.
  4. On any failure path — either the body raises or it returns a
     summary envelope with `status == "error"` — the original
     snapshot is returned instead, so persisting it is a byte-for-byte
     no-op. `state.json` is guaranteed unchanged when an error
     occurs mid-tick.
- The error envelope returned to the caller is unchanged in shape and
  content; only the on-disk side effect is fixed. After the operator
  fixes the underlying issue (e.g. adds the missing
  `transitions.yaml`), the next `tick` resumes cleanly from the
  preserved in-flight state and advances to the correct next phase.
- `main()` additionally short-circuits the `persist_state` call when
  `summary["status"] == "error"` (defense in depth on top of the
  rollback).

### Tests
- `skills/codenook-core/tests/python/test_tick_transactional.py`
  (4 cases): happy path, error mid-tick → byte-identical state.json,
  recovery after fix does not re-dispatch, and "no phantom history
  entry on errored tick".

### Compatibility
- No external contract change. Tick still returns the same
  `(state, summary)` tuple shape on success and the same error
  envelope shape on error. CLI exit codes unchanged.

---

## v0.18.0 (2026-04-22)

### Added
- **End-to-end LLM model selection through a four-layer priority chain.**
  CodeNook now controls which model the conductor passes to its sub-agent
  task tool when dispatching a phase agent. Resolution order, first match
  wins:
  1. **C — Task override** — `tasks/<T-NNN>/state.json :: model_override`
  2. **B — Phase default** — `plugins/<id>/phases.yaml :: phases[*].model`
  3. **A — Plugin default** — `plugins/<id>/plugin.yaml :: default_model`
  4. **D — Workspace default** — `<ws>/.codenook/config.yaml :: default_model`

  When all four are absent the dispatch envelope omits the `model` key
  entirely, so the conductor falls back to its platform default
  (backward compatible — v0.17.1 envelopes look identical).
- New helper `_lib/models.py :: resolve_model(workspace, plugin_id,
  phase_id, task_state)` implements the chain. Model strings are opaque
  — the kernel does not validate or whitelist them.
- `cmd_tick` calls `resolve_model` when augmenting the phase-dispatch
  envelope and emits `"model": "<name>"` only when resolution returns
  a non-empty string.
- **CLI: `task new --model <name>`** writes `model_override` into the
  new task's `state.json`.
- **CLI: `task set-model --task T-NNN (--model <name> | --clear)`**
  changes the per-task override on an existing task.
- Installer now seeds a placeholder `<ws>/.codenook/config.yaml` with
  a commented-out `default_model:` hint when none exists. Idempotent;
  never overwrites a user-provided file.
- `task-state.schema.json` accepts the optional `model_override` field
  (`string | null`).
- CLAUDE.md bootloader gains a new "Model selection in dispatch
  envelope" section telling the conductor to forward the envelope's
  optional `model` field verbatim to its task tool.

### Tests
- 13 new pytest cases in `tests/python/test_model_resolve.py` covering
  every layer of the chain, the empty-string sentinel, envelope
  construction (present + absent), and the new CLI flow
  (`task new --model`, `task set-model`, `--clear`, mutual-exclusion
  validation, help-text contains `--model`).

---



### Fixed
- **Windows shim now finds Python when it is not on `PATH`.** `install.py`
  records `sys.executable` (the absolute path of the interpreter that
  ran the installer) and bakes it into both `bin/codenook.cmd` and
  `bin/codenook` via a `{{PY_EXE}}` template substitution. The runtime
  fallback chain becomes: recorded path → `python` on PATH → `py -3` →
  helpful error. POSIX shim gets the recorded path as its shebang.
- **Installer now seeds `.codenook/memory/index.yaml`** with the empty
  `version: 1 / generated_at: null / skills: [] / knowledge: []`
  schema. Previously the file was created lazily by `export_index_yaml`
  on the first knowledge / skill write, but conductor and kernel
  surfaces that read it directly errored with `Path does not exist` on
  fresh workspaces. Idempotent — never overwrites an existing index.
- **`codenook status` no longer crashes on archive task dirs.** Added
  `is_active_task_dir(p)` / `iter_active_task_dirs(tasks_dir)` helpers
  in `_lib/cli/config.py` that treat a missing `state.json` (and dirs
  whose name starts with `.` or `_`, and non-directory entries) as
  "not an active task" and skip them silently. `cmd_status` now uses
  the helper so user-dropped legacy folders (e.g. `T-101..T-103` with
  archived investigation docs but no state machine) are invisible
  instead of fatal.

## v0.17.0 (2026-04-21)

### Changed — Simplify HITL: remove view-renderer + hitl prepare + hitl render; conductor renders both channels

The Python-side view-renderer machinery is removed. All HITL surface
rendering is now the conductor LLM's responsibility.

#### Removals

- **`view-renderer` builtin skill** (`skills/codenook-core/skills/builtin/view-renderer/`)
  — deleted entirely (`render.py`, `render.sh`, `render.cmd`, `_render.py`,
  `SKILL.md`, `templates/`).
- **`hitl prepare` subcommand** — removed from `cmd_hitl.py` and
  associated `view-renderer` invocation.
- **`hitl render` subcommand** — removed from `cmd_hitl.py`.
- **`cmd_render_html`** and `render-html` wiring in
  `hitl-adapter/_hitl.py` — removed (HTML rendering helpers,
  `_render_markdown`, `_render_inline`, `_html_escape`, `_open_in_browser`).
- **`hitl-adapter/html.sh`** shim — deleted.
- **Reviewer artefact fallback** (`reviewer.ansi`, `reviewer.html`)
  in `cmd_show` — removed.

#### Surviving HITL surface

- `<codenook> hitl list [--json]`
- `<codenook> hitl show --id <eid> [--raw]`
- `<codenook> hitl decide --id <id> --decision <…> [--reviewer …] [--comment …]`

#### Bootloader rewrite

CLAUDE.md bootloader HITL relay section rewritten: conductor chooses
`terminal` (paste markdown as normal response) or `html` (LLM produces
styled HTML, writes to disk, shells out to open in browser), then
submits via `hitl decide`.

## v0.16.1 (2026-04-21)

### Fixed
- **`codenook hitl prepare` now works on Windows** — `cmd_hitl.py`
  invokes `render.py` via `sys.executable` instead of shelling out
  to `bash render.sh`, so the subcommand no longer requires Git-Bash
  or `python3` on PATH.

### Added
- **`view-renderer/render.py`** — new Python CLI entry point
  (`python render.py prepare --id <eid> [--workspace <dir>]`).
  Replaces `render.sh` as the primary invocation. `render.sh` is
  updated to call `render.py` with a `python3 || python` fallback;
  `render.cmd` is added as a Windows shim.
- **Bootloader: pre-render promoted to step 0 (SHOULD)** — the
  "optional polish step" buried inside the channel-choice section is
  restructured as a separate numbered step (step 0) that runs
  **before** the channel-choice ask, with explicit SHOULD wording and
  the OS-agnostic `<codenook> hitl prepare --id <eid>` invocation.
  This replaces the direct `render.sh` call that blocked Windows.

## v0.16.0 (2026-04-21)

### Added
- **`view-renderer` builtin skill** — LLM-side rewriter that turns a
  rigid role-output markdown file into reviewer-friendly HTML + ANSI
  artefacts dropped into `.codenook/hitl-queue/<eid>.reviewer.{html,ansi}`.
  The skill itself ships only the orchestration script + prompt
  template + HTML wrapper (mermaid CDN preloaded so inline
  `<pre class="mermaid">flowchart …</pre>` blocks render in the
  browser); the actual content rewrite is performed by the host's
  LLM, following the contract in `templates/prompt.md`.
- `_hitl.py` `cmd_render_html` and `cmd_show` now prefer the
  reviewer artefact when present and silently fall back to the
  stdlib renderer (v0.15.2 behaviour) when missing — so the
  feature is best-effort and never blocks the gate.
- `codenook hitl prepare --id <eid>` thin wrapper that emits the
  view-renderer envelope; `codenook hitl show` learnt `--raw`
  to bypass both the reviewer artefact and the stdlib styling.
- CLAUDE.md bootloader gained an optional polish step instructing
  the host to invoke `view-renderer prepare` for each new pending
  HITL gate before relaying it to the user.

## v0.15.2 (2026-04-21)

### Fixed
- **HITL HTML preview rendered raw markdown as text** (`e655fcb`).
  `_hitl.py` `cmd_render_html` injected role-output markdown into a
  `<div class="ctx">` with `white-space:pre-wrap`, so headers, lists,
  code blocks and links were displayed as literal source. Added a
  stdlib-only `_render_markdown()` (ATX headers, fenced code,
  blockquote, ordered/unordered lists, paragraphs + inline code,
  bold, italic, links) and the matching `<style>` rules so the
  preview is now actually readable.
- **`hitl show` dumped raw markdown to the terminal** (`e91f3f4`).
  Added `_render_terminal()` — ANSI-styled headers, fenced code blocks
  with separator rules, blockquote rail, bullet/ordered markers,
  inline code/bold/italic/link styling. Honors `NO_COLOR`; falls back
  to raw bytes when stdout is not a TTY or when the new `--raw` flag
  is set on `terminal.sh show`.

### Changed
- **HITL preview is now reviewer-first** (`6865df7`, `7e1fc52`,
  `8b31dcc`, `798d5d4`). Stripped YAML front-matter from the
  rendered context; removed the redundant page chrome (H1 title,
  meta line, "How to answer" footer with stale `--id` syntax, and
  the decisions badges); the orchestrator no longer emits the
  `# Approval requested:` H1 nor the duplicated "Decide one of" /
  "Submit via" prompt blocks (the gate name and CLI contract are
  already first-class). The HTML page now shows only the markdown
  the reviewer needs to read.
- **Reader / Spec view toggle on the HITL preview** (`f56c281`,
  `21d6aaa`). Added a tiny client-side toggle (top-right) that
  hides chrome only the distiller cares about: the leading
  `Role — T-XXX` identification header, parenthetical hints in
  section titles (`Goal (user vocabulary)` → `Goal`), and any
  `## ... rationale` section intended for the distiller. Default is
  Reader view; Spec view restores the full source. Same transform
  is applied in the terminal renderer; `--raw` keeps the bytes as-is.



## v0.15.1 (2026-04-21)

### Changed
- **Knowledge extraction — coarse-grained per-task output** (`64f9c95`).
  `extractor-batch.sh` used to fan out one knowledge-extractor
  invocation per contributing role (clarifier / planner / tester /
  acceptor → four near-duplicate `by_topic` files per task). Per-role
  candidates harvested from `tasks/<T>/outputs/*.md` are now folded
  into a single synthesized candidate per task. Contributing roles
  are preserved on the merged entry's `sources_by_role:` frontmatter
  and in a trailing `## Sources` section. Skill-extractor retains
  its existing `PER_TASK_CAP=1` cap.
- **Write-time fuzzy-merge dedup** (`64f9c95`). Before materialising
  a new `memory/knowledge/by_topic/<topic>.md` or
  `memory/skills/<name>.md`, the layer scans existing entries via a
  new stdlib-only `text_fingerprint` module (normalized fingerprint
  + `difflib.SequenceMatcher` body ratio + 4-shingle Jaccard
  overlap). Matches land as a `sources:` append + optional dated
  `## Update — T-NNN — <iso>` section when the new body contributes
  ≥ 20% new shingles. Callers that need deterministic creation
  (tests, the extractor's suffix-on-collision branch) can pass
  `fuzzy_merge=False`. `memory/index.yaml` now emits per-entry
  `sources: [T-NNN, T-MMM, …]`.

### Fixed
- **Concurrent merge lost updates** (`151d8e5`, [CRITICAL]). The
  v0.15.1 merge helpers did scan → read → mutate → `_atomic_write_text`
  without holding a lock. Two concurrent writers fuzzy-matching the
  same target both read the pre-merge body, each appended only their
  own `sources:` entry, and `os.replace` serialised with the second
  writer silently overwriting the first's additions. Fixed by
  acquiring a directory-level `_knowledge_write_lock` /
  `_skills_write_lock` sentinel over the full
  scan+match+merge+write sequence, with a re-check of
  `target.exists()` inside the lock to close the TOCTOU gap.
- **Title-equality false positives** (`151d8e5`, [MAJOR]).
  `is_fuzzy_match` returned "merge" on `title_normalized_match` alone,
  which conflated unrelated entries sharing a generic title ("Key
  Findings", "Summary", "Notes"). Title equality now requires
  `body_ratio ≥ TITLE_MATCH_MIN_BODY_RATIO` (0.30) before declaring a
  match; the 0.85 body-ratio and 0.70 shingle-Jaccard paths remain
  disjunctive as before.
- **Suffix-on-collision branch silently bypassed by fuzzy-merge**
  (`151d8e5`, [MAJOR]). knowledge-extractor's "file exists → append
  timestamp suffix" branch (FR-LAY-3) forgot to pass
  `fuzzy_merge=False`, so a suffixed path chosen explicitly to stay
  distinct could still be folded into a prior entry through a title
  match. The branch now passes `fuzzy_merge=not suffixed`.
- **Sources block truncated away** (`151d8e5`). The aggregator
  truncated `body + "## Sources"` together, chopping off the Sources
  list for tasks with long role outputs. Truncation now happens
  before the Sources block is appended.
- **`append_by_role_reference` swallowed real failures** (`151d8e5`).
  Narrowed the except to `FileNotFoundError` / `ValueError`; other
  exceptions now emit an audit record with
  `verdict=by_role_reference_failed` for observability.
- **`extractor-batch.sh` exported dead `CN_ARTEFACT_PATHS`**
  (`151d8e5`). Removed; no consumer existed.
- **Fuzzy-match scan was O(N²) on disk reads** (`151d8e5`). Added a
  module-level `_BODY_CACHE` keyed by `(path, mtime_ns)` with
  `_read_knowledge_cached` / `_read_skill_cached` wrappers. Stale
  entries auto-invalidate on atomic write. Sufficient until memory
  grows beyond a few hundred entries, at which point a proper index
  is warranted (TODO in place).



### Added
- **Development plugin v0.2.0 — profile-aware 11-phase pipeline**
  (`40c1637`). `phases.yaml` now uses a two-key `phases:` (catalogue
  map keyed by id) + `profiles:` (`task_type → [phase id, …]`)
  shape. The catalogue covers
  `clarify → design → plan → implement → build → review → submit →
  test-plan → test → accept → ship` (the `ship` phase reuses the
  reviewer role with `mode: ship`). Seven profiles ship: `feature`
  (11 phases), `refactor` (9), `hotfix` (7), `test-only` (4), `docs`
  (4), `design` (3), `review` (3). Clarifier emits a `task_type`
  frontmatter field; tick caches the resolved profile in
  `state.profile` after the first dispatch (default: `feature`).
  Ten HITL gates wired (`requirements_signoff`, `design_signoff`,
  `plan_signoff`, `build_signoff`, `local_review_signoff`,
  `submit_signoff`, `test_plan_signoff`, `test_signoff`,
  `acceptance`, `ship_signoff`) — `implement` is the only gate-less
  phase by design.
- `memory/index.yaml` human-readable exporter (`77cc637`):
  regenerated on every memory write/delete and consumed by
  conductors / role agents to inventory available
  knowledge/skills/configs without scanning the filesystem.
- `extractor-batch` task-relevance routing (`c832bd3`): the
  dispatcher consults the planned routes before fanning out the
  three sub-extractors, reducing wasted LLM calls.
- HITL `html` channel auto-opens the rendered file in a browser
  (`62f98fa`); the bootloader's HITL channel-choice prompt is now
  mandatory (`1481a63`).
- Documentation set rewritten end-to-end for v0.14.0 + development
  v0.2.0 (`README.md`, `PIPELINE.md`, `docs/architecture.md`,
  `docs/skills-mechanism.md`, `docs/memory-and-extraction.md`,
  `docs/task-chains.md`) plus a regenerated three-layer architecture
  diagram (`docs/images/architecture.{svg,png}`).

### Changed
- **`codenook` CLI is now the sole sanctioned entry point**
  (`9c0d839`). Direct invocations of underlying helper scripts
  (`_tick.py`, `terminal.sh`, …) are unsupported; everything routes
  through `codenook task / tick / decide / hitl / extract / status /
  chain`.
- `cmd_decide` accepts either a phase id (`--phase clarify`) or a
  gate id (`--phase requirements_signoff`); the CLI resolves both
  shapes against `phases.yaml` (`48ea1b0`).
- All CLI commands and the orchestrator state machine now understand
  both the v0.2.0 catalogue+profiles map shape and legacy v0.1 flat
  `phases: [{id: …}, …]` lists, so existing plugins keep working
  unchanged (`48ea1b0`).
- Dispatch manifests substitute `{{TASK_CONTEXT}}` from
  `state.summary` so role agents get the user's intent without a
  side-channel read (`48ea1b0`).
- Bootloader (`CLAUDE.md`) no longer hardcodes a plugin id, so the
  block stays correct after `--plugin all` or any subset install
  (`06abc37`).

### Removed
- **`task_specific` extraction route deleted** (`77cc637`). All
  extracted artefacts now route to the `memory/` cross-task store;
  the per-task `extracted/` writers (`write_*_to_task` helpers) and
  the `TC-ROUTE-01` test are gone. `extraction_router.py` is kept
  as a thin compatibility shim that always returns `cross_task` —
  scheduled for full removal in a follow-up refactor.
- Stale top-level `CLAUDE.md` template (`08964fb`); the bootloader
  is now sourced exclusively from `claude_md_sync.render_block()`.
- **`router-agent` deprecated** (`077428e`): hidden from the
  bootloader template, and the `codenook router` flag now prints a
  deprecation warning. Scheduled for hard removal in the next major
  release; the conductor protocol drives `codenook` directly.

### Fixed
- Manifest YAML safety: orchestrator-tick no longer crashes on
  manifest templates with stray `{{ }}` Jinja-ish tokens
  (`48ea1b0`).
- `cmd_decide` removed an unreachable branch in the gate-id
  scanner (`e859578`).

## v0.14.0 (2026-04-20)

### Changed
- **Replaced bash CLI wrapper with Python.** The 623-line
  `templates/codenook-wrapper.sh` is gone (kept as
  `codenook-wrapper.sh.legacy` for one release). The installed shim
  at `<ws>/.codenook/bin/codenook(.cmd)` now forwards directly to the
  new `_lib/cli/__main__.py` package  no Git Bash, no
  `python3 -c '<inline>'` startup tax per subcommand.
- **Replaced bash installer with Python.** `install.sh` is gone
  (kept as `install.sh.legacy` for one release). Use
  `python install.py [--target <ws>] [--upgrade] [--plugin <id|all>]
  [--no-claude-md] [--yes] [--check] [--dry-run]`  same surface,
  no bash dependency on Windows.

### Added
- `skills/codenook-core/_lib/cli/` package: `app.py` dispatcher,
  `cmd_task / cmd_router / cmd_tick / cmd_decide / cmd_hitl /
  cmd_status / cmd_chain` modules. Subcommand surface is 1-for-1
  with the v0.13.x bash wrapper.
- `skills/codenook-core/_lib/install/` package: `cli.py`,
  `stage_kernel.py`, `stage_plugins.py`, `seed_workspace.py`.
- `templates/codenook-bin` (POSIX shim) +
  `templates/codenook-bin.cmd` (Windows shim)  thin python forwarders
  installed into `<ws>/.codenook/bin/`.
- `tests/python/test_cli_smoke.py`  pytest subprocess smoke for
  `--version`, `--help`, `status`, `task new`,
  entry-question, `hitl render` error path.

### Notes
- bats suite untouched and not run locally for this release (`bats`
  not installed on the dev box). The wrapper's external contract
  (stdin / stdout / exit codes) is preserved black-box, so the suite
  should pass in CI; verify there.
- The ~30 thin `skills/builtin/*/*.sh` shims are out of scope (Phase
  C); the new wrapper imports / subprocess-execs the underlying python
  helpers directly and bypasses those shims for performance.
- `install.sh.legacy`, `codenook-wrapper.sh.legacy` and
  `codenook-wrapper.cmd.legacy` ship one more release as fallbacks
  in case a user reports a contract regression with the new shims.
- Python floor: 3.9+ (PEP 585 `list[...]`/`dict[...]` used freely).
- `shellout` for user-supplied `plugins/*/validators/*.sh` is
  unchanged  the user-extension surface for plugin validators stays
  bash-friendly.
## v0.13.23 (2026-04-20)

### Added
- `hitl-adapter/html.sh render --id <eid>` — renders a pending HITL
  queue entry as a self-contained `.html` file (default location:
  `.codenook/hitl-queue/<id>.html`). The page includes the gate
  prompt, full context-file content, and the exact `codenook decide`
  command snippet. Useful when the gate prompt is long, code-heavy,
  or easier to review in a browser than in a terminal scroll.
- `codenook hitl <list|show|render|decide>` wrapper subcommand
  delegates to `terminal.sh` / `html.sh`; `render` writes the file
  and prints its absolute path on stdout.
- Bootloader (`CLAUDE.md`) HITL relay: when clearing a gate, the
  conductor now briefly asks the user whether to switch channels.
  **Default is `terminal`** (current behavior); the user can opt in
  to `html` per gate, in which case the conductor shells out to
  `codenook hitl render`, gives the user the file path, then
  collects the decision back in the terminal as usual. If the
  shell wrapper is unreachable the question is skipped and
  `terminal` is used unconditionally.

### Notes
- Decision submission still goes through `terminal.sh decide`
  (or the `codenook decide` / `codenook hitl decide` wrappers).
  `html.sh` is render-only by design — no clickable buttons,
  no localhost server, no embedded JS callbacks.
- The rendered file is HTML-escaped end-to-end and self-contained
  (inline CSS, no remote assets); safe to commit to a task branch
  for reviewer hand-off if desired.

## v0.13.22 (2026-04-20)

### Changed
- Bootloader (`CLAUDE.md`): clarifier phase now runs **inline in
  the conductor** instead of being dispatched to a `general-purpose`
  sub-agent. Saves ~30-60s per clarify round (no fresh context
  window, no role/knowledge re-load, no extra LLM round-trip).
  Mirrors the v0.13.19 router-agent demotion: any phase that is
  fundamentally "conductor talks to the user" belongs in the
  conductor itself.
- Hard rules tightened: conductor MUST run clarifier inline; MUST
  NOT spawn a sub-agent for it. Other phase roles (designer,
  planner, implementer, tester, acceptor, reviewer, validator)
  unchanged  still dispatched via `codenook tick`.
## v0.13.21 (2026-04-20)

### Added
- `plugins/development/plugin.yaml`: declarative `available_skills:` block
  (currently lists only the shipped `test-runner`). Single source of truth
  for which skills roles may invoke; extensible by users via
  workspace-local override of plugin.yaml.
- Chinese keywords in `plugins/development/plugin.yaml` (实现, 修复, 修 bug,
  重构, 调试, 测试, 代码评审, 提交) and `plugins/generic/plugin.yaml` (总结,
  解释, 说明, 帮我, 帮忙, 问答, 研究, 头脑风暴, 待办) for better conductor
  routing on Chinese prompts.

### Changed
- Development role files (clarifier/designer/planner/implementer/tester/
  acceptor/reviewer/validator) `## Skills` section: replaced the
  hard-coded "test-runner is the only one you should invoke" prose with
  a pointer to `available_skills:` in plugin.yaml + the `skill-resolve`
  invocation pattern. Adding a new skill now requires editing plugin.yaml
  only; role files stay stable.
- Plugin manifest version bump: development 0.1.1 -> 0.1.2,
  generic 0.1.1 -> 0.1.2 (writing unchanged).
# Changelog

All notable changes to this project will be documented in this file.

## [0.13.20] - bootloader: read state.json for installed plugins

### Fixed

- Conductor instructions now point at `.codenook/state.json`
  `installed_plugins` as the authoritative plugin list, instead of
  globbing `.codenook/plugins/*/plugin.yaml`. Globbing was
  unreliable across host LLM frontends (cwd / path-separator
  inconsistencies on Windows), causing the conductor to report
  "no plugins found" even when three were installed.

## [0.13.19] - conductor-driven plugin selection + dead router code removal

### Changed

- **Bootloader (`CLAUDE.md`)** flipped back: the conductor (host LLM
  session) now picks the plugin itself by reading
  `.codenook/plugins/*/plugin.yaml` (`applies_to`, `keywords`,
  `examples`) and skimming `.codenook/memory/{knowledge,skills,
  history,_pending,config.yaml}` for prior-task context. Default
  flow is `task new --plugin <id> --accept-defaults` → `tick`. The
  router-agent drafting sub-agent is **off by default** and only
  invoked when the user explicitly asks for it, or in multi-plugin
  ambiguous cases the conductor cannot resolve on its own.
- Hard rules relaxed accordingly: conductor MAY read plugin
  manifests and `memory/` (workspace-shared resources). Still MUST
  NOT read `plugins/*/roles/`, `plugins/*/skills/`, or
  `plugins/*/knowledge/` (those are sub-agent system prompts), and
  MUST NOT mention plugin ids in user-facing prose unless echoing
  back the user.

### Removed

- Dead `host_driver.py` (in-process LLM round-trip for router-agent)
  and its test (`tests/python/test_router_host_driver.py`). The
  `CN_ROUTER_DRIVE=1` opt-in block in the wrapper is removed; it
  was never enabled in production. Router still works via
  `codenook router` when explicitly invoked — `spawn.sh` +
  `render_prompt.py` are kept.

### Why

`router-agent` was costing a full sub-agent dispatch round-trip on
every task start, even when the user's intent already mapped
unambiguously to one plugin. Conductor-driven selection is one or
two file reads in main context, no extra LLM call, and lets the
conductor naturally surface ambiguity to the user via the host's
own prompting mechanism. Memory awareness was the missing piece:
prior-task knowledge now influences plugin choice and scope hints.

## [0.13.18] - re-promote router-agent as default + idempotent --upgrade

### Changed

- **Bootloader (`CLAUDE.md`)** now instructs the conductor to drive
  the default `task new` → `router` (drafting dialog) → `tick`
  loop. The single-call `task new --accept-defaults` shortcut is
  demoted to "single-plugin shortcut" with an explicit warning that
  it silently picks `installed_plugins[0]` in multi-plugin
  workspaces (which is almost always wrong). Restores the original
  intent of v6 — router-agent is the only component that actually
  ranks plugins by `applies_to` / `keywords` against user intent.

### Fixed

- `install.sh --upgrade` against an existing same-version install no
  longer trips G04 ("would downgrade or no-op"). The idempotent
  re-install path now applies regardless of whether `--upgrade` was
  passed explicitly. This unblocks kernel-only releases that don't
  bump per-plugin versions.

### Why

v0.13.13 demoted router-agent on the assumption that "single-plugin
workspaces are the common case". With multi-plugin install becoming
default in v0.13.16, that assumption no longer holds: silently
defaulting to plugin index 0 misroutes writing / generic tasks to
the development clarifier. Reverting to router-default makes
plugin selection explicit and LLM-mediated again.

## [0.13.17] - fix stale workspace knowledge / skills paths in role profiles

### Fixed

- **Plugin role profiles + manifest templates** referenced
  `.codenook/knowledge/` and `.codenook/skills/` for workspace-shared
  resources, but the actual layout puts those under
  `.codenook/memory/knowledge/` and `.codenook/memory/skills/`. Sub-
  agents reading the role profile during dispatch were chasing dead
  paths. All 34 affected files (development + generic + writing roles
  and manifest-templates) now point at the real locations.

- Same files referenced `.codenook/skills/builtin/orchestrator-tick`
  for the dispatcher. The kernel actually lives at
  `.codenook/codenook-core/skills/builtin/orchestrator-tick`. Fixed
  in 17 files.

## [0.13.16] - install all plugins by default + Windows path fixes

### Changed

- **`bash install.sh` now installs every plugin under `plugins/`** by
  default (currently `development`, `generic`, `writing`). The new
  `DEFAULT_PLUGIN="all"` triggers a fan-out loop that re-invokes
  `install.sh --plugin <id>` for each subdirectory containing a
  `plugin.yaml`. Use `--plugin <id>` to install a single plugin
  explicitly. Existing single-plugin invocations (`--plugin
  development`, etc.) are unchanged.

  Rationale: router-agent's plugin selection is meaningful only when
  multiple plugins are installed. Shipping just `development` made the
  generic / writing flows invisible to new users.

### Fixed

- **Windows reinstall stuck at G03/G07** — `install.sh`'s
  `read_plugin_version` and `state.json` lookups embedded bash-style
  paths (`/c/...`) directly into `python3 -c` strings. Python on
  Windows can't open MSYS-prefixed paths, so the lookups silently
  returned empty (errors swallowed by `2>/dev/null`), defeating the
  idempotent-reinstall auto-promote and tripping G03 ("already
  installed; use --upgrade") on every re-run. Now routes through a new
  `_native_path` helper that uses `cygpath -m` when available, and
  passes paths via env vars instead of shell-substituted string
  literals. Also adds `encoding='utf-8'` to those `open()` calls.

- **`install.sh` cp936 crash** — exports `PYTHONUTF8=1` and
  `PYTHONIOENCODING=utf-8` at the top so child Python processes can
  read non-ASCII YAML on Windows GBK locale (mirrors the wrapper fix
  shipped in v0.13.15).

## [0.13.15] - HITL queue prompt + clarify requirements_signoff gate

### Fixed

- **Windows GBK locale crash** — `codenook decide`, `tick`, and other
  wrapper subcommands silently failed (rc=1, no useful stderr) when
  any plugin YAML / Markdown file contained non-ASCII characters
  (em-dash, CJK), because Python's `open()` defaulted to the system
  cp936 codec. The wrapper now exports `PYTHONUTF8=1` and
  `PYTHONIOENCODING=utf-8` at the top, which is inherited by every
  child Python process (tick.sh, spawn.sh, hitl-adapter, host_driver,
  etc.). No script-level changes required.

### Added

- **`hitl-queue/<task>-<gate>.json`** entries now include a fully
  rendered **`prompt`** field. `_tick.write_hitl_entry` calls a new
  `_render_hitl_prompt` helper that combines the gate `description`
  from `hitl-gates.yaml`, the task title/summary/role/phase from
  `state.json`, the role's output `context_path`, and the standard
  `decide` invocation snippet into a Markdown approval prompt.

  Schema: added optional `prompt` property to
  `schemas/hitl-entry.schema.json` (kept off the `required` list so
  pre-0.13.15 fixtures stay valid).

  Bootloader rule "show the entry's `prompt` field verbatim" now
  matches reality. Conductor no longer has to read role output files
  and synthesize an approval question — that violated the
  zero-domain-budget protocol.

- **`plugins/development`** — added `requirements_signoff` HITL gate
  on the `clarify` phase. The clarifier writes the requirements spec
  (goals, acceptance criteria, non-goals, ambiguities) and the task
  pauses for human approval before any design work begins. Catches
  misunderstood scope at the cheapest point in the pipeline.

  `phases.yaml`: `gate: requirements_signoff` added to the `clarify`
  entry (no other phase changes).

  `hitl-gates.yaml`: new `requirements_signoff` gate definition,
  reviewer = human, description explains the rationale.



### Added

- **`cmd_tick` in `codenook-wrapper.sh`** — after running `tick.sh`,
  when invoked with `--json` and a phase agent has been dispatched,
  the wrapper now augments the tick output JSON with an **`envelope`**
  object identical in shape to the one `cmd_router` already emits:

  ```json
  {"envelope": {
     "action": "phase_prompt",
     "task_id": "T-001", "plugin": "development",
     "phase": "clarify", "role": "clarifier",
     "system_prompt_path": ".codenook/plugins/.../roles/clarifier.md",
     "prompt_path":        ".codenook/tasks/T-001/prompts/phase-1-clarifier.md",
     "reply_path":         ".codenook/tasks/T-001/outputs/phase-1-clarifier.md"
  }}
  ```

  The wrapper also renders
  `plugins/<plugin>/manifest-templates/phase-N-role.md` into the
  task's `prompts/` directory (substituting `{task_id}`, `{iteration}`,
  `{target_dir}`, …) so `prompt_path` always points at a real file
  the conductor can pass to its sub-agent. When a manifest template
  is missing, a minimal stub prompt is written instead.

- **`render_block` in `claude_md_sync.py`** — bootloader now teaches
  **one** unified dispatch protocol covering both router and phase
  agents. Whenever `tick --json` (or `router`) returns a JSON payload
  with an `envelope` field containing `prompt_path` / `reply_path`,
  the conductor performs the same round-trip: read the prompt, dispatch
  a sub-agent with `system_prompt_path` as system prompt and
  `prompt_path` as the user message, sub-agent writes `reply_path`,
  conductor re-ticks.

### Why

Before this change, `tick.sh` only wrote a 5-field
`outputs/<phase>-<role>.dispatched` marker and set
`state.in_flight_agent.expected_output`, leaving the conductor stranded:
the bootloader explicitly forbids reading `plugins/*/roles/`, so the
conductor had no legal way to know what prompt to give the dispatched
sub-agent. The result was an infinite `awaiting <role>` loop the user
saw in v0.13.13 — task created, ticked, then stuck because nothing
ever ran the dispatched agent.

By renderizing the manifest template and surfacing the same envelope
shape as router, phases now dispatch via the same protocol the
conductor already learned for router. No new bootloader concept.

### Compatibility

- The `.dispatched` marker is still written for back-compat; nothing
  reads it but external observers / tests may.
- Tick output shape is unchanged when `--json` is not passed or when
  no agent was dispatched on this tick — the `envelope` field is
  additive.
- The `CN_ROUTER_DRIVE=1` headless escape hatch from v0.13.12 is
  unchanged.



### Changed

- **`_lib/claude_md_sync.py` `render_block`** — restructured the
  bootloader so the **default** task-start flow is just two calls:
  `<codenook> task new --title --summary --accept-defaults` followed
  by `<codenook> tick --task T-NNN --json`. The router-agent dialog
  is moved to a separate **"Optional: router-agent drafting dialog
  (advanced)"** section and called out as only useful when there are
  multiple installed plugins to disambiguate or the user wants
  iterative drafting.

  Rationale: in single-plugin workspaces (the common case)
  router-agent is pure ceremony. `tick.sh` reads only `state.json`,
  which `task new --accept-defaults` already populates fully. Verified
  end-to-end: `task new` → `tick` advances cleanly to the clarifier
  phase without router ever being invoked.

  Also dropped the redundant *On user confirmation* section — the
  tick-loop instructions live next to `task new` now.

## [0.13.12] - cmd_router: stop hijacking the LLM round-trip; teach JSON envelope dispatch

### Fixed

- **`templates/codenook-wrapper.sh` `cmd_router`** — v0.13.11 made
  `codenook router` always run `host_driver.py` (which hits
  `_lib/llm_call.py`, defaulting to mock) and then cat
  `router-reply.md`. That stole the v6 protocol's LLM round-trip from
  the conductor (Copilot CLI / Claude Code / Cursor / etc.) and made
  every reply look like `[mock-llm:router] …`. Reverted to v6 design:
  `cmd_router` now only runs `spawn.sh` (which prints the JSON
  envelope on stdout) and exits. The conductor LLM is responsible for
  reading `prompt_path`, dispatching its own sub-agent with that file
  as the system prompt, and reading `reply_path` afterwards.
  Headless / batch use can opt back in with `CN_ROUTER_DRIVE=1`.

### Changed

- **`_lib/claude_md_sync.py` `render_block`** — rewrote the *How to
  start a task* and *On user follow-ups* sections to teach the
  conductor the JSON envelope dispatch protocol explicitly: parse
  `{prompt_path, reply_path, ...}`, dispatch sub-agent with
  `prompt_path` contents as system prompt, ensure sub-agent writes
  `reply_path`, then read and relay verbatim. Documented the
  `CN_ROUTER_DRIVE=1` headless escape hatch.

## [0.13.11] - Wrapper: Windows Python auto-discovery + relay router-reply

### Fixed

- **`templates/codenook-wrapper.cmd`** — the Windows shim previously only
  located `bash.exe`. Git-Bash bundled with Git-for-Windows ships **without
  Python**, so `bash codenook` failed at the very first `python3` call
  (silently parsed `kernel_dir` as empty → "kernel_dir missing/invalid").
  The shim now also discovers a Windows-side Python install and prepends
  its directory to `PATH` before launching bash. Search order:
  `%LOCALAPPDATA%\Programs\Python\Python3{13,12,11,10}`, then
  `%ProgramFiles%`/`%ProgramFiles(x86)%`, then `where python`, then
  `where py` (Python launcher).

- **`templates/codenook-wrapper.sh`** — Windows Python is named
  `python.exe`, not `python3.exe`, so prepending its dir alone is not
  enough — the wrapper (and every downstream call: `spawn.sh`, `tick.sh`,
  `host_driver.py`) hard-coded `python3`. The bash wrapper now synthesizes
  a tiny `python3` shim in a temp dir at startup if `python3` is absent
  but `python` is present, and front-loads it onto `PATH`. Subprocesses
  inherit `PATH`, so all 17 internal `python3` call sites just work
  without any per-site change.

- **`templates/codenook-wrapper.sh` `cmd_router`** — `spawn.sh` only
  prints a single-line JSON envelope (`{prompt_path, reply_path, ...}`)
  on stdout; the human-readable router reply lands in
  `tasks/<T>/router-reply.md`. Previously `cmd_router` returned just the
  envelope, leaving the conductor LLM to discover and read the file
  itself. `cmd_router` now appends the reply file contents to stdout,
  delimited by `----- router-reply.md -----` markers, so the LLM can
  relay it verbatim per the CLAUDE.md protocol contract.

## [0.13.10] - Bootloader: shell-agnostic examples (fix Linux regression)

### Fixed

- **`_lib/claude_md_sync.py` `render_block`** — v0.13.9 hard-coded
  PowerShell-style invocation (`.codenook\bin\codenook.cmd`,
  ```powershell``` fences, backslash paths) into every code example.
  This regressed Linux/macOS hosted-LLM sessions: bash treats `\` as
  an escape character, the `.cmd` file doesn't exist in POSIX
  installs, and shells skip ```powershell``` fences. Replaced all
  examples with a `<codenook>` placeholder, defined once in a
  per-shell mapping table:
    - bash/zsh/sh → `.codenook/bin/codenook`
    - PowerShell/cmd → `.codenook\bin\codenook.cmd`
  Code fences are now plain ```bash``` everywhere.

## [0.13.9] - Bootloader: prefer .cmd wrapper, drop raw bash invocations

### Changed

- **`_lib/claude_md_sync.py` `render_block`** — rewrite all
  invocation examples to use the `.codenook/bin/codenook[.cmd]` CLI
  wrapper instead of raw `bash spawn.sh` / `bash tick.sh` /
  `bash terminal.sh`. Background: hosted-LLM sessions on Windows
  (Copilot CLI, Cursor) typically don't have `bash` or `python3` on
  `PATH`. Real Copilot session was observed wasting many turns
  hunting `bash.exe` after CLAUDE.md said `bash spawn.sh ...`. The
  `.cmd` shim (added in v0.13.5) auto-discovers Git-for-Windows bash
  + python; LLM should always go through it.
- Drop the manual "scan tasks/T-* and increment" id-allocation
  instruction. `codenook task new --title "..."` allocates the next
  T-NNN automatically.
- Drop the now-redundant "Plain-shell alternative" section since the
  wrapper IS the canonical path.
- Adjust hard rules to reference `codenook` CLI subcommands instead
  of underlying `spawn.sh` / `tick.sh`.

## [0.13.8] - Bootloader: explicit-trigger only + always-ask-next-step rule

### Changed

- **`_lib/claude_md_sync.py` `render_block`** — removed the
  "LLM autonomously decides whether to start a task" section
  (with ✅/❌ examples and "lean toward starting" guidance). The
  conductor no longer guesses. A CodeNook task is started **only**
  when the user explicitly asks for one ("open a codenook task",
  "用 codenook 做", "走 codenook 流程", etc.). Without that explicit
  trigger the LLM answers the user normally and never spawns
  router-agent. This matches the original "main session has zero
  domain budget" design — even the trigger judgment is offloaded to
  the user.

### Added

- **Hard rule: always ask for next step** — every reply must end by
  asking the user what to do next (host's interactive prompt facility
  preferred, plain text otherwise). Applies whether or not a task is
  active.

## [0.13.7] - Bootloader: rewrite as autonomous-trigger main-session protocol

### Changed

- **`_lib/claude_md_sync.py` `render_block`** — the workspace
  CLAUDE.md bootloader was a soft "quick start" cheat sheet that told
  the LLM "at the start of every turn, invoke the router-agent skill".
  This (a) failed silently on hosts (Copilot CLI) that don't register
  a skill named `router-agent`, and (b) was too aggressive — every
  trivial Q&A would have spawned a task. Replaced with a strict
  conductor-style protocol:
  - **Trigger criteria**: LLM autonomously decides per turn — start a
    task when the user's intent is *"make me do something"*; do not
    when it's *"answer my question"*. Lean toward starting in doubt.
  - **Path**: explicit `bash .codenook/codenook-core/skills/builtin/router-agent/spawn.sh`
    invocations (no skill name lookup, works on any host).
  - **Loop**: full §1-§7 protocol covering initial spawn, follow-up
    user turns, confirm → handoff, tick driver loop with
    advanced/waiting/done/blocked branches, HITL relay.
  - **Hard rules**: zero domain budget — MUST NOT read plugin
    internals, mention plugin ids in prose, or modify state.json /
    router-context.md / draft-config.yaml directly.

  Net effect: a fresh hosted-agent session opening a CodeNook
  workspace will now pick up CodeNook on the first task-shaped user
  utterance instead of silently no-op-ing on a missing skill.

## [0.13.6] - Wrapper: normalize kernel_dir from Windows backslash form

### Fixed

- **`templates/codenook-wrapper.sh`** — `state.json.kernel_dir` is
  written by Python `Path.resolve()` which on Windows produces a native
  `C:\foo\bar` string. The wrapper then ran `[ -d "C:\foo\bar" ]`
  under msys/Git-Bash, which always returns false, so every
  `.codenook/bin/codenook` invocation on Windows aborted with
  "kernel_dir missing/invalid". Now normalised via `cygpath -u`
  (preferred) or a manual `^([A-Za-z]):\\(.*)$ → /\L\1/\2` rewrite.

## [0.13.5] - Windows: codenook.cmd shim so PowerShell can call the wrapper

### Added

- **`templates/codenook-wrapper.cmd`** — Windows shim installed alongside
  the existing bash wrapper. Forwards all args to bash via Git for
  Windows (`%ProgramFiles%\Git\bin\bash.exe`, then PATH). Without this,
  PowerShell users running `.codenook\bin\codenook ...` saw the
  Windows "Open with…" dialog because the unix-style `codenook` file
  has no extension. Now `.codenook\bin\codenook task new ...` works
  natively from PowerShell / cmd.
- **install.sh** — copies `codenook-wrapper.cmd` → `<ws>/.codenook/bin/codenook.cmd`
  next to the bash wrapper.

## [0.13.4] - Hot-fix: post-install assertion under Git-Bash on Windows

### Fixed

- **install.sh** — the E2E-P-001 post-install assertion read
  `state.json` by interpolating `$WORKSPACE` (a POSIX-style `/c/...`
  path under Git-Bash) directly inside a Python `-c` string. Native
  Windows Python could not open that path, so the assertion silently
  read `kernel_version=''` and aborted every install on Windows even
  though `state.json` was correct. Now passed via `CN_STATE` env var
  so msys path conversion kicks in.

## [0.13.3] - Code review follow-up: CI rebuild + doc version sync

### Fixed

- **CI workflow** (`.github/workflows/test.yml`) — old workflow still
  referenced `skills/codenook-init/` (deleted in v0.11.2), so CI failed
  on every push. Rewrote the workflow to:
  - verify top-level VERSION ≡ kernel VERSION (catch drift early);
  - syntax-check every `_lib/*.py` and every `builtin/**/*.sh`;
  - run `bash install.sh` against a temp workspace and assert that
    `state.json.kernel_dir` is workspace-local
    (`<ws>/.codenook/codenook-core/...`).
- **install.sh** — kernel bootstrap step (`init.sh "$WORKSPACE"`) now
  has explicit error handling that points at the half-written
  `<ws>/.codenook/codenook-core` and any `.codenook-core.*` staging
  dirs left behind, instead of dying silently under `set -e`.

### Changed

- **README.md** — replaced 9 stale `v0.11.x` / `v6` markers with the
  current `v0.13.x` / "plugin architecture" wording; updated badge,
  hero paragraph, install paragraph, init.sh paragraph, roadmap, and
  documentation table.
- **PIPELINE.md** — header, status-note (DR-003), and footer updated
  from `v0.11.x` to `v0.13.2`.

## [0.13.2] - 2026-04-20 · English CLAUDE.md + interactive install confirm

Two small but user-visible changes.

### Changed
- Repository `CLAUDE.md`: the previously Chinese `## 上下文水位监控` section
  is now `## Context watermark protocol`, fully translated to English.
  The full ≥80% watermark protocol contract (extractor-batch async dispatch,
  no direct memory scans, JSON envelope hand-off) is unchanged.
- `claude_md_linter._REQUIRED_HEADINGS_FOR_CLAUDE_MD` updated to the new
  English heading; matching bats fixtures (`good-memory-protocol.md`,
  `bad-no-memory-protocol.md`) and `m9-claude-md-linter.bats` assertion
  translated in lock-step. `docs/memory-and-extraction.md` literal
  reference updated.

### Added
- `install.sh` now **prompts before writing CLAUDE.md** by default, telling
  the user exactly which action will be taken (create stub / append block
  to existing file / replace existing block). Safe by construction: user
  content outside `<!-- codenook:begin --> ... <!-- codenook:end -->` is
  still never touched.
- New `--yes` / `-y` flag on `install.sh` for explicit auto-confirm.
  When stdin/stdout aren't a TTY (CI, piped installs), behaviour matches
  pre-v0.13.2 — proceeds silently. The prompt only appears when both stdin
  and stdout are interactive terminals, so existing automation is unaffected.
- `--no-claude-md` continues to skip the augmentation entirely (no prompt).

### Migration
None — pure forward-compatible. Interactive users will see a one-line
y/N prompt before any CLAUDE.md write; CI and pipelines are unchanged.

## [0.13.1] - 2026-04-20 · E2E-P round-2 fixes forward-ported

The 9 E2E-P findings from `docs/e2e-report-v0.11.3-parallel.md` (originally
shipped as v0.11.4 on the `release/v0.11.4` branch) are now forward-ported on
top of the v0.12 native-Windows port and the v0.13 self-contained workspace
kernel. No regressions: bats 914 / pytest 32, all green.

### Fixed

- **E2E-P-001** — `install.sh` now stamps `state.json.kernel_version` from
  the root `VERSION` file and asserts post-install that
  `state.kernel_version == VERSION` (catches inner/outer `VERSION` drift).
- **E2E-P-002** — `codenook task new` without `--dual-mode` returns a
  structured `entry_question` JSON + exit 2 instead of silently defaulting.
- **E2E-P-003** — extractor now consumes the real role-output frontmatter
  (`summary` + body) when no `extract:` block is present, so the memory
  layer is no longer observably empty after a full lifecycle.
- **E2E-P-004** — `claude_md_linter` learned a per-token inside-marker
  allowlist for kernel-reference tokens, resolving the linter ↔ installer
  self-conflict.
- **E2E-P-006** — `state.example.md` is now seeded into
  `.codenook/schemas/` (and any legacy copy at `.codenook/` root is
  removed), aligning bootloader and installer.

### Added

- **E2E-P-005** — `codenook task new --target-dir` flag (default `src/`);
  `tick` returns `entry_question` + exit 2 on missing `target_dir`;
  `codenook task set --field` subcommand to mutate `state.json`.
- **E2E-P-007** — dispatch-audit + hitl-adapter tee a per-task
  `audit.jsonl` alongside the global stream.
- **E2E-P-008** — `task new --priority P0|P1|P2|P3` (default P2); schema
  validation rejects invalid values.
- **E2E-P-009** — `tick` exit-code contract pinned: `0`=advanced/done,
  `2`=entry-question, `3`=hitl, `1`=error.

### Tests

- 11 new bats / pytest cases covering every round-2 regression: bats
  895 → 914, pytest 21 → 32.

See `docs/e2e-report-v0.11.3-parallel.md` for the full round-2 audit and
the v0.13.1 follow-up table.

## [0.13.0] - Self-contained workspace install

### Changed

- **install.sh** now bootstraps the kernel into the target workspace
  before invoking the orchestrator. Every workspace gets a private,
  fully self-contained copy of `codenook-core/` at
  `<ws>/.codenook/codenook-core/`. `state.json.kernel_dir` and all
  helper paths (`claude_md_sync.py`, `claude_md_linter.py`, schemas,
  templates) now resolve to the workspace-local copy, so a workspace
  no longer depends on the source repo's filesystem location.
- **builtin/init/init.sh** copies the entire `codenook-core/` tree
  (excluding `tests/`, `__pycache__`, `.pytest_cache`) via VERSION
  compare + atomic swap. Idempotent: re-running is a cheap version
  check.
- **CLAUDE.md** protocol command paths rewritten to
  `<ws>/.codenook/codenook-core/skills/builtin/...`. Removed all
  legacy "v6" version markers (current is v0.13.0).

### Why

Prior versions wrote the source repo's absolute path
(`<src>/skills/codenook-core/skills/builtin`) into each workspace's
`state.json`. Moving or deleting the source repo broke every
workspace. This release makes each workspace a portable, hermetic
unit.

## [0.11.3] - 2026-04-20 · Usability fix-pack (E2E round 1)


Round-1 follow-up to the v0.11.2 end-to-end report
(`docs/e2e-report-v0.11.2.md`): 11 user-blocking findings closed
(1 CRITICAL, 6 HIGH, 4 MEDIUM). Bats grows 885 → 895; pytest suite
introduced with 21 new tests covering router driver, tick verdict
parsing, entry-questions metadata, extractor frontmatter, linter modes,
and workspace state schema.

### Fixed

- **E2E-001 (CRITICAL)** — `bash install.sh` now installs an executable
  `.codenook/bin/codenook` wrapper exposing the canonical workflow:
  `task new`, `router`, `tick`, `decide`, `status`, `chain link`. The
  CLAUDE.md bootloader marker block lists literal commands instead of
  vague "invoke the router-agent skill" prose.
- **E2E-002** — added
  `skills/codenook-core/skills/builtin/router-agent/host_driver.py` for
  plain-shell / CI users without a hosted LLM driver. Reads
  `.router-prompt.md`, calls `_lib/llm_call.py`, writes
  `router-reply.md`. Wired into `codenook router`. Hosted agents
  (Claude Code / Copilot CLI) still drive the loop natively.
- **E2E-003** — installer now copies `task-state.schema.json`,
  `installed.schema.json`, `hitl-entry.schema.json`,
  `queue-entry.schema.json`, `locks-entry.schema.json` plus
  `state.example.md` into `.codenook/schemas/` and `.codenook/`.
- **E2E-005** — `_tick.read_verdict` now distinguishes `MISSING`,
  `NO_FRONTMATTER`, `YAML_PARSE_ERROR`, and `BAD_VERDICT` via a new
  `read_verdict_detailed()` API. Tick output reports
  `{"awaiting":"<role>","reason":"yaml_parse_error","detail":"...","file":"..."}`
  with a stderr warning instead of silently looking like the agent
  never returned.
- **E2E-006** — entry-questions blocked response now includes
  `allowed_values` (from `entry-questions.yaml` `questions:` block or
  the JSON-schema enum fallback for `dual_mode`) and a `recovery:`
  hint pointing to `codenook task set …`.
- **E2E-008** — `parent_id` / `chain_root` documented in
  `plugins/development/README.md`. New `codenook chain link --child T-X
  --parent T-Y` helper validates the relationship and echoes back the
  written fields for traceability.
- **E2E-009** — `knowledge-extractor` now consumes YAML frontmatter
  `extract:` blocks emitted by role outputs in
  `.codenook/tasks/<id>/outputs/*.md`. Falls back to LLM-driven
  extraction only when no role outputs exist; an outputs-present-but-
  no-`extract:` case yields `status: no_candidates` (not
  `parse_failed`). New pytest fixture asserts ≥1 knowledge entry per
  candidate.
- **E2E-015** (partial) — `extractor-batch` deduplicates
  `.extractor-*.err` lines so repeated runs don't grow unbounded.
- **E2E-016** — `bash install.sh` is now strictly idempotent: when
  `state.json` already records the same plugin id at the same version,
  the installer skips the gates that would fire G03/G07/G04 and prints
  `↻ already installed (idempotent)` with exit 0. Version mismatches
  still require an explicit `--upgrade`.
- **E2E-017** — `claude_md_linter` defaults to `--marker-only` mode
  (scan only INSIDE `<!-- codenook:begin … end -->`); `--strict`
  preserves the v0.11.2 whole-file behavior; new
  `--outside-marker-only` mode powers the installer's friendly warning
  about legacy v4.x tokens in user content.
- **E2E-018** — installer seeds `.codenook/memory/{knowledge,skills,
  history,_pending}/.gitkeep` plus a default `config.yaml` (`entries:
  []`). Idempotent — never overwrites an existing config.
- **E2E-019** — workspace `state.json` schema upgraded to v1:
  `schema_version`, `kernel_version`, `installed_at`, `kernel_dir`,
  `bin`, plus `installed_plugins[].{installed_at, files_sha256}`.
  Backward-compatible read of pre-0.11.3 format. Schema published at
  `.codenook/schemas/installed.schema.json`.

### Deferred to v0.12 (see `docs/e2e-report-v0.11.2.md` follow-up section)

E2E-004 (naming), E2E-007 (parent_suggester wrapper), E2E-010
(time-window UX), E2E-011 (post-validate produced_files audit),
E2E-012 (manifest expansion), E2E-013 (HITL silent), E2E-014 (workspace
state rename — addressed by `schema_version` instead).

## [0.11.2] - 2026-04-20 · Fix-pack (deep-review DR-001..DR-014 subset)

Fix-pack release applying the high-impact subset of the v0.11.1
deep-review (`docs/deep-review-v0.11.1.md`). Bats sweep grows from
**851 → 878** assertions (27 new); zero regressions. See
`docs/release-report-v0.11.md` §"v0.11.2 follow-up" for the full
matrix.

### Removed

- `skills/codenook-init/` — the v4.9.5 legacy initialiser was missed
  during v0.11.1 v5-poc cleanup. Deleted in full; the matching
  `sync-skills.sh` (which only existed to push that skill to
  `~/.copilot/` and `~/.claude/`) is also removed. Cross-references
  purged from README, PIPELINE, requirements, architecture and
  implementation docs (historical reports retain their original
  wording).

### Added

- Top-level `install.sh` rewritten: accepts `bash install.sh
  <workspace_path>` (DR-002) and delegates to
  `skills/codenook-core/install.sh`. New flags: `--dry-run`,
  `--upgrade`, `--check`, `--no-claude-md`, `--plugin <id>`. Always
  idempotent.
- `skills/codenook-core/skills/builtin/_lib/claude_md_sync.py` — new
  helper that writes/replaces a clearly delimited
  `<!-- codenook:begin --> ... <!-- codenook:end -->` bootloader block
  in the workspace `CLAUDE.md` (DR-006). Re-runs produce zero diff;
  user content outside the markers is never touched.
- `skills/codenook-core/skills/builtin/_lib/secret_scan.py` — extended
  ruleset (DR-005): JWT, Google API keys (`AIza…`), Slack tokens,
  generic `Authorization: Bearer …` (≥ 20-char token), modern GitHub
  PATs (`ghp_/ghs_/gho_/ghu_/ghr_`, `github_pat_`). Also added a thin
  CLI to the module so it can be invoked as
  `python3 secret_scan.py <file>...`.
- `skills/codenook-core/skills/builtin/preflight/_preflight.py`:
  `_discover_known_phases()` reads phase ids from the active plugin's
  `phases.yaml` (resolved via `state["plugin"]` or the single entry in
  workspace `state.json`); falls back to a generic legacy +
  development-plugin superset (DR-008).
- New bats: `tests/v011_2-fix-pack.bats` (19 cases),
  `tests/v011_2-install-claude-md.bats` (8 cases).

### Fixed

- `plugin_readonly.assert_writable_path` no longer over-blocks when
  called with `workspace_root=None`: now falls back to CWD as the
  implicit workspace, matching the kernel's runtime invariant
  (DR-001). Three legacy `m9-plugin-readonly.bats` tests
  (TC-M9.7-03 memory_layer, TC-M9.7-22 router_context, TC-M9.7-23
  draft_config) updated to chdir into the workspace, locking the new
  contract.
- `memory_index._write_snapshot` now `os.unlink`s the
  `.index-snapshot.json.lock` file after releasing the `flock`,
  preventing accumulation of stale lock files (DR-011).
- Source-tree docstrings rewritten: every `docs/v6/<name>-v6.md`
  reference now points at the flattened `docs/<name>.md` (DR-004).
  `grep -r docs/v6 skills/ plugins/` returns 0.

### Documentation

- README, PIPELINE, `docs/architecture.md`, `docs/implementation.md`:
  added `init.sh` subcommand status table / banner — only
  `--version`, `--help`, `--refresh-models` are ✅ live in v0.11.2;
  the rest are 🚧 planned for v0.12. Quick Start now points at
  `bash install.sh <workspace_path>` (DR-003).
- `docs/release-report-v0.11.md` MEDIUM-04 entry rewritten: clarifies
  that `fcntl.flock` IS implemented in `_write_snapshot`; only the
  cross-lock ordering between snapshot lock and per-task `task_lock`
  remains for v0.12 (DR-014).
- `docs/requirements.md` FR-INIT-2 updated to describe the new
  `install.sh` semantics and the legacy `codenook-init` removal.
- `blog/images/architecture-v0.11.{svg,png}` and the hero
  `blog/images/architecture.png` redrawn as a strict 4-layer C4
  diagram. `router-agent`, `orchestrator-tick`, `spawn`,
  `dispatch_subagent` now appear **once**, inside the Kernel
  container (alongside the other builtin skills and the `_lib/`
  utilities row). Hand-authored SVG; rendered via `rsvg-convert -w
  1920`.

## [0.11.1] - 2026-04-19 · Surface Cleanup (v5-poc removal)

Surface-only cleanup release. **No functional changes** to
codenook-core, plugins, or installer behaviour. All 851 bats
assertions continue to pass.

### Removed

- `skills/codenook-v5-poc/` deleted in full (79 files, 668 KB,
  11,856 LOC). The v5 monolithic PoC has been the historical
  predecessor of the v6 plugin architecture (codenook-core +
  plugins/) shipping since v0.10. Per `docs/architecture.md`
  §9, v5 is now retired. No source under `skills/codenook-core/`,
  `skills/codenook-init/`, or `plugins/` referenced v5-poc — verified
  by repo-wide grep before removal.

### Updated

- `README.md`: replaced v5.0 POC banner with v0.11.0 / v6 plugin
  architecture banner; added `docs/` navigation; bumped task-board
  and config schema examples from version `4.9.5` → `0.11.0`;
  reframed the v3.x / v4.x migration section as a "Historical
  Evolution" section pointing at v6.
- `install.sh`: rebranded banner to `# CodeNook v0.11.0 Installer`,
  removed v5-poc opt-in note, set pre-download `VERSION` fallback to
  `0.11.0`.
- `PIPELINE.md`: bumped header / footer markers to `v0.11.0+`.
- `plugins/development/{README,CHANGELOG}.md`: rephrased "ported from
  v5" → "built on v6 plugin framework".
- `plugins/development/prompts/criteria-{test,accept}.md`: dropped
  `(v5.0 POC)` header annotations.
- `skills/codenook-core/README.md`: removed "v5 remains the working
  end-to-end reference" note.
- `docs/{README,architecture,implementation,test-plan}.md`:
  flipped status from "design draft / shipping v5" to "implemented in
  v0.10 / v0.11"; marked v5 → v6 migration chapters as historical /
  completed archive.

### Preserved as history

- The v5.0 POC release entry below (5.0.0-poc.1, 2026-04-18) is kept
  verbatim as repository history.

## [0.11.0] - 2026-04-19 · Spec Consolidation & Cleanup

### 🧹 v6.0 Maintenance — M11 Spec Patches + Dead-Code Cleanup

Surgical release with **no new functional surface**. Three workstreams:

1. Reconcile the 8 spec/code inconsistencies + 10 spec omissions
   catalogued in `docs/requirements.md` §A.1 / §A.2.
2. Address two of the three M10 known-limitations
   (MINOR-04 / MINOR-06) with diagnostic-only hardening; defer the
   third (MEDIUM-04 snapshot TOCTOU) to v0.12 alongside the
   multi-process orchestration epic.
3. Drop two pieces of confirmed-dead code (`_SECRET_PATTERNS` alias,
   `now_safe_iso` stub).

Decision rationale lives in `docs/m11-decisions.md`.

#### Highlights

- **18 backlog items closed** (16 SPEC-PATCH, 2 CODE-FIX with bats
  lock-in). One item — A1-6 (session-resume M1-compat keys) — is
  deferred to v0.12 because removal requires rewriting
  `m1-session-resume.bats` end-to-end (10 asserts) and is best
  packaged as a `session-resume schema v2` epic.
- **Two new diagnostic audit kinds**, both fail-soft and best-effort:
  `chain_render_residual_slot` (MINOR-04) and `chain_parent_stale`
  (MINOR-06). Neither changes any user-visible behaviour or exit code;
  both surface previously-silent edge cases for ops visibility.
- **bats sweep: 851 / 851 PASS** (was 847; +4 lock-ins under
  `tests/v011-known-limitations.bats`).
- **Dead-code removed**: 10 LOC across 2 files, all 0-caller
  verified by repo-wide grep.
- **Real-workspace regression** at
  `/Users/mingdw/Documents/workspace/development` (~1000 active tasks)
  passes the M11.5 quality gates: session-resume JSON is well-formed
  and ≤500 B per task; `plugin_readonly --target . --json` reports
  `writes_to_plugins: []`; `claude_md_linter` exits 0.

#### Spec patches (per docs/m11-decisions.md)

| ID | Where patched | Topic |
|----|---------------|-------|
| A1-1 | requirements.md FR-TASK-3 | dual_mode optional, defaults to `serial` |
| A1-2 | requirements.md FR-CHAIN-2 + L-9 | `walk_ancestors` lib default `None`, router site default 100 |
| A1-3 | requirements.md G05 row | `plugin.yaml.sig` lenient first-non-blank-token compare |
| A1-4 | requirements.md FR-TASK-4 + FR-EXTRACT-4 + NFR-REL-4 + memory-and-extraction.md §5.2 | Trigger-key persistence (no 24h auto-expiry) |
| A1-5 | requirements.md FR-EXTRACT-5 | secret_scan = 9 patterns (single source of truth) |
| A1-7 | requirements.md FR-ROUTER-2 | `--confirm` exit 4 enumerates 5 failure paths |
| A1-8 | requirements.md G01 + G11 rows | Symlink policy split (defence in depth) |
| A2-1 | requirements.md FR-SKILL-2 | plugin_readonly standalone CLI mode + default exclusions |
| A2-2 | requirements.md FR-CHAIN-5 | ~70 EN+ZH stopwords + done/cancelled excluded |
| A2-3 | requirements.md FR-ROUTER-3 | task_lock 300 s threshold + unparsable payload conservative |
| A2-4 | requirements.md FR-MEM-4 | `promoted=true` entries never evicted |
| A2-6 | requirements.md FR-EXTRACT-5 | dispatch-audit redaction reuses `_lib/secret_scan` list |
| A2-7 | requirements.md FR-ROUTER-2 | `--user-turn-file -` reads stdin |
| A2-8 | requirements.md FR-DIST-1 | Sandbox blocks `__` and `import` tokens |
| A2-9 | requirements.md FR-EXTRACT-4 | `nohup` detach mechanism |
| A2-10 | requirements.md FR-PLUGIN-MANIFEST + §5.6 | `DEFAULT_PRIORITY = 100` |

#### Fixes

- **MINOR-04** — `render_prompt()` now scans the rendered prompt for
  residual `{{SLOT}}` tokens after the single-pass substitution loop;
  any leftover slot names are emitted in a fail-soft
  `chain_render_residual_slot` diagnostic audit. Substitution itself
  remains single-pass (no shell-style recursion); the diagnostic only
  surfaces accidental double-templating.
- **MINOR-06** — `cmd_confirm()` now looks up the candidate
  `parent_id`'s status before invoking `task_chain.set_parent`; if the
  parent transitioned to `done` or `cancelled` between prepare and
  confirm, a `chain_parent_stale` diagnostic is emitted and the attach
  proceeds (permissive, matches the router's existing "stale
  suggestion" semantics elsewhere).

#### Removed

- `skills/codenook-core/skills/builtin/_lib/secret_scan.py` —
  legacy module-level `_SECRET_PATTERNS` underscore alias (0 callers
  in production code, _lib, tests, or fixtures). Use the public
  `SECRET_PATTERNS` name.
- `skills/codenook-core/skills/builtin/session-resume/_resume.py` —
  unused `now_safe_iso(default="")` stub helper that returned its
  argument unchanged and was never invoked.

#### Backlog deferred to v0.12

- **A1-6** — session-resume M1-compat keys removal (schema v2 epic).
- **MEDIUM-04** — true `fcntl.flock` on snapshot rebuild (paired
  with multi-process orchestration design).
- **AT-REL-1** — manual SIGTERM reviewer procedure.
- **AT-LLM-2.1** — real-mode LLM guard bats.
- **AT-COMPAT-1** — Linux CI matrix.
- **AT-COMPAT-3** — `jq`-missing diagnostic bats.

#### Quality gates

- `bats skills/codenook-core/tests/*.bats` → **851 / 851 PASS**
- `claude_md_linter` → exit 0
- `plugin_readonly --target . --json` → exit 0,
  `writes_to_plugins: []`
- `git grep "M1-compat\\|backward.*compat\\|legacy alias"` → only
  the deliberate, documented session-resume case (DEFER-v0.12)
- secret-scan over staged diff → clean

---

## [0.10.0-m10.0] - 2026-04-19

### 🔗 v6.0 Milestone M10 — Task Chains

Greenfield parent–child linkage between tasks. A child task can now
declare a `parent_id`, and the router-agent automatically aggregates
chain context for the child's prompt: design decisions, summaries,
and key artefacts from each ancestor (root → parent) are
LLM-summarised into a single `## TASK_CHAIN (M10)` block above the
existing `MEMORY_INDEX`. A workspace-local
`.codenook/tasks/.chain-snapshot.json` (schema v2, gitignored) caches
chain roots so cold lookups stay sub-5 ms after the first walk.

#### Highlights

- **Parent–child task linking.** `state.json` gains optional
  `parent_id` and `chain_root` fields (additive — no migration; pre-M10
  tasks continue to be treated as independent roots).
- **Chain-aware context aggregation for child agents.** Router-agent
  invokes a 2-pass chain_summarize that (1) summarises each ancestor
  individually, (2) re-summarises the bundle if the per-chain token
  budget is exceeded; the newest 3 ancestors stay verbatim.
- **Snapshot-cached lineage walk.** v2 snapshot stores
  `{schema_version, generation, built_at, entries[<tid>] = {parent_id,
  chain_root, state_mtime}}`; mtime-aware invalidation rebuilds only
  on drift, full rebuild guaranteed sub-1 s for N ≤ 200 tasks.
- **Audit observability.** 6 canonical chain outcomes
  (`chain_attached`, `chain_attach_failed`, `chain_detached`,
  `chain_walk_truncated`, `chain_summarized`,
  `chain_summarize_failed`) plus 4 diagnostic kinds
  (`chain_root_stale`, `chain_snapshot_slow_rebuild`,
  `chain_summarize_redacted`, attach-time `chain_root_uncertain`).

#### New CLI

- `python -m task_chain {attach,detach,show,root}` — the M10 chain
  primitive surface, English-only output.
  - `attach <child> <parent> [--force]` — set the child's parent_id
    + chain_root; refuses self-loops, ancestor cycles, and corrupt
    parent ancestry.
  - `detach <child>` — clear parent_id and chain_root (idempotent).
  - `show <task> [--format text|json]` — print the ancestor chain
    in child→root order; JSON envelope includes
    `parent_id, chain_root, ancestors[], depth, snapshot_hit`.
  - `root <task>` — print cached chain_root.
  - Usage errors (unknown subcommand, missing positional, unknown
    flag) exit `64` per spec §4.3; operational errors map to `1` /
    `2` (cycle / corrupt) / `3` (already-attached) / `4` (parent
    attach failed at confirm time).

  Reference: `docs/task-chains.md` §4 (interface) and
  `docs/m10-test-cases.md` §M10.1 (behavioural test cases).

#### New library APIs

- **`_lib/task_chain`** — `get_parent`, `set_parent`,
  `walk_ancestors`, `chain_root`, `detach`, plus public
  `CycleError` / `CorruptChainError` / `TaskNotFoundError` /
  `AlreadyAttachedError`. Snapshot v2 maintained transparently on
  every mutation.
- **`_lib/parent_suggester`** — top-3 parent candidates with
  symmetric-difference + Jaccard score; threshold 0.15; ties broken
  alphabetically by task_id; `done` / `cancelled` tasks excluded.
- **`_lib/chain_summarize`** — 2-pass LLM summariser with built-in
  token-budget enforcement, secret-scan redaction, and per-call
  audit (`chain_summarized` / `chain_summarize_failed` /
  `chain_summarize_redacted`).
- **`_lib/token_estimate`** — shared 4-chars-per-token estimator;
  also exposes `truncate_to_budget`.

#### Router prompt

- New `{{TASK_CHAIN}}` slot, ordered above `{{MEMORY_INDEX}}` which
  remains above `{{USER_TURN}}`. When `parent_id` is null the slot
  collapses to empty (no `chain_summarize` invocation).
- New `{{PARENT_SUGGESTIONS}}` slot rendered during `prepare`, with
  the user-visible `## Suggested parents` block (top-3 +
  `0. independent (no parent)` opt-out).

#### State.json

- Optional `parent_id: string | null` and `chain_root: string | null`
  fields (no schema change required for legacy state.json files —
  both default to null).

#### Snapshot

- `.codenook/tasks/.chain-snapshot.json` (schema v2 per spec §8.2)
  cached per workspace, gitignored via the init skill's
  `.codenook/tasks/.gitignore`.

#### Audit

- 6 chain outcomes (canonical 8-key records, `asset_type=chain`).
- 4 diagnostic kinds emitted as `outcome=diagnostic, verdict=noop`
  side-records carrying a `kind` discriminator (does not violate
  the canonical-schema contract enforced by TC-M9.4-04).

#### Two-phase confirm

- `router-agent` `cmd_confirm` now writes `state.json` with
  `status=pending` BEFORE calling `task_chain.set_parent`; only
  flips to `in_progress` after attachment succeeds. A failed attach
  exits `4` (`parent_attach_failed`) and leaves the task in
  `pending` for the operator to re-prompt.

#### Known limitations

- **MEDIUM-04 (M10.6 §8 Issue 3) — Snapshot rebuild TOCTOU.** A
  concurrent writer mutating `state.json` during
  `_build_snapshot`'s O(N) scan may produce a snapshot that
  reflects a transient read. By contract M10 is single-process
  (the orchestrator serialises chain ops via the per-task
  task_lock); re-running set_parent / detach refreshes the
  snapshot deterministically. To be revisited if multi-process
  orchestration lands.
- **MINOR-04 (M10.5) — Substitution-recursion class.**
  `chain_summarize` body that itself contains the literal token
  `{{TASK_CHAIN}}` is rendered verbatim; the slot substitution is
  single-pass (no recursive re-render). Documented; not a security
  issue (no shell expansion).
- **MINOR-06 (M10.5) — `cmd_prepare` vs `cmd_confirm` slot timing.**
  `{{PARENT_SUGGESTIONS}}` is computed at `cmd_prepare` time; if a
  candidate task transitions to `done` / `cancelled` between
  prepare and confirm the user can still pick it. Confirm-side
  re-validation is NOT performed; behaviour matches "stale
  suggestion" semantics elsewhere in the router.

#### Migration

- **No migration required.** Pre-M10 tasks are naturally treated
  as independent (parent_id absent → null → no chain). Existing
  workspaces gain the new `.codenook/tasks/.chain-snapshot.json`
  file (and its `.gitignore` entry) on the next invocation of any
  M10 entry-point or `init` re-run.

#### Per-milestone

- **M10.0** Spec doc `docs/task-chains.md` (12 sections, 5
  FR groups, 7 NFR), `docs/m10-test-cases.md` test plan.
- **M10.1** `_lib/task_chain.py` primitives + state-schema fields
  + CLI; usage errors exit 64 (§4.3); R1 fixes raised
  CorruptChainError on corrupt parent ancestry and warn-class
  audit on truncated walks.
- **M10.2** `_lib/parent_suggester.py` with deterministic ranking
  + threshold + status filter.
- **M10.3** Router-agent spawn parent-UX hook (suggester →
  prompt; confirm → set_parent). Two-phase state.json write so
  attach failure leaves status=pending.
- **M10.4** `_lib/chain_summarize.py` 2-pass LLM aggregator,
  per-chain token budget, secret-scan redaction, audit; path
  traversal and unknown asset_type rejected.
- **M10.5** Router prompt `{{TASK_CHAIN}}` slot wired above
  `{{MEMORY_INDEX}}`; substitution failure mode = exit 0 + audit.
- **M10.6** Snapshot v2 schema, audit 6+4, perf budgets
  (depth=10 walk ≤100 ms avg, cold rebuild ≤1 s, warm cache
  ≤5 ms for N=200), cycle/self-parent → chain_root=null.
- **M10.7** Backlog fold: argparse exit-64 lock-in, set_parent
  warn-on-truncated, two-phase confirm, refuse-corrupt-ancestry,
  comment cleanup, and a comprehensive end-to-end TC binding all
  six audit outcomes + diagnostic + snapshot v2.

## [0.9.0-m9.0] - 2026-04-19

### 🧠 v6.0 Milestone M9 — Memory Layer + LLM-Driven Extraction

Greenfield memory subsystem: every task execution now sediments
`knowledge / skills / config` into a workspace-local writable layer at
`.codenook/memory/`, while the `plugins/` tree becomes strictly
read-only at runtime. The router-agent learns a `MEMORY_INDEX` of all
candidate + promoted entries and auto-injects matching ones into spawn
prompts. Anti-bloat is enforced by per-task caps, hash dedup, and the
new GC CLI.

#### Added — Per-milestone summary

- **M9.0** Spec doc `docs/memory-and-extraction.md` (Hermes-inspired
  patch-first pattern, 5 FR groups, 6 NFR, 8 milestones); architecture
  §13 ratifies M9; implementation.md M9 sections.
- **M9.1** Memory layout primitives — `_lib/memory_layer.py`
  (knowledge / skill / config + atomic IO + fcntl read-modify-write +
  21-function public API surface) and `_lib/memory_index.py`
  (mtime-cached snapshot at `.codenook/memory/.index-snapshot.json`,
  ≤500 ms over 1000 files). `init` skill creates the empty skeleton.
- **M9.2** Extraction triggers — `orchestrator-tick` `after_phase`
  hook, `extractor-batch.sh` async dispatcher (≤200 ms wall),
  CLAUDE.md 80% context water-mark protocol.
- **M9.3** Knowledge extractor — `knowledge-extractor` skill with
  patch-or-create flow, frontmatter strict validation (summary ≤200,
  tags ≤8), `find_similar()` + LLM merge / replace / create judge
  (default merge), per-task cap ≤3, hash dedup, secret scanner.
- **M9.4** Skill extractor — `skill-extractor` skill detecting ≥3
  repeated CLI / script invocations; per-task cap ≤1; reuses M9.3
  decision flow. `_read_task_context()` now ingests `notes/*.{md,txt,log}`.
- **M9.5** Config extractor — `config-extractor` skill normalising
  `task-config-set` calls into `config.yaml entries[]` with
  `applies_when`; same key merges to latest value; per-task ≤5.
- **M9.6** Router-agent memory awareness — `router-agent/prompt.md`
  now renders MEMORY_INDEX (name + description per entry); spawn.sh
  materialises plugins + memory two layers into the task prompt;
  `_lib/token_estimate.py` budget pruning; `router-context` 8-turn
  archiver.
- **M9.7** Plugin read-only enforcement — `_lib/plugin_readonly.py`
  (runtime guard inside `_atomic_write_text` + static checker CLI);
  CLAUDE.md linter expanded to forbid main-session direct memory greps.
- **M9.8** Release polish — see below.

#### Added — M9.8 (this release)

- **GC CLI** `_lib/memory_gc.py` (`python -m memory_gc --workspace
  <ws> [--dry-run] [--json]`) enforces per-task caps from spec
  §6 / §7 (knowledge=3, skill=1, config=5). Drops oldest by
  `created_at` (with path tie-break) within over-cap groups; promoted
  entries are never pruned. Real run audits each removal via
  `extract_audit.audit(outcome='gc_pruned', verdict='accepted')` and
  refreshes the memory-index snapshot. Exit codes: 0 nothing pruned /
  0 pruned OK / 1 error / 2 invalid args.
- **pre-commit hook template** `templates/pre-commit-hook.sh`
  (chmod 0755) — three gates: (1) staged write under `plugins/`
  rejected unconditionally, plus full `plugin_readonly.py --target .`
  static checker (M9.8 fix-r2: defaults now exclude
  `tests/fixtures/**` and `tests/**/fixtures/**` so the hook stops
  bricking the repo it ships with; `--exclude PATTERN` is repeatable
  and additive, `--no-default-excludes` restores legacy behaviour);
  (2) `claude_md_linter.py --check-claude-md` on root
  CLAUDE.md; (3) the shared SECRET_PATTERNS regex set across every
  staged blob. Install with `cp skills/codenook-core/templates/pre-commit-hook.sh
  .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit`.
- **E2E bats** `tests/e2e/m9-e2e.bats` covering TC-M9.8-01..04 (full
  spec contracts: extractor-batch round-trip surfacing α's summary in
  β's router prompt; watermark async produces a candidate within 5s;
  3 concurrent extractor-batch dispatches with no `.tmp.*` residue
  and no hash collisions; spawn `--confirm` materialises state.json
  while the rendered prompt cites seeded knowledge + applies_when
  config) plus regressions TC-M9.8-10 (GC dry-run/real run) and
  TC-M9.8-11 (pre-commit hook rejects top-level `plugins/` but allows
  nested `tests/fixtures/plugins/...` after the fast-gate anchor fix)
  and TC-M9.8-12 (router→extractor→memory-index loop idempotent
  across two ticks).
- **Backlog folds** — TC-M9.1-06 surface check now requires
  `promote_skill` and `promote_config_entry`; `_read_task_context()`
  also consumes `.txt` / `.log`; TC-M9.2-07 documents ±20% timing
  tolerance + `BATS_TEST_RETRIES=2`; design doc §10.1 explicit
  docstring for `promote_config_entry`.

#### Quality gates

- 798+ bats tests green across the full M1..M9.8 suite (M9.8 fix-r2
  adds 4 regressions in `tests/m9-plugin-readonly-excludes.bats`
  covering --exclude defaults, additive excludes, and
  --no-default-excludes; M9.8 fix-r1 brought 7 e2e cases —
  TC-M9.8-01..04 spec contracts + TC-M9.8-10..12 GC, hook regression,
  idempotent loop).
- `_lib/plugin_readonly.py --target . --json` exits 0 (defaults
  exclude bats fixture trees).
- `_lib/claude_md_linter.py --check-claude-md CLAUDE.md` 0 errors.
- 0 `description.md` references; no greenfield-forbidden tokens.
- 0 secret-scanner hits on the M9.8 diff (fixture AKIA / fd00 tokens
  in `m1-sec-audit.bats` and `m9-knowledge-extractor.bats` are
  constructed via runtime concatenation so the regex matches at test
  time but `git grep` finds nothing in source).

## [0.8.0-m8.0] - 2026-04-18

### 🚀 v6.0 Milestone M8 — Conversational Router Agent

Replaces the legacy stateless `router-triage` (M3) with a real
multi-turn, file-backed **router-agent** that drafts a task config in
conversation with the user and hands off to `orchestrator-tick` on
confirmation. **692/692 bats tests green.**

#### Added — Core (`skills/codenook-core/`)
- **M8.0** Spec doc `docs/router-agent.md` (640 lines) + decisions
  #46–#52 ratified in architecture.md §12 (router-agent as stateless
  subagent, YAML+md context, router calls init-task + first tick,
  300s stale-lock threshold, domain layering, M3 router-triage removed).
- **M8.1** Schemas + helpers — `_lib/router_context.py`,
  `_lib/draft_config.py`, plus M5-DSL schemas for router-context,
  draft-config, router-reply, router-lock.
- **M8.2** `router-agent` skill — `SKILL.md`, `spawn.sh`, `prompt.md`,
  `render_prompt.py`. Per-turn entry-point that prepares context,
  acquires fcntl lock, renders prompt, and on `--confirm` invokes the
  full handoff chain.
- **M8.3** Discovery indexes — `_lib/plugin_manifest_index.py`,
  `_lib/knowledge_index.py` (rank candidates, aggregate knowledge).
- **M8.4** Per-task fcntl lock — `_lib/task_lock.py` with positive-
  evidence stale recovery (closes unlink-recreate race).
- **M8.6** Domain-agnostic main session protocol — root `CLAUDE.md`
  (8-section v6 task lifecycle protocol) + `_lib/claude_md_linter.py`
  enforcing forbidden domain tokens going forward.
- **M8.9** Workspace user-overlay layer — `_lib/workspace_overlay.py`
  for project-scoped writable description/skills/knowledge/config that
  overlays the read-only plugin layer.
- **M8.10** Role enumeration + role-skip — `_lib/role_index.py`,
  `one_line_job` frontmatter on all 17 roles, draft-config gains
  `selected_plugins` + `role_constraints`, `orchestrator-tick`
  honours `role_constraints.excluded` by skipping phase.

#### Added — Tests
- 8 new bats files under `tests/m8-*.bats` (~85 tests covering every
  M8.x milestone, including a 5-test E2E acceptance suite).

#### Removed
- `router-triage` skill (M3) — superseded by router-agent. See entry
  above. Helper `_lib/router_select.py` retained as Python-only scoring
  API.

#### Domain-layering principle (codified)
- Main session is domain-agnostic (Conductor): only spawns
  router-agent, relays prompts, drives ticks, relays HITL.
- Router-agent owns all domain decisions on the creation side
  (Specialist).
- Linter enforces this on `CLAUDE.md` going forward.

## [Unreleased]

## [0.7.0-m7.2] - 2026-04-18

### 🚀 v6.0 Milestones M3–M7 + E2E Acceptance

v6 ships as the production successor to the v5 PoC: a single-workspace,
plugin-based architecture with a 12-gate install pipeline, a generic
orchestrator-tick state machine, 4-layer config resolution, and three
first-party plugins. **588/588 bats tests green.**

#### Added — Core (`skills/codenook-core/`)
- **M3** `router-triage` skill: dual-mode question, intent regex routing,
  4 PHASE_ENTRY_QUESTIONS contracts.
- **M4** `orchestrator-tick` skill: full state machine with phase advance,
  unit fan-out, HITL gate suspend/resume, recovery branch, session resume,
  iteration cap. Companion `hitl-adapter` (terminal + queue) and
  `session-resume` skills.
- **M5** `config-resolve` skill: 4-layer cascade (defaults → workspace →
  plugin → task) with tier-symbol expansion against
  `model_catalog.resolved_tiers`, full provenance trace, decisions #43/#44/#45
  enforced (warn+fallback unknown tier, router=tier_strong invariant,
  10-key whitelist). Companion `config-mutator` and
  `task-config-set` skills.
- Shared `_lib/`: `atomic.py`, `semver.py`, `manifest_load.py`,
  `builtin_catalog.py`, `jsonschema_lite.py`, `expr_eval.py` (no Python
  eval/exec), `config_layers.py`, `provenance.py`, `router_select.py`.

#### Added — Plugins (`plugins/`)
- **M6** `plugins/development/` — 8-phase software-development pipeline
  (clarify → design → plan → implement → test → accept → validate → ship)
  ported from v5 PoC. 8 role profiles, 8 manifest templates, 3 HITL gates
  (design_signoff, pre_test_review, acceptance), shipped test-runner skill,
  validators, prompts, knowledge.
- **M7** `plugins/generic/` — universal fallback plugin (clarify →
  analyze → execute → deliver), routing priority 10.
- **M7** `plugins/writing/` — long-form writing plugin (outline → draft →
  review → revise → publish) with `pre_publish` HITL gate, routing
  priority 50.

#### E2E Acceptance (12/12 PASS)
Real-CLI smoke test in a clean workspace:
- core install + 3-plugin install via 12-gate pipeline
- idempotency (rc=3 on re-install w/o `--upgrade`)
- 3/3 input-to-plugin routing
- full 8-phase task lifecycle in 12 ticks with 3 HITL approvals
- 4-layer config resolution (task-tier wins, provenance present)
- plugin upgrade path

#### Documented gaps (tracked as issues)
- #1 — `init.sh --workspace` is an M1 stub
- #2 — test-plan config layer paths don't match shipped contract
- #3 — Plugin upgrade does not archive prior version
- #4 — `router-triage` doesn't yet consume packaging fields

## [5.0.0-poc.1] - 2026-04-18

### 🧪 v5.0 POC — Workspace-First Architecture (preview, opt-in)

The v5.0 POC ships under `skills/codenook-v5-poc/` and is **opt-in**: existing
v4.x stable installs are unaffected. v5.0 is a breaking redesign — there is no
migration path from v4.x workspaces.

#### Added
- **Workspace-first layout**: `.codenook/` at project root replaces
  `.claude/codenook/`. Two-layer state (workspace `state.json` + per-task
  `state.json`); `task-board.json` is a derived index.
- **Bootloader**: single `CLAUDE.md` at project root; both Claude Code and
  Copilot CLI honor it. No more `.github/copilot-instructions.md`.
- **Core orchestrator** (`codenook-core.md`, ~1.6K lines, 24 sections):
  state machine, routing table, prompt-as-file, sub-agent self-bootstrap,
  validator pattern, scheduler, HITL gating, dispatch audit, secret scan,
  session distillation, model assignment protocol.
- **Helper scripts** (8): `preflight.sh`, `keyring-helper.sh`,
  `secret-scan.sh`, `dispatch-audit.sh`, `session-runner.sh`,
  `model-config.sh`, `rebuild-task-board.sh`, `subtask-runner.sh` /
  `queue-runner.sh`.
- **Sub-agent profiles** (11): clarifier, designer, planner, implementer,
  reviewer, tester, acceptor, validator, synthesizer, security-auditor,
  session-distiller. All use self-bootstrap + Context Budget enforcement.
- **§24 Model Assignment Protocol**: 5-level resolution
  (task[role] > task.default > workspace[role] > workspace.default > inherit).
  Default `inherit` means dispatch without `--model` so the platform reuses the
  main session's model. Subtasks always inherit from parent and are never asked.
- **Tests**: 22 assertions in `tests/run-all.sh` (T0–T28), all passing.
- **Interactive HTML doc**: `skills/codenook-v5-poc/docs/v5-poc.html`
  (single-page, 3-tab: Design / Tests / Implementation).
- **POC README** + main README pointer + install.sh banner.

#### Notes
- Real LLM end-to-end (driving the orchestrator through clarify → accept) is
  not yet validated; this release covers scaffolding, helpers, and tests.
- Stable users should keep using the v4.9.x line.

## [4.9.0] - 2026-04-16

### 🚀 v4.9.0 — Model Defaults, Copilot Paths, Generic Skill Provisioning

#### Changed
- **Default models**: All agents now default to `claude-opus-4.6`, reviewer defaults to `gpt-5.4`
  (was: acceptor/tester = haiku-4.5, designer/implementer/reviewer = sonnet-4)
- **Dual-mode recommended pairing**: `claude-opus-4.6 + gpt-5.4` (was: sonnet-4 + gpt-5.1)
- **Q4 Skill Provisioning**: Removed all hardcoded skill names (baoyu-*, 5g-ran-*, etc.);
  now classifies skills by reading SKILL.md description + keyword matching. Exclude list
  also changed from hardcoded names to heuristic pattern matching.
- **Agent Profile Templates**: Added Copilot CLI paths alongside Claude Code paths
- **HITL Adapter Scripts**: Added Copilot CLI source path reference
- **SKILL.md header**: Updated to v4.9.0, mentions both Claude Code and Copilot CLI platforms
- **install.sh**: Updated description text; architecture diagram in README now includes
  dual-agent mode visual
- **README**: Updated agent model table, config examples, architecture diagram with
  dual-agent flow, added Phase Constitution feature bullet

## [4.8.1] - 2026-04-15

### 📜 v4.8.1 — Phase Constitution for Cross-Examination

Added per-phase quality criteria (Phase Constitution) to the dual-agent cross-examination
system. Inspired by Constitutional AI, each phase now has explicit evaluation dimensions
that focus the orchestrator's analysis and the agent's self-assessment.

#### Added
- **PHASE_CONSTITUTION data structure**: maps each phase to its quality focus and evaluation
  criteria (requirements: completeness/testability/ambiguity; design: scalability/coupling/security;
  impl: code quality/DFMEA; review: finding validity/severity calibration; etc.)
- **Phase Constitution documentation**: new section in Dual-Agent Parallel Mode docs with
  summary table of all phases and their criteria
- **Criteria-aware analysis**: `analyze_divergence()` now injects phase-specific criteria
  into the orchestrator prompt, ensuring evaluation is domain-appropriate
- **Criteria-aware challenges**: `build_challenge_prompt()` includes the quality standards
  so agents know what they're being evaluated against

#### Changed
- **analyze_divergence()**: now calls `resolve_phase_name()` to look up constitution;
  prompt restructured with "Evaluation Focus" header and per-criterion assessment
- **build_challenge_prompt()**: adds "Quality Standards for This Phase" section;
  instructions updated to reference the standards
- **Challenge prompt docs**: updated to show the new prompt structure with criteria

## [4.8.0] - 2026-04-15

### 🔄 v4.8.0 — Iterative Convergence Cross-Examination

Redesigned the dual-agent cross-examination flow from one-shot parallel critique
to an iterative convergence protocol with up to 3 rounds.

#### Changed
- **Cross-examination redesign**: orchestrator now challenges each agent sequentially,
  requiring them to defend, concede, or merge on each divergence point (max 3 rounds)
- **Convergence detection**: orchestrator analyzes divergence between A/B documents
  each round; exits early when positions converge
- **Document artifacts**: versioned per round (`-agent-a-r0.md`, `-agent-a-r1.md`, etc.)
  instead of single static files
- **Synthesis prompt simplified**: no longer passes critique docs (agents already revised)
- **Cost model updated**: 4–10× calls per dual phase (was fixed 5×)

#### Added
- `analyze_divergence()` — orchestrator self-analysis function for convergence detection
- `build_challenge_prompt()` — replaces `build_cross_examination_prompt()`

#### Removed
- `build_cross_examination_prompt()` — replaced by iterative challenge flow

#### Fixed (from v4.7.3 deep review)
- `task` vs `current_task` naming inconsistency (9 instances in orchestrate/dual functions)
- Preflight `dual_mode` dict now includes `synthesizer` and `phase_models` for schema completeness
- `get_user_decision` signature updated with `multi_select=False` parameter
- `get_user_input` helper function declared

## [4.7.3] - 2026-04-15

### 🛡️ v4.7.3 — Preflight Check for Missing Creation-Time Fields

Fixes a design defect where tasks created in a previous session could advance
without answering mandatory creation-time questions (e.g., dual-agent mode).

#### Added
- **Preflight Check** in orchestration loop: on first iteration (`total_iterations == 0`), verifies that `dual_mode` is set; prompts user if `null` and no global default exists
- Cross-reference note in Task Creation Flow pointing to the preflight safety net

#### Fixed
- Tasks resumed cross-session no longer silently skip the dual-agent mode question

## [4.7.2] - 2026-04-15

### 🔒 v4.7.2 — HITL Adapter Enforcement & Task Creation Flow

Synced production-proven improvements from xueba-knowledge deployment.

#### Added
- **HITL Hard Constraint**: Mandatory adapter resolution check before any HITL interaction — prevents calling wrong adapter (e.g., `terminal.sh` when config specifies `local-html`)
- **Enforcement Checklist**: Mental checklist agents must execute before each HITL gate
- **Adapter Resolution Logging**: Traceability log for resolved adapter name and phase
- **Task Creation Flow (MANDATORY)**: Structured 6-question flow for task creation, including dual-agent mode prompt

#### Changed
- Adapter resolution wording: "per-phase from Q2" → "per-phase override", "global from Q2" → "global config — MOST COMMON"
- Pseudocode adapter section: enhanced with step-by-step comments (4a/4b/4c) and violation warnings

## [4.7.1] - 2025-07-29

### ⚡ v4.7.1 — Engine Token Optimization

Compressed knowledge system pseudocode to reduce token footprint without
behavioral changes. Passed two rounds of deep review (clean on round 2).

#### Optimized
- Collapsed 10 helper function implementations into compact signature table (-179 lines)
- Compressed `extract_knowledge()` prompt while preserving full format template
- Restored inline dedup algorithm in `load_knowledge()` for correctness
- Added parsing logic detail to `parse_knowledge_items` helper entry

#### Fixed (from optimization deep review)
- **CRITICAL:** Removed undefined function references (`extraction_prompt_with`, `deduplicate_by_item_headers`)
- **HIGH:** Added regex parsing logic to `parse_knowledge_items` table entry
- **MEDIUM:** Restored full extraction prompt format template with quality rules
- **LOW:** Restored Confidence field in index entry format

#### Metrics
- Engine size: 21.2K → 20.2K tokens (4.4% reduction)
- Lines: 1,785 → 1,645 (-140 lines)

## [4.7.0] - 2025-07-28

### 🧠 v4.7.0 — Knowledge Accumulation System

Agents now automatically extract and persist cross-task knowledge, becoming smarter
over time. New tasks benefit from accumulated experience — code conventions, pitfalls,
architecture decisions, and best practices are captured after each phase.

#### ✨ New Features
- **Automatic Knowledge Extraction**: After each HITL-approved phase, the orchestrator
  scans the phase document for reusable lessons and saves them to the knowledge base
- **Dual-Dimension Knowledge Base**: Knowledge indexed by role (`by-role/`) AND by
  topic (`by-topic/`) — 5 role files + 5 topic files + master index
- **Knowledge Loading**: Relevant knowledge automatically injected into agent prompts
  via `load_knowledge()` — agents see lessons from their own past tasks + relevant topics
- **Deduplication**: Knowledge items tracked by `[T-NNN]` headers to prevent duplicates
- **Confidence Threshold**: Configurable minimum confidence level for extracted items
  (HIGH/MEDIUM/LOW)
- **Capacity Management**: Per-role and per-topic max item limits with oldest-first rotation

#### 📁 New Directory Structure
```
codenook/knowledge/
├── by-role/          (implementer.md, reviewer.md, designer.md, tester.md, acceptor.md)
├── by-topic/         (code-conventions.md, architecture-decisions.md, pitfalls.md,
│                      best-practices.md, project-config.md)
└── index.md
```

#### 🔧 Config
```json
{ "knowledge": { "enabled": true, "auto_extract": true,
  "max_items_per_role": 100, "max_items_per_topic": 50,
  "max_chars": 8000, "confidence_threshold": "MEDIUM" } }
```

#### 📝 Agent Template Updates
- All 5 agent templates updated with Knowledge Base constraint — agents instructed
  to reference accumulated knowledge for conventions, pitfalls, and best practices

## [4.6.5] - 2025-07-28

### 🔧 v4.6.5 — Deep Review Round 5 (29 fixes) + Dual-Agent Mode

Comprehensive deep review sweep (29 issues: 3 CRITICAL, 7 HIGH, 11 MEDIUM, 8 LOW)
plus two new orchestration features.

#### ✨ New Features
- **Dual-Agent Parallel Mode**: Two agents (different models) execute same phase in parallel,
  cross-examine each other's work, and a third agent synthesizes the final document.
  Configurable per-task or globally via `dual_mode` config.
- **Per-Phase Model Configuration**: `phase_models` field allows different model pairs
  for each workflow phase (e.g., Opus+GPT for design, Sonnet+Codex for implementation).

#### 🐛 Bug Fixes

**Engine (17 fixes):**
- **[C1]** Circuit breaker "Continue" now resets retry_counts (prevents infinite loop)
- **[C1+H1]** Circuit breaker `break` saves task-board.json before breaking
- **[C2]** Rename `task` variable to `current_task` in orchestrate() (variable collision)
- **[H2]** Add `paused` status handler at top of while loop (resume or exit)
- **[H3]** Fix synthesis fallback comment (was misleading about heuristic)
- **[M1]** Remove duplicate PHASE_KEYS, reuse PHASE_NAME_MAP via resolve_phase_name()
- **[M2]** Add `abandoned` and lightweight dynamic statuses to exhaustive list
- **[M3]** Define prev_phase lookup using AGENT_PHASES backward walk
- **[M4]** Add `record_feedback` and `stop` to adapter interface table
- **[M5]** Add config.json complete schema example
- **[M6]** Add "develop+review" shortcut to commands table
- **[M7]** Add early check for `hitl.enabled = false` → auto-approve
- **[L2]** Add null validation for resolved agent_a/agent_b models
- **[L3]** Add retry-aware phase decisions re-ask prompt
- **[L4]** Add unknown decision value error handling
- Fix stale `<task.status>` reference → `<current_task.status>`
- Close else block for HITL enabled/disabled check

**Templates (12 fixes):**
- **[H4]** Acceptor: add `task_id` to all 3 phase input contracts
- **[H5]** Reviewer: add `task_id` to input contract
- **[H6]** Designer: add lightweight mode awareness note
- **[H7]** README: add Create to tester tools list
- **[M1]** install.sh: update version comment to v4.6.5
- **[M2]** SKILL.md: update title version to v4.6.5
- **[M3]** Acceptor: add lightweight mode note
- **[M4]** Seed version strings: update from 4.6 to 4.6.5
- **[L1]** CHANGELOG: fix v3.x dates (2026 → 2025 typos)
- **[L2]** Acceptor: output contract formatting consistency
- **[L3]** README: fix tester description to include "create"
- **[C3]** CHANGELOG: add missing entries for v4.4.0–v4.6.5

## [4.6.0] - 2025-07-28

### ⚡ v4.6 — Multi-Task Management, Phase Entry Decisions, Deep Review Round 2

Major orchestration improvements: multi-task management with parallel task support,
mandatory phase entry decisions, and conversation-triggered commands.

#### ✨ New Features
- **Multi-Task Management**: switch, pause, resume active tasks; `depends_on` for task dependencies
- **Any-Phase Entry**: `--start-at` flag to create tasks at any phase in the workflow
- **Phase Entry Decisions**: mandatory questions before each phase with config persistence
- **Conversation Triggers**: natural-language commands for task/framework operations

#### 🐛 Bug Fixes
- Deep review round 2: 10 critical/medium findings fixed
- Auto-persist phase entry decisions to config
- Fix pseudocode consistency (round 3 nits)

## [4.5.0] - 2025-07-28

### 🔧 v4.5 — Per-Phase Model & HITL Adapter Configuration

#### ✨ New Features
- Per-phase model configuration for fine-grained control
- Per-phase HITL adapter overrides

## [4.4.0] - 2025-07-28

### 🔧 v4.4 — Skill Provisioning

#### ✨ New Features
- **Project-Level Skill Auto-Loading**: project-level skills in `codenook/skills/` automatically loaded to sub-agents
- **Smart Skill Provisioning (Q4)**: skills provisioned based on agent role and task context

## [4.3.1] - 2025-07-28

### 🔧 v4.3.1 — Deep Review Rounds 3 & 4

Two additional rounds of deep code review, fixing 14 more issues (40 total across all 4 rounds).

#### 🐛 Bug Fixes

**Round 3 — Engine (6 fixes):**
- Bump version reference from v4.2 to v4.3 in engine title
- Add `mode`, `pipeline`, `retry_counts`, `total_iterations` to task-board schema example
- Record skip decision in `feedback_history` when agent fails (HITL audit trail)
- Quick Trigger now matches lightweight status names (agent_name prefix)
- Fix `build_lightweight_routing` acceptor filtering for duplicate pipeline entries
- Remove duplicate Circuit Breaker comment (edit leftover)

**Round 3 — Templates (3 fixes):**
- Designer and tester: upgrade to 4-backtick code fences for nested mermaid blocks
- Implementer: add lightweight mode guidance note (matches reviewer/tester)
- Implementer and tester: add `task_id` to input contract (matches designer)

**Round 4 — Engine (5 fixes):**
- Handle "Retry with different model" option in agent failure block (was falling through)
- Bump task-board schema version from 4.2 to 4.3 (new fields)
- Define `get_user_decision` helper and use consistently (replaces mixed `ask_user` usage)
- Add `"abandoned"` to while loop exit conditions for robustness
- Add routing lookup fallback with error message for unknown status

#### 📊 Deep Review Statistics (4 rounds total)
| Round | Issues | CRITICAL | HIGH | MEDIUM | LOW |
|-------|--------|----------|------|--------|-----|
| R1 | 19 | 2 | 6 | 5 | 6 |
| R2 | 7 | 1 | 1 | 2 | 3 |
| R3 | 9 | 0 | 1 | 7 | 1 |
| R4 | 5 | 0 | 1 | 1 | 3 |
| **Total** | **40** | **3** | **9** | **15** | **13** |

## [4.3.0] - 2025-07-28

### ⚡ v4.3 — Quick Trigger, Lightweight Mode & Deep Review Sweep

Three new orchestration features plus comprehensive quality fixes from two rounds of deep code review (26 issues total).

#### ✨ New Features
- **Quick Trigger Dispatch**: Keyword-based agent activation (ZH/EN) — say "测试" or "test" to invoke tester directly, with automatic task context detection
- **Mandatory Ask-User Rule**: Orchestrator MUST call `ask_user` at the end of every response with context-aware choices
- **Lightweight Task Mode**: Custom agent pipelines for focused workflows — predefined shortcuts (quick fix, develop, test only, review only) plus custom `--pipeline a,b,c` syntax
  - Dynamic routing via `build_lightweight_routing(pipeline)` — chains only specified agents
  - 6 predefined pipeline shortcuts with ZH/EN aliases
  - HITL gates enforced in both full and lightweight modes

#### 🐛 Bug Fixes (26 issues from 2 rounds of deep review)

**Round 1 — Engine (11 fixes):**
- Complete AGENT_PHASES table with all 5 agents and all phases
- Fix reject routing: plan phases → retry same status, execute phases → back to plan
- Adapt circuit breaker for lightweight mode with human-readable labels
- Merge redundant HITL enforcement sections
- Make verdict routing mode-aware (full vs lightweight)
- Add verdict → routing mapping table for clarity
- Update Agent Roles table with phase and document columns

**Round 1 — Agent Templates (8 fixes):**
- Tester/reviewer: upstream docs changed from required → 📎 recommended
- Implementer: fix all `.agents/docs/` paths → `codenook/docs/<task_id>/`
- Implementer: add verdict quality gate (COMPLETE only when all tests pass)
- All agents: explicit document save paths

**Round 2 — Engine (4 fixes):**
- Replace undefined `find_plan_status_for()` with inline logic + `find_status_for_agent()`
- Add global iteration counter (max 30) to circuit breaker
- Add lightweight mode note to document chain section
- Cross-reference Task Modes from Task Management Commands

**Round 2 — Agent Templates (3 fixes):**
- Standardize "📎 recommended" capitalization across reviewer template
- Clarify status name construction in lightweight routing comments
- Mark designer `task_id` as required in context table

#### 🔄 Changed
- Engine instructions: net change -20 lines after all features and fixes (683 lines)
- Task Management Commands: shortcut descriptions now reference Task Modes section
- Circuit breaker: dual trigger (per-status >3 OR global >30 iterations)

## [4.2.0] - 2025-07-27

### 🛡️ v4.2 — HITL Enforcement & Adapter Fixes

Systematic fix for HITL gate enforcement bugs and adapter architecture issues.

#### 🐛 Bug Fixes
- **Terminal adapter self-contained**: Added `record_feedback` command — terminal adapter no longer depends on `ask_user` or any LLM-specific tool
- **HITL status mismatch**: Fixed `hitl-verify.sh` status names to match actual routing table (`impl_planned`, `impl_done`, etc. instead of wrong `designing_done`, `implementing_done`)
- **Agent frontmatter**: Removed invalid `disallowedTools` field from all 5 agent `.agent.md` files (not a valid Copilot CLI YAML field)

#### ✨ New Features
- **Mandatory Bootstrap Rule**: Orchestrator MUST read `task-board.json` before ANY agent action
- **Agent Phase Summary table**: Quick-reference routing table in instructions
- **HITL Concrete Steps**: Exact bash command sequences for local-html and terminal adapters (replaces abstract pseudo-code)
- **"DO NOT substitute ask_user" guard**: Explicit prohibition against shortcutting local-html adapter

#### 🔄 Changed
- **All adapters now follow symmetric bash-based interface**: publish → poll → get_feedback (+ record_feedback for terminal)
- **`ask_user` downgraded to optional**: Referenced only as convenience for terminal adapter step 2, never as a requirement
- **Orchestration loop pseudo-code**: `ask_user()` calls replaced with `get_user_decision()` (environment-agnostic)

## [4.1.0] - 2025-07-26

### 📄 v4.1 — Document-Driven Workflow

Every agent now produces a planning document before execution. 10 HITL gates per task cycle (up from 5).

#### ✨ New Features
- **Document-driven workflow**: Plan → Approve → Execute → Report → Approve
- **10 HITL gates per task**: Every agent phase has a mandatory human approval gate
- **10 document artifacts per task**: requirement-doc, design-doc, implementation-doc, dfmea-doc, review-prep, review-report, test-plan, test-report, acceptance-plan, acceptance-report
- **Document storage**: All artifacts saved to `codenook/docs/T-NNN/` for traceability
- **Verdict-based routing**: Review/test/acceptance verdicts drive status transitions
- **Mandatory Mermaid diagrams**: All agent documents must include visual diagrams
- **HITL light theme**: Clean, minimal white UI replacing the dark theme
- **Init directory confirmation**: User confirms installation directory during setup

#### 🔄 Changed
- **Acceptor**: Now operates in 3 sub-phases (requirements, accept-plan, accept-exec)
- **Implementer**: Split into plan phase (implementation document) and execute phase (code + DFMEA)
- **Reviewer**: Split into plan phase (review prep with standards collection) and execute phase (review report)
- **Tester**: Split into plan phase (test plan document) and execute phase (test report)
- **Routing table**: 10 entries with unified agent → HITL pattern (was 10 entries with alternating agent/HITL)
- **Task board schema**: v4.1 with 10 artifact slots per task
- **Orchestration engine**: Updated loop with document storage, verdict routing, dual-phase invocation
- **SKILL.md**: v4.1 schema, docs/ directory, upgrade preserves docs/
- **highlight.js**: Switched from github-dark to github (light) theme
- **Mermaid**: Switched from dark to default theme

#### 📊 Phase Matrix
| Agent | Plan Phase | HITL | Execute Phase | HITL |
|-------|-----------|------|---------------|------|
| Acceptor (req) | Requirement Doc | ✅ | — | — |
| Designer | Design Doc | ✅ | — | — |
| Implementer | Implementation Doc | ✅ | Code + DFMEA | ✅ |
| Reviewer | Review Prep | ✅ | Review Report | ✅ |
| Tester | Test Plan | ✅ | Test Report | ✅ |
| Acceptor (accept) | Acceptance Plan | ✅ | Acceptance Report | ✅ |

#### 🔍 Deep Code Review (v4.0.1)
- Fixed 22 issues from 5-agent parallel code review
- XSS vulnerability patched (html.escape on all user content)
- Decision values aligned ("approve"/"feedback")
- Atomic writes with tempfile.mkstemp()
- install.sh integrity validation

## [4.0.0] - 2025-04-12

### 🚀 v4.0 — Subagent Architecture Redesign

Complete architectural overhaul: from 20 global skills + 13 hooks to 2 skills + subagent delegation.

#### ✨ New Architecture
- **2 skills** replace 20: `agent-init` (initialization + 5 templates) and `agent-orchestrator` (routing + HITL + memory)
- **Subagent delegation**: All agents run in separate context windows, spawned by the orchestrator
- **Project-level agents**: `agent-init` generates `.github/agents/` (Copilot) or `.claude/agents/` (Claude Code)
- **task-board.json**: Simple status-based routing replaces 11-state FSM
- **Multi-adapter HITL**: Auto-detects environment → local-html / terminal / confluence / github-issue
- **Hard constraints via frontmatter**: `tools`/`disallowedTools` in agent profiles replace hook enforcement
- **Memory management**: Orchestrator saves/loads markdown snapshots between phases

#### 🗑️ Removed (v3.x → v4.0)
- 18 global skills (agent-fsm, agent-switch, agent-messaging, agent-hooks, etc.)
- 13 shell hook scripts + hooks.json
- Session-level role switching (`/agent <name>` in main session)
- File-based messaging (inbox.json)
- `.agents/` runtime directory (events.db, state.json, workspace/)
- Global agent profiles (`~/.copilot/agents/`, `~/.claude/agents/`)
- Complex FSM state machine with guards

#### 📦 New File Structure
```
skills-v4/
├── agent-init/
│   ├── SKILL.md              — Initialization logic
│   └── templates/            — 5 agent profile templates
│       ├── acceptor.agent.md
│       ├── designer.agent.md
│       ├── implementer.agent.md
│       ├── reviewer.agent.md
│       └── tester.agent.md
└── agent-orchestrator/
    ├── SKILL.md              — Orchestration engine
    └── hitl-adapters/        — 4 HITL adapters
```

#### 📊 Size Comparison
| Metric | v3.x | v4.0 |
|--------|------|------|
| Skills | 20 | 2 |
| Hooks | 13 | 0 |
| Total lines | ~7,000 | ~1,200 |
| Install files | 40+ | 12 |
| Context per invocation | ~1,300 lines | ~200-350 lines |

#### 🔧 Updated
- `install.sh` rewritten for v4.0 (--install, --check, --uninstall, --clean-v3)
- HITL server `hitl-server.py` fixed: Python 3.13 regex compatibility + code block rendering

## [3.5.0] - 2025-07-24

### 🌐 Full English Internationalization (i18n)

- **Entire codebase translated from Chinese to English** — ~70 files, ~7000 lines
- All 20 skill docs (`skills/agent-*/SKILL.md`) — translated + optimized
- All 5 agent profiles (`agents/*.agent.md`) — fully translated
- All 11 documentation files (`docs/*.md`) — translated
- Global instructions (`copilot-instructions.md`, `CLAUDE.md`, `agent-rules.md`) — translated
- Task board descriptions (`.agents/task-board.json`) — 19 fields translated
- Project-level skills, DFMEA template, blog post, HITL server comments — translated
- 8 design docs and 10 review reports in runtime workspace — translated
- `agent-switch` preserves bilingual trigger keywords for Chinese-speaking users
- Zero Chinese characters remain in any active framework file

### 🔧 Maintenance

- Deduplicated `install.sh` guard logic + minimized global instructions (3712→46 lines)
- Fixed `install.sh` guard string to match both Chinese and English headers

## [3.4.1] - 2025-04-11

### 🔒 HITL Hook Enforcement

- **Hook hard constraint**: `agent-pre-tool-use.sh` now blocks FSM transitions in `task-board.json` when `hitl.enabled: true` and no approved feedback file exists
- **6 transitions enforced**: created→designing, designing→implementing, implementing→reviewing, reviewing→testing, testing→accepting, accepting→accepted
- **All 5 agent skills** updated with `🔒 Hook hard constraint` notice
- Backward transitions and property-only changes remain unrestricted
- HITL disabled (`hitl.enabled: false`) skips all gate checks

### 🧪 E2E Test Results
- 30/30 tests passed across 6 test groups
- Agent switching, role boundaries, HITL pipeline, mid-flow modifications, HITL disabled, memory isolation

## [3.4.0] - 2025-04-13

### 🚀 Agent Experience Enhancement

#### Unified FSM (T-039)
- Merged 18-state 3-Phase Engineering Closed Loop into **11-state unified FSM**
- Legacy 3-Phase states auto-migrate via 15-state mapping table
- Removed `workflow_mode` selection from `agent-init`

#### Human-in-the-Loop Review Gate (T-041, T-042)
- New `agent-hitl-gate` skill (20th skill)
- **All 5 agents** have HITL checkpoints before FSM transitions
- 4 platform adapters:
  - `local-html`: Interactive HTTP server with dark-themed Web UI + multi-round feedback
  - `terminal`: Pure CLI for Docker/SSH/headless environments
  - `github-issue`: GitHub Issue-based review via `gh` CLI
  - `confluence`: Confluence REST API integration with comment polling
- Docker auto-detection: binds `0.0.0.0`, skips browser open
- Atomic file writes (`os.rename`) for race condition prevention

#### DFMEA Integration (T-040)
- DFMEA template with **S×O×D→RPN** risk scoring
- Mandatory DFMEA analysis before coding (implementer Phase 1)
- FSM guard validates RPN ≥ 100 items have mitigation measures

#### Developer Experience
- **T-038**: Ask-next-step rule injection per agent role in `agent-init`
- **T-043**: Worktree prompt for feature isolation in acceptor workflow
- **T-044**: Role mismatch detection + switch prompt in all 5 agents

### 🔒 Security Hardening (3 rounds, 22 issues fixed)
- Command injection: Python `sys.argv` instead of `open('$file')` string embedding
- XSS defense: Pandoc `-raw_html` extension strips raw HTML blocks
- Path traversal: `^T-[0-9]+$` task ID validation
- Env var whitelist: only `CONFLUENCE_TOKEN/API_KEY/PAT/ATLASSIAN_TOKEN`
- Atomic file writes in `hitl-server.py` (tmp + `os.rename`)
- Port exhaustion: exit with error instead of silent fallback
- PID verification: `kill -0` check after server startup
- Dependency checks (`python3`, `gh`, `curl`) in all 4 adapters

### 🐛 Bug Fixes
- Hook false positive on role switch: now checks redirect targets individually, skips `active-agent`
- FSM auto-transition on switch: when target role has no matching tasks, offer batch transition
- 3-Phase deprecation notices in `agent-hooks` and `agent-orchestrator`

### 📊 Stats
- 16 commits since v3.3.6 | 31 files changed | ~2,600 lines added
- 7 tasks (T-038~T-044), 28 goals — all accepted
- 36/36 tests passing | 20 skills (was 19)

## [3.3.6] - 2025-04-11

### 🔒 Security Hardening — Hook Enforcement

**Virtual Event Enforcement via preToolUse:**
- **agentSwitch**: validates role names on write to `active-agent`; blocks empty/invalid writes and file deletion (`rm`, `mv`)
- **memoryWrite**: namespace isolation — agents can only write their own memory files; task memory (`T-NNN-*`) is shared
- **taskBoard**: JSON syntax validation for full `task-board.json` writes

**Security Vulnerabilities Fixed:**
- **False positive prevention**: strip quoted strings (`'...'`, `"..."`) before pattern matching — prevents `--notes "npm publish"` from triggering block
- **Active-agent bypass**: block `rm`/`mv` on `active-agent` file; default to `acceptor` (most restrictive) when file missing but framework initialized
- **Chained command bypass**: per-segment analysis (`has_dangerous_segment`) splits on `&&`, `||`, `;` to prevent danger hidden behind whitelist matches
- **Multi-line quote stripping**: collapse newlines with `tr '\n' ' '` before `sed` to handle multi-line commit messages
- **Cross-directory attacks**: Strategy 4 extracts absolute paths from bash commands to detect operations targeting projects from outside directories

**Hook Configuration Cleanup:**
- Removed 6 unsupported custom events from `hooks-copilot.json` (Copilot CLI only supports 6 built-in events)
- Retained: `sessionStart`, `preToolUse`, `postToolUse`

### Added
- `tests/test-false-positive.sh` — 15 false-positive test cases
- `tests/test-virtual-events.sh` — 31 virtual event + security test cases
- 4-strategy project root detection (cwd walk, file path walk, cd target, absolute path extraction)

### Verified
- 51/51 total tests: framework 5/5 ✅, false-positive 15/15 ✅, virtual events 31/31 ✅
- Live-tested cross-directory, chained command, and active-agent bypass scenarios

## [3.3.5] - 2025-04-11

### Added
- **Comprehensive hard constraints for all 5 agent roles** via `preToolUse` hook enforcement
  - **Tester**: blocked from `git commit/push`, `rm/mv/cp` on non-test files, redirects outside test directories; allowed: `.agents/`, `tests/`, `*.test.*`, `*.spec.*`
  - **Implementer**: blocked from `npm publish`, `docker push`; blocked redirects to other agents' workspaces
  - **Acceptor/Designer**: read-only except `.agents/`; blocked destructive commands and redirects
  - **Reviewer**: read-only except `.agents/reviewer/`, `docs/`, `task-board`; blocked destructive commands

### Fixed
- **Bash redirect bypass vulnerability**: detected `>`, `>>`, `tee`, `sed -i`, `patch`, `dd` patterns in bash commands to prevent write operations that bypassed edit/create restrictions
- Redirect whitelist for `.agents/` writes per-role and test directories for tester role

### Verified
- 44/44 hook enforcement test scenarios passed across all 5 roles
- 8/8 live enforcement tests passed in real Copilot CLI session (tester role)

## [3.3.4] - 2025-04-11

### Fixed
- **agent-pre-tool-use.sh**: Fixed project root detection that failed when Copilot CLI session started from a non-project directory (e.g., `~`). Now walks up directory tree from both `cwd` and file path to find `.agents/` directory.

### Verified
- **Copilot CLI hooks confirmed working** (v1.0.24): `preToolUse` hook with `permissionDecision: "deny"` successfully blocks tool execution
- Both `~/.copilot/hooks/hooks.json` and `config.json` inline hooks are executed
- All 6 hook events documented by GitHub are supported: `sessionStart`, `sessionEnd`, `userPromptSubmitted`, `preToolUse`, `postToolUse`, `errorOccurred`

## [3.2.0] - 2025-04-10

### 🚀 Skills Mechanism Optimization (T-SKILL-OPT)

**R2: Per-Agent Skill Isolation:**
- All 5 `.agent.md` profiles now declare `skills:` allowlist in frontmatter
- Each agent has explicit "Skill permissions" section with positive and negative constraints
- Shared skills (7): orchestrator, fsm, task-board, messaging, memory, switch, docs
- Role-specific skills (11): config, init, acceptor, designer, implementer, reviewer, tester, events, hooks, hypothesis, teams

**R1: Token Distribution Documentation Fix:**
- `docs/llm-message-structure.md`: Corrected token pie chart from "18 Skills full text 40%" to "Skills summary list 1%"
- Added explanation of two-level loading mechanism (summary ~1% + on-demand full text)
- Updated ASCII packet structure to reflect summary-only skill injection
- Corrected "Key Insights" section to describe two-level loading

**R4: Dual Installation Methods in README:**
- "Method 1: One-click Install" — `curl | bash` (script-driven)
- "Method 2: Prompt-based Install" — Tell AI assistant to install from repo (AI-guided)
- Added detailed manual install steps table (target directories per platform)
- Updated skill count from 15 to 18

## [3.1.5] - 2025-04-10

### 📝 Audit Round 10 — Convergence (2 doc fixes)

**Executable code: ZERO issues** — codebase converged ✅

**MEDIUM:**
- `agent-hooks/SKILL.md`: Fix Step→Agent table: `ci_monitoring` and `device_baseline` mapped to `tester` (was `implementer`)

**LOW:**
- `agent-hooks/SKILL.md`: Add 5 missing transitions to 3-Phase pseudocode (`design_review→test_scripting`, 4 hypothesis transitions)

## [3.1.4] - 2025-04-10

### 🔒 Security Audit Round 9 (16 issues fixed)

**HIGH:**
- `test-3phase-fsm.sh`: Fix `grep -q "LEGAL"` matching "ILLEGAL" — FSM test suite was non-functional
- `test-3phase-fsm.sh`: Add missing `design_review→test_scripting` in test FSM case statement
- `team-session.sh`: Escape agent names in tmux commands to prevent shell injection

**MEDIUM:**
- `install.sh`: Recreate TMP_DIR after cleanup — tarball install was falling through to git clone
- `agent-session-start.sh`: Use `PRAGMA busy_timeout=3000` instead of `.tables` for DB health check
- `auto-dispatch.sh`: Clear stale lock directories (>60s) to prevent permanent dispatch lockout
- `test-integration.sh`: Capture exit code before `set -e` masks staleness-check failures
- `install.sh`: Only backup hooks.json if `.bak` doesn't already exist (prevents overwriting user's original)
- `cron-scheduler.sh`: Document that `schedule` field is display-only, caller's crontab controls timing
- `agent-messaging/SKILL.md`: Clarify two `type` enum systems (auto-dispatch vs bidirectional)

**LOW:**
- `test-3phase-fsm.sh`: Fix label "26" → "27" legal transitions
- `test-integration.sh`: Remove dead `cp` immediately overwritten by `cat`
- `team-session.sh`: Validate `--agents/--task/--layout` have values (prevent `set -u` crash)
- `team-session.sh`: Portable `watch` fallback with `while sleep` loop for macOS
- `cron-scheduler.sh`: Fix file handle leak in Python `json.load(open(...))` → `with open()`
- `install.sh`: Add `trap 'rm -rf "$TMP_DIR"' EXIT` for cleanup on interrupt

## [3.1.3] - 2025-04-09

### 🚀 Strict Document Gate Mode

- `hooks/lib/fsm-validate.sh`: Document gate now supports `"strict"` mode — blocks transitions (`LEGAL=false`) when required docs are missing
- Configuration via `task-board.json` top-level field `"doc_gate_mode": "strict"` (default: `"warn"`)
- `skills/agent-docs/SKILL.md`: Updated with strict/warn mode documentation
- `skills/agent-fsm/SKILL.md`: Added document gate as guard #5 in FSM validation rules
- `tests/test-integration.sh`: 2 new tests (strict blocks, warn allows) — 25 total

## [3.1.2] - 2025-04-09

### 🔒 Security Audit Round 7 (10 issues fixed)

**HIGH:**
- `agent-before-memory-write.sh`: Block path traversal (`..`) in memory file paths

**MEDIUM:**
- `agent-before-compaction.sh`: Validate agent name against `[a-z_-]+` allowlist
- `agent-fsm/SKILL.md`: Document `design_review→test_scripting` transition (was in code but not docs)
- `test-integration.sh`: Fix hypothesis test field name `.path` (was `.file_path`, test was vacuous)
- `cron-scheduler.sh`: Use `project_dir` for task-board path in generate-report
- `team-session.sh`: Escape `PROJECT_DIR` in dashboard pane tmux command

**LOW:**
- `test-3phase-fsm.sh`: Add `design_review:test_scripting` to legal transitions test array
- `agent-pre-tool-use.sh`: Add tester bash restrictions (block git push, npm publish, docker run)
- `install.sh`: Narrow chmod +x to `agent-*.sh` + `security-scan.sh` only

## [3.1.1] - 2025-04-09

### 🔒 Security Audit Round 6 (16 issues fixed)

**HIGH:**
- `install.sh`: Fixed symlink attack — tarball now extracts directly to mktemp dir with `--strip-components=1`
- `webhook-handler.sh`: Added `|| true` to sqlite3 call; log previous agent on switch
- `verify-init.sh`: Replaced all python3 code injection vectors with jq; fixed shebang + `set -euo pipefail`
- `agent-pre-tool-use.sh`: Reviewer now allowed to write `.agents/docs/` (fixes doc gate/boundary conflict)

**MEDIUM:**
- `cron-scheduler.sh`: Pass shell vars via `os.environ` instead of interpolating into Python strings
- `fsm-validate.sh`: Convergence gate uses `$NEW_STATUS` (not `$NEW_STATUS_SQL`); escape PT_* in JSON
- `auto-dispatch.sh`: Moved duplicate check inside lock to prevent TOCTOU race condition
- `team-session.sh`: Escape single quotes in TASK_FILTER and PROJECT_DIR for tmux
- `test-integration.sh`: Fixed hypothesis test using wrong field names (was snake_case, now camelCase)
- `install.sh`: Removed `git config --global http.postBuffer` side effect

**LOW:**
- `agent-pre-tool-use.sh`: Quote `$CWD` in parameter expansion to prevent glob interpretation
- `team-dashboard.sh`: Fixed progress bar off-by-one at 0%
- `webhook-handler.sh`: Log previous agent name on webhook-triggered switch
- `test-3phase-fsm.sh`: Removed redundant rm -rf (EXIT trap handles cleanup)
- `fsm-validate.sh`: SQL-escape PT_* values in convergence gate JSON

## [3.1.0] - 2025-04-09

### 🚀 Agent Teams — Bidirectional Messaging, Parallel Execution, Competitive Hypothesis

**New Features:**
- **Bidirectional Messaging**: Added `thread_id`, `reply_to` fields to message schema; `broadcast` message type for team-wide announcements
- **tmux Team Session**: `scripts/team-session.sh` launches multi-agent split-pane session with auto-refresh dashboard
- **Team Dashboard**: `scripts/team-dashboard.sh` shows real-time agent status, inbox counts, pipeline progress bar, recent events
- **Competitive Hypothesis**: New `agent-hypothesis` skill (18th skill) — Fork/Evaluate/Promote pattern for parallel approach exploration
- **`hypothesizing` FSM state**: New state in both Simple and 3-Phase workflows; `designing→hypothesizing` and `implementing→hypothesizing` transitions
- **Inbox on Switch**: After-switch hook now shows unread message count with urgent priority highlighting

**Enhancements:**
- `agent-messaging/SKILL.md`: Added thread support, broadcast type, updated routing rules
- `agent-teams/SKILL.md`: Added tmux session architecture, competitive hypothesis pattern, workspace storage
- `agent-fsm/SKILL.md`: Added `hypothesizing` to universal transitions
- `auto-dispatch.sh`: `hypothesizing` status skips auto-dispatch (coordinator manages)
- README: Added "Agent Teams" section with architecture diagram, 3 features, usage scenarios
- Integration tests expanded 21→23 (hypothesis transition + team dashboard)

## [3.0.23] - 2025-04-09

### 🔒 Security Audit Round 5 (16 issues fixed)

**HIGH:**
- `agent-post-tool-use.sh`: Fixed ACTIVE_AGENT double-escaping — raw value now stored, escaped only at SQL use sites (H1)
- `agent-post-tool-use.sh`: All sqlite3 calls now have `2>/dev/null || true` to prevent hook crash on DB errors (H2)
- `auto-dispatch.sh`: `created` status now routes to acceptor in 3-phase mode (was always designer) (H3)

**MEDIUM:**
- `fsm-validate.sh`: Added `design_review→test_scripting` transition (M1)
- `agent-fsm/SKILL.md`: Fixed ci_monitoring/device_baseline agent assignment (implementer→tester) (M2)
- `fsm-validate.sh`: Document gate now covers 3-phase states + acceptance-criteria.md (M3)
- `agent-post-tool-use.sh`: Reordered modules — FSM validation runs BEFORE auto-dispatch (M4)
- `memory-capture.sh`: Skips FSM-violated tasks to avoid capturing illegal transitions (M5)
- `fsm-validate.sh`: Goal guard uses `$NEW_STATUS` instead of `$NEW_STATUS_SQL` for comparison (M6)
- `install.sh`: Uses `mktemp -d` instead of predictable `/tmp/multi-agent-framework` path (M7)
- `agent-pre-tool-use.sh`: grep pattern uses `(\s|$)` to catch commands at end of line (M8)

**LOW:**
- `test-3phase-fsm.sh`: Added trap for temp dir cleanup (L1)
- `install.sh`: Split `local` declarations from assignments to avoid masking exit codes (L2)
- `verify-install.sh`: Replaced python3 path-injection-prone JSON check with jq (L4)
- `cron-scheduler.sh`: Resolved subprocess paths relative to script directory (L5)

## [3.0.22] - 2025-04-09

### 🔒 Security Audit Round 4 (22 issues fixed)

**CRITICAL:**
- `install.sh`: Now copies `hooks/lib/` directory (auto-dispatch, fsm-validate, memory-capture modules were missing after install!)

**HIGH — SQL/Code Injection:**
- `session-start.sh`: TIMESTAMP numeric validation (missed in Round 1)
- `memory-search.sh`: escape QUERY, ROLE, LAYER params; validate LIMIT is numeric
- `security-scan.sh`: sanitize newlines in JSON output (was producing invalid JSON)

**MEDIUM — Correctness & Safety:**
- `memory-capture.sh`: use jq for memory file JSON (fixes title with double quotes)
- `post-tool-use.sh`: escape double quotes/backslashes in TOOL_ARGS detail JSON; fix TOCTOU race (snapshot from cache, not disk)
- `install.sh`: fix operator precedence in integrity check; consistent skill count (17)
- `fsm-validate.sh`: compare raw status (not sql-escaped) for blocked_from
- `staleness-check.sh`: fix Perl code injection via environment variable
- `auto-dispatch.sh`: use @tsv (tab) instead of pipe delimiter; fail-safe lock skip
- `verify-install.sh`: add agent-docs to skill check list; threshold 16→17
- `agent-after-switch.sh`: jq for JSON output; null-safety for assigned_to
- `agent-before-task-create.sh`: jq for JSON output

**LOW — Hardening:**
- `config.sh`: use escaped values in sed append; escape regex in tool removal
- Test schema aligned with production (created_at column)
- Test #14 validates exit code + output (no false pass on crash)
- Remove redundant staleness-check from PostToolUse hooks.json
- `memory-index.sh`: track + report actual indexed count
- `webhook-handler.sh`: validate CWD before writing files

## [3.0.21] - 2025-04-09

### 🔒 Security Audit Round 3 (12 issues fixed)

**HIGH — SQL Injection:**
- `webhook-handler.sh`: escape PAYLOAD before SQL insertion
- `memory-index.sh`: escape file paths and checksum in all SQL queries

**MEDIUM — Security & Correctness:**
- `auto-dispatch.sh`: escape ACTIVE_AGENT in SQL JSON detail
- `memory-capture.sh` + `fsm-validate.sh`: fix `||`/`&&` operator precedence bug (guard clause now uses explicit `if/fi`)
- `agent-after-switch.sh`: replace jq `first` (1.6+) with `.[0]` for older jq compat; add null-safety for `.assigned_to`
- `agent-post-tool-use.sh`: validate task-board.json with `jq empty` before processing
- `auto-dispatch.sh`: fail-safe lock timeout (skip instead of proceeding unprotected)
- `config.sh`: escape special chars in sed replacement patterns

**LOW — Hardening:**
- `agent-pre-tool-use.sh`: escape agent name in JSON error output
- `agent-after-switch.sh`: replace unsafe `ls *.md` with `find -name "*.md"`

## [3.0.20] - 2025-04-09

### ⚡ Performance Optimization

**`fsm-validate.sh`**: Reduced jq calls from O(10×N) to O(2) total per hook invocation:
- Pre-extract ALL task fields (id, status, workflow_mode, feedback_loops, blocked_from, goals, parallel_tracks) in ONE jq call using `@tsv`
- Pre-load snapshot statuses with single jq call + awk lookup
- Eliminated 4 consecutive parallel_tracks queries (→ pre-extracted)
- Deduplicated `blocked_from` extraction across simple/3phase validators

**`memory-capture.sh`**: Same pattern — single jq call for all task data.

**`agent-staleness-check.sh`**:
- Cache date tool detection at startup (try once, reuse) instead of 3-tool fallback per call
- Consolidate 3→1 jq calls per state.json file

### 🧪 Integration Tests Expanded (12 → 21)

New tests: pre-tool-use agent boundaries (acceptor/implementer/reviewer), before-memory-write (empty/wrong-path/valid), on-goal-verified event logging, session-start event, staleness-check execution.

### 📖 README

- Added "Known Limitations & Troubleshooting" section

## [3.0.19] - 2025-04-09

### 🔧 Hook Modularization

Split the 364-line `agent-post-tool-use.sh` monolith into a clean 79-line main hook + 3 focused modules:

- `hooks/lib/auto-dispatch.sh` (75 lines) — message routing on status change
- `hooks/lib/fsm-validate.sh` (171 lines) — FSM transitions, goal guard, doc gate, feedback limit
- `hooks/lib/memory-capture.sh` (49 lines) — status transition detection + memory init

### 🧪 Integration Tests

- New `tests/test-integration.sh` with 12 actual hook execution tests
- Covers: tool logging, auto-dispatch, FSM violation, doc gate, memory capture, after-switch, compaction, security scan, before-task-create, events DB
- Added to `tests/run-all.sh` — full suite now 5/5

### 📄 Other

- `agent-init` skill now auto-creates `.agents/docs/` directory
- README: added document pipeline section with flow diagram

## [3.0.18] - 2025-04-09

### 📄 New Feature: Document Pipeline (`agent-docs` skill)

**Core concept**: Each SDLC phase must produce standardized documents that serve as inputs to the next phase.

**Document flow matrix**:
| Phase | Agent | Input | Output |
|-------|-------|-------|--------|
| Requirements | Acceptor | user request | `requirements.md` + `acceptance-criteria.md` |
| Design | Designer | requirements.md | `design.md` |
| Implementation | Implementer | requirements + design | `implementation.md` |
| Review | Reviewer | requirements + design + implementation | `review-report.md` |
| Testing | Tester | requirements + design + implementation | `test-report.md` |
| Acceptance | Acceptor | acceptance-criteria + all docs | Accept/Reject |

**What's included**:
- New `agent-docs` skill with 6 document templates (requirements, acceptance-criteria, design, implementation, review-report, test-report)
- Storage convention: `.agents/docs/T-XXX/` per task
- FSM document gate: warns when transitioning without required output document
- After-switch hook: lists available input documents for the current task
- All 5 agent profiles updated with explicit document input/output requirements
- 3-Phase mode document mapping included

## [3.0.17] - 2025-04-09

### 🐛 Deep Audit Round 2 (20 issues fixed)

**Security & Robustness:**
- **CWD extraction** in `agent-before-task-create.sh` — duplicate check now works from any directory
- **Lock release safety** — jq/mv failures no longer leave stale tmp files
- **grep pattern portability** in `security-scan.sh` — single-quote matching works across all grep implementations
- **CWD validation** in `security-scan.sh` — graceful exit if directory invalid
- **Download integrity** in `install.sh` — verify key files exist after tarball extraction
- **Copilot rules write check** — warn if append to copilot-instructions.md fails

**Cross-Platform Compatibility:**
- **Portable sed** in `config.sh` — `_sed_i()` helper detects macOS vs Linux (fixes `sed -i ''` failure on Linux/CI)
- **Portable date parsing** in `agent-staleness-check.sh` — replaced python3 fallback with perl `Time::Piece` (faster, no timeout risk)

**FSM Logic & Safety:**
- **Simple mode feedback loop protection** — `reviewing→implementing`, `testing→fixing`, `accept_fail→designing` now capped at 10 loops
- **Convergence gate event logging** — gate failures now logged to events.db (audit trail)
- **Unblock warnings** — tasks unblocked without `blocked_from` record get visible warning

**Memory & State:**
- **Memory directory creation check** — explicit error if `mkdir -p` fails
- **Compaction hook guard** — skip diary flush if no active agent found

**Documentation:**
- **README skill count** — badge updated 15→16, added `agent-config` to skills table
- **Section anchor** — `#15-skills` → `#16-skills`

## [3.0.16] - 2025-04-09

### 🐛 Critical Bug Fixes (Security & Reliability Audit)
- **TIMESTAMP SQL injection** — validate timestamp is numeric before SQL insertion
- **Pipe subshell variable loss** — convert `| while` to `while ... done < <(...)` in agent-post-tool-use.sh and agent-staleness-check.sh; staleness detection was completely broken
- **macOS file locking** — replace Linux-only `flock` with portable `mkdir`-based atomic lock
- **JSON null validation** — guard TASK_ID/NEW_STATUS against null/empty before FSM processing
- **TOOL_ARGS truncation order** — truncate before SQL escaping (not after) to prevent broken escape sequences
- **CWD initialization** — add INPUT/CWD extraction to 5 hooks missing it (after-memory-write, after-task-status, before-compaction, on-goal-verified, after-switch)

## [3.0.15] - 2025-04-09

### ✨ New Skill: agent-config
- **CLI model configuration** — `config.sh model set <agent> <model>` to configure agent models
- **CLI tools management** — `config.sh tools set/add/rm/reset` to control per-agent tool access
- **Dynamic agent discovery** — auto-scans all `*.agent.md` files, no hardcoded list
- **Dynamic model discovery** — `config.sh models` queries platform CLIs for available models
- **Dual-platform sync** — all changes applied to `~/.claude/agents/` and `~/.copilot/agents/` simultaneously
- **Backward compatible** — old `config.sh set/reset` commands still work

### 🔔 Model Switch Hints
- **agent-after-switch hook** — reads agent's `model` field on switch, suggests `/model <id>` command
- If `model` configured → "📌 Use /model xxx to switch"
- If only `model_hint` → "💡 hint information"
- If neither → silent (no noise)

### 🔧 Fixes
- **verify-install.sh** — updated skill count 15→16 (added agent-config)
- **SKILL.md interactive workflow** — AI now mandated to run discovery commands first, not assume agent/model lists

## [3.0.14] - 2025-04-09

### 🤝 Copilot Parity
- **Full Copilot CLI support** — installer now detects `~/.copilot` and auto-installs agents + skills + hooks + rules (same as Claude Code)
- **Agent profiles for Copilot** — 5 `.agent.md` files installed to `~/.copilot/agents/` (Copilot CLI natively supports custom agents via `/agent`)
- **Dual-platform check_install** — `--check` reports status for both Claude Code and Copilot CLI
- **Dual-platform uninstall** — `--uninstall` cleans both `~/.claude` and `~/.copilot` agent files

### 📝 Documentation
- **Updated platform compatibility table** — README now shows full parity between Claude Code and Copilot CLI
- **English usage instructions** — installer Done message now in English

## [3.0.13] - 2025-04-09

### ✨ Features
- **Per-agent model config** — added `model` and `model_hint` fields to all 5 agent profiles
- **Project-type-aware init** — agent-init Step 1c classifies projects (ios/frontend/backend/systems/ai-ml/devops) and adapts skill generation per type
- **Model resolution in agent-switch** — priority: task override → agent model → project config → system default

## [3.0.12] - 2025-04-09

### ⚡ Performance
- **Task-board cache** — cached task-board.json content in variable (15→1 disk reads per hook invocation)

### 🛡️ Resilience
- **events.db auto-repair** — session-start validates schema with `.tables` check, auto-recreates corrupted DB

### 🔧 CI/CD
- **GitHub Actions CI** — added `.github/workflows/test.yml`, runs all tests on push/PR to main

## [3.0.11] - 2025-04-09

### 📝 Documentation
- **Add 3-Phase sections** to implementer, reviewer, tester SKILL.md — each role now documents its 3-Phase responsibilities, steps, and differences from Simple mode
- **Trim monitoring diagrams** — replaced 48-line ASCII flowcharts with concise 5-step numbered lists (implementer −22 lines, tester −21 lines)

## [3.0.10] - 2025-04-09

### 🐛 Critical Fix
- **Fix undefined variables in auto-memory-capture** — `OLD_STATUS_SQL`/`NEW_STATUS_SQL`/`TASK_ID_SQL` were from a separate pipe subshell; memory events were never logged

### 🔒 Security
- **Bash command boundary enforcement** — acceptor, designer, reviewer now blocked from destructive bash commands (`rm`, `mv`, `git push`, `npm publish`, `docker run`, etc.)

### 🔧 Improvements
- **Improved uninstall()** — now removes security-scan.sh, rules/ files, restores hooks.json from `.bak`, cleans up Copilot installation

## [3.0.9] - 2025-04-09

### 🔧 Improvements
- **Standardize hook paths** — all 7 hooks with bare `.agents/` paths now use `AGENTS_DIR="${CWD:-.}/.agents"` variable
- **Clarify flock portability** — Linux-only with graceful no-op on macOS
- **CONTRIBUTING.md** — added dual-platform hook format comparison table (PascalCase vs camelCase, command vs bash, timeout ms vs sec)

### 🧪 Tests
- **test-hooks.sh expanded** — JSON validity checks for both hooks.json files, event count parity, rules/ validation, shebang + pipefail enforcement

## [3.0.8] - 2025-04-09

### 🐛 Critical Fix
- **Fix variable use-before-define** in `agent-post-tool-use.sh` — `OLD_STATUS_SQL`/`NEW_STATUS_SQL` were referenced before assignment, causing FSM validation to silently skip; also fixed self-referencing `sql_escape()` calls

### 🔧 Improvements
- **Complete Copilot hooks.json**: Added 6 missing event types (agentSwitch, taskCreate, taskStatusChange, memoryWrite, compaction, goalVerified) — Copilot users now get full hook coverage
- **verify-install.sh hardened**: Shebang → `#!/usr/bin/env bash`, error handling → `set -euo pipefail`

## [3.0.7] - 2025-04-09

### 🐛 Bug Fixes
- **README.md**: Fixed unclosed code fence after task lifecycle diagram — headings and text were rendered inside code block
- **install.sh hook count**: Fixed glob pattern (`agent-*.sh` → `*.sh`) to include `security-scan.sh` (12/13 → 13/13)
- **install.sh threshold**: Raised completeness check from 12 to 13 hooks

### 🔧 Improvements
- **hooks.json backup+replace**: Install now backs up existing hooks.json before overwriting (creates `.bak`) instead of skipping — applies to both Claude and Copilot platforms

## [3.0.6] - 2025-04-08

### 🔒 Security
- **CRITICAL: Fix SQL injection** in 11 sqlite3 calls across 6 hooks — all variables now escaped via `sql_escape()` helper
- **Expanded secret scanning**: Add detection for Stripe keys, Slack tokens, database connection strings, JWT/Bearer tokens, webhook URLs

### 🔧 Improvements
- **python3→jq migration**: All 7 hooks now use jq for JSON parsing (consistent, lighter, portable)
- **Shebang standardization**: All 13 hooks now use `#!/usr/bin/env bash` (was mixed `#!/bin/bash`)
- **SQLite error handling**: All hooks now log warnings on insert failure instead of silent suppression
- **.gitignore hardened**: Add agent runtime files (events.db, state.json, inbox.json, snapshots, logs, backups)

## [3.0.5] - 2025-04-08

### ⚡ Performance
- **SKILL.md context reduction**: agent-init 680→173 (−75%), agent-switch 588→141 (−76%)
- Total across 4 files: 3654→1116 lines (−69%, ~10K tokens/session)

## [3.0.4] - 2025-04-08

### 📦 New Features
- **FSM unblock validation**: `blocked→X` now restricted to `blocked→blocked_from` state only (prevents state-skipping)
- **Goal guards**: Acceptance (`→accepted`) blocked unless ALL goals have `status=verified`
- **11 new behavioral tests**: Unblock validation (5 tests) + goal guard (6 tests) — total 31 FSM tests

### ⚡ Performance
- **SKILL.md context reduction**: agent-orchestrator 1394→500 lines (−64%), agent-memory 992→302 lines (−70%)

### 🔧 Improvements
- **Consolidated hooks**: Merged memory-index trigger from agent-after-task-status.sh into agent-post-tool-use.sh (single source of truth)
- **SQLite error handling**: agent-after-task-status.sh now logs warnings on failure

## [3.0.3] - 2025-04-08

### ⚡ Performance
- **jq loop optimization**: Auto-dispatch now uses pipe-delimited parsing (3 jq calls → 1 per task)
- **SQLite transactions**: `memory-index.sh` wraps all inserts in a single transaction (atomicity + ~10x speed)

### 🐛 Bug Fixes
- **File locking**: Add `flock`-based locking on inbox.json writes to prevent race conditions
- **Cross-platform dates**: Add python3 fallback for ISO date parsing (macOS + Linux + containers)
- **SQLite error logging**: Replace silent `2>/dev/null || true` with proper warning on failure
- **Shell safety**: Standardize `set -euo pipefail` across all 6 hook scripts

### 📦 New Features
- **Orphan task detection**: Staleness check now flags blocked tasks with no activity >48h (🔴 warning)

## [3.0.2] - 2025-04-08

### 🐛 Bug Fixes
- **CRITICAL**: Fix missing `accepting→accept_fail` FSM transition in Simple mode validation — previously blocked all acceptance failure flows
- **macOS compatibility**: Replace `grep -P` (GNU-only) with `sed` in agent-post-tool-use.sh — fixes silent failure on macOS
- **Shell injection**: Fix unsanitized `$TASK_ID` in agent-before-task-create.sh — now passed via env var
- **Broken paths**: Fix `scripts/memory-index.sh` references in hooks — now searches `.agents/scripts/` and `scripts/` with fallback
- **3-Phase auto-dispatch**: Add all 15 3-Phase state→agent mappings to post-tool-use dispatch — previously only Simple mode states were dispatched

### 📦 New Features
- **Modular rules** (`rules/`): Leverage Claude Code's native `.claude/rules/` system with path-scoped rules
  - `agent-workflow.md` — Role + FSM rules (scoped to `.agents/**`, `hooks/**`, `skills/**`)
  - `security.md` — Secret scanning rules (scoped to code files)
  - `commit-standards.md` — Conventional commit format
- **Platform compatibility table**: Document Claude Code vs GitHub Copilot support matrix

### 📝 Documentation
- Fix README lifecycle diagram: add missing `accepting → accept_fail → designing` path
- Fix duplicate "Claude Code, Claude Code" → "Claude Code, GitHub Copilot"
- Fix "15+ Hook" → "13 Hook" in skills table and roadmap
- Fix staleness-check event type: SessionStart → PostToolUse (matches hooks.json)
- Update docs/agent-rules.md with 3-Phase workflow rules
- Update install.sh to install modular rules to `~/.claude/rules/`
- Update AGENTS.md: fix chmod for security-scan.sh, fix hook count verification
- Add rules/ directory structure to README file tree

### 🧪 Tests
- Expand test-hooks.sh from 5 to 13 hooks (full v2.0 coverage)

## [3.0.0] - 2025-04-12

### 🚀 Major Release — 3-Phase Engineering Closed Loop

#### Phase 13: 3-Phase Engineering Closed Loop
- **Dual-mode FSM**: Tasks now support `workflow_mode: "simple"` (default, backward compatible) or `"3phase"` (new)
- **18 new FSM states** across 3 phases for the 3-Phase workflow:
  - Phase 1 — Design: requirements → architecture → tdd_design → dfmea → design_review
  - Phase 2 — Implementation: implementing + test_scripting (parallel) → code_reviewing → ci_monitoring/ci_fixing → device_baseline
  - Phase 3 — Testing & Verification: deploying → regression_testing → feature_testing → log_analysis → documentation
- **Orchestrator daemon**: Background shell script that autonomously drives 3-Phase tasks end-to-end
- **Parallel tracks**: Phase 2 runs 3 concurrent tracks (implementer, tester, reviewer) with convergence gate
- **Feedback loops**: Phase 3 → Phase 2 (test failure), Phase 2 → Phase 1 (design gap), with MAX_FEEDBACK_LOOPS=10 safety limit
- **Pluggable external systems**: CI (GitHub Actions/Jenkins/GitLab CI), Code Review (GitHub PR/Gerrit/GitLab MR), Device/Test environment — all configurable via `{PLACEHOLDER}` tokens
- **16 prompt templates**: Step-specific prompts for autonomous agent invocation, generated during project init
- **Convergence gate**: All parallel tracks must complete before device_baseline
- **Feedback safety**: Auto-block tasks that exceed 10 feedback loops
- **New skill**: `agent-orchestrator` (3-Phase daemon management + prompt templates)
- Extended `agent-fsm` with 3-Phase state definitions, transitions, and guard rules
- Extended `agent-hooks` with 3-Phase dispatch logic, convergence validation, feedback counting
- Extended `agent-init` with workflow mode selection and 3-Phase initialization (orchestrator + prompts)
- Extended `agent-teams` with Phase 2 parallel track documentation
- Extended `agent-post-tool-use.sh` with dual-mode FSM validation (simple + 3-phase)
- Extended `task-board.json` schema with `workflow_mode`, `phase`, `step`, `parallel_tracks`, `feedback_loops`, `feedback_history` fields

### 📊 Stats
- Skills: 14 → **15** (+agent-orchestrator)
- FSM States: 10 (simple) + **18** (3-phase)
- Prompt Templates: **16** (generated per project)
- Workflow Modes: **2** (simple + 3-phase)
- Feedback Safety Limit: 10 loops per task

## [2.0.0] - 2025-04-07

### 🚀 Major Release — 5 New Phases

#### Phase 8: Memory 2.0
- Three-layer memory architecture (MEMORY.md long-term + diary/YYYY-MM-DD.md + PROJECT_MEMORY.md shared)
- SQLite FTS5 full-text indexing with unicode61 tokenizer (`scripts/memory-index.sh`)
- Hybrid search CLI with role/layer/limit filters (`scripts/memory-search.sh`)
- Memory lifecycle: 30-day temporal decay, 6-signal auto-promotion scoring
- Compaction-safe memory flush

#### Phase 9: Hook System 2.0
- Expanded from 5 hooks to **13 scripts** across **9 event types**
- New lifecycle hooks: AgentSwitch, TaskCreate, TaskStatusChange, MemoryWrite, Compaction, GoalVerified
- Block/Approval semantics — hooks can return `{"block": true}` to prevent operations
- Priority chains — multiple hooks execute in order, block stops chain
- Per-role tool profiles in `.agents/tool-profiles.json`
- New skill: `agent-hooks` (hook lifecycle management)

#### Phase 10: Scheduling & Automation
- Cron scheduler (`scripts/cron-scheduler.sh`) with `jobs.json` configuration
- Webhook handler (`scripts/webhook-handler.sh`) for GitHub push/PR/CI events
- FSM auto-advance — task completion auto-triggers next agent switch

#### Phase 11: Context Engine
- Token budget allocation per agent role
- Role-aware bootstrap injection (global skill + project skill + task + memory Top-6)
- Intelligent compression preserving key decisions

#### Phase 12: Agent Teams
- Subagent spawn protocol for parallel task execution
- Multi-implementer parallel pattern
- Parallel review coordination
- New skill: `agent-teams` (team orchestration)

### 📊 Stats
- Skills: 12 → **14** (+agent-hooks, +agent-teams)
- Hooks: 5 scripts / 3 events → **13 scripts / 9 events**
- Scripts: 2 → **6** (+memory-index, memory-search, cron-scheduler, webhook-handler)

## [1.0.0] - 2025-04-06

### 🎉 Initial Release

#### Phase 1: Core Framework
- 5 Agent roles: Acceptor, Designer, Implementer, Reviewer, Tester
- FSM state machine with 10 states and guard rules
- Task board with optimistic locking
- Goals-based task tracking (pending → done → verified)
- Agent messaging via inbox.json

#### Phase 2: Enforcement & Auditing
- Shell hooks for agent boundary enforcement
- Pre-tool-use boundary checking
- Post-tool-use audit logging
- SQLite events.db for activity tracking
- Security scan (pre-commit secret detection)

#### Phase 3: Automation
- Auto-dispatch: task state changes trigger downstream agent notification
- Staleness detection: warn on tasks idle > 24 hours
- Batch processing mode: agents process all pending tasks in a loop
- Monitor mode: Tester ↔ Implementer auto fix-verify cycle
- Structured issue tracking (JSON + optimistic locking)

#### Phase 4: Memory & Visualization
- Auto memory capture on FSM stage transitions
- Smart memory loading (role-based field filtering)
- ASCII pipeline visualization in agent status panel
- Project-level living documents (6 docs in docs/)
- Event summary in status panel (24h activity per agent)

#### Phase 5: Best Practices Integration
- Implementer: TDD discipline (RED/GREEN/REFACTOR + git checkpoints + 80% coverage gate)
- Implementer: Build fix workflow (one error at a time)
- Implementer: Pre-review verification (typecheck → build → lint → test → security)
- Reviewer: Severity levels (CRITICAL/HIGH/MEDIUM/LOW) with approval rules
- Reviewer: OWASP Top 10 security checklist
- Reviewer: Code quality thresholds (function >50 lines, file >800 lines, nesting >4)
- Reviewer: Confidence-based filtering (≥80% confidence)
- Reviewer: Design + code review (can route back to designer)
- Tester: Coverage analysis workflow
- Tester: Flaky test detection and quarantine
- Tester: E2E testing with Playwright Page Object Model
- Designer: Architecture Decision Records (ADR)
- Designer: Goal coverage self-check
- Acceptor: User story format for goals

## v3.2.1

### R3: Architecture Docs Update
- Rewrote `docs/skills-mechanism.md` with 5 updated Mermaid diagrams
- New: Two-level loading sequence diagram (summary ~1% + on-demand full text)
- New: Skill discovery paths comparison (Claude Code vs Copilot CLI)
- New: Per-Agent skill isolation flowchart with shared/role-specific allocation
- Updated: Three-layer behavior control (added skill constraints)
- Updated: Request lifecycle (reflects two-level loading + doc gate)

### R5: Conditional Activation (Partial)
- Added `paths:` frontmatter to `agent-hooks` skill (`hooks/**`, `**/*.sh`, config files)
- Documented `paths:` feature in skills-mechanism.md platform comparison table
- Role skills (tester, implementer) excluded to avoid breaking agent workflow

## v3.2.2

### Documentation Cleanup
- Fix stale references: skill count 14/15/17→18 across README, USAGE_GUIDE, badges
- Update claude-code-flow.md: two-level Skill loading + per-agent isolation diagram
- Update agent-rules.md: remove stale state.json, add skills: isolation mention
- Simplify README: condense issue tracking + memory sections, collapsible narrative
- Fix doc gate limitation entry: strict mode now exists (was listed as planned)
- README: 734→682 lines (−7%)

## v3.2.3

### agent-init Rework
- Step 1b: Scan both CLAUDE.md and .github/copilot-instructions.md
- Step 1e: Scan all 18 global skills (was only 7), read agent profiles with skills: isolation
- Step 1f: NEW — detect platform (Claude Code / Copilot CLI / both)
- Step 3: Remove stale state.json references
- Step 6: Fix .gitignore (remove state.json)
- Step 7: NEW — generate/update CLAUDE.md + copilot-instructions.md with framework refs
- Step 7c: NEW — auto-append .agents runtime paths to project .gitignore
- Step 8: Updated summary with platform + global skill count

## v3.2.4

### Skills Loading Animation
- Interactive HTML animation (8 steps, keyboard/auto-play)
- GIF (378KB) + MP4 (152KB) versions for sharing
- Visualizes two-level loading, per-agent isolation, token efficiency

### Audit Round 11
- 1 doc-only issue fixed (stale version in USAGE_GUIDE)
- Executable code: ZERO issues for 3rd consecutive round

## v3.3.0

### Worktree-Based Parallel Tasks
- NEW `agent-worktree` skill: create/list/merge/status commands
- Each task gets isolated worktree + branch (task/T-XXX)
- Shared task-board.json + events.db via symlink
- Isolated runtime (inbox, memory, docs) per worktree
- Auto-copy memory/docs back to main on merge

### Framework Updates
- Skill count: 18 → 19 (agent-worktree added as shared skill)
- Shared skills: 7 → 8 (all agents get worktree access)
- Updated all 5 agent profiles + skills-mechanism diagram
- Design doc: `.agents/docs/T-WORKTREE/design.md`

## v3.3.1

### Worktree P2-P5 Implementation
- P2: `team-session.sh --worktree --tasks T-042,T-043` (one tmux window per task)
- P3: auto-dispatch cross-worktree message routing
- P4: task-board.json `worktree` field (path/branch/created_at)
- P5: USAGE_GUIDE §3.4 + 5 new integration tests (30 total)

## v3.3.2

### Forced Natural Language Agent Switch
- agent-switch SKILL.md: expanded description with 7 trigger patterns (CN+EN)
- Added mandatory trigger rules section with name mapping table
- agent-rules.md: new "Forced Role Switch" top-priority section
- agent-init Step 7a: CLAUDE.md template now includes switch trigger rules
- Supports: "switch to acceptor" (CN), "switch to tester", "/agent acceptor", "I am implementer" (CN), etc.

## v3.3.3

### Role Permission Enforcement
- agent-rules.md: new "Role Permission Enforcement" section with permission matrix
- Self-check before every file operation: read active-agent → check matrix → block violations
- Violation response template: shows role, blocked action, and switch suggestion
- agent-init Step 7a: CLAUDE.md template includes enforcement rules
- Works in both Claude Code (hook-enforced) and Copilot CLI (self-check enforced)



