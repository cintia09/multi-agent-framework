# CodeNook Pipeline — v0.13 Runtime Reference

This document describes the end-to-end runtime of CodeNook v0.13.2: how a user
turn becomes a task, how a task advances through phases, how memory accumulates,
and how task chains stitch follow-up work back to its ancestors.

The kernel is `skills/codenook-core/`; the canonical software-engineering
plugin is `plugins/development/`. Everything else is per-workspace state under
`.codenook/`.

---

## 1. Lifecycles at a glance

```
┌─ workspace ───────────────────────────────────────────────────────────────┐
│                                                                          │
│   init.sh                init.sh --install-plugin                        │
│      │                            │                                      │
│      ▼                            ▼                                      │
│   .codenook/ seeded   →   .codenook/plugins/<p>/  (atomic, read-only)    │
│                                                                          │
│   ┌─ per turn ──────────────────────────────────────────────────────┐    │
│   │ user turn ──► router-agent.spawn (prepare) ──► user confirms    │    │
│   │                       │                                         │    │
│   │                       ▼                                         │    │
│   │           spawn --confirm  ─►  first orchestrator-tick          │    │
│   │                                                                 │    │
│   │   ┌─ per task ───────────────────────────────────────────────┐  │    │
│   │   │ tick → load phase → dispatch sub-agent → read verdict    │  │    │
│   │   │      → post_validate → extractor-batch → hitl gate? →    │  │    │
│   │   │      → advance per transitions.yaml → tick again         │  │    │
│   │   └──────────────────────────────────────────────────────────┘  │    │
│   └─────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────┘
```

There are three nested loops: workspace (one-shot install), turn (one
router-agent invocation per user utterance), and task (orchestrator-tick,
called once per phase).

---

## 2. Workspace setup

> **Status note (v0.13.2 — DR-003):** the `init.sh` subcommands shown
> below describe the *target* M5+ pipeline. In v0.13.2 only
> `init.sh --version`, `--help`, and `--refresh-models` are live; `init.sh`
> with no args, `--install-plugin`, `--uninstall-plugin`,
> `--scaffold-plugin`, `--pack-plugin`, and `--upgrade-core` are 🚧
> planned for v0.12 (they currently `exit 2: TODO`). The supported install
> path today is `bash install.sh <workspace_path>` (top-level wrapper,
> see README §Quick Start) which delegates to the kernel
> `skills/codenook-core/install.sh` and runs the same 12 gates.

### 2.1 Seed

```bash
init.sh                              # 🚧 planned for v0.12
bash install.sh <workspace_path>     # ✅ live alternative
```

Creates `.codenook/` with an empty `tasks/`, an empty `memory/`, a default
`config.yaml`, and a `state.json` skeleton.

### 2.2 Plugin install (12 gates)

```bash
init.sh --install-plugin <path|url>                         # 🚧 planned for v0.12
bash skills/codenook-core/install.sh \
     --src <path|url> --workspace <ws>                      # ✅ live alternative
```

The `install-orchestrator` skill runs gates G01–G12 against the staged tarball
and only commits to `.codenook/plugins/<id>/` on success.

| Gate | Skill | Purpose |
|------|-------|---------|
| G01 | `plugin-format` | Well-formedness, no escaping symlinks |
| G02 | `plugin-schema` | `plugin.yaml` schema validation |
| G03 | `plugin-id-validate` | Id regex + reserved + already-installed |
| G04 | `plugin-version-check` | SemVer + `--upgrade` strict-greater |
| G05 | `plugin-signature` | Optional sha256 (when `CODENOOK_REQUIRE_SIG`) |
| G06 | `plugin-deps-check` | `requires.core_version` comparator |
| G07 | `plugin-subsystem-claim` | `declared_subsystems` collision detection |
| G08 | `sec-audit` | Workspace security scan |
| G09 | inline | Disk-quota check |
| G10 | `plugin-shebang-scan` | Shebang allowlist for `+x` files |
| G11 | `plugin-path-normalize` | No symlinks; no abs / `~` / `..` in YAML paths |
| G12 | inline | Atomic commit (rename staged tree into place) |

After install, the plugin tree is **read-only** by contract — `plugin_readonly`
verifies this on every kernel invocation.

---

## 3. Per-turn pipeline (router-agent)

The main session (Claude Code or Copilot CLI) invokes
`skills/builtin/router-agent/spawn.sh` once per user turn.

### 3.1 Prepare

```
spawn.sh --task-id T-NNN --workspace <ws> --user-turn-file <f>
```

`render_prompt.py` runs deterministically (no LLM) and:

1. Acquires a per-task fcntl lock on `tasks/<tid>/.lock`.
2. Computes the four prompt slots:
   - `{{MEMORY_INDEX}}` — `_lib/memory_index.py` digest of `memory/knowledge/`
     and `memory/config.yaml` (token-budgeted).
   - `{{PLUGINS_INDEX}}` — list of installed plugins with one-line summaries.
   - `{{TASK_CHAIN}}` — `_lib/chain_summarize.py` output if a parent is set,
     otherwise empty.
   - `{{USER_TURN}}` — verbatim user utterance.
3. Renders `prompt.md` into `tasks/<tid>/.router-prompt.md`.
4. Emits a JSON envelope telling the host runtime to spawn a Task sub-agent
   with that prompt.

### 3.2 Sub-agent run

The router-agent sub-agent (default model: `claude-opus-4.7`) reads the
rendered prompt and writes back three artefacts:

| File | Purpose |
|------|---------|
| `tasks/<tid>/router-context.md` | What the agent observed about the workspace |
| `tasks/<tid>/router-reply.md` | Conversational reply for the user |
| `tasks/<tid>/draft-config.yaml` | Proposed plugin, phase entry, dual_mode, model tier, parent task |

If a parent task is suggested, `_lib/parent_suggester.py` has already computed
the Jaccard top-3 candidates and they are presented inline.

### 3.3 Confirm

Once the user confirms (`spawn.sh --confirm …`), `render_prompt.py`:

1. Materialises `draft-config.yaml` into `tasks/<tid>/state.json`.
2. Overlays the chosen plugin and the memory layer into the task prompt
   directory (`_lib/workspace_overlay.py`).
3. Invokes `orchestrator-tick` for the first time.

---

## 4. Per-task pipeline (orchestrator-tick)

`tick.sh --task T-NNN` advances the task by exactly one phase.

```
tick
 │
 ├─ resolve current phase from plugins/<p>/phases.yaml
 │
 ├─ entry-questions check (entry-questions.yaml)
 │     └─ block if any required state field missing
 │
 ├─ dispatch_subagent
 │     ├─ render manifest-templates/phase-N-<role>.md
 │     │     with role profile, criteria-<phase>.md, ancestor context
 │     ├─ resolve model (task → phase → role → tier_* → platform default)
 │     └─ spawn sub-agent; wait for outputs/phase-N-<role>.md
 │
 ├─ read_verdict
 │     └─ parse YAML frontmatter (verdict ∈ {ok, needs_revision, blocked})
 │
 ├─ post_validate (if phases.yaml declares post_validate)
 │     └─ run validators/post-<phase>.sh; non-zero ⇒ verdict = needs_revision
 │
 ├─ extractor-batch (after_phase hook)
 │     └─ see §5
 │
 ├─ open HITL gate (if phases.yaml declares gate)
 │     └─ enqueue to .codenook/queue/hitl-<gate>; tick exits 1 (blocked)
 │
 └─ advance via transitions.yaml
       ok            → next phase
       needs_revision→ replay current phase (retry counter += 1)
       blocked       → exit 1 (blocked)
```

Exit codes: `0` advanced / waiting / done · `1` blocked (entry questions, HITL,
max_iterations, error) · `2` usage error · `3` legacy idle / terminal phase.

### 4.1 The development plugin's 8 phases

| # | Phase | Role | Output | Gate | Notes |
|---|-------|------|--------|------|-------|
| 1 | `clarify` | clarifier | `outputs/phase-1-clarifier.md` | — | turns the user's vague request into a testable spec |
| 2 | `design` | designer | `outputs/phase-2-designer.md` | `design_signoff` | dual_mode_compatible |
| 3 | `plan` | planner | `outputs/phase-3-planner.md` | — | `allows_fanout` (sub-tasks seeded if `decomposed=true`) |
| 4 | `implement` | implementer | `outputs/phase-4-implementer.md` | `pre_test_review` | dual_mode_compatible · `post_validate=validators/post-implement.sh` · `supports_iteration` · `allows_fanout` |
| 5 | `test` | tester | `outputs/phase-5-tester.md` | — | `post_validate=validators/post-test.sh` · `supports_iteration` |
| 6 | `accept` | acceptor | `outputs/phase-6-acceptor.md` | `acceptance` | |
| 7 | `validate` | validator | `outputs/phase-7-validator.md` | — | |
| 8 | `ship` | reviewer | `outputs/phase-8-reviewer.md` | — | |

Each role has a profile in `plugins/development/roles/<role>.md` that pins the
`one_line_job`, the verdict enum, and the dispatch contract. Quality criteria
for the three high-stakes phases live in
`plugins/development/prompts/criteria-{implement,test,accept}.md`.

---

## 5. Memory & extraction lifecycle

`extractor-batch` runs after every phase. It invokes three sub-extractors:

| Sub-extractor | Reads | Writes | Per-task cap |
|---------------|-------|--------|--------------|
| `knowledge-extractor` | role output + criteria | `memory/knowledge/<topic>.md` (patch or create) | 3 |
| `skill-extractor` | role output | `memory/skills/<name>/SKILL.md` | 1 |
| `config-extractor` | role output | `memory/config.yaml` (single `entries[]` log) | 5 |

### 5.1 Patch-or-create

For each candidate extraction, `_lib/memory_layer.py`:

1. Computes a content hash; bails if the hash already exists in
   `memory/history/extraction-log.jsonl`.
2. Asks the LLM (`_lib/llm_call.py`) to compare the candidate against the
   pre-computed `memory_index` digest of all current notes.
3. The LLM returns either `{action: patch, target: <path>, diff: …}` or
   `{action: create, topic: <slug>, body: …}`.
4. Atomic write under `memory/`; append a JSONL audit entry.

### 5.2 Water-marks

The 80% prompt-budget water-mark is enforced by `_lib/token_estimate.py`. When
the running prompt for the next phase would exceed 80% of the model's context
window (computed from `state.json.model_catalog`), `extractor-batch` skips the
non-essential extractions for that round and emits a `truncated` audit kind.

### 5.3 Workspace promotion

The `distiller` skill promotes plugin-local notes to workspace level when the
plugin's `plugin.yaml.knowledge.produces.promote_to_workspace_when` boolean
expressions evaluate to true. The expression context includes hit-count,
cross-task references, and explicit `promote: true` directives in the note's
frontmatter.

---

## 6. Task chains

### 6.1 Parent suggestion

Before the router-agent presents `draft-config.yaml`, `_lib/parent_suggester.py`:

1. Loads every active task's title and last-phase summary.
2. Tokenises the user turn and computes Jaccard similarity against each
   candidate.
3. Returns the top-3 with scores plus an `independent` option.

### 6.2 Chain context injection

If the user picks a parent (or chain of ancestors), `_lib/chain_summarize.py`:

1. Walks ancestors from root → child via `state.json.parent_task_id`.
2. Two-pass LLM compression — pass 1 summarises each ancestor individually;
   pass 2 merges the summaries into a single ≤8K-token narrative.
3. Injects the narrative into the child task's prompt as `{{TASK_CHAIN}}`.

This is what makes follow-up turns like *"now add refresh-token support"*
inherit the original *"add JWT login"* design without dragging in unrelated
history.

---

## 7. Quality gates per commit

Every commit on this repo passes the following before merge to `main`:

```bash
# 1. Full bats sweep
bats skills/codenook-core/tests/                       # 851 / 851 expected

# 2. CLAUDE.md linter
python3 skills/codenook-core/_lib/claude_md_linter.py --check-claude-md CLAUDE.md

# 3. Plugin read-only invariant
python3 skills/codenook-core/_lib/plugin_readonly.py --target . --json

# 4. Secret scan
python3 skills/codenook-core/_lib/secret_scan.py <changed-files>

# 5. Greenfield grep on user-facing docs (legacy version phrasing must be empty)
#    Pattern enforced by CI; expected output: GREENFIELD CLEAN
bash skills/codenook-core/tests/greenfield-docs.sh \
    README.md PIPELINE.md docs/README.md blog/vibe-coding-and-multi-agent.md
```

CI fails on any non-zero exit.

---

## 8. Where to look when something breaks

| Symptom | First file to read |
|---------|-------------------|
| Tick exits 1 immediately | `tasks/<tid>/audit/tick-*.json` (latest) |
| Sub-agent verdict missing | `tasks/<tid>/outputs/phase-N-<role>.md` (frontmatter parse) |
| Memory write failed | `memory/history/extraction-log.jsonl` (last entry) |
| HITL never resolves | `.codenook/queue/hitl-<gate>/` (queue-runner state) |
| Plugin install failed | `install-orchestrator` JSON output (gate id + reason) |
| Router-agent loops | `tasks/<tid>/.router-prompt.md` (slot rendering) |

---

*Generated for CodeNook v0.13.2 — kernel + plugin runtime reference.*
