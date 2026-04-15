---
name: codenook-init
description: "Initialize the multi-agent development framework in a project. Generates agent profiles, creates task board and config for Claude Code."
---

# Agent System Initialization (v4.3.1)

> Trigger: "initialize agent system" | "agent init" | "codenook-init"

Platform: **Claude Code** — all files are generated under `.claude/`.
Instructions are appended to project-root `CLAUDE.md`.

## Step 1 — Directory Confirmation

Ask the user to confirm the installation directory:

```
ask_user "Install CodeNook agent system to: <project_root>/.claude/"
  choices:
    ".claude/ (Recommended)" → proceed
    "Custom path"            → ask for custom root path (validate: reject paths with shell metacharacters $;&|`<>)
    "Cancel"                 → abort
```

Show the full resolved path (e.g., `/Users/dev/my-project/.claude/`).

---

## Step 2 — Idempotency Check & Upgrade

Before creating anything, check if the system already exists:

```
IF .claude/codenook/config.json exists:
  existing_version = config.json → "version"

  ask_user "CodeNook v{existing_version} detected. What would you like to do?"
    choices:
      "Upgrade (recommended)" → upgrade mode
      "Fresh install"         → rm -rf everything; proceed as new install
      "Cancel"                → abort

  IF upgrade mode:
    # ── Preserve runtime data ──
    PRESERVE = [
      ".claude/codenook/task-board.json",
      ".claude/codenook/task-board.json.bak",
      ".claude/codenook/config.json",
      ".claude/codenook/memory/*",
      ".claude/codenook/reviews/*",
      ".claude/codenook/docs/*",
      ".claude/codenook/skills/*",
    ]

    # ── Regenerate framework files ──
    REGENERATE = [
      ".claude/agents/*.agent.md",
      ".claude/codenook/hitl-adapters/*",
      # Re-append engine block to CLAUDE.md
    ]

    # ── Merge config.json ──
    # Keep existing: models, hitl.adapter, preferences.*
    # Update: version field → new version
    # Add: any new keys from seed template (with defaults)

    # Skip questions Q1-Q3 — preferences already in config.json
    Proceed to Step 4 (upgrade mode)
```

---

## Step 3 — Configuration Questions

Collect preferences via `ask_user` (3 prompts max):

### Q1 — Agent Models
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

### Q2 — HITL Adapter
> "HITL adapter?"
> Choices (context-dependent):

| Environment | Choices                                      |
|-------------|----------------------------------------------|
| Desktop     | `Local HTML ★` · `Terminal` · `GitHub Issue` |
| Headless    | `Terminal ★` · `GitHub Issue`                |
| +Confluence | Append `Confluence` to either list           |

★ = recommended default

### Q3 — Gitignore
> "Add agent system files to .gitignore?"
> Choices: `Yes ★` · `No`

Items to append (relative to project root):
- `.claude/agents/` — agent profile files
- `.claude/codenook/` — entire runtime directory

The entire agent system is treated as a dev tool — not committed to project source.

---

## Step 4 — Directory & File Generation

> **Upgrade mode:** Skip creating directories and seed files that already exist.
> Only regenerate agent profiles, HITL scripts, and engine instructions.
> Runtime data (task-board.json, memory/, config.json) is preserved.

Create the full tree under `.claude/`:

```
.claude/
├── agents/
│   ├── acceptor.agent.md      ← from template
│   ├── designer.agent.md
│   ├── implementer.agent.md
│   ├── reviewer.agent.md
│   └── tester.agent.md
└── codenook/
    ├── docs/                  ← document artifacts per task (created per-task)
    ├── memory/                ← empty directory (with .gitkeep)
    ├── reviews/               ← empty directory (with .gitkeep), HITL history files
    ├── skills/                ← project-level skills injected into sub-agent prompts (with .gitkeep)
    ├── task-board.json        ← seed content below
    ├── config.json            ← seed content below
    └── hitl-adapters/         ← copied from skill's hitl-adapters/ directory
        ├── terminal.sh
        ├── local-html.sh
        ├── github-issue.sh
        ├── confluence.sh
        ├── hitl-server.py
        └── hitl-verify.sh
```

Also append engine content to project-root `CLAUDE.md`.

**docs/ directory structure** — created per-task during orchestration:
```
.claude/codenook/docs/
└── T-001/
    ├── requirement-doc.md         ← Acceptor (requirements)
    ├── design-doc.md              ← Designer
    ├── implementation-doc.md      ← Implementer (plan)
    ├── dfmea-doc.md               ← Implementer (execute)
    ├── review-prep.md             ← Reviewer (plan)
    ├── review-report.md           ← Reviewer (execute)
    ├── test-plan.md               ← Tester (plan)
    ├── test-report.md             ← Tester (execute)
    ├── acceptance-plan.md         ← Acceptor (accept-plan)
    └── acceptance-report.md       ← Acceptor (accept-exec)
```

### Agent Profile Templates

Read templates from the `templates/` subdirectory relative to this SKILL.md file.
The path is typically `~/.claude/skills/codenook-init/templates/`.

For each template:
1. Read the file content
2. Write to `.claude/agents/<role>.agent.md`

Models are NOT embedded in agent profiles. They are configured in `config.json` → `models` map and resolved by the orchestrator at spawn time.

### HITL Adapter Scripts

Copy all files from the `hitl-adapters/` subdirectory relative to this SKILL.md file
to `.claude/codenook/hitl-adapters/`. Ensure all `.sh` files are executable (chmod +x).

### Instructions File (Orchestration Engine)

Read `templates/codenook.instructions.md` and replace `${ROOT}` with `.claude`,
then append the content to project-root `CLAUDE.md`.

If `CLAUDE.md` already exists, append the engine content after a `\n---\n\n` separator.
If `CLAUDE.md` already contains a CodeNook engine block (identified by `# CodeNook Orchestration Engine`
header), replace that block instead of appending a duplicate.

This instructions file contains the **full orchestration engine**: routing table, HITL enforcement,
memory management, task commands. It is automatically loaded as part of every session context.

### Seed: `task-board.json`

> **Upgrade mode:** SKIP — preserve existing task history.

```json
{
  "version": "4.2",
  "tasks": []
}
```

### Seed: `config.json`

> **Upgrade mode:** MERGE — read existing config, update `version` field,
> add any new keys from template with defaults, preserve all user settings.

```json
{
  "version": "4.2",
  "platform": "claude-code",
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
  "skills": {
    "auto_load": true,
    "agent_mapping": {}
  },
  "preferences": {
    "autoGitignore": true
  }
}
```

**Skills configuration:**
- `skills.auto_load` (default `true`): When enabled, the orchestrator scans `${ROOT}/codenook/skills/`
  for SKILL.md files and injects their content into sub-agent prompts.
- `skills.agent_mapping` (default `{}`): Optional per-agent skill assignment. When empty, ALL skills
  are loaded for ALL agents. When configured, only listed skills are loaded per role:
  ```json
  "agent_mapping": {
    "designer": ["uml", "architecture", "cloud"],
    "implementer": ["uml", "graphviz"],
    "reviewer": [],
    "tester": [],
    "acceptor": []
  }
  ```
  An empty array `[]` means no project skills for that agent. Omitted roles get all skills.

---

## Step 5 — Post-Init Verification

After all files are written:

1. **Enumerate** every expected file path (agents, hitl-adapters, seeds, CLAUDE.md)
2. **Assert** each exists and has size > 0
3. **Print summary** to the user:

```
✅ Agent system initialized!                    # or "✅ Agent system upgraded!" in upgrade mode

Platform:  Claude Code
Directory: .claude/
Agents:    5 (acceptor, designer, implementer, reviewer, tester)
HITL:      local-html (port 8765) — 10 gates per task cycle
Engine:    CLAUDE.md (appended, auto-loaded by Claude Code)
Workflow:  Document-driven (plan → approve → execute → report → approve)
Models:
  acceptor:    claude-haiku-4.5
  designer:    claude-sonnet-4
  implementer: claude-sonnet-4
  reviewer:    claude-sonnet-4
  tester:      claude-haiku-4.5

# Upgrade mode only:
Preserved: task-board.json (N tasks), memory/ (M snapshots), docs/ (D documents), skills/ (S skills), config.json
Updated:   5 agent profiles, 6 HITL scripts, engine in CLAUDE.md

Next steps:
  1. Say "create task <title>" to create your first task
  2. Say "run task T-001" to start orchestration
  3. Documents are saved to codenook/docs/T-NNN/ for traceability
  4. Each phase produces a document → HITL approval → next phase
```

If any file is missing or empty, report the failure and offer to retry.

---

## Uninstall — Remove Agent System from Project

> Trigger: "remove agent system" | "uninstall agents" | "clean codenook"

1. Confirm with user: "Remove agent system from this project? This deletes .claude/agents/, .claude/codenook/, and the engine block from CLAUDE.md."
2. If confirmed:
   - `rm -rf .claude/agents/`
   - `rm -rf .claude/codenook/`
   - Remove the CodeNook engine block from `CLAUDE.md` (identified by `# CodeNook Orchestration Engine` header)
   - Remove agent-related entries from `.gitignore` (if added by init)
3. Print: "✅ Agent system removed from project."

This only removes project-level files. The global `codenook-init` skill (`~/.claude/skills/`) is managed by `install.sh --uninstall`.

