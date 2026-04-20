<p align="center">
  <img src="blog/images/architecture.png" alt="CodeNook" width="680" />
</p>

<h1 align="center">🤖 CodeNook — Multi-Agent Development Framework</h1>

<p align="center">
  <a href="https://github.com/cintia09/CodeNook/releases"><img src="https://img.shields.io/github/v/release/cintia09/CodeNook?style=for-the-badge&color=6366f1" alt="Release"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge" alt="MIT License"></a>
  <a href="https://github.com/cintia09/CodeNook/stargazers"><img src="https://img.shields.io/github/stars/cintia09/CodeNook?style=for-the-badge&color=f59e0b" alt="Stars"></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/v0.11.1-stable-10b981?style=flat-square" alt="v0.11.1 stable">
  <img src="https://img.shields.io/badge/v6-plugin_architecture-6366f1?style=flat-square" alt="v6 plugin architecture">
  <img src="https://img.shields.io/badge/bats-851%2F851-22c55e?style=flat-square" alt="bats 851/851">
  <img src="https://img.shields.io/badge/M1–M11-shipped-8b5cf6?style=flat-square" alt="M1-M11 shipped">
</p>

<p align="center">
  <strong>A two-layer framework — <a href="skills/codenook-core/"><code>codenook-core</code></a> kernel plus per-workspace <a href="plugins/development/"><code>plugins/</code></a> — that turns natural-language turns into audited, multi-phase software-engineering work with persistent memory and task chains.</strong>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> ·
  <a href="#architecture">Architecture</a> ·
  <a href="#workflow">Workflow</a> ·
  <a href="#memory-layer">Memory</a> ·
  <a href="#task-chains">Chains</a> ·
  <a href="#extending-write-your-own-plugin">Extending</a> ·
  <a href="#quality-gates">Gates</a> ·
  <a href="docs/README.md">v6 Design Docs</a> ·
  <a href="PIPELINE.md">Pipeline</a>
</p>

---

## What is CodeNook

CodeNook is a zero-runtime-dependency framework for driving software work through Claude Code or Copilot CLI. Every user turn is routed by a **router-agent** into a structured task; tasks are advanced one phase at a time by an **orchestrator-tick** state machine; each phase runs as an isolated sub-agent with a fully-rendered prompt; and after every phase the **extractor-batch** distills useful artefacts back into a workspace **memory layer** that future tasks read.

The current shipped surface (v0.11.1) is the **v6 plugin architecture** — a kernel (`skills/codenook-core/`) plus an installable **development plugin** (`plugins/development/`) that defines the 8-phase software-engineering pipeline. Other domains (writing, generic, …) ship as additional plugins on the same kernel.

## Why

Vibe-coding alone produces undebuggable, untested code. Bolting full SDLC onto every chat is too heavy. CodeNook splits the difference:

- **Conversational** — you talk to the main session in natural language; the router-agent turns that into a draft task config you confirm.
- **Structured** — once confirmed, work runs through an explicit phase pipeline (analyst → designer → planner → implementer → tester → acceptor → validator → reviewer) with HITL gates where they matter.
- **Stateful** — knowledge, skills, and config decisions are extracted after every phase and written to `.codenook/memory/`, so the next task starts with everything the previous one learned.
- **Auditable** — every dispatch, every state mutation, and every memory write is logged under `.codenook/tasks/<T-NNN>/` and `.codenook/memory/history/`.
- **Composable** — plugins are read-only, signed, version-checked artefacts installed by a 12-gate pipeline. Swap or stack plugins without touching the kernel.

## Architecture

CodeNook ships in two layers; the diagram at the top shows their relationship.

### Layer 1 — `skills/codenook-core/` (the kernel)

The kernel knows nothing about software engineering. It contains:

| Subsystem | Key skills |
|-----------|------------|
| Routing | `router-agent`, `router-context-scan`, `router-dispatch-build` |
| Orchestration | `orchestrator-tick`, `dispatch-audit`, `hitl-adapter`, `queue-runner`, `session-resume` |
| Memory | `extractor-batch`, `knowledge-extractor`, `skill-extractor`, `config-extractor`, `distiller` |
| Plugin install (12 gates) | `install-orchestrator`, `plugin-format`, `plugin-schema`, `plugin-id-validate`, `plugin-version-check`, `plugin-signature`, `plugin-deps-check`, `plugin-subsystem-claim`, `plugin-shebang-scan`, `plugin-path-normalize`, `sec-audit` |
| Config & models | `config-resolve`, `config-validate`, `config-mutator`, `model-probe`, `secrets-resolve`, `task-config-set`, `preflight` |
| Helpers (`_lib/`) | `task_chain`, `parent_suggester`, `chain_summarize`, `memory_layer`, `memory_index`, `llm_call`, `render_prompt`, `token_estimate`, `workspace_overlay`, `claude_md_linter`, `plugin_readonly`, `secret_scan` |

Entry points: `init.sh` (workspace seed + plugin manager — see status table in §Quick Start) and `install.sh` (top-level install/upgrade wrapper around the 12-gate kernel installer; accepts a positional `<workspace_path>`).

### Layer 2 — `plugins/development/` (the domain pipeline)

A v6 plugin is a self-contained directory with a manifest (`plugin.yaml`), a phase table (`phases.yaml`), a transition table (`transitions.yaml`), HITL gates, role profiles, dispatch templates, and prompts.

The shipped **development** plugin defines 8 phases:

```
clarify → design → plan → implement → test → accept → validate → ship
```

mapped to 8 roles (`clarifier`, `designer`, `planner`, `implementer`, `tester`, `acceptor`, `validator`, `reviewer`) with criteria prompts under `plugins/development/prompts/criteria-*.md` and pytest-based post-validators under `plugins/development/validators/`.

### Per-workspace runtime layout

A workspace's `.codenook/` directory is the only place the kernel writes:

```
.codenook/
├── plugins/<plugin>/        # read-only, copied at install (M2 atomic commit)
├── memory/
│   ├── knowledge/<topic>.md # workspace-promoted notes (LLM-judged)
│   ├── skills/<name>/       # extracted reusable skills
│   ├── config.yaml          # single entries[] decision log
│   └── history/extraction-log.jsonl
├── tasks/<T-NNN>/
│   ├── state.json           # phase, verdict, dual_mode, retry counts
│   ├── outputs/phase-N-*.md # role outputs (verdict frontmatter)
│   ├── .router-prompt.md    # rendered router prompt (per turn)
│   └── audit/               # dispatch + extraction logs
└── state.json               # workspace-level model catalog + config
```

`plugin_readonly` and `secret_scan` enforce that nothing outside `tasks/` and `memory/` is mutated by the kernel; `claude_md_linter` keeps `CLAUDE.md` clean of v0.11-prohibited content.

## Quick Start

### 1. Install

Clone the repo and run the top-level installer against a workspace:

```bash
git clone https://github.com/cintia09/CodeNook.git
cd CodeNook
bash install.sh <workspace_path>          # install development plugin
bash install.sh --dry-run <workspace>     # gates only, no commit
bash install.sh --upgrade <workspace>     # re-install / version bump
bash install.sh --check <workspace>       # report install state
```

The top-level `install.sh` (v0.11.2):

* Runs the kernel installer (`skills/codenook-core/install.sh`) and stages the plugin into `<workspace>/.codenook/plugins/<id>/` (atomic commit on green G01–G12).
* Idempotently augments the workspace `CLAUDE.md` with a clearly delimited `<!-- codenook:begin --> ... <!-- codenook:end -->` bootloader block (re-runs replace the block in place; user content outside the markers is never touched).

### 2. (Optional) Manage plugins from inside a workspace

The kernel ships an `init.sh` wrapper for plugin management subcommands. **In v0.11.2 most subcommands are still planned for v0.12** — only the meta and refresh commands are live:

| Subcommand | Status |
|---|---|
| `init.sh --version` | ✅ live |
| `init.sh --help` | ✅ live |
| `init.sh --refresh-models` | ✅ live (re-probes model catalog into `.codenook/state.json`) |
| `init.sh` (no args, seed CWD) | 🚧 planned for v0.12 — use `bash install.sh <ws>` |
| `init.sh --install-plugin <path>` | 🚧 planned for v0.12 — use `bash skills/codenook-core/install.sh --src <path> --workspace <ws>` |
| `init.sh --uninstall-plugin <name>` | 🚧 planned for v0.12 |
| `init.sh --scaffold-plugin <name>` | 🚧 planned for v0.12 |
| `init.sh --pack-plugin <dir>` | 🚧 planned for v0.12 |
| `init.sh --upgrade-core` | 🚧 planned for v0.12 |

To install another plugin into a workspace today, call the kernel installer directly:

```bash
bash skills/codenook-core/install.sh \
     --src plugins/writing \
     --workspace ~/code/my-project
```

This runs the 12-gate install pipeline (`install-orchestrator`) and atomically commits the staged plugin tree into `.codenook/plugins/<id>/`.

### 3. Start a turn

In your AI session:

> "I want to add JWT login to the auth service."

The main session calls `skills/builtin/router-agent/spawn.sh` once. The router-agent:

1. Renders a system prompt with slots `{{MEMORY_INDEX}}`, `{{PLUGINS_INDEX}}`, `{{TASK_CHAIN}}`, `{{USER_TURN}}`.
2. Runs as a sub-agent that writes `tasks/<T-NNN>/draft-config.yaml` (plugin choice, dual_mode, model tier, parent task suggestion).
3. Asks you to confirm the draft.

On confirm, `spawn.sh --confirm` materialises the plugin + memory overlay into the task prompt and runs the first `orchestrator-tick`. From then on every `tick` advances one phase, dispatches the role sub-agent, runs the post-validator, opens the next HITL gate (if any), and appends to the audit log.

### 4. Inspect

```bash
cat .codenook/tasks/T-001/state.json | jq .phase
cat .codenook/memory/history/extraction-log.jsonl | tail -5
ls .codenook/memory/knowledge/
```

## Workflow

The end-to-end runtime loop, summarised — the full description with diagrams lives in [`PIPELINE.md`](PIPELINE.md).

```
user turn
   │
   ▼
router-agent.spawn  ──► renders prompt with MEMORY_INDEX + PLUGINS_INDEX + TASK_CHAIN
   │                    drafts tasks/<tid>/draft-config.yaml
   │                    suggests parent task (Jaccard top-3) or "independent"
   ▼
user confirms
   │
   ▼
spawn --confirm  ──► overlays plugins/<p>/ + memory/ into task prompt
                     materialises tasks/<tid>/state.json, fires first tick
   │
   ▼
orchestrator-tick (loop)
   ├─ load phase from plugins/<p>/phases.yaml
   ├─ dispatch_subagent  → role sub-agent runs against criteria-*.md
   ├─ read_verdict from outputs/phase-N-<role>.md frontmatter
   ├─ post_validate (e.g. validators/post-implement.sh)
   ├─ extractor-batch  → knowledge / skill / config extractors
   │                     (LLM-judged patch-or-create vs MEMORY_INDEX,
   │                      hash dedup, per-task caps 3/1/5)
   ├─ open hitl gate (if phases.yaml declares one)
   └─ advance per transitions.yaml (ok / needs_revision / blocked)
```

Every transition writes to `tasks/<tid>/audit/`, every extraction writes to `memory/history/extraction-log.jsonl`, and every model invocation goes through `_lib/llm_call.py` so token + retry policy is uniform.

## Memory Layer

The memory layer is a small, deterministic side-effect surface. There are exactly four artefact kinds:

| Path | Producer | Shape |
|------|----------|-------|
| `memory/knowledge/<topic>.md` | `knowledge-extractor` (after_phase) + `distiller` (promotion) | Markdown note, LLM-compressed, cross-task-relevant |
| `memory/skills/<name>/` | `skill-extractor` | Reusable skill skeleton (SKILL.md + scripts) |
| `memory/config.yaml` | `config-extractor` | Single `entries[]` decision log; one entry per locked-in decision |
| `memory/history/extraction-log.jsonl` | `extractor-batch` | Append-only audit (one JSON line per extraction attempt) |

Three guarantees enforced by `_lib/memory_layer.py`:

1. **Patch-or-create** — every extraction is judged against `memory_index` (a precomputed digest of all current knowledge files); the LLM either patches an existing note or creates a new one. Hash dedup prevents identical content from landing twice.
2. **Per-task caps** — at most 3 knowledge + 1 skill + 5 config entries per task. Caps are enforced by `extractor-batch` and water-marked at 80% of the prompt budget.
3. **Workspace promotion gate** — the `distiller` consults `plugin.yaml.knowledge.produces.promote_to_workspace_when` boolean expressions to decide whether a plugin-local note promotes to workspace-level `memory/knowledge/`.

`memory_index` is what the router-agent injects into `{{MEMORY_INDEX}}` on every turn — it is the only thing the next task needs to know about everything the previous tasks learned.

## Task Chains

Tasks form a DAG. When the router-agent prepares a turn it calls `_lib/parent_suggester.py`, which:

1. Tokenises the user turn and every active task's title + last-phase summary.
2. Computes Jaccard similarity and returns the top-3 candidate parents (plus `independent`).
3. The router presents the suggestions to the user; the user picks one.

If a parent is chosen, `_lib/chain_summarize.py` walks the ancestor chain, runs a two-pass LLM compression (first pass per-ancestor summary, second pass chain-merge), and stays within an 8K token budget. The result is injected into the child's prompt as `{{TASK_CHAIN}}`. This is how a follow-up turn like *"now add refresh-token support"* automatically gets the original *"add JWT login"* design + decisions without dragging in unrelated history.

## Extending — write your own plugin

A plugin is a directory with the following minimum surface (see `plugins/development/` for the canonical example):

```
my-plugin/
├── plugin.yaml              # M2 install manifest (id, version, requires.core_version, declared_subsystems)
├── config-defaults.yaml     # tier_* model defaults + hitl/concurrency
├── config-schema.yaml       # M5 config-validate DSL fragment
├── phases.yaml              # ordered phase list (id, role, produces, gate, allows_fanout, …)
├── transitions.yaml         # verdict → next-phase routing
├── entry-questions.yaml     # required state fields per phase
├── hitl-gates.yaml          # named gates referenced from phases.yaml
├── roles/<role>.md          # role profiles (one per phase)
├── manifest-templates/      # phase-N-<role>.md dispatch templates
├── prompts/                 # criteria-*.md (role-specific quality criteria)
└── validators/post-*.sh     # optional post-phase validators
```

Build a tarball with `init.sh --pack-plugin <dir>`, install with `init.sh --install-plugin <tarball>`. The 12-gate install pipeline checks well-formedness (G01), schema (G02), id (G03), semver (G04), optional sha256 sig (G05), `requires.core_version` (G06), subsystem collisions (G07), security (G08 via `sec-audit`), shebang allowlist (G10), and YAML path normalisation (G11). On success the staged tree is atomically committed to `.codenook/plugins/<id>/`.

The verdict contract is the only thing roles must obey:

```yaml
---
verdict: ok          # or needs_revision / blocked
summary: <≤200 chars>
---
<human-readable body>
```

`orchestrator-tick.read_verdict` reads only the frontmatter; the body is for humans and downstream phases.

## Quality Gates

Every commit on this repo runs:

| Gate | Command | What it checks |
|------|---------|----------------|
| Bats sweep | `bats skills/codenook-core/tests/` | 851 assertions across 101 test files (M1–M11) |
| `claude_md_linter` | `python3 skills/codenook-core/_lib/claude_md_linter.py --check-claude-md CLAUDE.md` | CLAUDE.md is free of forbidden surface |
| `plugin_readonly` | `python3 skills/codenook-core/_lib/plugin_readonly.py --target . --json` | Kernel never mutates `plugins/` outside install |
| `secret_scan` | `python3 skills/codenook-core/_lib/secret_scan.py <files>` | No keys / tokens / connection strings |
| Greenfield grep | repo-wide grep for legacy version phrasing on user-facing docs | Top-level docs stay current with the shipped surface |

The kernel ships with bats fixtures for every gate failure mode under `skills/codenook-core/tests/fixtures/plugins/`, so changes to the install pipeline can be regression-tested deterministically.

## Roadmap

v0.11.1 is the **specification-consolidation milestone** — M1–M11 are shipped, 851/851 bats green, 100 of 117 acceptance tests PASS / 13 PARTIAL / 4 SKIP. The deferred surface for v0.12 is small and well-scoped:

- **A1-6** — `session-resume` schema v2 (replace 10 M1-compat keys, rewrite `m1-session-resume.bats` end-to-end).
- **MEDIUM-04** — snapshot `fcntl.flock` to close the multi-process snapshot TOCTOU window.
- **AT-REL-1, AT-LLM-2.1, AT-COMPAT-1, AT-COMPAT-3** — four acceptance tests deferred pending real-LLM and multi-host fixtures.

Tracked in [`docs/release-report-v0.11.md`](docs/release-report-v0.11.md) and [`docs/cleanup-report-v0.11.1.md`](docs/cleanup-report-v0.11.1.md).

## Documentation

| Doc | Purpose |
|-----|---------|
| [`PIPELINE.md`](PIPELINE.md) | End-to-end runtime pipeline reference |
| [`docs/README.md`](docs/README.md) | Index of the 9 v6 design docs + acceptance + execution reports |
| [`docs/architecture.md`](docs/architecture.md) | Plugin architecture design (42 ratified decisions) |
| [`docs/router-agent.md`](docs/router-agent.md) | Router-agent specification |
| [`docs/memory-and-extraction.md`](docs/memory-and-extraction.md) | Memory layer + extraction policy |
| [`docs/task-chains.md`](docs/task-chains.md) | Parent suggestion + chain summarisation |
| [`docs/requirements.md`](docs/requirements.md) | ~70 FR / NFR (1162 lines) |
| [`docs/acceptance.md`](docs/acceptance.md) | 117 acceptance tests |
| [`docs/acceptance-execution-report.md`](docs/acceptance-execution-report.md) | 100 PASS / 13 PARTIAL / 4 SKIP |
| [`blog/vibe-coding-and-multi-agent.md`](blog/vibe-coding-and-multi-agent.md) | Background essay |
| [`CHANGELOG.md`](CHANGELOG.md) | Release notes |

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feat/my-feature`)
3. Run `bats skills/codenook-core/tests/` and the four quality gates above before committing
4. Commit changes (English commit messages, include the `Co-authored-by` trailer if the work was AI-paired)
5. Open a Pull Request against `main`

## License

MIT — see [`LICENSE`](LICENSE).
