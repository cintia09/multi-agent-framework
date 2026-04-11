---
name: agent-orchestrator
description: "Orchestrator Daemon. Autonomous background process that drives tasks through the unified FSM workflow. Invokes agents via Copilot CLI with step-specific prompt templates."
---

# Agent Orchestrator — Workflow Daemon

> ⚠️ **v3.4.0 更新**: 原 3-Phase Orchestrator 已升级为统一 FSM 编排器。
> 3-Phase 的 18 状态已合并为 11 状态统一 FSM (参见 `agent-fsm/SKILL.md`)。
> 旧任务的 3-Phase 状态会自动映射到统一 FSM 状态。

Background shell script that autonomously drives tasks through the unified FSM workflow:
1. Reads task state from `task-board.json`, determines next step via FSM
2. Selects agent + prompt template, invokes via Copilot CLI
3. Evaluates result, advances FSM, handles feedback loops

Generated during `agent-init` with `{PLACEHOLDER}` tokens filled in.

## Configuration Variables

| Placeholder | Description | Example |
|-------------|-------------|---------|
| `{PROJECT_DIR}` | Project root | `/home/user/my-project` |
| `{BUILD_CMD}` | Build command | `npm run build` |
| `{TEST_CMD}` | Test command | `npm test` |
| `{LINT_CMD}` | Lint command | `npm run lint` |
| `{CI_SYSTEM}` | CI platform | `github-actions` / `jenkins` / `gitlab-ci` |
| `{CI_URL}` | CI dashboard URL | `https://github.com/org/repo/actions` |
| `{CI_STATUS_CMD}` | Check CI status | `gh run list --limit 1 --json status` |
| `{CI_TRIGGER_CMD}` | Trigger CI run | `gh workflow run ci.yml` |
| `{REVIEW_SYSTEM}` | Review platform | `github-pr` / `gerrit` / `gitlab-mr` |
| `{REVIEW_CMD}` | Create/check review | `gh pr create` |
| `{REVIEW_STATUS_CMD}` | Check review status | `gh pr checks` |
| `{CLI_COMMAND}` | AI CLI command | `claude` / `copilot` |
| `{DEVICE_TYPE}` | Target environment | `localhost` / `staging` / `hardware` |
| `{DEPLOY_CMD}` | Deployment command | `docker compose up -d` |
| `{LOG_CMD}` | Log retrieval | `docker compose logs --tail=200` |
| `{BASELINE_CMD}` | Baseline check | `curl -sf http://localhost:8080/health` |

## Step → Agent Mapping

| Step | Agent | Step | Agent |
|------|-------|------|-------|
| requirements | acceptor | implementing | implementer |
| architecture | designer | test_scripting | tester |
| tdd_design | designer | code_reviewing | reviewer |
| dfmea | designer | ci_monitoring | implementer |
| design_review | reviewer | ci_fixing | implementer |
| deploying | implementer | device_baseline | implementer |
| regression_testing | tester | feature_testing | tester |
| log_analysis | tester | documentation | designer |

## Step → Prompt Template

Each step has a file in `.agents/prompts/`: `phase{N}-{step}.txt`

| Phase | File | Phase | File |
|-------|------|-------|------|
| 1 | `phase1-requirements.txt` | 2 | `phase2-ci-monitoring.txt` |
| 1 | `phase1-architecture.txt` | 2 | `phase2-ci-fixing.txt` |
| 1 | `phase1-tdd-design.txt` | 2 | `phase2-device-baseline.txt` |
| 1 | `phase1-dfmea.txt` | 3 | `phase3-deploying.txt` |
| 1 | `phase1-design-review.txt` | 3 | `phase3-regression-testing.txt` |
| 2 | `phase2-implementing.txt` | 3 | `phase3-feature-testing.txt` |
| 2 | `phase2-test-scripting.txt` | 3 | `phase3-log-analysis.txt` |
| 2 | `phase2-code-reviewing.txt` | 3 | `phase3-documentation.txt` |

## Result Fields

Agents write results to task-board.json; orchestrator reads them for branching.

| Field | Values | Set By Step |
|-------|--------|-------------|
| `design_review_result` | `"pass"` / `"fail"` | design_review |
| `regression_result` | `"pass"` / `"fail"` | regression_testing |
| `feature_result` | `"pass"` / `"fail"` | feature_testing |
| `log_analysis_result` | `"clean"` / `"anomaly"` | log_analysis |
| `device_baseline_result` | `"pass"` / `"fail"` | device_baseline |

## Phase 2 Parallel Execution

```
design_review PASS → Track A: implementing (implementer) + Track B: test_scripting (tester)
  → Track C: code_reviewing (reviewer, after A/B produce artifacts)
  → Convergence Gate → ci_monitoring → ci_fixing loop → device_baseline
```

## Feedback Loops

Max 10 loops per task. Exceeding → task `blocked`. Counter + history stored in task-board.json.

---

## Generic Orchestrator Daemon Template

Complete runnable script. `{PLACEHOLDER}` tokens replaced by `agent-init`.

```bash
#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="{PROJECT_DIR}"
BUILD_CMD="{BUILD_CMD}"; TEST_CMD="{TEST_CMD}"; LINT_CMD="{LINT_CMD}"
CI_SYSTEM="{CI_SYSTEM}"; CI_URL="{CI_URL}"
CI_STATUS_CMD="{CI_STATUS_CMD}"; CI_TRIGGER_CMD="{CI_TRIGGER_CMD}"
REVIEW_SYSTEM="{REVIEW_SYSTEM}"; REVIEW_CMD="{REVIEW_CMD}"; REVIEW_STATUS_CMD="{REVIEW_STATUS_CMD}"
DEVICE_TYPE="{DEVICE_TYPE}"; DEPLOY_CMD="{DEPLOY_CMD}"
LOG_CMD="{LOG_CMD}"; BASELINE_CMD="{BASELINE_CMD}"
MAX_FEEDBACK_LOOPS=10

AGENTS_DIR="${PROJECT_DIR}/.agents"
TASKBOARD="${AGENTS_DIR}/task-board.json"
PROMPTS_DIR="${AGENTS_DIR}/prompts"
LOG_DIR="${AGENTS_DIR}/orchestrator/logs"
PID_FILE="${AGENTS_DIR}/orchestrator/daemon.pid"
EVENTS_DB="${AGENTS_DIR}/events.db"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${GREEN}[orch]${NC} $1"; }
warn()  { echo -e "${YELLOW}[orch]${NC} $1"; }
error() { echo -e "${RED}[orch]${NC} $1"; }
step()  { echo -e "${CYAN}[step]${NC} $1"; }

mkdir -p "$LOG_DIR"
echo $$ > "$PID_FILE"
info "Orchestrator started (PID: $$) | Project: $PROJECT_DIR"

get_task_field() {
  jq -r --arg tid "$1" ".tasks[] | select(.id == \$tid) | .$2 // empty" "$TASKBOARD"
}

get_agent_for_step() {
  case "$1" in
    requirements) echo "acceptor" ;; architecture|tdd_design|dfmea|documentation) echo "designer" ;;
    design_review|code_reviewing) echo "reviewer" ;;
    implementing|ci_monitoring|ci_fixing|device_baseline|deploying) echo "implementer" ;;
    test_scripting|regression_testing|feature_testing|log_analysis) echo "tester" ;;
    *) echo "" ;;
  esac
}

get_phase_for_step() {
  case "$1" in
    requirements|architecture|tdd_design|dfmea|design_review) echo "1" ;;
    implementing|test_scripting|code_reviewing|ci_monitoring|ci_fixing|device_baseline) echo "2" ;;
    deploying|regression_testing|feature_testing|log_analysis|documentation) echo "3" ;;
    *) echo "0" ;;
  esac
}

transition_task() {
  local task_id="$1" new_status="$2" note="${3:-}"
  local ts; ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  local phase; phase=$(get_phase_for_step "$new_status")
  jq --arg tid "$task_id" --arg status "$new_status" --arg note "$note" \
     --arg ts "$ts" --arg phase "$phase" \
     '(.tasks[] | select(.id == $tid)) |=
       (.status = $status | .phase = $phase | .step = $status |
        .history += [{"to": $status, "at": $ts, "note": $note}] |
        .version = (.version + 1))' \
     "$TASKBOARD" > "${TASKBOARD}.tmp" && mv "${TASKBOARD}.tmp" "$TASKBOARD"
  step "Task $task_id → $new_status (Phase $phase)"
  sqlite3 "$EVENTS_DB" "INSERT INTO events (timestamp, event_type, agent, task_id, detail)
    VALUES ($(date +%s), 'orchestrator_transition', 'orchestrator', '$task_id',
    '{\"to\":\"$new_status\",\"phase\":\"$phase\",\"note\":\"$note\"}');" 2>/dev/null || true
}

invoke_agent() {
  local agent="$1" prompt_file="$2" task_id="$3"
  local logfile="${LOG_DIR}/${task_id}-${agent}-$(date +%Y%m%d-%H%M%S).log"
  [ ! -f "$prompt_file" ] && { error "Prompt not found: $prompt_file"; return 1; }
  local prompt
  prompt=$(sed -e "s|{TASK_ID}|${task_id}|g" -e "s|{PROJECT_DIR}|${PROJECT_DIR}|g" < "$prompt_file")
  info "Invoking $agent for $task_id"
  {CLI_COMMAND} --agent "$agent" --prompt "$prompt" --project-dir "$PROJECT_DIR" --non-interactive \
    2>&1 | tee -a "$logfile"
  local rc=${PIPESTATUS[0]}
  [ "$rc" -ne 0 ] && warn "Agent $agent exit code: $rc"
  return "$rc"
}

check_convergence() {
  local tid="$1"
  local i t c m
  i=$(jq -r --arg tid "$tid" '.tasks[] | select(.id == $tid) | .parallel_tracks.implementing // "pending"' "$TASKBOARD")
  t=$(jq -r --arg tid "$tid" '.tasks[] | select(.id == $tid) | .parallel_tracks.test_scripting // "pending"' "$TASKBOARD")
  c=$(jq -r --arg tid "$tid" '.tasks[] | select(.id == $tid) | .parallel_tracks.code_reviewing // "pending"' "$TASKBOARD")
  m=$(jq -r --arg tid "$tid" '.tasks[] | select(.id == $tid) | .parallel_tracks.ci_monitoring // "pending"' "$TASKBOARD")
  [ "$i" = "complete" ] && [ "$t" = "complete" ] && [ "$c" = "complete" ] && [ "$m" = "green" ]
}

handle_feedback() {
  local task_id="$1" from_step="$2" to_step="$3" reason="$4"
  local count; count=$(jq -r --arg tid "$task_id" '.tasks[] | select(.id == $tid) | .feedback_loops // 0' "$TASKBOARD")
  if [ "$count" -ge "$MAX_FEEDBACK_LOOPS" ]; then
    error "SAFETY LIMIT: $task_id reached $MAX_FEEDBACK_LOOPS loops → BLOCKED"
    transition_task "$task_id" "blocked" "Feedback loop limit ($count/$MAX_FEEDBACK_LOOPS)"
    return 1
  fi
  local ts; ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  jq --arg tid "$task_id" --arg from "$from_step" --arg to "$to_step" \
     --arg reason "$reason" --arg ts "$ts" \
     '(.tasks[] | select(.id == $tid)) |=
       (.feedback_loops = ((.feedback_loops // 0) + 1) |
        .feedback_history += [{"from": $from, "to": $to, "at": $ts, "reason": $reason}])' \
     "$TASKBOARD" > "${TASKBOARD}.tmp" && mv "${TASKBOARD}.tmp" "$TASKBOARD"
  warn "Feedback $((count + 1))/$MAX_FEEDBACK_LOOPS: $from_step → $to_step ($reason)"
  transition_task "$task_id" "$to_step" "Feedback: $reason"
}

run_phase2_parallel() {
  local task_id="$1"
  invoke_agent "implementer" "$PROMPTS_DIR/phase2-implementing.txt" "$task_id" &
  local pid_a=$!
  invoke_agent "tester" "$PROMPTS_DIR/phase2-test-scripting.txt" "$task_id" &
  local pid_b=$!
  sleep 30
  invoke_agent "reviewer" "$PROMPTS_DIR/phase2-code-reviewing.txt" "$task_id" &
  local pid_c=$!
  local rc_a=0 rc_b=0 rc_c=0
  wait $pid_a || rc_a=$?; wait $pid_b || rc_b=$?; wait $pid_c || rc_c=$?
  jq --arg tid "$task_id" \
     --arg impl "$([ $rc_a -eq 0 ] && echo complete || echo failed)" \
     --arg test_s "$([ $rc_b -eq 0 ] && echo complete || echo failed)" \
     --arg code_r "$([ $rc_c -eq 0 ] && echo complete || echo failed)" \
     '(.tasks[] | select(.id == $tid)) |=
       (.parallel_tracks = {"implementing": $impl, "test_scripting": $test_s, "code_reviewing": $code_r, "ci_monitoring": "pending"})' \
     "$TASKBOARD" > "${TASKBOARD}.tmp" && mv "${TASKBOARD}.tmp" "$TASKBOARD"
}

run_3phase() {
  local task_id="$1"
  info "3-Phase orchestration for: $task_id"
  local status; status=$(get_task_field "$task_id" "status")

  while [ "$status" != "accepted" ] && [ "$status" != "blocked" ]; do
    step "Current: $status"
    case "$status" in
      created)
        transition_task "$task_id" "requirements" "Entering Phase 1"
        invoke_agent "acceptor" "$PROMPTS_DIR/phase1-requirements.txt" "$task_id"
        transition_task "$task_id" "architecture" "Requirements approved" ;;
      architecture)
        invoke_agent "designer" "$PROMPTS_DIR/phase1-architecture.txt" "$task_id"
        transition_task "$task_id" "tdd_design" "Architecture complete" ;;
      tdd_design)
        invoke_agent "designer" "$PROMPTS_DIR/phase1-tdd-design.txt" "$task_id"
        invoke_agent "tester" "$PROMPTS_DIR/phase1-tdd-design.txt" "$task_id"
        transition_task "$task_id" "dfmea" "TDD design complete" ;;
      dfmea)
        invoke_agent "designer" "$PROMPTS_DIR/phase1-dfmea.txt" "$task_id"
        transition_task "$task_id" "design_review" "DFMEA complete" ;;
      design_review)
        invoke_agent "reviewer" "$PROMPTS_DIR/phase1-design-review.txt" "$task_id"
        local dr; dr=$(get_task_field "$task_id" "design_review_result")
        [ "$dr" = "pass" ] && transition_task "$task_id" "implementing" "Review PASS → Phase 2" \
          || handle_feedback "$task_id" "design_review" "architecture" "Review FAIL" ;;
      implementing)
        run_phase2_parallel "$task_id"
        transition_task "$task_id" "ci_monitoring" "Parallel tracks complete" ;;
      ci_monitoring)
        invoke_agent "implementer" "$PROMPTS_DIR/phase2-ci-monitoring.txt" "$task_id"
        local ci; ci=$(eval "$CI_STATUS_CMD" 2>/dev/null | head -1 || echo "unknown")
        if echo "$ci" | grep -qi "success\|pass\|green"; then
          jq --arg tid "$task_id" '(.tasks[] | select(.id == $tid)).parallel_tracks.ci_monitoring = "green"' \
             "$TASKBOARD" > "${TASKBOARD}.tmp" && mv "${TASKBOARD}.tmp" "$TASKBOARD"
          check_convergence "$task_id" && transition_task "$task_id" "device_baseline" "CI green + converged"
        else transition_task "$task_id" "ci_fixing" "CI failure"; fi ;;
      ci_fixing)
        invoke_agent "implementer" "$PROMPTS_DIR/phase2-ci-fixing.txt" "$task_id"
        transition_task "$task_id" "ci_monitoring" "CI fix applied" ;;
      device_baseline)
        invoke_agent "implementer" "$PROMPTS_DIR/phase2-device-baseline.txt" "$task_id"
        local bl; bl=$(eval "$BASELINE_CMD" 2>/dev/null && echo "pass" || echo "fail")
        [ "$bl" = "pass" ] && transition_task "$task_id" "deploying" "Baseline pass → Phase 3" \
          || handle_feedback "$task_id" "device_baseline" "implementing" "Baseline failed" ;;
      deploying)
        invoke_agent "implementer" "$PROMPTS_DIR/phase3-deploying.txt" "$task_id"
        eval "$DEPLOY_CMD" 2>&1 | tee -a "$LOG_DIR/${task_id}-deploy.log"
        transition_task "$task_id" "regression_testing" "Deployed" ;;
      regression_testing)
        invoke_agent "tester" "$PROMPTS_DIR/phase3-regression-testing.txt" "$task_id"
        local rr; rr=$(get_task_field "$task_id" "regression_result")
        [ "$rr" = "pass" ] && transition_task "$task_id" "feature_testing" "Regression pass" \
          || handle_feedback "$task_id" "regression_testing" "implementing" "Regression fail" ;;
      feature_testing)
        invoke_agent "tester" "$PROMPTS_DIR/phase3-feature-testing.txt" "$task_id"
        local fr; fr=$(get_task_field "$task_id" "feature_result")
        [ "$fr" = "pass" ] && transition_task "$task_id" "log_analysis" "Feature pass" \
          || handle_feedback "$task_id" "feature_testing" "tdd_design" "Feature gap" ;;
      log_analysis)
        invoke_agent "tester" "$PROMPTS_DIR/phase3-log-analysis.txt" "$task_id"
        invoke_agent "designer" "$PROMPTS_DIR/phase3-log-analysis.txt" "$task_id"
        local lr; lr=$(get_task_field "$task_id" "log_analysis_result")
        [ "$lr" = "clean" ] && transition_task "$task_id" "documentation" "Logs clean" \
          || handle_feedback "$task_id" "log_analysis" "ci_fixing" "Log anomaly" ;;
      documentation)
        invoke_agent "designer" "$PROMPTS_DIR/phase3-documentation.txt" "$task_id"
        transition_task "$task_id" "accepted" "Task DONE ✅" ;;
      blocked) warn "Task $task_id BLOCKED. Manual intervention needed."; sleep 60 ;;
      *) error "Unknown state: $status"; break ;;
    esac
    status=$(get_task_field "$task_id" "status")
  done
  [ "$status" = "accepted" ] && info "🎉 Task $task_id completed!" || warn "Task $task_id ended: $status"
}

case "${2:-}" in
  --status) [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null && info "Running (PID: $(cat "$PID_FILE"))" || warn "Not running"; exit 0 ;;
  --stop) [ -f "$PID_FILE" ] && { kill "$(cat "$PID_FILE")" 2>/dev/null || true; rm -f "$PID_FILE"; info "Stopped"; }; exit 0 ;;
esac
TASK_ID="${1:?Usage: $0 <task-id> [--dry-run|--status|--stop]}"
run_3phase "$TASK_ID"
rm -f "$PID_FILE"; info "Orchestrator exited"
```

## Prompt Templates

All templates below are compact. Agent writes results to task-board.json via `jq`.

### `phase1-requirements.txt`
```
ACCEPTOR agent | Task {TASK_ID} | {PROJECT_DIR} | Phase 1: Requirements

Read task from .agents/task-board.json. Produce requirements document.
1. Extract functional & non-functional requirements
2. User story format: "As a [role], I want [feature], so that [benefit]"
3. Define acceptance criteria per requirement. Flag ambiguities.
Output: .agents/runtime/acceptor/workspace/requirements/{TASK_ID}-requirements.md
Sections: Functional, Non-Functional, Constraints, Open Questions
Each: ID, description, priority (P0-P3), acceptance criteria
Gate: All testable, no ambiguous language, ≥1 criterion per requirement
```

### `phase1-architecture.txt`
```
DESIGNER agent | Task {TASK_ID} | {PROJECT_DIR} | Phase 1: Architecture

Input: .agents/runtime/acceptor/workspace/requirements/{TASK_ID}-requirements.md
1. Design: component diagram (text/Mermaid), data model, API design, tech choices
2. Identify integration points, dependencies, error handling, edge cases
Output: .agents/runtime/designer/workspace/design-docs/{TASK_ID}-design.md
Sections: Overview, Components, Data Model, API, Error Handling, Open Questions
Gate: All requirements addressed, complete data model, API has error responses, no circular deps
```

### `phase1-tdd-design.txt`
```
DESIGNER agent (with TESTER input) | Task {TASK_ID} | {PROJECT_DIR} | Phase 1: TDD Design

Inputs: design-docs/{TASK_ID}-design.md, requirements/{TASK_ID}-requirements.md
1. Per component: unit tests (RED), impl strategy (GREEN), refactor opportunities
2. Integration & E2E scenarios matching acceptance criteria. Test data & fixtures.
Output: .agents/runtime/designer/workspace/design-docs/{TASK_ID}-tdd-plan.md
Sections: Unit Tests, Integration, E2E, Test Data, Execution Order
Each test: ID, description, input, expected output, component under test
Gate: Every requirement has ≥1 test, Red→Green→Refactor, edge-case coverage
```

### `phase1-dfmea.txt`
```
DESIGNER agent | Task {TASK_ID} | {PROJECT_DIR} | Phase 1: DFMEA

Inputs: design-docs/{TASK_ID}-design.md, design-docs/{TASK_ID}-tdd-plan.md
1. Per component: failure modes, Severity/Occurrence/Detection (1-10), RPN = S×O×D
2. Mitigations for RPN > 100. Consider: data loss, security, performance, concurrency
3. Cross-ref TDD plan — high-risk items must have tests
Output: .agents/runtime/designer/workspace/design-docs/{TASK_ID}-dfmea.md
Format: Risk Matrix table + Top 5 risks summary
Gate: All components analyzed, RPN>100 mitigated, S≥8 items have test cases
```

### `phase1-design-review.txt`
```
REVIEWER agent | Task {TASK_ID} | {PROJECT_DIR} | Phase 1: Design Review

Inputs: requirements/{TASK_ID}-requirements.md, design-docs/{TASK_ID}-design.md,
  design-docs/{TASK_ID}-tdd-plan.md, design-docs/{TASK_ID}-dfmea.md
1. Review completeness, consistency across all Phase 1 docs
2. Set design_review_result = "pass" or "fail" (with reasons)
Output: .agents/runtime/reviewer/workspace/review-reports/review-{TASK_ID}-design.md
Update: jq --arg tid "{TASK_ID}" '(.tasks[] | select(.id == $tid)).design_review_result = "pass"' .agents/task-board.json > .agents/task-board.json.tmp && mv .agents/task-board.json.tmp .agents/task-board.json
Gate: Requirements→components traced, components→tests traced, no unmitigated high-severity risks
```

### `phase2-implementing.txt`
```
IMPLEMENTER agent | Task {TASK_ID} | {PROJECT_DIR} | Phase 2: TDD Development (Track A)

Inputs: design-docs/{TASK_ID}-design.md, test-specs/{TASK_ID}-test-spec.md, design-docs/{TASK_ID}-tdd-plan.md
1. Per TDD component: test FIRST (RED) → {TEST_CMD} fail → impl (GREEN) → {TEST_CMD} pass → refactor → git commit
2. Full build: {BUILD_CMD} | Lint: {LINT_CMD} | Update goals in task-board.json
3. CI ({CI_SYSTEM}): push and monitor {CI_URL}
Gate: Tests pass, build succeeds, lint clean, all goals "done"
```

### `phase2-test-scripting.txt`
```
TESTER agent | Task {TASK_ID} | {PROJECT_DIR} | Phase 2: Test Scripting (Track B)

Inputs: design-docs/{TASK_ID}-tdd-plan.md, test-specs/{TASK_ID}-test-spec.md, design-docs/{TASK_ID}-design.md
1. Create test infra: fixtures, factories, mock data, env config
2. Write: unit tests, integration tests (setup/teardown), E2E tests (acceptance criteria)
3. Verify runnable: {TEST_CMD}
Output: .agents/runtime/tester/workspace/test-cases/{TASK_ID}-tests.md
Gate: All TDD cases have scripts, isolated/repeatable, DFMEA edge cases covered
```

### `phase2-code-reviewing.txt`
```
REVIEWER agent | Task {TASK_ID} | {PROJECT_DIR} | Phase 2: Code Review (Track C)

Inputs: design-docs/{TASK_ID}-design.md, design-docs/{TASK_ID}-dfmea.md
1. Review `git diff` against design. Security: no secrets, input validation, injection prevention, error handling
2. Quality: style ({LINT_CMD}), no dead code, clear naming, separation of concerns
Output: .agents/runtime/reviewer/workspace/review-reports/review-{TASK_ID}-code.md
Format: Critical (must fix) | Warnings | Suggestions | Verdict: APPROVE/REQUEST_CHANGES
Gate: Build ({BUILD_CMD}), lint ({LINT_CMD}), no critical security, matches design
```

### `phase2-ci-monitoring.txt`
```
IMPLEMENTER agent | Task {TASK_ID} | {PROJECT_DIR} | Phase 2: CI Monitoring
CI: {CI_SYSTEM} | URL: {CI_URL}
1. Trigger: {CI_TRIGGER_CMD} | Monitor: {CI_STATUS_CMD}
2. Local: {BUILD_CMD} && {TEST_CMD} && {LINT_CMD}
3. Pass → parallel_tracks.ci_monitoring = "green" | Fail → report logs
Gate: CI complete, all tests pass, artifacts generated
```

### `phase2-ci-fixing.txt`
```
IMPLEMENTER agent | Task {TASK_ID} | {PROJECT_DIR} | Phase 2: CI Fixing
CI: {CI_SYSTEM} | URL: {CI_URL} | Logs: {LOG_CMD}
1. Read failure logs, categorize (build/test/lint/env)
2. Root cause → minimal fix → verify: {BUILD_CMD} && {TEST_CMD} && {LINT_CMD}
3. Commit "fix(ci): [desc]" → re-trigger: {CI_TRIGGER_CMD}
Gate: Failing checks pass locally, fixes minimal, CI re-triggered
```

### `phase2-device-baseline.txt`
```
IMPLEMENTER agent | Task {TASK_ID} | {PROJECT_DIR} | Phase 2: Device Baseline
Device: {DEVICE_TYPE} | Deploy: {DEPLOY_CMD} | Check: {BASELINE_CMD} | Logs: {LOG_CMD}
1. Deploy → wait stable → baseline check → log check
2. Set device_baseline_result = "pass" or "fail" (with diagnosis)
Update: jq --arg tid "{TASK_ID}" '(.tasks[] | select(.id == $tid)).device_baseline_result = "pass"' .agents/task-board.json > .agents/task-board.json.tmp && mv .agents/task-board.json.tmp .agents/task-board.json
Gate: Deploy OK, health pass, no error logs, core endpoints respond
```

### `phase3-deploying.txt`
```
IMPLEMENTER agent | Task {TASK_ID} | {PROJECT_DIR} | Phase 3: Deploying
Device: {DEVICE_TYPE} | Deploy: {DEPLOY_CMD} | Check: {BASELINE_CMD} | Logs: {LOG_CMD}
1. Verify build artifact (from Phase 2 CI)
2. Deploy → health check → verify clean logs
Log: .agents/orchestrator/logs/{TASK_ID}-deploy.log
Gate: No deploy errors, health pass, app responds, no error logs
```

### `phase3-regression-testing.txt`
```
TESTER agent | Task {TASK_ID} | {PROJECT_DIR} | Phase 3: Regression Testing
Deploy: {DEVICE_TYPE} | Tests: {TEST_CMD} | Logs: {LOG_CMD}
1. Verify healthy: {BASELINE_CMD} → run full suite: {TEST_CMD}
2. Per failure: capture trace, check pre-existing vs new regression
3. Set regression_result = "pass" (→ feature_testing) or "fail" (→ feedback to implementing)
Output: .agents/runtime/tester/workspace/test-cases/{TASK_ID}-regression.md
Update: jq --arg tid "{TASK_ID}" '(.tasks[] | select(.id == $tid)).regression_result = "pass"' .agents/task-board.json > .agents/task-board.json.tmp && mv .agents/task-board.json.tmp .agents/task-board.json
```

### `phase3-feature-testing.txt`
```
TESTER agent | Task {TASK_ID} | {PROJECT_DIR} | Phase 3: Feature Testing
Deploy: {DEVICE_TYPE} | Tests: {TEST_CMD}
Inputs: design-docs/{TASK_ID}-tdd-plan.md, requirements/{TASK_ID}-requirements.md
1. Run feature tests from TDD plan → verify acceptance criteria
2. Per failure: test gap vs impl bug
3. Set feature_result = "pass" (→ log_analysis) or "fail" (→ feedback to tdd_design)
Output: .agents/runtime/tester/workspace/test-cases/{TASK_ID}-feature-test.md
Update: jq --arg tid "{TASK_ID}" '(.tasks[] | select(.id == $tid)).feature_result = "pass"' .agents/task-board.json > .agents/task-board.json.tmp && mv .agents/task-board.json.tmp .agents/task-board.json
```

### `phase3-log-analysis.txt`
```
TESTER agent (with DESIGNER input) | Task {TASK_ID} | {PROJECT_DIR} | Phase 3: Log Analysis
Logs: {LOG_CMD} | Device: {DEVICE_TYPE} | DFMEA: design-docs/{TASK_ID}-dfmea.md
1. Collect logs → analyze: errors, warnings, perf anomalies, security, resource leaks
2. Cross-ref DFMEA predicted risks
3. Set log_analysis_result = "clean" (→ documentation) or "anomaly" (→ feedback to ci_fixing)
Output: .agents/runtime/tester/workspace/test-cases/{TASK_ID}-log-analysis.md
Update: jq --arg tid "{TASK_ID}" '(.tasks[] | select(.id == $tid)).log_analysis_result = "clean"' .agents/task-board.json > .agents/task-board.json.tmp && mv .agents/task-board.json.tmp .agents/task-board.json
```

### `phase3-documentation.txt`
```
DESIGNER agent | Task {TASK_ID} | {PROJECT_DIR} | Phase 3: Documentation

Inputs: requirements/{TASK_ID}-requirements.md, design-docs/{TASK_ID}-design.md, test-cases/
1. Release notes: features, fixes, breaking changes, migration steps
2. Update: README.md, API docs, config docs
Output: docs/{TASK_ID}-release-notes.md | Commit changes
Gate: All features documented, no undocumented breaking changes, valid links
```
