<p align="center">
  <img src="docs/images/codenook-workspace-model.png" alt="CodeNook workspace model" width="900" />
</p>

<h1 align="center">🤖 CodeNook</h1>

<p align="center">
  <a href="https://github.com/cintia09/CodeNook/releases"><img src="https://img.shields.io/github/v/release/cintia09/CodeNook?style=for-the-badge&color=6366f1" alt="Release"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge" alt="MIT License"></a>
  <a href="https://github.com/cintia09/CodeNook/stargazers"><img src="https://img.shields.io/github/stars/cintia09/CodeNook?style=for-the-badge&color=f59e0b" alt="Stars"></a>
</p>

<p align="center">
  <strong>CodeNook is a multi-agent framework that installs a phase-gated task pipeline — driven by your Claude Code or Copilot CLI session — into any workspace.</strong>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> ·
  <a href="#architecture">Architecture</a> ·
  <a href="#how-it-works">How it works</a> ·
  <a href="#plugins">Plugins</a> ·
  <a href="PIPELINE.md">Pipeline walkthrough</a> ·
  <a href="docs/README.md">Design docs</a>
</p>

---

## What you get

CodeNook turns a single workspace into a **task-orchestration node**. The CLI session you already use (Claude Code, Copilot CLI) becomes a **pure conductor**: it relays user intent to a small Python kernel, which dispatches sub-agents through a phase-gated pipeline, with **human-in-the-loop (HITL) gates** between phases and a **persistent memory layer** that grows as tasks land.

Nothing is global. Everything lives under `<workspace>/.codenook/`. Pull the workspace to a new machine and the kernel, plugins, tasks, queue, and memory come with it.

## Quick start

```bash
# 1. Clone (or download a release)
git clone https://github.com/cintia09/CodeNook.git
cd CodeNook

# 2. Install the kernel + the development plugin into your workspace
python3 install.py --target ~/code/my-project --plugin development --yes

# 3. Open your workspace in Claude Code or Copilot CLI and just talk:
#    "use codenook to add a --tag filter to the xueba CLI list command"
```

The Python installer is the **only sanctioned entry point** as of v0.14.0 — there are no manual `cp` steps, no shell wrapper, no per-OS installers. Pass `--plugin all` to install every shipped plugin, or `--upgrade` to refresh an existing workspace in place.

After install, the workspace contains:

```
<workspace>/.codenook/
├── codenook-core/          ← kernel (CLI + builtin skills, plugin-agnostic)
├── plugins/<id>/           ← installed plugins (read-only)
├── bin/codenook(.cmd)      ← thin Python shim, on $PATH-style
├── tasks/                  ← per-task state, prompts, outputs
├── memory/                 ← cross-task knowledge + skills + index.yaml
├── hitl-queue/             ← pending HITL gate entries
└── extraction-log.jsonl    ← audit trail for memory writes
```

A single bootloader block is appended (idempotently) to your workspace `CLAUDE.md` so the conductor knows the protocol on the next session start.

## Architecture

CodeNook is a **three-layer system**:

| Layer | Lives in | Role |
|-------|----------|------|
| **Kernel** | `<ws>/.codenook/codenook-core/` | Plugin-agnostic. Ships the `codenook` CLI (`tick`, `decide`, `hitl-show`, `preflight`, `extract`, …), the orchestrator state machine, the three memory extractors, and the HITL adapter. |
| **Plugins** | `<ws>/.codenook/plugins/<id>/` | Domain knowledge. Each plugin defines `phases.yaml` (catalogue + profiles), `hitl-gates.yaml`, role files, manifest templates, optional knowledge / skills / validators. |
| **Workspace state** | `<ws>/.codenook/tasks/`, `memory/`, `hitl-queue/` | Per-task and cross-task runtime data. State is plain JSON / YAML / Markdown — resumable, auditable, diff-able. |

The diagram at the top of this README shows the same picture with the dispatch arrows drawn in. For the full deep dive, see [`docs/architecture.md`](docs/architecture.md).

## How it works

1. **Install** — `python3 install.py --target <ws> --plugin <id>` stages the kernel and plugin atomically into `<ws>/.codenook/`, then syncs the bootloader block in `<ws>/CLAUDE.md`.
2. **Conductor reads `CLAUDE.md`** — on the next CLI session start, your Claude/Copilot reads the bootloader. When you trigger a task ("use codenook to …"), it allocates a `T-NNN-<slug>` id (slug auto-derived from your input; falls back to plain `T-NNN` when no input is given) and calls `codenook tick --task T-NNN[-slug] --json`.
3. **Tick loop dispatches sub-agents** — `codenook tick` advances the state machine one phase at a time: it loads the role file from the plugin, renders a manifest into `tasks/<T>/prompts/`, dispatches a sub-agent, reads its `verdict`-stamped output from `tasks/<T>/outputs/`, runs `post_validate`, and triggers `extractor-batch` to harvest memory.
4. **HITL gates approve transitions** — when a phase has a gate, tick parks the task with `status: waiting` and writes an entry to `hitl-queue/`. The conductor surfaces the gate verbatim; you approve / reject / amend; the conductor calls `codenook decide --task T-NNN --phase <id> --decision <verb>`; tick resumes.

Loop until `status` is `done` or `blocked`.

## Plugins

Three first-party plugins ship in this repo and install through the same pipeline:

| Plugin | Version | Purpose |
|--------|---------|---------|
| **`development`** | v0.2.0 | Profile-aware software-engineering pipeline. 11-phase catalogue (clarify → design → plan → implement → build → review → submit → test-plan → test → accept → ship) with 7 profiles (`feature`, `hotfix`, `refactor`, `test-only`, `docs`, `review`, `design`). Clarifier picks the profile from the user's intent. |
| **`writing`** | v0.1.1 | Long-form authoring (outline → draft → review → revise → publish). |
| **`generic`** | v0.1.2 | Low-priority catch-all for tasks that don't match a specialised plugin. |

For the full development pipeline walkthrough — every phase, every gate, every profile — see [`PIPELINE.md`](PIPELINE.md).

## Documentation map

| Doc | What's inside |
|-----|---------------|
| [`PIPELINE.md`](PIPELINE.md) | End-to-end runtime walkthrough for the development plugin's `feature` profile. |
| [`docs/architecture.md`](docs/architecture.md) | Three-layer deep dive: kernel internals, plugin contract, workspace schema, concurrency model, bootloader. |
| [`docs/skills-mechanism.md`](docs/skills-mechanism.md) | How builtin / plugin / extracted skills are discovered and dispatched. |
| [`docs/memory-and-extraction.md`](docs/memory-and-extraction.md) | The memory layer (`memory/skills/`, `memory/knowledge/`, `index.yaml`), the three extractors, the context-pressure path, the audit log. |
| [`docs/task-chains.md`](docs/task-chains.md) | Catalogue + profiles, iteration, fanout, dual-mode, worked example through all 11 feature phases. |
| [`docs/vibe-coding-and-multi-agent.md`](docs/vibe-coding-and-multi-agent.md) | Concept primer: why structured multi-agent work beats free-form vibe-coding. |
| [`CHANGELOG.md`](CHANGELOG.md) | Release-by-release history. |

> **Deprecated.** The `router-agent` (described in `docs/router-agent.md`) is hidden from the v0.14.0 bootloader and the CLI flag warns on use. It is scheduled for hard removal in the next major release; the conductor protocol now drives `codenook` directly.

## Contributing

Bug reports, plugin contributions, and design discussions are welcome via GitHub issues / PRs. When adding a plugin, mirror the layout of `plugins/development/` (manifest + `phases.yaml` + `hitl-gates.yaml` + `roles/` + `manifest-templates/`) and validate locally with `python3 install.py --check`.

## License

MIT — see [`LICENSE`](LICENSE).
