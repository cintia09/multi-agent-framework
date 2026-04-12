---
name: codenook-init
description: "Initialize the multi-agent development framework in a project. Detects platform, generates agent profiles, creates task board and config."
---

# Agent System Initialization (v4.0)

> Trigger: "initialize agent system" | "agent init" | "codenook-init"

## Step 1 — Platform Detection

Detect which AI coding platform is available:

```
1. Run `which copilot` and `which claude` (or check PATH)
2. Match result:
   ┌─────────────────────┬───────────────────────────────┐
   │ copilot only        │ Platform = copilot-cli        │
   │ claude only         │ Platform = claude-code         │
   │ both found          │ ask_user → pick one or "both" │
   │ neither found       │ warn; allow manual selection   │
   └─────────────────────┴───────────────────────────────┘
3. Also detect environment:
   - $DISPLAY or $BROWSER set → desktop
   - Otherwise              → headless
```

Platform determines the **root directory** for all generated files:

| Platform     | Root Dir   | Agents Dir             | CodeNook Dir             | Instructions Target                                    |
|--------------|------------|------------------------|--------------------------|--------------------------------------------------------|
| copilot-cli  | `.github/` | `.github/agents/`      | `.github/codenook/`      | `.github/instructions/codenook.instructions.md`        |
| claude-code  | `.claude/` | `.claude/agents/`      | `.claude/codenook/`      | Append to project-root `CLAUDE.md`                     |

---

## Step 2 — Idempotency Check

Before creating anything, check if the root directory already exists:

```
IF <root>/config.json exists:
  ask_user "Agent system already initialized. Reinitialize?"
    choices:
      Merge  → regenerate agent profiles; preserve task-board.json & memory/
      Fresh  → rm -rf <root>; proceed as new install
      Cancel → abort
```

---

## Step 3 — Configuration Questions

Collect preferences via `ask_user` (4 prompts max):

### Q1 — Platform
> "Which platform? [Auto-detected: **{detected}**]"
> Choices: `Copilot CLI` · `Claude Code` · `Both`

### Q2 — Agent Models
> "Configure models for agents?"
> Choices: `Use defaults` · `Custom per-agent`

Default model map:

| Agent        | Default Model       |
|--------------|---------------------|
| acceptor     | claude-haiku-4.5    |
| designer     | claude-sonnet-4     |
| implementer  | claude-sonnet-4     |
| reviewer     | claude-sonnet-4     |
| tester       | claude-haiku-4.5    |

If **Custom**: loop through 5 agents, ask model for each.

### Q3 — HITL Adapter
> "HITL adapter?"
> Choices (context-dependent):

| Environment | Choices                                      |
|-------------|----------------------------------------------|
| Desktop     | `Local HTML ★` · `Terminal` · `GitHub Issue` |
| Headless    | `Terminal ★` · `GitHub Issue`                |
| +Confluence | Append `Confluence` to either list           |

★ = recommended default

### Q4 — Gitignore
> "Add agent system files to .gitignore?"
> Choices: `Yes ★` · `No`

Items to append (relative to project root):
- `<root>/codenook/` — entire runtime directory (memory, task-board, config)

Where `<root>` is `.github/` or `.claude/` depending on platform.
Agent profiles at `<root>/agents/` are also ignored by default.
The entire agent system is treated as a dev tool — not committed to project source.

---

## Step 4 — Directory & File Generation

Create the full tree under `<root>`:

```
<root>/
├── agents/
│   ├── acceptor.agent.md      ← from template, ${MODEL} replaced
│   ├── designer.agent.md
│   ├── implementer.agent.md
│   ├── reviewer.agent.md
│   └── tester.agent.md
├── codenook/
│   ├── memory/                ← empty directory (with .gitkeep)
│   ├── task-board.json        ← seed content below
│   ├── config.json            ← seed content below
│   └── hitl-adapters/         ← copied from skill's hitl-adapters/ directory
│       ├── terminal.sh
│       ├── local-html.sh
│       ├── github-issue.sh
│       ├── confluence.sh
│       ├── hitl-server.py
│       └── hitl-verify.sh
└── instructions/              ← Copilot CLI only
    └── codenook.instructions.md  ← orchestration engine (auto-loaded)
```

For Claude Code: append engine content to project-root `CLAUDE.md` instead of instructions/.

### Agent Profile Templates

Read templates from the `templates/` subdirectory relative to this SKILL.md file.
The path is typically `~/.copilot/skills/codenook-init/templates/` or `~/.claude/skills/codenook-init/templates/`.

For each template:
1. Read the file content
2. Replace `${MODEL}` with the user's model choice for that agent
3. Write to `<root>/agents/<role>.agent.md`

### HITL Adapter Scripts

Copy all files from the `hitl-adapters/` subdirectory relative to this SKILL.md file
to `<root>/codenook/hitl-adapters/`. Ensure all `.sh` files are executable (chmod +x).

### Instructions File (Orchestration Engine)

Read `templates/codenook.instructions.md` and replace `${ROOT}` with the platform root
(`.github` or `.claude`), then write to the appropriate location:
- **Copilot CLI:** Write to `<root>/instructions/codenook.instructions.md` (auto-loaded by platform)
- **Claude Code:** Append content to project-root `CLAUDE.md`

This instructions file contains the **full orchestration engine**: routing table, HITL enforcement,
memory management, task commands. It is automatically loaded as part of every session context.
No separate global skill needed — the engine lives entirely in the project.

### Seed: `task-board.json`
```json
{
  "version": "4.0",
  "tasks": []
}
```

### Seed: `config.json`
```json
{
  "version": "4.0",
  "platform": "<copilot-cli|claude-code>",
  "models": {
    "acceptor":    "<model>",
    "designer":    "<model>",
    "implementer": "<model>",
    "reviewer":    "<model>",
    "tester":      "<model>"
  },
  "hitl": {
    "enabled": true,
    "adapter": "<local-html|terminal|github-issue|confluence>",
    "port": 8765,
    "auto_open_browser": true
  },
  "preferences": {
    "autoGitignore": true
  }
}
```

---

## Step 5 — Post-Init Verification

After all files are written:

1. **Enumerate** every expected file path (agents, hitl-adapters, seeds, instructions)
2. **Assert** each exists and has size > 0
3. **Print summary** to the user:

```
✅ Agent system initialized!

Platform:  Copilot CLI
Directory: .github/
Agents:    5 (acceptor, designer, implementer, reviewer, tester)
HITL:      local-html (port 8765)
Engine:    .github/instructions/codenook.instructions.md (auto-loaded)
Models:
  acceptor:    claude-haiku-4.5
  designer:    claude-sonnet-4
  implementer: claude-sonnet-4
  reviewer:    claude-sonnet-4
  tester:      claude-haiku-4.5

Next steps:
  1. Say "create task <title>" to create your first task
  2. Say "run task T-001" to start orchestration
  3. HITL gates will pause for your approval between each phase
  4. The orchestration engine is auto-loaded — no extra setup needed
```

If any file is missing or empty, report the failure and offer to retry.

---

## Uninstall — Remove Agent System from Project

> Trigger: "remove agent system" | "uninstall agents" | "clean codenook"

1. Detect platform root (`.github/` or `.claude/`)
2. Confirm with user: "Remove agent system from this project? This deletes agents/, codenook/, and instructions."
3. If confirmed:
   - `rm -rf <root>/agents/`
   - `rm -rf <root>/codenook/`
   - Remove `<root>/instructions/codenook.instructions.md` (Copilot) or the framework block from `CLAUDE.md` (Claude Code)
   - Remove agent-related entries from `.gitignore` (if added by init)
4. Print: "✅ Agent system removed from project."

This only removes project-level files. The global `codenook-init` skill (`~/.copilot/skills/`, `~/.claude/skills/`) is managed by `install.sh --uninstall`.
