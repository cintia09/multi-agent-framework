---
name: agent-init
description: "Initialize the multi-agent development framework in a project. Detects platform, generates agent profiles, creates task board and config."
---

# Agent System Initialization (v4.0)

> Trigger: "initialize agent system" | "agent init" | "agent-init"

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

| Platform     | Root Dir   | Agents Dir             | Instructions Target                                    |
|--------------|------------|------------------------|--------------------------------------------------------|
| copilot-cli  | `.github/` | `.github/agents/`      | `.github/instructions/agent-framework.instructions.md` |
| claude-code  | `.claude/` | `.claude/agents/`      | Append to project-root `CLAUDE.md`                     |

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
> "Add runtime files to .gitignore?"
> Choices: `Yes ★` · `No`

Items to append (relative to platform root, e.g. `.github/` or `.claude/`):
- `memory/` — phase snapshots
- `task-board.json` — runtime state
- `task-board.json.bak` — backup

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
├── memory/                    ← empty directory (with .gitkeep)
├── task-board.json            ← seed content below
└── config.json                ← seed content below
```

Plus platform-specific instructions file (see Step 1 table).

### Agent Profile Templates

Read templates from the `templates/` subdirectory relative to this SKILL.md file.
The path is typically `~/.copilot/skills/agent-init/templates/` or `~/.claude/skills/agent-init/templates/`.

For each template:
1. Read the file content
2. Replace `${MODEL}` with the user's model choice for that agent
3. Write to `<root>/agents/<role>.agent.md`

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

### Instructions File Content

The framework instructions file (Copilot) or CLAUDE.md append block contains:

```markdown
## Multi-Agent Framework v4.0

This project uses the multi-agent development framework.

### Orchestration Rules
1. All development tasks flow through the task board (task-board.json)
2. Each phase is handled by a specialized subagent (designer → implementer → reviewer → tester → acceptor)
3. HITL gates pause between every phase for human approval
4. Use the `agent-orchestrator` skill for task management

### Quick Commands
- "Create task <title>" — add a new task
- "Show task board" — view all tasks
- "Run task T-XXX" — start orchestration for a task
- "Agent status" — show current state
```

---

## Step 5 — Post-Init Verification

After all files are written:

1. **Enumerate** every expected file path
2. **Assert** each exists and has size > 0
3. **Print summary** to the user:

```
✅ Agent system initialized!

Platform:  Copilot CLI
Directory: .github/
Agents:    5 (acceptor, designer, implementer, reviewer, tester)
HITL:      local-html (port 8765)
Models:
  acceptor:    claude-haiku-4.5
  designer:    claude-sonnet-4
  implementer: claude-sonnet-4
  reviewer:    claude-sonnet-4
  tester:      claude-haiku-4.5

Next steps:
  1. Tell me your requirements to create a task
  2. Or say "create task <title>" to start manually
```

If any file is missing or empty, report the failure and offer to retry.
