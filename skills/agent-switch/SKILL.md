---
name: agent-switch
description: "Agent role switching and status panel. Trigger patterns: 'switch to acceptor/designer/implementer/reviewer/tester', '/agent <name>', 'act as acceptor', 'agent status'. Must trigger on ANY role-switch phrase."
---

# Agent Role Management

## ⛔ Intent Auto-Router — Read When No Active Role

> **When no active role exists** (`.agents/runtime/active-agent` missing or empty), detect user intent and **auto-switch to the matching role**:

| Intent Keywords | Routes To | Note |
|----------------|-----------|------|
| "new feature", "develop", "build", "新功能", "新需求" | 🎯 **acceptor** | New features start with acceptor |
| "design", "architecture", "设计", "架构" | 🏗️ **designer** | Design intent |
| "implement", "fix", "code", "实现", "修bug" | 💻 **implementer** | Coding intent |
| "review", "code review", "审查" | 🔍 **reviewer** | Review intent |
| "test", "QA", "verify", "测试", "验证" | 🧪 **tester** | Testing intent |
| "accept", "release", "deploy", "验收" | 🎯 **acceptor** | Acceptance intent |

**Routing flow:**
1. Check `.agents/runtime/active-agent` — if missing/empty, enter intent detection
2. Match keywords in user message → determine target role
3. **Prompt**: "🔀 Detected intent → suggesting switch to <role>. Confirm?"
4. On confirmation, execute the full role switch flow (below)
5. If a role is already active, use the "role boundary detection" flow (in each agent skill)

> 💡 **Default route**: If intent is unclear, default to **acceptor** since most new conversations start with requirements.

## ⚡ Mandatory Trigger Rules

Any of these expressions **must** immediately trigger a role switch — never ignore or treat as suggestion:

| Trigger Pattern | Example |
|----------------|---------|
| `/agent <name>` | `/agent acceptor`, `/agent designer` |
| `切换到<role>` | "切换到验收者", "切换到实现者" |
| `switch to <role>` | "switch to acceptor", "switch to tester" |
| `当<role>` / `做<role>` | "当验收者", "做实现者" |
| `act as <role>` | "act as reviewer" |
| `我是<role>` | "我是测试者" |
| `以<role>身份` | "以设计者身份工作" |

**Role name mapping:**

| Chinese | English | ID |
|---------|---------|-----|
| 验收者 | acceptor | acceptor |
| 设计者 | designer | designer |
| 实现者 | implementer | implementer |
| 审查者 | reviewer | reviewer |
| 测试者/QA | tester | tester |

**Mandatory actions on trigger detection:**
1. Read `agents/<role>.agent.md` — load role definition
2. Write `.agents/runtime/active-agent` — record current role
3. Read role's inbox — display unread messages
4. Load task board — show tasks assigned to this role
5. Announce: "🔄 Switched to <role>"

> ⚠️ Role switch requests are formal framework operations, not "simulation" or "role-play".

## View All Agent Status (/agent status)

Read each agent's state.json and display summary:

```
🤖 Agent Status Panel
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Role         Status   Task       Queue       Last Active
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 Acceptor   idle     —          —          10:00
🏗️ Designer   busy     T-002      —          10:30
💻 Implementer idle    —          [T-003]    09:45
🔍 Reviewer   idle     —          —          09:00
🧪 Tester     busy     T-001      —          10:15
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 Task Pipeline (each in-progress task):
  T-008: ┌Acceptor✅┐→┌Designer✅┐→┌Implemen⏳┐→┌Reviewer⏸️┐→┌Tester⏸️┐

📊 Last 24h Activity (events.db) | 🚨 Blocked Tasks (if any)
```

Implementation:
```bash
AGENTS_DIR="\/Volumes/MacData/MyData/Documents/project/multi-agent-framework/.agents"
[ -d "" ] || AGENTS_DIR="./.agents"
for agent in acceptor designer implementer reviewer tester; do
  cat "\/runtime/\/state.json"
done
cat "\/task-board.json"
[ -f "\/events.db" ] && sqlite3 "\/events.db" \
  "SELECT agent, count(*) FROM events WHERE created_at > datetime('now', '-24 hours') GROUP BY agent ORDER BY 2 DESC;"
```

Pipeline icons: ✅ Done | ⏳ In Progress | ⏸️ Not Reached | ⛔ Blocked

## Switch Role (/agent <name>)

1. Confirm target role: acceptor | designer | implementer | reviewer | tester
2. **Precondition check** — verify task-board has tasks in matching status:
   | Role | Required Status | Exception |
   |------|----------------|-----------|
   | acceptor | `accepting` / new requirements | Always switchable |
   | designer | `created` / `accept_fail` | — |
   | implementer | `implementing` / `fixing` | — |
   | reviewer | `reviewing` | — |
   | tester | `testing` | — |
   - No match → **check for auto-transition** (see below)
   - Still no match → warn + ask whether to proceed
2a. **FSM Auto-Transition on Switch**:
   When target role has no matching tasks but **previous role's tasks are complete**, auto-execute FSM transition:
   | Switch Direction | Detection | Auto-Transition |
   |-----------------|-----------|-----------------|
   | → designer | Has `created` tasks | None needed (already matched) |
   | → implementer | Has `designing` tasks (design done) | `designing` → `implementing` |
   | → reviewer | Has `implementing` tasks (impl done) | `implementing` → `reviewing` |
   | → tester | Has `reviewing` tasks (review passed) | `reviewing` → `testing` |
   | → acceptor | Has `testing` tasks (tests passed) | `testing` → `accepting` |
   - Prompt: "📋 Found N tasks completed in previous phase. Auto-transition to <target status>?"
   - Confirmed → batch FSM transition → continue switch
   - Declined → switch role only, no task status change
3. **Save and check current agent state**
   - Save state.json
   - **⛔ Switch-Away Guard** — check if current role has unfinished critical outputs:
     | Current Role | Check | Warning Condition |
     |-------------|-------|-------------------|
     | acceptor | task-board.json | Requirements gathered but no task published |
     | designer | design docs | Design drafted but task not moved to implementing |
     | implementer | code + DFMEA | Code modified but uncommitted / no DFMEA |
     | reviewer | review report | Review started but no report generated |
     | tester | test report | Tests executed but no report generated |
   - If unfinished output detected → warn: "⚠️ Current role has unfinished work: [desc]. Switch anyway?"
   - Continue only after user confirmation
4. Write active-agent: `echo "<name>" > .agents/runtime/active-agent`
5. Clean context (RESPAWN — no carry-over from previous agent memory)
6. **Model resolution** (priority high → low):
   - Task-level: `model_override` in task-board.json for current task
   - Agent-level: `model` in `~/.claude/agents/<name>.agent.md` frontmatter
   - Project-level: recommended model in `.agents/skills/project-agents-context/SKILL.md`
   - System default: unspecified, use platform default
   - If model resolved → prompt: "📌 Current agent using model: <model>"
7. Load target agent skill
8. **Process inbox**: Read unread messages, display, mark as read
9. **Task overview**: Show assigned tasks
10. **Load task memory**: Auto-read `.agents/memory/T-NNN-memory.json`, filter by role
11. **Staleness warning**: Alert for tasks inactive > 24h
12. Execute startup flow, print "🔄 Switched to <role>"

### Exit Role
```bash
rm -f .agents/runtime/active-agent
```

## Batch Processing Mode

Triggered by "process tasks" / "start working" / "处理任务":

1. Check inbox — read unread messages, mark as read
2. Scan task-board — filter tasks in current role's responsible statuses, sort by priority
3. Process highest priority task
4. Update status (FSM transition) → save memory → write downstream inbox → auto-dispatch
5. Report progress → return to step 2

| Role | Responsible Statuses | Transitions To |
|------|---------------------|----------------|
| 🎯 acceptor | `accepting` | `accepted` / `accept_fail` |
| 🏗️ designer | `created`, `accept_fail` | `implementing` |
| 💻 implementer | `implementing`, `fixing` | `reviewing` |
| 🔍 reviewer | `reviewing` | `testing` / back to `implementing` |
| 🧪 tester | `testing` | `accepting` / `fixing` |

**Safety rules**: Single-task isolation | Failure doesn't block (mark blocked, continue) | Optimistic lock protection | Auto-notify

## Event Management
```bash
# View last 24h activity
sqlite3 .agents/events.db "SELECT agent, count(*) FROM events WHERE created_at > datetime('now', '-24 hours') GROUP BY agent ORDER BY 2 DESC;"
# Purge events older than 30 days
sqlite3 .agents/events.db "DELETE FROM events WHERE created_at < datetime('now', '-30 days');"
# Reset all
sqlite3 .agents/events.db "DELETE FROM events; DELETE FROM sqlite_sequence WHERE name='events';"
```

## Available Roles
| Command | Role | Emoji |
|---------|------|-------|
| `/agent acceptor` | Acceptor | 🎯 |
| `/agent designer` | Designer | 🏗️ |
| `/agent implementer` | Implementer | 💻 |
| `/agent reviewer` | Reviewer | 🔍 |
| `/agent tester` | Tester | 🧪 |
| `/agent status` | Status Panel | 🤖 |

## Cycle Time Tracking

Record in `tasks/T-NNN.json` on each FSM transition:
```json
{"cycle_time":{"created_at":"...","stages":{"designing":{"entered_at":"...","exited_at":"...","duration_minutes":90},"implementing":{"entered_at":"...","exited_at":null,"duration_minutes":null}},"blocked_time":[{"from":"...","to":"...","duration_minutes":60,"reason":"..."}],"total_elapsed_minutes":null}}
```

**Recording rules**: Enter → write `entered_at` | Exit → write `exited_at` + calc duration | Re-enter → append `rounds` array | Accepted → calc total | Blocked time excluded from stage duration

| Stage | Stale Threshold | 2x → 🔴 Critical | 3x → ⛔ Suggest Block |
|-------|----------------|-------------------|----------------------|
| designing | 2h | 4h | 6h |
| implementing | 4h | 8h | 12h |
| reviewing | 1h | 2h | 3h |
| testing | 2h | 4h | 6h |
| accepting | 1h | 2h | 3h |

Display cycle time summary + stale warnings at the bottom of `/agent status`.

## Automation Integration

### Cron Scheduling
```
*/5 * * * * cd /path/to/project && bash scripts/cron-scheduler.sh --run
```
Jobs: staleness-check (30min) | daily-summary (9AM) | memory-index (2h)

### Webhook Integration
```bash
bash scripts/webhook-handler.sh github-push '{"branch":"main"}'
bash scripts/webhook-handler.sh ci-success '{"build":123}'
bash scripts/webhook-handler.sh wake '{"reason":"manual"}'
```

### FSM Auto-Advance
Task status change → `after-task-status-change` hook → auto-switch to next agent.
Set `"auto_advance": false` on task to disable.

## Role Bootstrap Protocol

Auto-injected on role switch (in order):
1. Global Skill: `~/.claude/skills/agent-{role}/SKILL.md`
2. Project Skill: `.agents/skills/project-{role}/SKILL.md`
3. Current task: goals, status, design doc
4. Top-6 memories: `bash scripts/memory-search.sh "<task>" --role {role} --limit 6`
5. Upstream handoff: inbox messages
6. Project context: `project-agents-context/SKILL.md`

**Phase-specific extra context**: designing → architecture constraints + ADR | implementing → coding standards + TDD | reviewing → review checklist + quality thresholds | testing → test commands + coverage | accepting → acceptance criteria + quality gates

**Handoff message format**:
```json
{"from":"designer","to":"implementer","task_id":"T-024","type":"handoff","summary":"...","artifacts":["...design-docs/T-024.md","...test-specs/T-024-test-spec.md"]}
```

**Implementer → Reviewer Handoff extended fields**:
```json
{
  "from": "implementer",
  "to": "reviewer",
  "task_id": "T-024",
  "type": "handoff",
  "summary": "T-024 implementation complete (5/5 goals done)",
  "review_location": {
    "type": "github_pr",
    "url": "https://github.com/owner/repo/pull/42",
    "pr_number": 42,
    "base_commit": "abc1234",
    "change_id": "Iabc...def"
  },
  "artifacts": ["..."]
}
```
- `review_location.type`: `"github_pr"` | `"gerrit"` | `"local"`
- GitHub PR: reviewer uses `gh pr diff` + `gh pr review`
- Gerrit: reviewer reviews in Gerrit Web UI
- Local: reviewer uses `git diff <base_commit>..HEAD`
