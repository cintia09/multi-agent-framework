---
name: codenook-v5-poc
description: "CodeNook v5.0 Proof-of-Concept. Generates a minimal .codenook/ workspace (core.md orchestrator + implementer + validator) to validate the workspace-first, main-as-router, prompt-as-file, self-bootstrap, and validator-pattern architecture. Use when asked to 'init codenook v5 poc', 'bootstrap v5 workspace', or when evaluating v5.0 design end-to-end."
---

# CodeNook v5.0 POC

Minimal viable prototype of the v5.0 architecture. Generates a `.codenook/` workspace at the current project root that demonstrates:

1. **Workspace-first** — state lives in files under `.codenook/`
2. **Main-as-Router** — `codenook-core.md` does only routing
3. **Prompt-as-File** — per-phase variable manifests reference long-term templates
4. **Self-Bootstrap Sub-Agents** — profiles define how agents fetch their own context
5. **Validator Pattern** — every worker output passes through a validator before HITL
6. **Two-Layer State** — workspace `state.json` + per-task `state.json`

## What This POC Includes

- 1 orchestrator core (`codenook-core.md`, ~7K)
- 2 role templates: implementer + validator
- 2 agent profiles (with self-bootstrap protocol)
- 1 criteria template (implement)
- 3 stable project docs (ENVIRONMENT / CONVENTIONS / ARCHITECTURE)
- 1 config.yaml
- 1 initial workspace state.json
- 1 bootloader (`CLAUDE.md`, works for both Claude Code and Copilot CLI)
- 3-phase lifecycle (clarify → implement → validate)

## What This POC Omits (Full v5.0)

- Dual-agent cross-examination
- Parallel scheduler / queue
- Full 10-phase state machine
- HITL adapters (terminal inline only)
- Automatic distillation skills
- Subtask decomposition
- Dashboard

## How to Invoke

```bash
# From target project root:
bash /path/to/CodeNook/skills/codenook-v5-poc/init.sh
```

Or from an LLM session:
> "Initialize CodeNook v5 POC in this directory"

## Expected Result

```
<project-root>/
├── CLAUDE.md
└── .codenook/
    ├── state.json
    ├── config.yaml
    ├── core/codenook-core.md
    ├── prompts-templates/{implementer,validator}.md
    ├── prompts-criteria/criteria-implement.md
    ├── agents/{implementer,validator}.agent.md
    ├── project/{ENVIRONMENT,CONVENTIONS,ARCHITECTURE}.md
    ├── tasks/
    └── history/
```

## Demo Run

1. Run `init.sh` in an empty project
2. Start Claude Code or Copilot CLI — bootloader loads core.md
3. Say: "New task: write a hello-world CLI in Python"
4. Core dispatches clarifier → implementer → validator
5. Observe: main session context stays ≤ 22K; outputs accumulate in `.codenook/tasks/T-001/`

## Files

See `init.sh` for bootstrap logic and `templates/` for all scaffolded files.
