---
name: codenook-init
description: "Initialize the multi-agent development framework in a project. Detects platform, generates agent profiles, creates task board and config."
---

# Agent System Initialization (v4.1)

> Trigger: "initialize agent system" | "agent init" | "codenook-init"

## Step 1 — Platform Detection & Directory Confirmation

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

### Directory Confirmation (MANDATORY)

After platform detection, **always** ask the user to confirm the installation directory:

```
ask_user "Install CodeNook agent system to: <project_root>/<detected_root>/"
  choices:
    "<detected_root>/ (Recommended)" → proceed with detected
    "Custom path"                    → ask for custom root path
    "Cancel"                         → abort
```

This confirmation is mandatory even if the platform was auto-detected.
Show the full resolved path (e.g., `/Users/dev/my-project/.github/`).

---

## Step 2 — Idempotency Check & Upgrade

Before creating anything, check if the system already exists:

```
IF <root>/codenook/config.json exists:
  # Existing installation detected
  existing_version = config.json → "version"

  ask_user "CodeNook v{existing_version} detected. What would you like to do?"
    choices:
      "Upgrade (recommended)" → upgrade mode
      "Fresh install"         → rm -rf everything; proceed as new install
      "Cancel"                → abort

  IF upgrade mode:
    # ── Preserve runtime data ──
    # These files contain task history and context — NEVER overwrite:
    PRESERVE = [
      "<root>/codenook/task-board.json",       # task history
      "<root>/codenook/task-board.json.bak",   # backup
      "<root>/codenook/config.json",           # user preferences (models, HITL, etc.)
      "<root>/codenook/memory/*",              # all memory snapshots
      "<root>/codenook/reviews/*",             # HITL review history
      "<root>/codenook/docs/*",                # all document artifacts per task
    ]

    # ── Regenerate framework files ──
    # These are "code" that ships with the framework — always update:
    REGENERATE = [
      "<root>/agents/*.agent.md",              # agent profiles (with current templates)
      "<root>/codenook/hitl-adapters/*",        # HITL scripts
      "<root>/instructions/codenook.instructions.md",  # engine (Copilot CLI)
      # For Claude Code: re-append engine block to CLAUDE.md
    ]

    # ── Merge config.json ──
    # Read existing config, merge with latest defaults:
    # - Keep existing: models, hitl.adapter, preferences.*
    # - Update: version field → new version
    # - Add: any new keys from seed template (with defaults)
    # This ensures new features are available without losing settings.
    # Note: model choices live in config.json only — agent profiles do not embed models.

    # ── Skip questions Q1-Q4 ──
    # All preferences already exist in config.json. Skip interactive prompts.
    # Proceed directly to Step 4 (file generation) in upgrade mode.

    Proceed to Step 4 (upgrade mode)
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
- `<root>/agents/` — agent profile files
- `<root>/codenook/` — entire runtime directory (memory, reviews, task-board, config, hitl-adapters)
- `<root>/instructions/` — orchestration engine (Copilot CLI only; skip for Claude Code)

Where `<root>` is `.github/` or `.claude/` depending on platform.
The entire agent system is treated as a dev tool — not committed to project source.

---

## Step 4 — Directory & File Generation

> **Upgrade mode:** Skip creating directories and seed files that already exist.
> Only regenerate agent profiles, HITL scripts, and engine instructions.
> Runtime data (task-board.json, memory/, config.json) is preserved.

Create the full tree under `<root>`:

```
<root>/
├── agents/
│   ├── acceptor.agent.md      ← from template
│   ├── designer.agent.md
│   ├── implementer.agent.md
│   ├── reviewer.agent.md
│   └── tester.agent.md
├── codenook/
│   ├── docs/                  ← document artifacts per task (created per-task)
│   ├── memory/                ← empty directory (with .gitkeep)
│   ├── reviews/               ← empty directory (with .gitkeep), HITL history files
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

**docs/ directory structure** — created per-task during orchestration:
```
<root>/codenook/docs/
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

For Claude Code: append engine content to project-root `CLAUDE.md` instead of instructions/.

### Agent Profile Templates

Read templates from the `templates/` subdirectory relative to this SKILL.md file.
The path is typically `~/.copilot/skills/codenook-init/templates/` or `~/.claude/skills/codenook-init/templates/`.

For each template:
1. Read the file content
2. Write to `<root>/agents/<role>.agent.md`

Models are NOT embedded in agent profiles. They are configured in `config.json` → `models` map and resolved by the orchestrator at spawn time.

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

> **Upgrade mode:** SKIP — preserve existing task history.

```json
{
  "version": "4.1",
  "tasks": []
}
```

### Seed: `config.json`

> **Upgrade mode:** MERGE — read existing config, update `version` field,
> add any new keys from template with defaults, preserve all user settings.

```json
{
  "version": "4.1",
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
✅ Agent system initialized!                    # or "✅ Agent system upgraded!" in upgrade mode

Platform:  Copilot CLI
Directory: .github/
Agents:    5 (acceptor, designer, implementer, reviewer, tester)
HITL:      local-html (port 8765) — 10 gates per task cycle
Engine:    .github/instructions/codenook.instructions.md (auto-loaded)
Workflow:  Document-driven (plan → approve → execute → report → approve)
Models:
  acceptor:    claude-haiku-4.5
  designer:    claude-sonnet-4
  implementer: claude-sonnet-4
  reviewer:    claude-sonnet-4
  tester:      claude-haiku-4.5

# Upgrade mode only:
Preserved: task-board.json (N tasks), memory/ (M snapshots), docs/ (D documents), config.json
Updated:   5 agent profiles, 6 HITL scripts, engine instructions

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

1. Detect platform root (`.github/` or `.claude/`)
2. Confirm with user: "Remove agent system from this project? This deletes agents/, codenook/, and instructions."
3. If confirmed:
   - `rm -rf <root>/agents/`
   - `rm -rf <root>/codenook/`
   - Remove `<root>/instructions/codenook.instructions.md` (Copilot) or the framework block from `CLAUDE.md` (Claude Code)
   - Remove agent-related entries from `.gitignore` (if added by init)
4. Print: "✅ Agent system removed from project."

This only removes project-level files. The global `codenook-init` skill (`~/.copilot/skills/`, `~/.claude/skills/`) is managed by `install.sh --uninstall`.
