# Skills Mechanism — Loading, Injection & Agent Behavior

## 1. Two-Level Loading

```mermaid
sequenceDiagram
    participant FS as 📂 File System
    participant Platform as Claude Code / Copilot CLI
    participant SP as System Prompt
    participant LLM as 🧠 LLM
    participant Msg as Messages Array

    Note over FS: 19 SKILL.md files<br/>~/.claude/skills/ or ~/.copilot/skills/

    FS->>Platform: Scan skills directory
    Platform->>Platform: Extract name + description (≤250 chars)

    rect rgb(255, 212, 59)
        Note over Platform,SP: Level 1: Summary list (~1% token)
        Platform->>SP: Inject skill name+description list
    end

    SP->>LLM: System Prompt (with summary list)
    LLM->>LLM: Determine which skill is needed based on user intent

    rect rgb(81, 207, 102)
        Note over LLM,Msg: Level 2: On-demand full text (5-15% token)
        LLM->>Platform: Call /skillname or auto-activate
        Platform->>FS: Read full SKILL.md
        FS-->>Platform: Full content + variable substitution
        Platform->>Msg: Inject full text into Messages array
    end

    Msg->>LLM: Next conversation turn includes skill full text
```

## 2. Skill Discovery Paths

```mermaid
flowchart TB
    subgraph CC["Claude Code"]
        CC1["~/.claude/skills/ (user-level)"]
        CC2[".claude/skills/ (project-level)"]
        CC3[".agents/skills/ (shared path)"]
    end

    subgraph CP["GitHub Copilot CLI"]
        CP1["~/.copilot/skills/ (user-level)"]
        CP2[".github/skills/ (project-level)"]
        CP3[".claude/skills/ (compat path)"]
        CP4[".agents/skills/ (shared path)"]
    end

    subgraph Agent["🤖 Current Agent"]
        A1["Skills Summary List<br/>(all 19)"]
    end

    CC1 & CC2 & CC3 --> A1
    CP1 & CP2 & CP3 & CP4 --> A1

    style CC fill:#845ef7,color:#fff
    style CP fill:#4dabf7,color:#fff
    style Agent fill:#51cf66,color:#fff
```

| Dimension | Claude Code | Copilot CLI |
|-----------|------------|-------------|
| User-level | `~/.claude/skills/` | `~/.copilot/skills/` |
| Project-level | `.claude/skills/` | `.github/skills/` |
| Shared path | `.agents/skills/` ✅ | `.agents/skills/` ✅ |
| Hot reload | ⚠️ Memoize cache, requires new session | `/skills reload` |
| Conditional activation | frontmatter `paths:` glob | Not supported (ignored) |

> **`paths:` Conditional Activation**: Adding `paths: ["hooks/**", "**/*.sh"]` to SKILL.md frontmatter limits that skill to auto-load into the summary list only when operating on matching files. Manual `/skillname` invocation is unaffected. Currently only `agent-hooks` uses this feature.

## 3. Per-Agent Skill Isolation

```mermaid
flowchart LR
    subgraph Shared["📚 Shared Skills (8)"]
        SK1["orchestrator"]
        SK2["fsm"]
        SK3["task-board"]
        SK4["messaging"]
        SK5["memory"]
        SK6["switch"]
        SK7["docs"]
        SK8["worktree"]
    end

    subgraph RoleSkills["🎯 Role-Specific Skills"]
        direction TB
        RS1["acceptor: config, init,<br/>acceptor, teams"]
        RS2["designer: designer,<br/>hypothesis"]
        RS3["implementer: implementer,<br/>events, hooks, hypothesis"]
        RS4["reviewer: reviewer"]
        RS5["tester: tester, events"]
    end

    subgraph Agents["👥 Agent Profiles"]
        A1["🎯 Acceptor<br/>skills: shared 8 + role 4 = 12"]
        A2["🏗️ Designer<br/>skills: shared 8 + role 2 = 10"]
        A3["💻 Implementer<br/>skills: shared 8 + role 4 = 12"]
        A4["🔍 Reviewer<br/>skills: shared 8 + role 1 = 9"]
        A5["🧪 Tester<br/>skills: shared 8 + role 2 = 10"]
    end

    Shared --> A1 & A2 & A3 & A4 & A5
    RS1 --> A1
    RS2 --> A2
    RS3 --> A3
    RS4 --> A4
    RS5 --> A5

    style Shared fill:#ffd43b,color:#333
    style RoleSkills fill:#ff922b,color:#fff
    style A1 fill:#ff6b6b,color:#fff
    style A2 fill:#845ef7,color:#fff
    style A3 fill:#51cf66,color:#fff
    style A4 fill:#4dabf7,color:#fff
    style A5 fill:#ff922b,color:#fff
```

> **Isolation Strength**: Prompt-based soft constraint (~95% LLM compliance). Isolation only applies between the 5 project-level agent roles; it does not affect skill usage in non-agent mode.

## 4. Three-Layer Behavior Control

```mermaid
flowchart TB
    subgraph Layer1["Layer 1: Agent Profile + Skill Constraints (Definition)"]
        direction LR
        P1["acceptor.agent.md<br/>skills: [shared 8 + role 4]<br/>Cannot write code"]
        P2["implementer.agent.md<br/>skills: [shared 8 + role 4]<br/>Can write code"]
    end

    subgraph Layer2["Layer 2: Pre-Tool-Use Hook (Enforcement)"]
        direction LR
        H1["Reviewer calls rm?"]
        H2{agent-pre-tool-use.sh}
        H3["⛔ Deny: Reviewer<br/>cannot run write commands"]
        H4["✅ Allow"]
    end

    subgraph Layer3["Layer 3: Auto-Dispatch (Routing)"]
        direction LR
        D1["State changes to testing"]
        D2{auto-dispatch.sh}
        D3["📨 Message → tester inbox<br/>'Please test T-042'"]
    end

    subgraph Analogy["🏢 Analogy"]
        direction TB
        AN1["Skills Summary = 📖 Table of Contents<br/>(visible to all)"]
        AN2["Skill Full Text = 📚 Manual<br/>(loaded on demand)"]
        AN3["Agent Profile = 📋 Job Description<br/>(includes skill permissions)"]
        AN4["Hook = 🔒 Access Control<br/>(runtime enforcement)"]
    end

    Layer1 -->|"LLM self-compliance<br/>(soft constraint)"| Layer2
    Layer2 -->|"Hook runtime enforcement<br/>(hard constraint)"| Layer3

    H1 --> H2
    H2 -->|"Violation"| H3
    H2 -->|"Compliant"| H4
    D1 --> D2 --> D3

    style Layer1 fill:#4a90d9,color:#fff
    style Layer2 fill:#ff6b6b,color:#fff
    style Layer3 fill:#51cf66,color:#fff
    style Analogy fill:#ffd43b,color:#333
```

## 5. Complete Request Lifecycle

```mermaid
sequenceDiagram
    participant U as 👤 User
    participant CC as Claude Code/Copilot
    participant LLM as 🧠 LLM

    Note over CC: 📂 Scan 19 Skills → Build summary list (~1% token)<br/>+ Agent Profile (with skills: constraints)

    U->>CC: "Change T-042 status to testing"

    CC->>LLM: System Prompt (summary list + Agent Profile)<br/>+ Conversation history<br/>+ User message

    Note over LLM: 🧠 LLM identifies from summary:<br/>1. agent-fsm → load full text on demand<br/>2. agent-task-board → load full text on demand<br/>3. Check skills: constraints → allow operation

    LLM-->>CC: Call Write tool to modify task-board.json

    Note over CC: 🪝 Pre-Hook: implementer can write files ✅
    Note over CC: 🔧 Execute: Write task-board.json
    Note over CC: 🪝 Post-Hook:<br/>1. FSM: implementing→testing ✅ valid<br/>2. Doc Gate: ⚠️/⛔ check docs<br/>3. Dispatch: 📨 message→tester<br/>4. Memory: 🧠 record state change

    CC-->>LLM: Tool result + Hook output

    LLM-->>U: "T-042 status changed to testing,<br/>tester has been notified"
```
