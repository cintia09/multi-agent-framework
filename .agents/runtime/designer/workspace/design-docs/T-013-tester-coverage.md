# T-013: Enhance Tester Coverage Analysis and Flaky Detection

## Context

The current `agent-tester SKILL.md` defines complete test workflows (Flow A/B) and issue tracking, but lacks:
1. **Coverage analysis**: No systematic coverage detection, parsing, or high-priority uncovered area identification
2. **Flaky test detection**: Intermittent test failures destabilize CI, with no current detection or isolation mechanism
3. **E2E test guidance**: Missing end-to-end testing best practices such as Page Object Model and Playwright integration

## Decision

Enhance `agent-tester SKILL.md` with three core sections: Coverage Analysis Workflow + Flaky Detection & Isolation + E2E Testing Best Practices.

## Alternatives Considered

| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| **A: SKILL.md enhancement (selected)** | Framework-consistent, language-agnostic | Relies on Agent compliance | ✅ Selected |
| **B: Integrate Codecov/Coveralls** | Automated coverage tracking | Requires external service and CI | ❌ External dependency |
| **C: Custom coverage scripts** | Precise control | Separate implementation per language | ❌ Maintenance cost |
| **D: Handle only in Implementer** | Reduces Tester burden | Unclear responsibility; Tester should verify quality | ❌ Wrong ownership |

## Design

### Architecture

```
Enhanced Tester Workflow:

┌─────────────────────────────────────────────┐
│  Existing Flow A: New Task Testing           │
│  ...                                         │
│  New step: Coverage Analysis                 │
│  ┌────────────────────────────────────┐       │
│  │ Detect test framework              │       │
│  │    ▼                               │       │
│  │ Run coverage command               │       │
│  │    ▼                               │       │
│  │ Parse coverage report              │       │
│  │    ▼                               │       │
│  │ Identify high-priority uncovered   │       │
│  │ areas                              │       │
│  │    ▼                               │       │
│  │ Output coverage summary            │       │
│  └────────────────────────────────────┘       │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│  Flaky Detection Flow                        │
│  ┌────────────────────────────────────┐       │
│  │ Test failed?                       │       │
│  │    │yes                            │       │
│  │    ▼                               │       │
│  │ Re-run 3-5 times                   │       │
│  │    ▼                               │       │
│  │ Results inconsistent?              │       │
│  │  ──yes──→ Mark as Flaky            │       │
│  │    │no          ▼                  │       │
│  │    ▼       test.fixme() quarantine │       │
│  │ Confirmed real failure             │       │
│  │    ▼                               │       │
│  │ Report issue                       │       │
│  └────────────────────────────────────┘       │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│  E2E Testing Best Practices                  │
│  ├── Page Object Model pattern               │
│  ├── data-testid selector strategy           │
│  ├── Playwright recommended config           │
│  └── Screenshots/video on failure            │
└─────────────────────────────────────────────┘
```

### Data Model

**Coverage report format**:

```json
{
  "task_id": "T-013",
  "timestamp": "2026-04-06T16:00:00Z",
  "framework": "jest",
  "overall": {
    "lines": 83.2,
    "branches": 76.5,
    "functions": 88.1,
    "statements": 82.9
  },
  "uncovered_critical": [
    {
      "file": "src/hooks/agent-post-tool-use.ts",
      "lines": "45-62",
      "reason": "auto-dispatch logic branch not covered"
    }
  ]
}
```

**Flaky test record format**:

```json
{
  "test_name": "should auto-dispatch on status change",
  "file": "tests/hooks.test.ts:42",
  "runs": [
    {"run": 1, "result": "FAIL", "duration_ms": 1200},
    {"run": 2, "result": "PASS", "duration_ms": 980},
    {"run": 3, "result": "FAIL", "duration_ms": 1150},
    {"run": 4, "result": "PASS", "duration_ms": 1020},
    {"run": 5, "result": "PASS", "duration_ms": 990}
  ],
  "pass_rate": "60%",
  "verdict": "FLAKY",
  "action": "quarantine with test.fixme()",
  "quarantined_at": "2026-04-06T16:30:00Z"
}
```

### API / Interface

**New sections in agent-tester SKILL.md**:

#### 1. Coverage Analysis Workflow

```markdown
### Coverage Analysis Workflow

After test execution, perform coverage analysis:

#### Step 1: Detect Test Framework
Auto-detect the project's test framework and coverage tool:
| Framework | Coverage Command | Report Format |
|-----------|-----------------|---------------|
| Jest | `npx jest --coverage --coverageReporters=text` | Terminal text |
| Vitest | `npx vitest run --coverage` | Terminal text |
| pytest | `pytest --cov=src --cov-report=term-missing` | Terminal text |
| Go | `go test -cover -coverprofile=coverage.out ./...` | Text |

#### Step 2: Run Coverage
Execute the corresponding command from the table above, capture output.

#### Step 3: Parse Report
Extract key metrics: line coverage, branch coverage, function coverage.

#### Step 4: Identify High-Priority Uncovered Areas
Priority order:
1. Uncovered lines in modified files (files_modified) — highest priority
2. Uncovered branches in core business logic files
3. Error handling paths (catch/error/reject)

#### Step 5: Output Summary
Write coverage summary to test report; flag as "needs attention" if below 80%.
```

#### 2. Flaky Test Detection and Isolation

```markdown
### Flaky Test Detection and Isolation

When a test fails, first determine if it's Flaky (intermittent failure):

#### Detection Flow
1. Test fails → do NOT immediately report issue
2. Re-run the test 3-5 times (using `--bail` or running individually)
3. Calculate pass rate:
   - Pass rate 100% → original failure was sporadic, mark as suspected Flaky, continue monitoring
   - Pass rate 0% → confirmed as real failure, report issue
   - Pass rate 1-99% → confirmed as Flaky

#### Isolation Actions
For confirmed Flaky tests:
1. Mark with `test.fixme()` / `test.skip()` + explanatory comment
2. Create Flaky issue in `T-NNN-issues.json`, severity MEDIUM
3. Record Flaky details to `.agents/runtime/tester/workspace/flaky-tests.json`

#### Root Cause Analysis Hints
Common Flaky root causes:
- Time dependency (setTimeout, Date.now)
- Network dependency (external API calls)
- State leakage (shared state between tests)
- Race conditions (non-deterministic async operation order)
```

#### 3. E2E Testing Best Practices

```markdown
### E2E Testing Best Practices

For web application end-to-end testing, follow these practices:

#### Page Object Model (POM)
Create a corresponding Page Object class for each page:
```typescript
// pages/LoginPage.ts
export class LoginPage {
  constructor(private page: Page) {}
  
  async login(username: string, password: string) {
    await this.page.getByTestId('username').fill(username);
    await this.page.getByTestId('password').fill(password);
    await this.page.getByTestId('login-btn').click();
  }
}
```

#### Selector Strategy
Priority (high to low):
1. `data-testid` — most stable, unaffected by UI changes
2. `role` + `name` — semantic, supports accessibility
3. `text` — user-visible text
4. ❌ Avoid: CSS class, XPath, DOM structure

#### Playwright Recommended Config
```typescript
// playwright.config.ts
export default defineConfig({
  retries: 2,
  use: {
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    trace: 'on-first-retry',
  },
});
```

#### Evidence Collection on Failure
Automatically collect on test failure:
- Screenshot
- Video recording
- Network logs (HAR)
- Console logs
Save to `.agents/runtime/tester/workspace/e2e-artifacts/`
```

### Implementation Steps

1. **Update `skills/agent-tester/SKILL.md` — Coverage analysis section**:
   - Add "Coverage Analysis" step at end of existing Flow A workflow
   - Define coverage commands for 4 mainstream test frameworks
   - Define identification rules for high-priority uncovered areas
   - Define coverage summary output format

2. **Add Flaky test detection section**:
   - Define detection flow: failure → re-run 3-5 times → determination
   - Define pass rate thresholds and corresponding actions
   - Define isolation actions (test.fixme + issue + record file)
   - List common Flaky root causes

3. **Add E2E testing best practices section**:
   - Define Page Object Model pattern with code examples
   - Define selector priority strategy
   - Provide Playwright recommended config
   - Define evidence collection rules on failure

4. **Define output file paths**:
   - Coverage report: `.agents/runtime/tester/workspace/coverage-summary.json`
   - Flaky records: `.agents/runtime/tester/workspace/flaky-tests.json`
   - E2E evidence: `.agents/runtime/tester/workspace/e2e-artifacts/`

5. **Update existing Flow A workflow**:
   - After "run tests" step, add "coverage analysis" sub-step
   - Before "report issue" step, add "Flaky detection" check
   - Add coverage summary and Flaky statistics to test report template

6. **Update test report template**:
   - Add "Coverage Summary" section
   - Add "Flaky Tests" section
   - Add "E2E Test Results" section (with screenshot links)

## Test Spec

### Unit Tests

| # | Test Scenario | Expected Result |
|---|--------------|-----------------|
| 1 | SKILL.md contains coverage analysis section | All 4 framework coverage commands present |
| 2 | SKILL.md contains Flaky detection section | Re-run count and determination thresholds clearly defined |
| 3 | SKILL.md contains E2E section | POM pattern, selector strategy, Playwright config all present |
| 4 | Flaky record format defined | JSON format includes runs, pass_rate, verdict |

### Integration Tests

| # | Test Scenario | Expected Result |
|---|--------------|-----------------|
| 5 | Test fails, re-run 3 times, 2 pass | Marked as Flaky, isolated with test.fixme() |
| 6 | Test fails, re-run 3 times, 0 pass | Confirmed as real failure, issue reported |
| 7 | Coverage < 80% | Test report flagged "needs attention", uncovered areas listed |
| 8 | E2E test fails | Screenshots and video auto-collected to e2e-artifacts/ |

### Acceptance Criteria

- [ ] G1: Coverage analysis workflow includes framework detection, execution, parsing, high-priority area identification
- [ ] G2: Flaky detection includes 3-5 re-runs, pass rate determination, test.fixme() isolation
- [ ] G3: E2E section includes POM pattern, data-testid strategy, Playwright config, failure screenshots

## Consequences

**Positive**:
- Coverage is quantitatively trackable; high-priority blind spots get tests first
- Flaky tests no longer block CI pipeline, but are still tracked for fixing
- E2E testing has standardized practices; new Agents can quickly get started

**Negative/Risks**:
- Coverage commands may need adjustment due to project-specific configurations
- Flaky re-runs (3-5 times) increase test execution time
- POM pattern increases initial writing cost (but reduces maintenance cost)

**Future Impact**:
- T-011 Implementer's coverage threshold can work in concert with Tester's coverage analysis
- Flaky records can be used for project-level quality analysis
