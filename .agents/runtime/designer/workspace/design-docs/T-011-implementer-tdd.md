# T-011: Enhance Implementer TDD Discipline and Verification Loop

## Context

The current `agent-implementer SKILL.md` contains a basic TDD workflow (Flow A), but lacks:
1. **Strict git checkpoint discipline**: No requirement to git commit at each RED/GREEN/REFACTOR step, making rollback difficult
2. **Coverage threshold**: No explicit coverage requirement; implementer may write insufficient tests
3. **Incremental build fix workflow**: No systematic strategy for fixing build errors one at a time
4. **Pre-commit verification checklist**: No mandatory quality checks before FSM transition

Borrowing from ECC (Effective Copilot Coding) best practices, these disciplines need to be integrated into the Implementer workflow.

## Decision

Enhance `agent-implementer SKILL.md` with three core sections:
1. **TDD Strict Mode**: RED/GREEN/REFACTOR with git checkpoint at each step + 80% coverage threshold
2. **Build Fix Workflow**: Fix errors one at a time + rebuild + progress tracking
3. **Pre-Review Verification Checklist**: 5-step quality check chain

## Alternatives Considered

| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| **A: SKILL.md enhancement (selected)** | No extra tools needed, consistent with existing framework | Relies on Agent compliance | ✅ Selected |
| **B: Hook enforcement** | Hard constraint | Hooks are shell scripts, cannot run tests/lint | ❌ Technical limitation |
| **C: External CI integration** | True automation | Adds external dependency, out of framework scope | ❌ Scope creep |
| **D: Separate verification Agent** | Separation of concerns | Agent count bloat, longer workflow | ❌ Over-engineering |

## Design

### Architecture

```
Enhanced Implementer Workflow:

┌─────────────────────────────────────────────┐
│  Flow A: TDD Strict Mode                     │
│  ┌─────┐   ┌─────┐   ┌─────────┐            │
│  │ RED │──→│GREEN│──→│REFACTOR │──→ loop     │
│  │ 🔴  │   │ 🟢  │   │ 🔵      │            │
│  └──┬──┘   └──┬──┘   └────┬────┘            │
│     │git      │git        │git              │
│     │commit   │commit     │commit           │
│     ▼         ▼           ▼                 │
│  checkpoint  checkpoint  checkpoint          │
│                                              │
│  Coverage >= 80%? ──no──→ Add tests ──→ loop │
│       │yes                                   │
│       ▼                                      │
│  ┌──────────────────────────────────────┐    │
│  │  Pre-Review Verification             │    │
│  │  typecheck → build → lint → test     │    │
│  │  → security scan                     │    │
│  │  All ✅ → FSM: implementing→reviewing │    │
│  └──────────────────────────────────────┘    │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│  Build Fix Workflow (on build failure)        │
│  ┌────────┐  ┌──────────┐  ┌─────────┐      │
│  │Read err│──→│Fix 1st   │──→│Rebuild  │      │
│  │list    │  │error     │  │         │      │
│  └────────┘  └──────────┘  └────┬────┘      │
│                                  │           │
│                  More errors? ──yes──→ loop   │
│                         │no                  │
│                         ▼                    │
│                    Build success ✅           │
└─────────────────────────────────────────────┘
```

### API / Interface

**New sections in agent-implementer SKILL.md**:

#### 1. TDD Strict Mode

```markdown
### TDD Strict Mode

#### RED Phase 🔴
1. Write **failing tests** based on the design document
2. Run tests, confirm test failure (expected failure)
3. `git add -A && git commit -m "test: RED - <test description>"`

#### GREEN Phase 🟢
1. Write **minimum code** to make tests pass
2. Run tests, confirm all pass
3. `git add -A && git commit -m "feat: GREEN - <feature description>"`

#### REFACTOR Phase 🔵
1. Optimize code structure, eliminate duplication
2. Run tests, confirm all still pass
3. `git add -A && git commit -m "refactor: REFACTOR - <refactor description>"`

#### Coverage Threshold
- Target: **80%+** line coverage
- Check method: Run coverage tool (jest --coverage / pytest --cov / go test -cover)
- Below threshold: Add more test cases, repeat RED-GREEN cycle
- Coverage report saved to `.agents/runtime/implementer/workspace/coverage-report.txt`
```

#### 2. Build Fix Workflow

```markdown
### Build Fix Workflow

When build/compilation fails, follow this process:

1. **Collect errors**: Run build command, capture all error output
2. **Sort errors**: Sort by file and line number, start from the first
3. **Fix one at a time**:
   - Fix only the current first error
   - Rebuild immediately after fix
   - Log: `Error N/M fixed`
4. **Loop until success**: Repeat step 3 until build passes
5. **Progress tracking**: Output progress to stderr `[BUILD FIX] 3/7 errors fixed`

⚠️ Never fix multiple unrelated errors at once — fixing one at a time avoids introducing new issues.
```

#### 3. Pre-Review Verification Checklist

```markdown
### Pre-Review Verification Checklist

Before transitioning task status from `implementing` to `reviewing`, the following 5 checks **must** pass in order:

| # | Check Item | Example Command | Pass Criteria |
|---|-----------|----------------|---------------|
| 1 | Type check | `tsc --noEmit` / `mypy` | 0 errors |
| 2 | Build | `npm run build` / `go build` | exit 0 |
| 3 | Lint | `eslint .` / `flake8` | 0 errors (warnings OK) |
| 4 | Test | `npm test` / `pytest` | All pass + coverage >= 80% |
| 5 | Security scan | `npm audit` / `pip audit` | No HIGH/CRITICAL |

If any check fails, FSM state transition is **prohibited**. Fix and re-run the failing check.

Verification results saved to `.agents/runtime/implementer/workspace/verification-report.md`:
```

**Verification report template**:

```markdown
# Pre-Review Verification Report — T-NNN

| Check Item | Status | Details |
|-----------|--------|---------|
| Type check | ✅ | 0 errors |
| Build | ✅ | Build succeeded in 12s |
| Lint | ✅ | 0 errors, 3 warnings |
| Test | ✅ | 47/47 passed, 83% coverage |
| Security scan | ✅ | No vulnerabilities found |

**Conclusion**: All passed, ready to transition to reviewing phase.
```

### Implementation Steps

1. **Update `skills/agent-implementer/SKILL.md`**:
   - After existing "Flow A: New Feature Implementation", add "TDD Strict Mode" section
   - Define specific steps and git commit format for RED/GREEN/REFACTOR phases
   - Define 80% coverage threshold and verification method

2. **Add "Build Fix Workflow" section**:
   - Add after existing workflow in SKILL.md
   - Define one-at-a-time fix strategy, progress tracking format
   - Emphasize "fix only one error at a time" principle

3. **Add "Pre-Review Verification Checklist" section**:
   - Define 5-step check chain (typecheck → build → lint → test → security)
   - Provide command examples for various languages/frameworks
   - Define verification report template and storage path

4. **Update existing Flow A and Flow B**:
   - Flow A references "TDD Strict Mode" section
   - Flow B (Bug Fix) references "Build Fix Workflow"
   - Both flows reference "Pre-Review Verification" as final step

5. **Define verification report storage locations**:
   - Path: `.agents/runtime/implementer/workspace/verification-report.md`
   - Coverage report: `.agents/runtime/implementer/workspace/coverage-report.txt`

6. **Update FSM Guard rules**:
   - In `skills/agent-fsm/SKILL.md` guard rules, add:
     `implementing → reviewing` requires verification report to exist with all ✅

## Test Spec

### Unit Tests

| # | Test Scenario | Expected Result |
|---|--------------|-----------------|
| 1 | SKILL.md contains "TDD Strict Mode" section | Section exists with RED/GREEN/REFACTOR steps |
| 2 | SKILL.md contains "Build Fix Workflow" section | Section exists with one-at-a-time fix process |
| 3 | SKILL.md contains "Pre-Review Verification" section | Section exists with 5 checks |
| 4 | Git commit format defined | Contains `test: RED -`, `feat: GREEN -`, `refactor: REFACTOR -` templates |

### Integration Tests

| # | Test Scenario | Expected Result |
|---|--------------|-----------------|
| 5 | Implementer executes full TDD cycle | Produces RED/GREEN/REFACTOR three git commits |
| 6 | Build Fix after build failure | Fixes one at a time, rebuilds after each fix |
| 7 | Pre-Review verification fails | Blocked from transitioning to reviewing, retry after fix |
| 8 | Coverage < 80% | Blocked from submission, prompted to add tests |

### Acceptance Criteria

- [ ] G1: TDD section includes RED/GREEN/REFACTOR git checkpoints + 80% coverage threshold
- [ ] G2: Build Fix Workflow includes one-at-a-time fix + rebuild + progress tracking
- [ ] G3: Pre-Review Verification includes typecheck → build → lint → test → security scan 5-step check

## Consequences

**Positive**:
- Significantly improved code quality with comprehensive quality gates
- Clear git history, each step traceable and rollback-friendly
- Build issues resolved systematically, avoiding chaotic fixes

**Negative/Risks**:
- TDD strict mode increases development time (but reduces later fix time)
- Coverage threshold may be too high for some projects (but 80% is industry consensus)
- Requires strict Implementer Agent compliance

**Future Impact**:
- T-012 Reviewer can verify TDD discipline compliance (by checking git log)
- T-013 Tester can leverage coverage reports
