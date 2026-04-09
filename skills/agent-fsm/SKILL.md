---
name: agent-fsm
description: "FSM 引擎: 管理 Agent 和任务的状态机。调用时说 'FSM 状态转移' 或 '更新任务状态'。"
---

# Agent FSM 引擎

## FSM Mode Selection

The framework supports **dual workflow modes**. Each task operates in exactly one mode, determined at task creation and recorded in `task-board.json`:

| Mode | Value | Use Case | States |
|------|-------|----------|--------|
| **Simple Linear** | `"simple"` (default) | Standard features, bug fixes, typical SDLC | 10 states |
| **3-Phase Engineering** | `"3phase"` | Complex/safety-critical features, hardware/firmware, multi-team | 18 states |

The mode is stored in the task's `workflow_mode` field:
```json
{
  "id": "T-001",
  "workflow_mode": "simple",
  "status": "designing"
}
```

If `workflow_mode` is absent, default to `"simple"`.

---

## Simple Linear FSM

## Agent 状态定义

Agent 有 3 种状态:
- `idle` — 空闲, 可接新任务
- `busy` — 忙碌, 正在处理任务
- `blocked` — 阻塞, 需要人工介入

## 任务状态定义与转移规则

合法的任务状态转移 (from → to):

```
created      → designing                 (designer 接单)
designing    → implementing              (设计完成)
implementing → reviewing                 (提交代码审查)
reviewing    → implementing              (审查退回)
reviewing    → testing                   (审查通过)
testing      → fixing                    (发现问题)
testing      → accepting                 (测试全通过)
fixing       → testing                   (修复完成, 重新测试)
accepting    → accepted                  (验收通过 ✅)
accepting    → accept_fail               (验收失败)
accept_fail  → designing                 (重新进入流程)
ANY          → blocked                   (遇到无法解决的问题)
blocked      → [previous_state]          (人工 unblock)
```

## 操作指令

### 读取 Agent 状态
```bash
cat <project>/.agents/runtime/<agent>/state.json
```

### 更新 Agent 状态
读取 → 检查 version → 修改 → 写入 (version + 1)

state.json 格式:
```json
{
  "agent": "<agent_name>",
  "status": "idle|busy|blocked",
  "current_task": null,
  "sub_state": null,
  "queue": [],
  "last_activity": "<ISO 8601>",
  "version": 0,
  "error": null
}
```

### 任务状态转移
1. 读取 task-board.json
2. 找到目标任务
3. 验证转移是否合法 (参考上面的转移规则)
4. 如果不合法, **拒绝并说明原因** — 绝不执行非法转移
5. 如果合法:
   a. 更新 task status
   b. 更新 assigned_to (根据新状态确定下一个负责 Agent)
   c. 记录 history entry: `{"from": "old", "to": "new", "by": "agent", "at": "ISO8601", "note": "..."}`
   d. 写入目标 Agent 的 inbox.json (通知)
   e. 更新 task-board.json 的 version
   f. 同步更新 task-board.md

### 状态 → Agent 映射
| 新状态 | 分配给 |
|--------|--------|
| created | designer |
| designing | designer |
| implementing | implementer |
| reviewing | reviewer |
| testing | tester |
| fixing | implementer |
| accepting | acceptor |
| accepted | — (完成) |
| accept_fail | designer |
| blocked | — (等待人工) |

### Guard 规则
在执行转移前, 检查:
1. 当前状态 → 目标状态是否在合法转移列表中
2. 执行转移的 Agent 是否是当前任务的 assigned_to
3. task-board.json 的 version 是否与读取时一致 (乐观锁)
4. **目标清单检查 (goals guard)**:
   - `implementing → reviewing`: 任务的 goals 数组中所有目标的 status 必须为 `done` — 有任何 `pending` 则拒绝, 提示 implementer 还有未完成的功能目标
   - `accepting → accepted`: 任务的 goals 数组中所有目标的 status 必须为 `verified` — 有任何 `pending`/`done`/`failed` 则拒绝, 提示 acceptor 还有未验证或验证失败的目标

如果任何 Guard 检查失败, 中止转移, 报告原因。

---

## 3-Phase Engineering Closed Loop FSM

For complex, safety-critical, or multi-team features, the 3-Phase workflow provides a rigorous 18-state engineering process with parallel tracks and feedback loops.

### 3-Phase State Definitions

| # | Phase | State | Description | Assigned To |
|---|-------|-------|-------------|-------------|
| 1 | — | `created` | Task created, pending triage | acceptor |
| 2 | 1: Design | `requirements` | Gathering & refining requirements | acceptor |
| 3 | 1: Design | `architecture` | System/module architecture design | designer |
| 4 | 1: Design | `tdd_design` | TDD test plan + DFMEA input | designer + tester |
| 5 | 1: Design | `dfmea` | Design Failure Mode & Effects Analysis | designer |
| 6 | 1: Design | `design_review` | Formal design review gate | reviewer |
| 7 | 2: Implementation | `implementing` | Feature coding (Track A) | implementer |
| 8 | 2: Implementation | `test_scripting` | Test automation scripting (Track B) | tester |
| 9 | 2: Implementation | `code_reviewing` | Continuous code review (Track C) | reviewer |
| 10 | 2: Implementation | `ci_monitoring` | CI pipeline monitoring | tester |
| 11 | 2: Implementation | `ci_fixing` | CI failure resolution | implementer |
| 12 | 2: Implementation | `device_baseline` | Device/environment baseline verification | tester |
| 13 | 3: Testing | `deploying` | Deploy to test environment | implementer |
| 14 | 3: Testing | `regression_testing` | Full regression test suite | tester |
| 15 | 3: Testing | `feature_testing` | New feature-specific testing | tester |
| 16 | 3: Testing | `log_analysis` | Log/diagnostic analysis | tester + designer |
| 17 | 3: Testing | `documentation` | Release notes, docs update | designer |
| 18 | — | `accepted` | Task complete ✅ | — |

### Legal Transitions (3-Phase)

#### Phase 1 — Design Flow
```
created         → requirements              (acceptor triages to 3-phase)
requirements    → architecture              (requirements approved)
architecture    → tdd_design                (architecture complete)
tdd_design      → dfmea                     (TDD plan + test strategy ready)
dfmea           → design_review             (DFMEA complete)
design_review   → implementing              (design review PASS → Phase 2)
design_review   → architecture              (design review FAIL → rework)
```

#### Phase 2 — Implementation Flow (Parallel Tracks)
```
implementing    → code_reviewing            (code ready for review)
implementing    → ci_monitoring             (code pushed, CI triggered)
test_scripting  → code_reviewing            (test scripts ready for review)
code_reviewing  → implementing              (review rejection → rework)
code_reviewing  → ci_monitoring             (review pass → verify CI)
ci_monitoring   → ci_fixing                 (CI failure detected)
ci_monitoring   → device_baseline           (CI green → baseline check)
ci_fixing       → ci_monitoring             (fix applied, re-check CI)
device_baseline → deploying                 (baseline pass → Phase 3)
device_baseline → implementing              (baseline fail → rework)
```

**Parallel Track Launch**: When entering Phase 2 (`design_review → implementing`), the orchestrator simultaneously launches:
- **Track A**: `implementing` (implementer)
- **Track B**: `test_scripting` (tester)
- **Track C**: `code_reviewing` (reviewer — starts when Track A/B produce artifacts)

**Convergence Gate**: `device_baseline` can only be entered when ALL parallel tracks report complete. The orchestrator checks:
```
parallel_tracks.implementing   == "complete"
parallel_tracks.test_scripting == "complete"
parallel_tracks.code_reviewing == "complete"
parallel_tracks.ci_monitoring  == "green"
```

#### Phase 3 — Testing & Verification Flow
```
deploying           → regression_testing    (deployment confirmed)
regression_testing  → feature_testing       (regression pass)
regression_testing  → implementing          (regression FAIL → feedback loop)
feature_testing     → log_analysis          (feature tests complete)
feature_testing     → tdd_design            (feature FAIL → feedback to design)
log_analysis        → documentation         (no anomalies)
log_analysis        → ci_fixing             (anomaly found → feedback loop)
documentation       → accepted              (docs complete, task done ✅)
```

#### Feedback Loop Transitions
```
regression_testing  → implementing          (Phase 3 → Phase 2: test failure)
feature_testing     → tdd_design            (Phase 3 → Phase 1: design gap)
log_analysis        → ci_fixing             (Phase 3 → Phase 2: anomaly fix)
device_baseline     → implementing          (Phase 2 → Phase 2: baseline fail)
design_review       → architecture          (Phase 1 → Phase 1: review fail)
code_reviewing      → implementing          (Phase 2 → Phase 2: review reject)
```

#### Universal Transitions
```
ANY                 → blocked               (unresolvable issue)
blocked             → [previous_state]      (human unblock)
designing           → hypothesizing         (fork competitive approaches)
implementing        → hypothesizing         (fork competitive approaches)
hypothesizing       → designing             (winner promoted → design)
hypothesizing       → implementing          (winner promoted → implementation)
```

### Safety Limit: Feedback Loops

**MAX_FEEDBACK_LOOPS = 10** per task.

Each feedback transition increments `feedback_loops` counter in task-board.json:
```json
{
  "id": "T-005",
  "workflow_mode": "3phase",
  "feedback_loops": 3,
  "feedback_history": [
    {"from": "regression_testing", "to": "implementing", "at": "2026-04-10T14:00:00Z", "reason": "3 regression failures"},
    {"from": "feature_testing", "to": "tdd_design", "at": "2026-04-10T16:00:00Z", "reason": "edge case not covered in design"},
    {"from": "log_analysis", "to": "ci_fixing", "at": "2026-04-11T09:00:00Z", "reason": "memory leak in log"}
  ]
}
```

When `feedback_loops >= MAX_FEEDBACK_LOOPS`:
1. Task automatically transitions to `blocked`
2. Reason: "Feedback loop safety limit reached (10/10). Manual intervention required."
3. Event logged to events.db: `fsm_feedback_limit`
4. Human must review, resolve root cause, reset counter, and unblock

### Extended Guard Rules (3-Phase)

In addition to the Simple FSM guard rules, 3-Phase mode enforces:

1. **Phase gate guard**: `design_review → implementing` requires reviewer to explicitly PASS the design review
2. **Convergence guard**: `ci_monitoring → device_baseline` requires all parallel tracks complete (see above)
3. **Feedback loop guard**: Any feedback transition checks `feedback_loops < MAX_FEEDBACK_LOOPS`
4. **Phase consistency guard**: Cannot jump between phases without going through the defined transition path (e.g., cannot go from `requirements` directly to `deploying`)
5. **Parallel track guard**: `test_scripting` and `code_reviewing` cannot advance to `device_baseline` independently — must converge
6. **Workflow mode guard**: A task with `workflow_mode: "simple"` cannot use 3-Phase states, and vice versa

### 3-Phase 状态 → Agent 映射

| State | Primary Agent | Secondary Agent |
|-------|--------------|-----------------|
| created | acceptor | — |
| requirements | acceptor | — |
| architecture | designer | — |
| tdd_design | designer | tester |
| dfmea | designer | — |
| design_review | reviewer | — |
| implementing | implementer | — |
| test_scripting | tester | — |
| code_reviewing | reviewer | — |
| ci_monitoring | tester | — |
| ci_fixing | implementer | — |
| device_baseline | tester | — |
| deploying | implementer | — |
| regression_testing | tester | — |
| feature_testing | tester | — |
| log_analysis | tester | designer |
| documentation | designer | — |
| accepted | — | — |
| blocked | — | — |

### 3-Phase 操作指令

#### Task Status Transition (3-Phase)
1. Read task-board.json
2. Check `workflow_mode` — if `"3phase"`, use 3-Phase transition rules
3. Validate transition legality against the 3-Phase transition table above
4. Check feedback loop count if this is a feedback transition
5. Check convergence gate if transitioning to `device_baseline`
6. If legal:
   a. Update task status
   b. Update `phase` and `step` fields
   c. Update `parallel_tracks` if applicable
   d. Increment `feedback_loops` if this is a feedback transition
   e. Record history entry
   f. Write to target Agent's inbox.json
   g. Update task-board.json version
   h. Sync task-board.md
