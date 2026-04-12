# The Essence of Vibe Coding: Natural Language Is the New Programming Language, but Software Engineering Isn't Going Away

## From Compilers to Agents: The Unchanged Essence

Vibe Coding is essentially natural language programming.

In traditional programming, we use specialized languages — Java, C++, Python — to describe functionality, then compilers translate it into executable code.

Vibe Coding does the same thing: describe functionality in natural language, and an AI Agent translates it into executable code.

**What hasn't changed**: Whether you use natural language or Java, they're just tools for describing "what I need built."

**What has changed**: Because Agents are smart enough, natural language descriptions don't need the precision of traditional languages, and you don't need to learn arcane programming concepts. This dramatically lowers the barrier to programming.

But here's my point — **the essence of software engineering hasn't changed**. If you want to build a quality application, you still need requirements analysis, architecture design, code review, and testing.

## Why This Matters: A Painful Vibe Coding Experience

This conclusion isn't theoretical — it comes from real, painful Vibe Coding experience.

A typical session looks like this:

```
Me: "Implement user login"
Agent: (codes away, done)
Me: (manual testing)...nope, blank page after login
Me: "Blank page after login, fix it"
Agent: (codes away again)
Me: (manual testing)...login works now, but registration is broken
Me: "Why is registration broken?"
Agent: (codes away yet again)
Me: (manual testing)...
...repeat N times...
```

You're stuck at your computer, endlessly chatting with the Agent, typing, manually testing, reworking. Frankly, **it's painful**.

The problem isn't that the Agent isn't smart enough — the process lacks **structure**:
- No one thinks through requirements and design before coding
- No automated tests — everything verified manually
- No code review — bugs keep piling up
- No structured issue tracking — fix one, another appears

![Traditional Vibe Coding vs Multi-Agent Framework](images/comparison.png)

Aren't these exactly the problems traditional software engineering already solved?

## My Experiment: Agent-Driven Full SDLC

So I built a project: **Multi-Agent Software Development Framework**.

Core idea — if Vibe Coding is "natural language programming," then the entire software development lifecycle should be definable and executable in natural language too.

I defined 5 AI Agent roles using Markdown documents and Skills. Each role corresponds to a real responsibility in software development, and the entire system is Agent-driven.

![Multi-Agent Framework Architecture](images/architecture.png)

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│   🎯 Acceptor          🏗️ Designer         💻 Implementer   │
│   (Product Manager)    (Architect)         (Developer)      │
│                                                             │
│   🔍 Reviewer          🧪 Tester                            │
│   (Code Review)        (QA)                                 │
│                                                             │
│   ┌─────────────────────────────────────────────────────┐   │
│   │                Infrastructure Layer                  │   │
│   │                                                     │   │
│   │  📋 Task Board      🔄 State Machine  📨 Messaging   │   │
│   │  task-board.json     FSM Engine       inbox.json     │   │
│   │                                                     │   │
│   │  🔒 Hook Boundaries 📊 Audit Log     🐛 Issue Track  │   │
│   │  pre-tool-use       events.db        issues.json     │   │
│   │                                                     │   │
│   │  📡 Auto-dispatch   ⏰ Staleness     🔄 Batch Engine │   │
│   │  auto-dispatch      detection        batch processor │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                             │
│   Built entirely with Markdown + JSON + Shell, zero deps    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## A Complete Workflow

Take "add user login" as an example — compare traditional Vibe Coding with the framework approach:

### Traditional Vibe Coding (Painful)

```
You: "Implement login" → Agent codes → you test manually → broken → you type feedback
→ Agent fixes → you test again → still broken → more feedback → ... repeat N times
→ you give up and ship a half-baked product
```

### Using Multi-Agent Framework (Structured)

```
                    User
                     │
              "创建一个登录任务"
                     │
                     ▼
     🎯 Acceptor ── Create task ──→ 📋 T-001: User Login
     (Define requirements & criteria)    │
                           自动通知 ▼
     🏗️ Designer ◄── 📥 Received    Designing
     │                          │
     ├── Output: API design doc        │
     ├── Output: DB schema design      │
     ├── Output: Test specifications   │
     │                        Auto-notify ▼
     │                             Implementing
     💻 Implementer ◄── �� Received  │
     │                          │
     ├── Read design docs            │
     ├── TDD: write tests → write code │
     ├── Complete goals one by one ✅  │
     │                        Auto-notify ▼
     │                             Reviewing
     🔍 Reviewer ◄── 📥 Received    │
     │                          │
     ├── Review code quality          │
     ├── Check security vulnerabilities │
     ├── Review passed ✅             │
     │                        Auto-notify ▼
     │                             Testing
     🧪 Tester ◄── 📥 Received      │
     │                          │
     ├── Run automated tests          │
     │                          │
     ├── Bugs found?                  │
     │   └── YES: Create issues.json
     │       ┌───────────────────────────────┐
     │       │  🔄 Fully automated fix-verify loop │
     │       │                               │
     │       │  🧪 Tester: reports 3 bugs         │
     │       │       ↓                       │
     │       │  💻 Implementer: auto-fix          │
     │       │       ↓                       │
     │       │  🧪 Tester: auto-verify            │
     │       │       ↓                       │
     │       │  (if failures remain, loop again) ↻│
     │       │                               │
     │       │  Until all bugs fixed & verified ✅ │
     │       └───────────────────────────────┘
     │                          │
     ├── All passed ✅               │
     │                        Auto-notify ▼
     │                             Accepting
     🎯 Acceptor ◄── 📥 Received    │
     │                          │
     ├── Verify goals one by one      │
     └── Accepted ✅ ──────→ 🎉 T-001: accepted!
```

**You only do two things: create the task + final acceptance.** Design, implementation, review, testing, and bug fixes are all handled automatically by Agents.

## Benefits

### 1. No More Manual Testing Loops

The biggest pain point of traditional Vibe Coding — manual testing and endless rework — is replaced by the Tester Agent. It automatically runs tests, reports bugs, and verifies fixes. **You don't need to sit at your computer watching anymore.**

### 2. Quality Is Process-Driven, Not Luck

With the Designer doing upfront design, the Reviewer doing code review, and the Tester running automated tests, code quality no longer depends on "whether the Agent is having a good day" — it's **guaranteed by process**.

### 3. Structured Bug Tracking

Every bug has a structured JSON record (severity, reproduction steps, fix description, verification result) — no more scrolling through chat history asking "was that issue fixed?"

### 4. Enforceable Process Boundaries

An Agent saying "I promise to only do this" isn't enough. The framework uses Shell Hooks to **enforce** rules — the Tester can't modify code, the Implementer can't skip review — these are code-level constraints, not AI "self-discipline."

### 5. Resumable at Any Point

All state lives in files (JSON + SQLite), not in AI memory. Even if the CLI crashes, the machine restarts, or you switch sessions, Agents can resume from where they left off.

## How to Use

### Install (30 Seconds)

In Claude Code / GitHub Copilot, say:

> "Follow the instructions in the cintia09/multi-agent-framework repo to install agents locally."

The AI assistant auto-installs 14 Skills, 5 Agents, and 13 Hooks.

### Start in Any Project

```bash
# 1. Initialize — AI auto-analyzes your tech stack and generates custom config
"Initialize Agent system"

# 2. Create a task
/agent acceptor
"Create task: add user login feature"

# 3. Let each role handle it automatically
/agent designer
"Process task"                  # Auto-generates design docs + test specs

/agent implementer
"Process task"                  # Auto TDD implementation

/agent reviewer
"Process task"                  # Auto code review

/agent tester
"Process task"                  # Auto testing
"Monitor implementer fixes"      # Fully automated fix-verify loop

/agent acceptor
"Process task"                  # Final acceptance
```

Each step takes just one sentence — Agents handle everything automatically.

## Conclusion

Vibe Coding has lowered the barrier to programming to unprecedented levels. But **writing code is just one part of software engineering**.

Those "seemingly tedious" steps in traditional software engineering — requirements analysis, design review, code review, testing — exist not to torment developers, but because **good software simply requires them**.

AI hasn't changed this fact, but AI can change *who* does these things.

Before: humans design, humans code, humans test. Now: Agents design, Agents code, Agents test. Humans only need to define "what to build" and verify "how well it was built."

This may be the ultimate form of Vibe Coding — not one person endlessly going back and forth with one Agent, but an **Agent team** where each member has a clear role, collaborating like a real software development team.

And the interesting part? This framework itself was built by Agents.

---

> 🔗 项目地址: [github.com/cintia09/multi-agent-framework](https://github.com/cintia09/multi-agent-framework)
> 
> Zero dependencies, pure Markdown + JSON, works out of the box.
