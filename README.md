<p align="center">
  <img src="docs/images/codenook-workspace-model.png" alt="CodeNook workspace model" width="900" />
</p>

<h1 align="center">🤖 CodeNook</h1>

<p align="center">
  <strong>Plug domain expertise into your AI coding session.</strong><br/>
  Turn any Claude Code or Copilot CLI workspace into a phase-gated, multi-agent task pipeline — one <code>install.py</code> away.
</p>

<p align="center">
  <a href="https://github.com/cintia09/CodeNook/releases"><img src="https://img.shields.io/github/v/release/cintia09/CodeNook?style=for-the-badge&color=6366f1" alt="Release"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge" alt="MIT License"></a>
  <a href="https://github.com/cintia09/CodeNook/stargazers"><img src="https://img.shields.io/github/stars/cintia09/CodeNook?style=for-the-badge&color=f59e0b" alt="Stars"></a>
  <img src="https://img.shields.io/badge/python-3.9%2B-3776ab?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.9+">
</p>

<p align="center">
  <a href="#-the-3-concepts">Concepts</a> ·
  <a href="#-quick-start">Quick Start</a> ·
  <a href="#-why-codenook">Why</a> ·
  <a href="#-plugin-catalogue">Plugins</a> ·
  <a href="#-architecture">Architecture</a> ·
  <a href="PIPELINE.md">Pipeline walkthrough</a> ·
  <a href="docs/README.md">Docs</a>
</p>

---

## ✨ The 3 concepts

CodeNook stands on three deliberately small ideas. If you only read one section of this README, read this one.

| Concept | What it is | Real-world analogue |
|---|---|---|
| 🧩 **Plugin** | A **business domain** — packaged. Bundles the vocabulary, workflows, role definitions, gate policies, and reusable knowledge of a specific kind of work (software delivery, PR investigation, long-form writing, …). | A *team handbook* for a specific discipline. |
| 🔄 **Phase** | A **stage in a workflow**. Each plugin declares an ordered chain of phases (e.g. `clarify → design → plan → dfmea → implement → review → ship`). Phases have entry conditions, output contracts, and optional human-in-the-loop gates. | A *step on a process map*. |
| 🤖 **Agent** | An **executor** — the AI sub-agent that does the work of one phase. Each phase ships its own role profile, system prompt, allowed tool surface, and verdict format. The kernel dispatches them; the conductor (your CLI session) relays. | A *specialist* you'd hire for one specific step. |

> **The mental model in one sentence:** install a plugin, get its domain knowledge and workflow; the kernel walks the workflow phase-by-phase, dispatching the right specialist agent at each step, with you as the human gate-keeper between phases.

This is the whole product. Everything else — the kernel, the CLI, the memory layer, the HITL queue — exists to make those three concepts work cleanly together.

---

## 🚀 Quick start

```bash
# 1. Clone (or download a release)
git clone https://github.com/cintia09/CodeNook.git
cd CodeNook

# 2. Install the kernel + the development plugin into your workspace
python3 install.py --target ~/code/my-project --plugin development --yes

# 3. Open your workspace in Claude Code or Copilot CLI and just talk:
#    "use codenook to add a --tag filter to the CLI list command"
```

That's it. The conductor (your CLI session) reads the bootloader block in `CLAUDE.md` on the next start, and the next time you say "use codenook to …" it spins up a task, dispatches phase agents, surfaces HITL gates for your approval, and walks the work to completion.

Pass `--plugin all` to install every shipped plugin, or `--upgrade` to refresh an existing workspace in place.

---

## 🎯 Why CodeNook

Today's AI coding assistants are powerful but **monolithic**: one giant prompt, one giant context window, one improvised plan per conversation. That's fine for "fix this typo" — and a mess for anything multi-step or domain-specific.

CodeNook splits the work along the natural grain of how humans actually deliver:

| Without CodeNook | With CodeNook |
|---|---|
| One huge agent juggles requirements, design, code, tests, and reviews in the same context. | Each phase has its own specialist agent with a focused prompt and limited tool surface. |
| You re-explain the project's conventions every session. | Conventions live in plugins (`knowledge/`, `skills/`); every agent reads them automatically. |
| "Did the AI consider security?" — you hope so. | Explicit phases like **DFMEA** force the question; gates make you sign off. |
| State lives in chat history. Pause = lose context. | State lives on disk under `<workspace>/.codenook/`. Resume tomorrow, on another machine, mid-phase. |
| One-off plans, no learning. | Memory layer captures reusable knowledge & skills across tasks. |
| Long autonomous runs that go off the rails silently. | HITL gates between phases. The AI proposes; you approve, reject, or amend. |

If you've ever wanted your AI assistant to **work like a team instead of a soloist**, that's the gap CodeNook fills.

---

## 🧩 Plugin catalogue

Five first-party plugins ship in this repo and install through the same `python3 install.py` pipeline. Community plugins follow the same contract — see [`docs/plugin-authoring.md`](docs/architecture.md) and the `plugins/` folder for reference layouts.

| Plugin | Version | Domain | Phase chain (default profile) |
|---|---|---|---|
| 🛠️ **`development`** | `v0.5.1` | Software delivery — feature work, hotfixes, refactors, docs, reviews. | `clarify → design → plan → dfmea → implement → build → review → submit → test-plan → test → accept → ship` |
| ✍️ **`writing`** | `v0.3.0` | Long-form authoring — articles, docs, RFCs. | `outline → draft → review → revise → publish` |
| 🧰 **`generic`** | `v0.3.0` | Low-priority catch-all for tasks that don't match a specialised plugin. | `clarify → execute → review` |
| 🔎 **`issuenook`** | `v0.1.0` | Runtime issue investigation — collect context, analyze logs/code, form and verify root-cause hypotheses. | `info_collect → log_analyse → code_analyse → hypothesise → verify_hypothesis → conclude` |
| 📚 **`researchnook`** | `v0.1.0` | Research and investigation reports — evidence assessment, framework selection, analysis, review, and publish. | `brief → framework_select → scope → source_plan → data_collect → data_assess → analysis → synthesis → draft_report → review → revise_publish` |

The development plugin alone ships **7 profiles** (`feature`, `hotfix`, `refactor`, `test-only`, `docs`, `review`, `design`) — each a different ordering of the same 12-phase catalogue. The clarifier picks the profile from your intent, so you never need to know the profile names.

For the full development walkthrough — every phase, every gate, every verdict — see [`PIPELINE.md`](PIPELINE.md).

> 💡 **Building your own plugin?** A plugin is just a directory with `plugin.yaml` + `phases.yaml` + `hitl-gates.yaml` + `roles/<name>/role.md` files. No code required for most domains; you're declaring a workflow, not implementing one.

---

## 🏗️ Architecture

CodeNook is a **three-layer system** — and the layers map 1:1 onto the three concepts above.

| Layer | Lives in | Concept it serves | Role |
|---|---|---|---|
| **Kernel** | `<ws>/.codenook/codenook-core/` | runs **agents** + walks **phases** | Plugin-agnostic. Ships the `codenook` CLI (`tick`, `decide`, `task`, `knowledge`, `history`, …), the orchestrator state machine, the memory layer, and the HITL adapter. |
| **Plugins** | `<ws>/.codenook/plugins/<id>/` | encodes a **business domain** | Each plugin declares its phase catalogue (`phases.yaml`), gate policy (`hitl-gates.yaml`), per-phase role files, manifest templates, and optional knowledge / skills / validators. |
| **Workspace state** | `<ws>/.codenook/{tasks,memory,hitl-queue,history}/` | the running **work** | Per-task and cross-task runtime data. Plain JSON / YAML / Markdown — resumable, auditable, diff-able, version-controllable. |

```
<workspace>/.codenook/
├── codenook-core/       ← kernel (CLI + orchestrator + builtin skills)
├── plugins/<id>/        ← installed plugins (read-only)
├── bin/codenook(.cmd)   ← thin Python shim
├── tasks/<T-NNN>/       ← per-task state, prompts, outputs, history
├── memory/              ← cross-task knowledge, skills, history snapshots
├── hitl-queue/          ← pending HITL gate entries
└── state.json           ← installed-plugins manifest
```

Nothing is global. Pull the workspace to a new machine and the kernel, plugins, tasks, queue, and memory come with it. The conductor (your Claude/Copilot session) reads a single bootloader block appended idempotently to `<ws>/CLAUDE.md` and follows the protocol from there.

For the deep dive — kernel internals, plugin contract, concurrency model, dispatch envelope — see [`docs/architecture.md`](docs/architecture.md).

---

## 🔁 How a task actually runs

```
┌──────────────┐                  ┌──────────────┐                  ┌──────────────┐
│              │  "use codenook   │              │   tick --json    │              │
│     YOU      │ ───────────────▶│   CONDUCTOR  │ ────────────────▶│    KERNEL    │
│              │   to add ..."    │ (Claude/CLI) │                  │   (Python)   │
└──────────────┘                  └──────┬───────┘                  └──────┬───────┘
       ▲                                 │                                 │
       │                                 │   dispatches sub-agent          │
       │                                 │◀────────────────────────────────│
       │                                 │   (designer / planner /         │
       │  HITL gate:                     │    implementer / reviewer …)    │
       │  approve? reject? amend?        │                                 │
       │◀────────────────────────────────│                                 │
       │                                 │   writes phase output           │
       │  approve ───────────────────────▶  decide --decision approve ────▶│  next phase…
       │                                 │                                 │
```

1. **Install** → `python3 install.py --target <ws> --plugin <id>` stages the kernel + plugin atomically.
2. **Conductor reads `CLAUDE.md`** → learns the protocol on the next CLI session start.
3. **Tick loop** → `codenook tick` advances one phase: loads the role file, renders a manifest, dispatches a sub-agent, reads its `verdict`-stamped output, runs validators, snapshots history.
4. **HITL gates** → tick parks the task with `status: waiting`; conductor surfaces the gate verbatim; you approve / reject / amend; `codenook decide` resumes the loop.
5. **Memory** → finished tasks can be promoted into `memory/knowledge/<slug>/index.md` or `memory/skills/<slug>/SKILL.md` for reuse by future tasks.

Loop until `status` is `done` or `blocked`.

---

## 📚 Documentation

| Doc | What's inside |
|-----|---------------|
| [`PIPELINE.md`](PIPELINE.md) | End-to-end runtime walkthrough for the development plugin's `feature` profile. |
| [`docs/architecture.md`](docs/architecture.md) | Three-layer deep dive: kernel internals, plugin contract, workspace schema, concurrency model, bootloader. |
| [`docs/skills-mechanism.md`](docs/skills-mechanism.md) | How builtin / plugin / memory skills are discovered and dispatched. |
| [`docs/memory-and-extraction.md`](docs/memory-and-extraction.md) | The memory layer (`memory/skills/`, `memory/knowledge/`, history snapshots, retention). |
| [`docs/task-chains.md`](docs/task-chains.md) | Catalogue + profiles, iteration, fanout, dual-mode, worked example through every phase. |
| [`docs/vibe-coding-and-multi-agent.md`](docs/vibe-coding-and-multi-agent.md) | Concept primer: why structured multi-agent work beats free-form vibe-coding. |
| [`CHANGELOG.md`](CHANGELOG.md) | Release-by-release history. |

---

## 🤝 Contributing

Bug reports, plugin contributions, and design discussions are welcome via GitHub issues / PRs.

When adding a plugin, mirror the layout of `plugins/development/` (`plugin.yaml` + `phases.yaml` + `hitl-gates.yaml` + `roles/` + `manifest-templates/`) and validate locally with:

```bash
python3 install.py --check
```

A few non-negotiables for contributors (these match the bootloader rules):

- Executable artefacts shipped in plugin `skills/` or `validators/` must be **Python 3** — no `.sh`.
- Plugin role files address sub-agents, never the conductor; keep imperative language scoped to the role.
- Don't hand-edit `state.json`, queue entries, or task history — go through the CLI.

---

## 📜 License

MIT — see [`LICENSE`](LICENSE).

---

<p align="center">
  <sub>Built for people who want their AI assistant to <strong>work like a team</strong>, not a soloist.</sub>
</p>
