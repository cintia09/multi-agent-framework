---
name: codenook-init
description: "Initialize the multi-agent development framework in a project. Generates agent profiles, creates task board and config for Claude Code and Copilot CLI."
---

# Agent System Initialization (v4.9.2)

> Trigger: "initialize agent system" | "agent init" | "codenook-init"

Platform: **Claude Code** or **Copilot CLI** — project files are generated under `.claude/`.
Global skills are loaded from `~/.claude/skills/` (Claude Code) or `~/.copilot/skills/` (Copilot CLI).
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

    # ── Merge config.json (DEEP MERGE) ──
    # Strategy: deep-merge at each level, never overwrite user values.
    # 1. Preserve all existing keys and their values
    # 2. Add new keys from seed template (with defaults) at the correct nesting level
    # 3. Update: version field → new version
    #
    # Example: if old config has models: { acceptor: "X" } and new seed adds
    # models.phase_overrides, result is models: { acceptor: "X", phase_overrides: {} }

    # Skip questions Q1-Q3 — preferences already in config.json
    # Q4 (Skill Provisioning) — run ONLY if config.skills key is entirely missing
    #   (i.e., upgrading from pre-v4.4 that didn't have skill provisioning)
    #   If config.skills exists (even with auto_load=false) → preserve it, skip Q4
    Proceed to Step 4 (upgrade mode)
```

---

## Step 3 — Configuration Questions

Collect preferences via `ask_user`:

### Q1 — Agent Models
> "Configure models for agents?"
> Choices: `Use defaults ★` · `Custom per-agent` · `Custom per-phase (advanced)`

Default model map:

| Agent        | Default Model       |
|--------------|---------------------|
| acceptor     | claude-opus-4.6     |
| designer     | claude-opus-4.6     |
| implementer  | claude-opus-4.6     |
| reviewer     | gpt-5.4             |
| tester       | claude-opus-4.6     |

If **Custom per-agent**: loop through 5 agents, ask model for each.
Config result: `"models": { "acceptor": "...", "designer": "...", ... }`

If **Custom per-phase**: present the 10-phase table and ask model for each.
This allows different models for plan vs. execute phases (e.g., cheaper model for
planning, premium for execution). Config result:
```json
"models": {
  "acceptor": "claude-opus-4.6",
  "designer": "claude-opus-4.6",
  "implementer": "claude-opus-4.6",
  "reviewer": "gpt-5.4",
  "tester": "claude-opus-4.6",
  "phase_overrides": {
    "requirements":   "claude-opus-4.6",
    "design":         "claude-opus-4.6",
    "impl_plan":      "claude-opus-4.6",
    "impl_execute":   "claude-opus-4.6",
    "review_plan":    "gpt-5.4",
    "review_execute": "gpt-5.4",
    "test_plan":      "claude-opus-4.6",
    "test_execute":   "claude-opus-4.6",
    "accept_plan":    "claude-opus-4.6",
    "accept_execute": "claude-opus-4.6"
  }
}
```
Phase-level model takes priority over agent-level. Agent-level is the fallback.

Recommended per-phase defaults (if user wants guidance):

| Phase | Recommended Model | Rationale |
|-------|------------------|-----------|
| requirements | claude-opus-4.6 | Needs deep language understanding for ambiguity detection |
| design | claude-opus-4.6 | Architecture requires deep reasoning |
| impl_plan | claude-opus-4.6 | Implementation planning benefits from thorough analysis |
| impl_execute | claude-opus-4.6 | Code generation needs quality |
| review_plan | gpt-5.4 | Review planning benefits from diverse perspective |
| review_execute | gpt-5.4 | Code review benefits from diverse perspective |
| test_plan | claude-opus-4.6 | Test design needs thorough edge-case analysis |
| test_execute | claude-opus-4.6 | Test generation needs quality |
| accept_plan | claude-opus-4.6 | Acceptance criteria need deep requirements tracing |
| accept_execute | claude-opus-4.6 | Final verification needs thoroughness |

### Q2 — HITL Adapter
> "HITL adapter?"
> Choices (context-dependent):

| Environment | Choices                                      |
|-------------|----------------------------------------------|
| Desktop     | `Local HTML ★` · `Terminal` · `GitHub Issue` |
| Headless    | `Terminal ★` · `GitHub Issue`                |
| +Confluence | Append `Confluence` to either list           |

★ = recommended default

After initial selection, ask:
> "Same adapter for all phases, or customize per-phase?"
> Choices: `Same for all ★` · `Custom per-phase`

If **Custom per-phase**: for each of the 10 phases, ask which adapter to use.
This enables scenarios like:
- `terminal` for lightweight plan phases (fast inline approval)
- `local-html` for execute phases (richer document review)
- `confluence` for design and acceptance phases (team-wide visibility)
- `github-issue` for review phases (code review integration)

Config result for per-phase HITL:
```json
"hitl": {
  "enabled": true,
  "adapter": "local-html",
  "port": 8765,
  "auto_open_browser": true,
  "phase_overrides": {
    "requirements":   "confluence",
    "design":         "confluence",
    "impl_plan":      "terminal",
    "impl_execute":   "local-html",
    "review_plan":    "terminal",
    "review_execute": "github-issue",
    "test_plan":      "terminal",
    "test_execute":   "local-html",
    "accept_plan":    "terminal",
    "accept_execute": "confluence"
  }
}
```
Phase-level adapter takes priority over the global `adapter` field. Global is the fallback.

### Q3 — Gitignore
> "Add agent system files to .gitignore?"
> Choices: `Yes ★` · `No`

**Config result:** `config.preferences.autoGitignore = true/false`

Items to append (relative to project root):
- `.claude/agents/` — agent profile files
- `.claude/codenook/` — entire runtime directory

The entire agent system is treated as a dev tool — not committed to project source.

### Q4 — Project Skill Provisioning

> "Auto-provision skills for sub-agents?"
> Choices: `Yes, scan and assign ★` · `Skip (no project skills)`

If user selects **"Yes, scan and assign"**:

1. **Discover global skills** — scan the platform's global skill directories:
   - `~/.copilot/skills/` (Copilot CLI)
   - `~/.claude/skills/` (Claude Code)
   - Collect each skill's `name` and `description` from SKILL.md YAML frontmatter.
   - **If neither directory exists or both are empty:** inform the user "No global skills found.
     Skipping skill provisioning." and set `skills.auto_load = true`, `agent_mapping = {}`.
   - **If a skill's SKILL.md has no parseable frontmatter:** skip that skill with a warning.
   - **Exclude** framework/meta skills by heuristic:
     - Skills whose name contains `codenook` (framework itself)
     - Skills whose description indicates meta/configuration purpose (e.g., "instructions",
       "default reply", "language setting", "workspace layout", "export skills", "save skills")
     - Skills with no `description` field and a generic/config-like name

2. **Classify skills by relevance** — read each skill's `SKILL.md` description and use LLM
   judgment to categorize into one of these functional categories:
   - `diagram` — visualization/diagramming (keywords: diagram, chart, graph, architecture,
     UML, flowchart, infographic, canvas, visualization, SVG, draw)
   - `workflow` — development workflow (keywords: code-review, CI/CD, deploy, git,
     confluence, jira, jenkins, gerrit, build, pipeline)
   - `content` — content creation/transformation (keywords: translate, format, markdown,
     convert, article, url-to-markdown, illustrate)
   - `domain` — project-specific domain knowledge (keywords: domain-specific terms,
     product names, internal tools, custom integrations)
   - `media` — image/media generation (keywords: image, cover, compress, comic, slide,
     photo, video, generate image)
   - `social` — social media posting (keywords: post, publish, share, weibo, wechat,
     twitter, xiaohongshu)

   **Classification approach:** Do NOT hardcode skill names to categories. Instead:
   - Parse the `name` and `description` fields from each skill's SKILL.md frontmatter
   - Match against the category keywords above
   - If a skill matches multiple categories, assign to the most specific one
   - If no category matches, classify as `domain` (catch-all)

3. **Map skills to agents** — apply these default assignment rules:

   | Agent | Auto-assigned categories | Rationale |
   |-------|------------------------|-----------|
   | **designer** | `diagram`, `domain` | Architects need visualization and domain knowledge |
   | **implementer** | `diagram` (subset: UML/code-related), `workflow`, `domain` | Developers need UML for code design, workflow for CI/CD, domain for context |
   | **reviewer** | `workflow` (subset: review/audit tools), `domain` | Reviewers need code review tools and domain knowledge |
   | **tester** | `domain` | Testers need domain knowledge for test case design |
   | **acceptor** | `diagram` (subset: infographic/summary), `content`, `domain` | POs need visual summaries and content tools for requirements |

   > **Note:** Skills classified as `media` or `social` are not auto-assigned to any agent.
   > They are copied to the project `skills/` directory but require manual assignment
   > via `config.json → skills.agent_mapping` if needed.

4. **Present mapping for confirmation** — show the user the proposed assignment:
   ```
   Proposed skill assignments (based on SKILL.md descriptions):
     designer:     [diagram skills], [domain skills]
     implementer:  [diagram subset], [workflow skills], [domain skills]
     reviewer:     [workflow subset], [domain skills]
     tester:       [domain skills]
     acceptor:     [diagram subset], [content skills], [domain skills]

   Total: N unique skills to copy to project
   ```
   > Choices: `Accept ★` · `Customize` · `Load all for all agents` · `Skip`

   If **Customize**: for each agent, ask which skills to include/exclude.
   If **Load all**: set `agent_mapping = {}` (empty = all skills for all agents).

5. **Copy skill files** — for each unique skill in the mapping:
   ```bash
   mkdir -p ${ROOT}/codenook/skills/<skill-name>
   # Copy only SKILL.md and lightweight reference files
   cp <source-skill-dir>/<skill-name>/SKILL.md ${ROOT}/codenook/skills/<skill-name>/
   # Optionally copy examples/ and references/ if they exist and are small (<100KB total)
   # Skip: node_modules/, __pycache__/, *.bin, .git/, caches, platform scripts
   ```
   Source directory: `~/.copilot/skills/` (Copilot CLI) or `~/.claude/skills/` (Claude Code) —
   use whichever platform was detected in Step 2 or scan both.

6. **Populate config.json** — write the `skills.agent_mapping` section:
   ```json
   "skills": {
     "auto_load": true,
     "agent_mapping": {
       "designer": ["<classified-diagram-skills>", "<classified-domain-skills>"],
       "implementer": ["<classified-diagram-subset>", "<classified-workflow-skills>", "<classified-domain-skills>"],
       "reviewer": ["<classified-review-tools>", "<classified-domain-skills>"],
       "tester": ["<classified-domain-skills>"],
       "acceptor": ["<classified-diagram-subset>", "<classified-content-skills>", "<classified-domain-skills>"]
     }
   }
   ```

> **Upgrade mode:** If `skills/` already has content, show existing skills vs. proposed changes.
> Offer to merge (add new skills, keep existing), replace, or skip.

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
    ├── knowledge/             ← cross-task knowledge base (auto-populated)
    │   ├── by-role/           ← per-agent accumulated knowledge
    │   │   ├── implementer.md
    │   │   ├── reviewer.md
    │   │   ├── designer.md
    │   │   ├── tester.md
    │   │   └── acceptor.md
    │   ├── by-topic/          ← knowledge indexed by topic
    │   │   ├── code-conventions.md
    │   │   ├── architecture-decisions.md
    │   │   ├── pitfalls.md
    │   │   ├── best-practices.md
    │   │   └── project-config.md
    │   └── index.md           ← master index of all knowledge items
    ├── reviews/               ← empty directory (with .gitkeep), HITL history files
    ├── skills/                ← populated by Q4 skill provisioning; sub-agent prompt injection (with .gitkeep)
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

**knowledge/ directory** — create all files during init (empty, with headers):
```bash
mkdir -p ${ROOT}/codenook/knowledge/by-role ${ROOT}/codenook/knowledge/by-topic
for role in acceptor designer implementer reviewer tester; do
  touch ${ROOT}/codenook/knowledge/by-role/${role}.md
done
for topic in code-conventions architecture-decisions pitfalls best-practices project-config; do
  touch ${ROOT}/codenook/knowledge/by-topic/${topic}.md
done
touch ${ROOT}/codenook/knowledge/index.md
```

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
The path depends on the platform:
- Copilot CLI: `~/.copilot/skills/codenook-init/templates/`
- Claude Code: `~/.claude/skills/codenook-init/templates/`

For each template:
1. Read the file content
2. Write to `<project-root>/.claude/agents/<role>.agent.md`

> **Note:** Agent profiles are always written to `.claude/agents/` regardless of which
> platform the skill was loaded from. The `.claude/` directory is the project-level standard.

Models are NOT embedded in agent profiles. They are configured in `config.json` → `models` map and resolved by the orchestrator at spawn time.

### HITL Adapter Scripts

Copy all files from the `hitl-adapters/` subdirectory relative to this SKILL.md file
to `.claude/codenook/hitl-adapters/`. Ensure all `.sh` files are executable (chmod +x).

The source path depends on the platform:
- Copilot CLI: `~/.copilot/skills/codenook-init/hitl-adapters/`
- Claude Code: `~/.claude/skills/codenook-init/hitl-adapters/`

### Instructions File (Orchestration Engine)

Read `templates/codenook.instructions.md` (relative to this SKILL.md) and replace
`${ROOT}` with `.claude`, then append the content to project-root `CLAUDE.md`.

If `CLAUDE.md` already exists, append the engine content after a `\n---\n\n` separator.
If `CLAUDE.md` already contains a CodeNook engine block (identified by a line starting with
`# CodeNook Orchestration Engine`), replace that block instead of appending a duplicate.

This instructions file contains the **full orchestration engine**: routing table, HITL enforcement,
memory management, task commands. It is automatically loaded as part of every session context.

### .gitignore (if Q3 = Yes)

If `config.preferences.autoGitignore` is `true`, append these lines to the project's `.gitignore`
(create it if it doesn't exist; skip lines that already exist):

```
# CodeNook agent system (auto-generated)
.claude/agents/
.claude/codenook/
```

### Seed: `task-board.json`

> **Upgrade mode:** SKIP — preserve existing task history.

```json
{
  "version": "4.9.2",
  "active_task": null,
  "tasks": []
}
```

### Seed: `config.json`

> **Upgrade mode:** MERGE — read existing config, update `version` field,
> add any new keys from template with defaults, preserve all user settings.

```json
{
  "version": "4.9.2",
  "platform": "<claude-code|copilot-cli>",
  "models": {
    "acceptor":    "<model>",
    "designer":    "<model>",
    "implementer": "<model>",
    "reviewer":    "<model>",
    "tester":      "<model>",
    "phase_overrides": {}
  },
  "hitl": {
    "enabled": true,
    "adapter": "<local-html|terminal|github-issue|confluence>",
    "port": 8765,
    "auto_open_browser": true,
    "phase_overrides": {}
  },
  "skills": {
    "auto_load": true,
    "agent_mapping": {}
  },
  "dual_mode": {
    "enabled": false,
    "phases": ["all"],
    "models": {
      "agent_a": "claude-opus-4.6",
      "agent_b": "gpt-5.4",
      "synthesizer": null
    },
    "phase_models": {}
  },
  "phase_defaults": {},
  "knowledge": {
    "enabled": true,
    "auto_extract": true,
    "max_items_per_role": 100,
    "max_items_per_topic": 50,
    "max_chars": 8000,
    "confidence_threshold": "MEDIUM"
  },
  "preferences": {
    "autoGitignore": true,
    "coding_conventions": null,
    "review_checklist": null,
    "phase_entry_decisions": {}
  },
  "reviewer_agent_type": "code-review"
}
```

**Model resolution order** (highest to lowest priority):
1. `task.model_override` — per-task override set at runtime
2. `config.models.phase_overrides[phase_name]` — per-phase model from Q1
3. `config.models[role]` — per-agent model from Q1
4. Platform default (no model parameter → platform picks)

**HITL adapter resolution order**:
1. `config.hitl.phase_overrides[phase_name]` — per-phase adapter from Q2
2. `config.hitl.adapter` — global adapter from Q2
3. Auto-detect from environment ($SSH_TTY, $DISPLAY, etc.)

**Skills configuration:**
- `skills.auto_load` (default `true`): When enabled, the orchestrator scans `${ROOT}/codenook/skills/`
  for SKILL.md files and injects their content into sub-agent prompts.
- `skills.agent_mapping` (default `{}`): Per-agent skill assignment. **Populated automatically by
  Q4 (Skill Provisioning)** during init. Semantics:
  - `{}` (empty object) = ALL project skills loaded for ALL agents (default)
  - Configured with agent keys = only listed skills per role
  - Empty array `[]` for a role = NO project skills for that agent
  - Omitted role = gets ALL project skills (same as not being in the map)
  ```json
  "agent_mapping": {
    "designer": ["<diagram-skill-A>", "<domain-skill-B>"],
    "implementer": ["<diagram-skill-A>", "<workflow-skill-C>"],
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

Platform:  <detected platform>
Directory: .claude/
Agents:    5 (acceptor, designer, implementer, reviewer, tester)
HITL:      local-html (port 8765) — 10 gates per task cycle
Engine:    CLAUDE.md (appended, auto-loaded by session)
Workflow:  Document-driven (plan → approve → execute → report → approve)
Skills:    N skills provisioned → {designer: [...], implementer: [...], ...}
Models:
  acceptor:    claude-opus-4.6
  designer:    claude-opus-4.6
  implementer: claude-opus-4.6
  reviewer:    gpt-5.4
  tester:      claude-opus-4.6

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
   - Remove the CodeNook engine block from `CLAUDE.md` (identified by a line starting with `# CodeNook Orchestration Engine`)
   - Remove agent-related entries from `.gitignore` (if added by init)
3. Print: "✅ Agent system removed from project."

This only removes project-level files. The global `codenook-init` skill (`~/.claude/skills/` or `~/.copilot/skills/`) is managed by `install.sh --uninstall`.

