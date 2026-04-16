# CodeNook Pipeline — Full Workflow (v4.9.2+)

## Overview

CodeNook uses a 10-phase pipeline with 5 specialized agents. Each phase has
a Human-in-the-Loop (HITL) gate. The implementation phase includes automatic
build verification and local review. The review phase has 3 stages (local +
remote + CI). The test phase operates on real devices.

```
requirements → design → impl_plan → impl_execute → review_plan → review_execute → test_plan → test_execute → accept_plan → accept_execute → done
```

---

## Phase 1-2: Requirements + Design

```
requirements → HITL → design → HITL → design_approved
(acceptor)           (designer)
```

- **Acceptor** gathers requirements from user, produces `requirement-doc.md`
- **Designer** produces architecture and `design-doc.md`

---

## Phase 3: Implementation Plan

```
design_approved → implementer(plan) → implementation-doc.md → HITL → impl_planned
```

- **Implementer** produces TDD plan, file plan, dependency & risk analysis

---

## Phase 4: Implementation Execute (with automatic gates)

```
impl_planned → implementer(execute)
  ├─ Step 1-3: TDD (Red → Green → Refactor)
  │
  ├─ Step 3b: 🔨 BUILD VERIFICATION (automatic)
  │   ├─ Production code compilation
  │   └─ Full unit test suite
  │   ❌ Failure → auto-retry implementer with error feedback
  │
  ├─ Step 3c: 🔍 QUICK LOCAL REVIEW (automatic)
  │   ├─ Reviewer agent performs local code review
  │   └─ Checks logic, security, maintainability
  │   ❌ CHANGES_REQUESTED → auto-retry implementer with review feedback
  │
  ├─ Step 4: DFMEA analysis
  ├─ Step 5: Local commit only (NO push to remote)
  └─ → HITL gate → user decides → impl_done
```

**Key**: Build + UT + local review all happen automatically before HITL gate.

---

## Phase 5: Review Plan

```
impl_done → reviewer(plan) → review-prep.md → HITL → review_planned
```

- **Reviewer** collects review standards, scope, checklist, focus areas

---

## Phase 6: Review Execute (3 Stages)

```
review_planned → reviewer(execute)
  │
  ├─ Stage 1: 🔍 LOCAL REVIEW
  │   ├─ Code analysis (logic/security/reliability/maintainability)
  │   ├─ Run test suite + static analysis
  │   └─ Checklist verification
  │   ❌ Critical issues → CHANGES_REQUESTED → impl_planned
  │
  ├─ Stage 2: 🌐 REMOTE REVIEW
  │   ├─ Push to Gerrit / GitHub PR / GitLab MR
  │   ├─ Monitor remote reviewer feedback
  │   └─ Merge remote feedback into report
  │   ❌ Remote rejection → CHANGES_REQUESTED → impl_planned
  │
  ├─ Stage 3: ⚙️ CI VERIFICATION
  │   ├─ Trigger/monitor CI pipeline (Jenkins/GitHub Actions/GitLab CI)
  │   ├─ Collect: build status, test results, coverage, lint
  │   └─ Record CI artifacts
  │   ❌ CI failure → CHANGES_REQUESTED → impl_planned
  │
  └─ Final: review-report.md → HITL
     ✅ APPROVED → review_done
```

**⚠️ CI must pass before entering the test phase.**

---

## Phase 7: Test Plan (Module + System Testing)

```
review_done → tester(plan) → test-plan.md → HITL → test_planned
  ├─ Module test scenarios (inter-component integration)
  ├─ System test scenarios (real device validation)
  ├─ Device environment setup
  └─ Regression strategy
```

**Pre-condition**: `review_done` status requires reviewer verdict == `APPROVED` (includes CI pass).

---

## Phase 8: Test Execute (Real Devices)

```
test_planned → tester(execute)
  ├─ 📦 Deploy test bundle to target device
  ├─ ✅ Verify deployment succeeded
  ├─ 🔧 Module testing (inter-component interfaces)
  ├─ 🖥️ System testing (end-to-end on real hardware)
  ├─ 🔄 Regression testing (baseline comparison)
  └─ 📋 test-report.md → HITL
     ✅ PASS → test_done
     ❌ FAIL → impl_planned (back to implementer)
```

**Note**: Unit tests are the implementer's responsibility (build verification). The tester focuses on module and system tests on actual devices.

---

## Phase 9-10: Acceptance

```
test_done → acceptor(plan) → HITL → acceptor(exec) → HITL → done ✅
```

**Phase 9 — Acceptance Plan** (`acceptance-plan.md`):
- Acceptor reviews all upstream documents and defines acceptance criteria
- Maps requirements to verification methods
- HITL approves the acceptance plan

**Phase 10 — Acceptance Execution** (`acceptance-report.md`):
- Acceptor verifies each acceptance criterion against evidence
- Produces final acceptance report with deployment readiness assessment
- HITL makes the final go/no-go decision

---

## Quality Gates Summary

### Implementation Phase (Automatic, no human intervention)

| Gate | What it checks |
|------|---------------|
| Build Verification | Production code compiles + full UT passes |
| Quick Local Review | Reviewer agent approves code quality |

### Review Phase (3 Stages)

| Stage | What it checks |
|-------|---------------|
| Local Review | Code analysis + checklist + static analysis |
| Remote Review | Gerrit/GitHub/GitLab reviewer approval |
| CI Verification | Pipeline passes (build + test + coverage) |

### Test Phase (Real Devices)

| Gate | What it checks |
|------|---------------|
| Bundle Deploy | User provides bundle + deployment verified |
| Module Testing | Inter-component integration tests |
| System Testing | End-to-end validation on real hardware |
| Regression Testing | No existing functionality broken |

---

## Rejection Paths

| From | Condition | Goes to |
|------|-----------|---------|
| impl_execute | Build fails / UT fails | Retry implementer (automatic) |
| impl_execute | Local review rejects | Retry implementer (automatic) |
| review_execute | Local review critical issues | `impl_planned` |
| review_execute | Remote review rejects | `impl_planned` |
| review_execute | CI fails | `impl_planned` |
| test_execute | Tests fail on device | `impl_planned` |
| accept_execute | Acceptance rejects | `design_approved` |

---

## Phase Entry Questions

Each phase asks configuration questions before starting. Key ones:

| Phase | Key Questions |
|-------|--------------|
| impl_execute | Build command, Test command, Local review toggle, Commit strategy |
| review_execute | Review stages (local/remote/CI), Remote target (Gerrit/GitHub), CI pipeline |
| test_plan | Test scope (module/system), Test environment (real device/simulator) |
| test_execute | Test bundle path/ID, Device access method, Failure policy |

---

*Generated for CodeNook v4.9.2+*
