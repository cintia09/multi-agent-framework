---
name: agent-hooks
description: "Hook lifecycle management. Shell scripts triggered at lifecycle points to enforce boundaries, validate operations, and coordinate agents."
paths:
  - "hooks/**"
  - "**/*.sh"
  - ".claude/hooks.json"
  - ".github/hooks-copilot.json"
---

# Skill: Agent Hooks

## Description
Manages the hook lifecycle for the multi-agent framework. Hooks are shell scripts triggered at specific lifecycle points to enforce boundaries, log events, validate operations, and coordinate agents.

## Trigger
- Agent switch, task creation/status change, memory write, context compaction, goal verification
- Pre/post tool usage, session start

## Hook Inventory

### Existing Hooks (5 — v1.0 Core)
| Hook | File | Event | Purpose |
|------|------|-------|---------|
| Security Scan | `security-scan.sh` | PreToolUse | Block secrets from being committed |
| Session Start | `agent-session-start.sh` | SessionStart | Initialize events.db, check pending work |
| Pre-Tool-Use | `agent-pre-tool-use.sh` | PreToolUse | Enforce agent role boundaries |
| Post-Tool-Use | `agent-post-tool-use.sh` | PostToolUse | Audit logging, auto-dispatch |
| Staleness Check | `agent-staleness-check.sh` | PostToolUse | Warn about inactive tasks/agents |

### New Hooks (8 — v2.0 Lifecycle)
| Hook | File | Event | Purpose |
|------|------|-------|---------|
| Before Switch | `agent-before-switch.sh` | AgentSwitch | Validate agent role switch is allowed |
| After Switch | `agent-after-switch.sh` | AgentSwitch | Log switch event, inject role context |
| Before Task Create | `agent-before-task-create.sh` | TaskCreate | Validate task (title, duplicate check) |
| After Task Status | `agent-after-task-status.sh` | TaskStatusChange | Log status change, trigger memory capture |
| Before Memory Write | `agent-before-memory-write.sh` | MemoryWrite | Validate memory content and path |
| After Memory Write | `agent-after-memory-write.sh` | MemoryWrite | Update FTS5 search index |
| Before Compaction | `agent-before-compaction.sh` | Compaction | Flush session memories before context compression |
| On Goal Verified | `agent-on-goal-verified.sh` | GoalVerified | Log goal verification to events.db |

## Hook Control Semantics

### Block Semantics
Any `before-*` hook can return a block response to prevent the operation:
```json
{"block": true, "reason": "Reviewer cannot modify source files"}
```
When blocked:
- The operation is **cancelled**
- The reason is displayed to the agent
- An event is logged to `events.db`

### Approval Semantics
Hooks can request human confirmation:
```json
{"requireApproval": true, "message": "Task has unmet goals, confirm acceptance?"}
```
When approval requested:
- The operation is **paused**
- The message is displayed to the user
- User must confirm or deny before proceeding

### Priority Chain
Multiple hooks for the same event execute in priority order:
- Priority 1 (highest) → Priority N (lowest)
- If any hook returns `block: true`, remaining hooks are **skipped**
- Default priority: **50** (configurable in `hooks.json`)

### Hook Response Protocol
```json
// Allow (default if no output)
{"allow": true}

// Block (terminal — stops operation and remaining hooks)
{"block": true, "reason": "..."}

// Approval (pauses for human confirmation)
{"requireApproval": true, "message": "..."}

// Status (informational, for after-* hooks)
{"status": "ok"}

// Permission decision (for PreToolUse hooks specifically)
{"permissionDecision": "deny", "permissionDecisionReason": "..."}
```

## Role Tool Profiles

Tool profiles are defined in `.agents/tool-profiles.json` and control what each agent role is allowed to do:

| Role | Tools | Write Access | Restrictions |
|------|-------|-------------|--------------|
| **acceptor** | Read, Bash, Grep, Glob, View | None (read-only) | No `rm`, `mv`, `cp`, redirect |
| **designer** | All | `.agents/runtime/designer/`, design docs | Cannot modify skills, hooks, scripts, tests |
| **implementer** | All | All source code | Cannot modify `task-board.json` |
| **reviewer** | All | `.agents/runtime/reviewer/`, review docs | Cannot modify skills, hooks, scripts |
| **tester** | All | `tests/`, `.agents/runtime/tester/` | Cannot modify skills, hooks, agents |

Enforcement is done by `agent-pre-tool-use.sh` which reads the active agent from `.agents/runtime/active-agent` and applies the corresponding profile restrictions.

## Configuration

All hooks are registered in `hooks/hooks.json`. Each entry specifies:
- **matcher**: glob pattern for which tools/events trigger the hook
- **hooks**: array of hook definitions with `type`, `command`, and `timeout`

## Input/Output Contract

**Input**: Hooks receive JSON on stdin with context-specific fields:
- Agent switch: `{from_agent, to_agent, task_id}`
- Task operations: `{task_id, title, new_status, agent}`
- Memory operations: `{file_path, content}`
- Goal verification: `{task_id}`
- Tool use: `{toolName, toolArgs, cwd}`

**Output**: Hooks write JSON to stdout (see Response Protocol above).

## Steps
1. Hook scripts are installed to `hooks/` and made executable
2. `hooks.json` maps lifecycle events to hook scripts
3. The runtime calls hooks at the appropriate lifecycle point
4. `before-*` hooks can block operations; `after-*` hooks are informational
5. Tool profiles in `.agents/tool-profiles.json` define per-role boundaries

---

## 3-Phase Dispatch Logic (已废弃 — Legacy)

> ⚠️ **v3.4.0 起已废弃**: 3-Phase 工作流已合并到统一 FSM (11 状态)。以下代码仅供参考和向后兼容。
> 新项目应使用统一 FSM 模式 (参见 `agent-fsm/SKILL.md`)。
> 旧任务的 3-Phase 状态会自动映射到统一 FSM 状态 (参见 FSM Legacy 迁移表)。

### Step → Agent Mapping (3-Phase)

| Step | Primary Agent | Secondary Agent | Phase |
|------|--------------|-----------------|-------|
| `requirements` | acceptor | — | 1 |
| `architecture` | designer | — | 1 |
| `tdd_design` | designer | tester | 1 |
| `dfmea` | designer | — | 1 |
| `design_review` | reviewer | — | 1 |
| `implementing` | implementer | — | 2 |
| `test_scripting` | tester | — | 2 |
| `code_reviewing` | reviewer | — | 2 |
| `ci_monitoring` | tester | — | 2 |
| `ci_fixing` | implementer | — | 2 |
| `device_baseline` | tester | — | 2 |
| `deploying` | implementer | — | 3 |
| `regression_testing` | tester | — | 3 |
| `feature_testing` | tester | — | 3 |
| `log_analysis` | tester | designer | 3 |
| `documentation` | designer | — | 3 |

### Parallel Dispatch (Dual-Agent Steps)

For steps with a secondary agent (`tdd_design`, `log_analysis`), the dispatch logic sends messages to both agents:

```bash
dispatch_3phase_step() {
  local task_id="$1" step="$2"
  local primary secondary

  case "$step" in
    tdd_design)    primary="designer";  secondary="tester" ;;
    log_analysis)  primary="tester";    secondary="designer" ;;
    *)             primary=$(get_agent_for_step "$step"); secondary="" ;;
  esac

  # Dispatch to primary agent inbox
  send_inbox_message "$primary" "$task_id" "Execute step: $step"

  # Dispatch to secondary agent inbox (if any)
  if [ -n "$secondary" ]; then
    send_inbox_message "$secondary" "$task_id" "Assist with step: $step (secondary role)"
  fi
}
```

### FSM Validation (Dual-Mode)

The `agent-post-tool-use.sh` hook validates transitions based on the task's `workflow_mode`:

```bash
validate_transition() {
  local task_id="$1" old_status="$2" new_status="$3"

  # Read workflow mode
  local mode
  mode=$(jq -r --arg tid "$task_id" \
    '.tasks[] | select(.id == $tid) | .workflow_mode // "simple"' \
    "$AGENTS_DIR/task-board.json")

  if [ "$mode" = "3phase" ]; then
    validate_3phase_transition "$old_status" "$new_status"
  else
    validate_simple_transition "$old_status" "$new_status"
  fi
}

validate_3phase_transition() {
  local from="$1" to="$2"
  local LEGAL=false

  case "${from}→${to}" in
    # Phase 1: Design
    "created→requirements")          LEGAL=true ;;
    "requirements→architecture")     LEGAL=true ;;
    "architecture→tdd_design")       LEGAL=true ;;
    "tdd_design→dfmea")              LEGAL=true ;;
    "dfmea→design_review")           LEGAL=true ;;
    "design_review→implementing")    LEGAL=true ;;
    "design_review→test_scripting")  LEGAL=true ;;
    "design_review→architecture")    LEGAL=true ;;  # feedback

    # Phase 2: Implementation
    "implementing→code_reviewing")   LEGAL=true ;;
    "implementing→ci_monitoring")    LEGAL=true ;;
    "test_scripting→code_reviewing") LEGAL=true ;;
    "code_reviewing→implementing")   LEGAL=true ;;  # rejection
    "code_reviewing→ci_monitoring")  LEGAL=true ;;
    "ci_monitoring→ci_fixing")       LEGAL=true ;;
    "ci_monitoring→device_baseline") LEGAL=true ;;
    "ci_fixing→ci_monitoring")       LEGAL=true ;;
    "device_baseline→deploying")     LEGAL=true ;;
    "device_baseline→implementing")  LEGAL=true ;;  # feedback

    # Hypothesis exploration (from designing or implementing)
    "designing→hypothesizing")       LEGAL=true ;;
    "implementing→hypothesizing")    LEGAL=true ;;
    "hypothesizing→designing")       LEGAL=true ;;
    "hypothesizing→implementing")    LEGAL=true ;;

    # Phase 3: Testing & Verification
    "deploying→regression_testing")      LEGAL=true ;;
    "regression_testing→feature_testing") LEGAL=true ;;
    "regression_testing→implementing")   LEGAL=true ;;  # feedback
    "feature_testing→log_analysis")      LEGAL=true ;;
    "feature_testing→tdd_design")        LEGAL=true ;;  # feedback
    "log_analysis→documentation")        LEGAL=true ;;
    "log_analysis→ci_fixing")            LEGAL=true ;;  # feedback
    "documentation→accepted")            LEGAL=true ;;

    # Universal
    *→blocked)                           LEGAL=true ;;
    "blocked→"*)                         LEGAL=true ;;
  esac

  echo "$LEGAL"
}
```

### Convergence Gate Validation

Before allowing transition to `device_baseline`, the hook validates all parallel tracks are complete:

```bash
check_convergence_gate() {
  local task_id="$1"
  local tracks
  tracks=$(jq -r --arg tid "$task_id" \
    '.tasks[] | select(.id == $tid) | .parallel_tracks // {}' \
    "$AGENTS_DIR/task-board.json")

  local impl=$(echo "$tracks" | jq -r '.implementing // "pending"')
  local test_s=$(echo "$tracks" | jq -r '.test_scripting // "pending"')
  local code_r=$(echo "$tracks" | jq -r '.code_reviewing // "pending"')
  local ci_m=$(echo "$tracks" | jq -r '.ci_monitoring // "pending"')

  if [ "$impl" != "complete" ] || [ "$test_s" != "complete" ] || \
     [ "$code_r" != "complete" ] || [ "$ci_m" != "green" ]; then
    echo '{"block": true, "reason": "Convergence gate: not all parallel tracks complete (impl='$impl', test='$test_s', review='$code_r', ci='$ci_m')"}'
    return 1
  fi
  return 0
}
```

### Feedback Loop Counting & Safety

The hook enforces the MAX_FEEDBACK_LOOPS=10 safety limit:

```bash
check_feedback_safety() {
  local task_id="$1" from="$2" to="$3"

  # Only check for feedback transitions
  local is_feedback=false
  case "${from}→${to}" in
    "regression_testing→implementing"|"feature_testing→tdd_design"|\
    "log_analysis→ci_fixing"|"device_baseline→implementing"|\
    "design_review→architecture"|"code_reviewing→implementing")
      is_feedback=true ;;
  esac

  if [ "$is_feedback" = true ]; then
    local count
    count=$(jq -r --arg tid "$task_id" \
      '.tasks[] | select(.id == $tid) | .feedback_loops // 0' \
      "$AGENTS_DIR/task-board.json")

    if [ "$count" -ge 10 ]; then
      echo '{"block": true, "reason": "Feedback loop safety limit reached (10/10). Task must be manually reviewed and unblocked."}'
      return 1
    fi
  fi
  return 0
}
```
