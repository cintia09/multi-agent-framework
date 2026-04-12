# T-015: Project-Level Living Documents System

## Context

In the current framework, each task's documents are scattered across Agent workspace subdirectories:

- Requirements: `.agents/runtime/acceptor/workspace/requirements/T-NNN-requirement.md`
- Design docs: `.agents/runtime/designer/workspace/design-docs/T-NNN-design.md`
- Test specs: `.agents/runtime/designer/workspace/test-specs/T-NNN-test-spec.md`
- Review reports: `.agents/runtime/reviewer/workspace/review-reports/T-NNN-review.md`
- Acceptance reports: `.agents/runtime/acceptor/workspace/acceptance-reports/T-NNN-report.md`

This fragmented storage causes three problems:

1. **No global view**: Cannot overview all tasks' requirements, designs, tests, and implementation history at once; must jump between multiple nested directories
2. **No knowledge accumulation**: Each task has isolated files; subsequent tasks cannot benefit from prior design decisions
3. **Cross-Agent information gaps**: Tester must manually locate requirement and design files in two different directories; Reviewer cannot quickly understand upstream design intent

The `docs/` directory currently only has `agent-rules.md` (collaboration rules), with no per-task accumulated project-level documentation.

## Decision

Create 6 **project-level living documents** in `docs/`, each maintained by the corresponding Agent who appends new sections after completing their task phase:

| Document | Maintainer | Append Trigger |
|----------|-----------|----------------|
| `docs/requirement.md` | Acceptor | Flow A complete (after requirement published) |
| `docs/design.md` | Designer | Flow A complete (after design finished) |
| `docs/test-spec.md` | Tester | Flow A after test case generation |
| `docs/implementation.md` | Implementer | Flow A after implementation complete |
| `docs/review.md` | Reviewer | After review complete (pass or reject) |
| `docs/acceptance.md` | Acceptor | Flow B after acceptance complete (pass or fail) |

Documents are **cumulative** — each time a new `## T-NNN: <title>` section is appended without overwriting existing content.

## Alternatives Considered

| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| **A: docs/ living documents (selected)** | Centralized global view, Git-traceable, Agent auto-maintained | Files grow with task count | ✅ Selected |
| **B: Per-task standalone document set** | Good isolation | Current approach; lacks global view and knowledge accumulation | ❌ Does not solve current problems |
| **C: SQLite database storage** | Flexible querying | Poor readability, unsuitable for human reading and Git diff | ❌ Readability sacrifice |
| **D: Single CHANGELOG.md** | Simple | Six document types mixed together, hard to locate specific info | ❌ Too coarse-grained |
| **E: Wiki system** | Feature-rich | Introduces external dependency, exceeds lightweight framework scope | ❌ Over-engineering |

## Design

### Architecture

```
Document write flow (triggered after each task phase completes):

┌─────────────────────────────────────────────────────────┐
│  Task Lifecycle                                          │
│                                                          │
│  created ─────────────────────────────────────────────── │
│     │                                                    │
│     ▼  Acceptor Flow A complete                          │
│  designing ──┬── Append docs/requirement.md              │
│     │        │   ## T-NNN: <title>                       │
│     ▼        │                                           │
│  implementing ── Designer Flow A complete                │
│     │        ├── Append docs/design.md                   │
│     │        │   ## T-NNN: <title>                       │
│     ▼        │                                           │
│  reviewing ──── Implementer Flow A complete              │
│     │        ├── Append docs/implementation.md           │
│     │        │   ## T-NNN: <title>                       │
│     ▼        │                                           │
│  testing ────── Reviewer review complete                 │
│     │        ├── Append docs/review.md                   │
│     │        │   ## T-NNN: <title>                       │
│     ▼        │                                           │
│  accepting ──── Tester Flow A complete                   │
│     │        ├── Append docs/test-spec.md                │
│     │        │   ## T-NNN: <title>                       │
│     ▼        │                                           │
│  accepted ───── Acceptor Flow B complete                 │
│              └── Append docs/acceptance.md               │
│                  ## T-NNN: <title>                       │
└─────────────────────────────────────────────────────────┘

Tester input dependencies before writing test-spec.md:

  docs/requirement.md ──┐
                        ├──→ Tester reads → generates test-spec section
  docs/design.md ───────┘

agent-init initialization:

  Step 2 (create directory structure) adds:
  ┌──────────────────────────────┐
  │  docs/                       │
  │  ├── agent-rules.md (exists) │
  │  ├── requirement.md  (new)   │
  │  ├── design.md       (new)   │
  │  ├── test-spec.md    (new)   │
  │  ├── implementation.md(new)  │
  │  ├── review.md       (new)   │
  │  └── acceptance.md   (new)   │
  └──────────────────────────────┘
```

**Change scope**:

```
New files (created by agent-init as empty templates):
  docs/requirement.md
  docs/design.md
  docs/test-spec.md
  docs/implementation.md
  docs/review.md
  docs/acceptance.md

Modified files (SKILL.md adds living document append steps):
  skills/agent-acceptor/SKILL.md     — Flow A end + Flow B end
  skills/agent-designer/SKILL.md     — Flow A end
  skills/agent-tester/SKILL.md       — Flow A step 3 adds reading + append after completion
  skills/agent-implementer/SKILL.md  — Flow A end
  skills/agent-reviewer/SKILL.md     — Review process end

Modified files (agent-init adds template creation step):
  skills/agent-init/SKILL.md         — Step 2 adds docs/ template creation

Verification script update:
  scripts/verify-init.sh             — Add existence check for 6 docs/ files
```

### Data Model

#### Living Document Common Structure

Each living document follows the same top-level structure:

```markdown
# <Document Type>

> This document is automatically maintained by <Agent Role>. A new section is appended after each task phase completes. Do not edit manually.

---

## T-001: <Task Title>

<Document-type-specific sub-sections>

### Changelog
| Date | Action | Description |
|------|--------|-------------|
| 2026-04-10 | Created | Initial version |

---

## T-002: <Another Task Title>

...
```

**Accumulation rules**:
- New sections **appended to end of file** (after the last `---` separator)
- Each task section separated by `---` (horizontal rule)
- Section title fixed format: `## T-NNN: <title from task-board.json>`
- Same task can be appended multiple times (e.g., after acceptance failure and redesign, Designer appends revision section titled `## T-NNN: <title> (Revision R2)`)

### Template Specs

#### 1. docs/requirement.md — Requirements Document (Acceptor-maintained)

Initial template (created by agent-init):

```markdown
# Requirements Document

> This document is automatically maintained by Acceptor. A new requirements section is appended after each task is published. Do not edit manually.
```

Append section template (written after Acceptor Flow A step 6):

```markdown
---

## T-NNN: <Task Title>

### Background
<Business context of the requirement, core content extracted from T-NNN-requirement.md>

### Functional Goals
| Goal ID | Description | Priority |
|---------|------------|----------|
| G1 | <Goal description> | <High/Medium/Low> |
| G2 | <Goal description> | <High/Medium/Low> |

### Acceptance Criteria
<Key acceptance conditions extracted from T-NNN-acceptance.md>

### Non-Functional Requirements
<Performance, security, compatibility requirements; write "None" if not applicable>

### Changelog
| Date | Action | Description |
|------|--------|-------------|
| <ISO date> | Created | Requirements published with N functional goals |
```

**Acceptor writing guidance**:
- Source: `acceptor/workspace/requirements/T-NNN-requirement.md` + goals array from `task-board.json`
- Not a copy-paste of the original file; **extract core summary** (keep within 30-50 lines)
- Functional goals table must correspond 1:1 with goals in task-board.json

#### 2. docs/design.md — Design Document (Designer-maintained)

Initial template:

```markdown
# Design Document

> This document is automatically maintained by Designer. A new design section is appended after each task design is completed. Do not edit manually.
```

Append section template (written before Designer Flow A step 7):

```markdown
---

## T-NNN: <Task Title>

### Decision Summary
<One paragraph summarizing the core design decision>

### Architecture Changes
<Overview of modules/files changed in this design, ASCII diagrams preferred>

### Key Design Points
1. <Design point 1: approach chosen and rationale>
2. <Design point 2: approach chosen and rationale>

### File Change List
| File Path | Operation | Description |
|-----------|----------|-------------|
| `path/to/file` | Add/Modify/Delete | <Change description> |

### Detailed Design Reference
Full design document: `.agents/runtime/designer/workspace/design-docs/T-NNN-*.md`

### Changelog
| Date | Action | Description |
|------|--------|-------------|
| <ISO date> | Created | Design complete, covering N Goals |
```

**Designer writing guidance**:
- Source: just-completed `designer/workspace/design-docs/T-NNN-*.md`
- This is a **summary version**, not a copy of the full design doc — retain decisions and architecture changes, omit detailed implementation steps
- Must include file change list (Implementer and Tester need to know impact scope)
- For revisions (Flow B), change section title to `## T-NNN: <title> (Revision RN)`, append revision record to Changelog

#### 3. docs/test-spec.md — Test Specification (Tester-maintained)

Initial template:

```markdown
# Test Specification

> This document is automatically maintained by Tester. A new test spec section is appended after each test case generation. Do not edit manually.
```

Append section template (written after Tester Flow A step 4):

```markdown
---

## T-NNN: <Task Title>

### Input Documents
- Requirements: docs/requirement.md → T-NNN section
- Design: docs/design.md → T-NNN section

### Test Matrix
| # | Test Scenario | Type | Covers Goal | Expected Result |
|---|--------------|------|------------|-----------------|
| 1 | <Scenario description> | Unit/Integration/E2E | G1 | <Expected> |
| 2 | <Scenario description> | Unit/Integration/E2E | G1, G2 | <Expected> |

### Boundary Conditions and Exceptions
| # | Boundary/Exception Scenario | Expected Behavior |
|---|---------------------------|-------------------|
| 1 | <Boundary condition> | <Expected> |

### Test Case Location
`tester/workspace/test-cases/T-NNN/`

### Changelog
| Date | Action | Description |
|------|--------|-------------|
| <ISO date> | Created | N test scenarios covering N Goals |
```

**Tester writing guidance**:
- **Must read before writing**: `docs/requirement.md` and `docs/design.md` sections for corresponding T-NNN
- "Covers Goal" column in test matrix must reference Goal IDs defined in requirement.md
- Ensure each Goal is covered by at least one test scenario
- For fix verification (Flow B), append fix verification record to existing T-NNN section's Changelog

#### 4. docs/implementation.md — Implementation Document (Implementer-maintained)

Initial template:

```markdown
# Implementation Document

> This document is automatically maintained by Implementer. A new implementation section is appended after each task implementation is completed. Do not edit manually.
```

Append section template (written after Implementer Flow A step 8 git commit):

```markdown
---

## T-NNN: <Task Title>

### Implementation Summary
<One paragraph summarizing implementation approach and key technical choices>

### Completed Goals
| Goal ID | Description | Implementation Approach | Commit |
|---------|------------|------------------------|--------|
| G1 | <Goal description> | <Brief implementation approach> | `abc1234` |
| G2 | <Goal description> | <Brief implementation approach> | `def5678` |

### File Change Statistics
- Added: N files
- Modified: N files
- Deleted: N files

### Technical Debt and Notes
<Technical debt, temporary solutions, known limitations discovered during implementation; write "None" if not applicable>

### Changelog
| Date | Action | Description |
|------|--------|-------------|
| <ISO date> | Created | N/N Goals completed, XX% coverage |
```

**Implementer writing guidance**:
- Write after `git commit` completes, before FSM state transition
- Goal completion table must match goals status in task-board.json
- Commit column should contain actual git commit hash short codes
- For bug fixes (Flow B), append fix record to existing T-NNN section's Changelog

#### 5. docs/review.md — Review Document (Reviewer-maintained)

Initial template:

```markdown
# Review Document

> This document is automatically maintained by Reviewer. A new review section is appended after each code review is completed. Do not edit manually.
```

Append section template (written after Reviewer review process step 6):

```markdown
---

## T-NNN: <Task Title>

### Review Verdict: ✅ Approved / ❌ Rejected

### Review Scope
Changed files: N, +X / -Y lines

### Issues Found
| # | Severity | File | Description | Status |
|---|----------|------|-------------|--------|
| 1 | Must fix | `path/file` | <Issue description> | Unfixed/Fixed |

(Write "No issues found" if none)

### Quality Assessment
- Build: ✅/❌
- Test: ✅/❌
- Lint: ✅/❌

### Detailed Report Reference
Full review report: `.agents/runtime/reviewer/workspace/review-reports/T-NNN-review.md`

### Changelog
| Date | Action | Description |
|------|--------|-------------|
| <ISO date> | Review | Verdict: Approved/Rejected, N issues |
```

**Reviewer writing guidance**:
- Write after review report output, before FSM state transition
- If reviewing again after rejection, append new review record to existing T-NNN section's Changelog and update issue status column

#### 6. docs/acceptance.md — Acceptance Document (Acceptor-maintained)

Initial template:

```markdown
# Acceptance Document

> This document is automatically maintained by Acceptor. A new acceptance section is appended after each acceptance is completed. Do not edit manually.
```

Append section template (written after Acceptor Flow B step 6/7):

```markdown
---

## T-NNN: <Task Title>

### Acceptance Verdict: ✅ Passed / ❌ Failed

### Goals Acceptance Results
| Goal ID | Description | Acceptance Result | Notes |
|---------|------------|-------------------|-------|
| G1 | <Goal description> | ✅ verified / ❌ failed | <Failure reason or pass notes> |
| G2 | <Goal description> | ✅ verified / ❌ failed | <Notes> |

### Acceptance Summary
<Overall assessment, including notable highlights or areas needing future improvement>

### Detailed Report Reference
Full acceptance report: `.agents/runtime/acceptor/workspace/acceptance-reports/T-NNN-report.md`

### Changelog
| Date | Action | Description |
|------|--------|-------------|
| <ISO date> | Acceptance | Verdict: Passed/Failed, N/M Goals verified |
```

**Acceptor writing guidance**:
- Goals acceptance results must match verified/failed status of goals in task-board.json
- If re-accepting after failure, append new acceptance record to existing T-NNN section's Changelog

### Implementation Steps

#### Step 1: Create 6 Living Document Initial Template Files

Create the following 6 files in the project `docs/` directory, each containing its initial template (title and description line only, no task sections):

| File | Title Line | Agent Role in Description |
|------|-----------|--------------------------|
| `docs/requirement.md` | `# Requirements Document` | Acceptor |
| `docs/design.md` | `# Design Document` | Designer |
| `docs/test-spec.md` | `# Test Specification` | Tester |
| `docs/implementation.md` | `# Implementation Document` | Implementer |
| `docs/review.md` | `# Review Document` | Reviewer |
| `docs/acceptance.md` | `# Acceptance Document` | Acceptor |

Each file's initial content format:

```markdown
# <Title>

> This document is automatically maintained by <Agent Role>. A new section is appended after each task phase completes. Do not edit manually.
```

#### Step 2: Update skills/agent-init/SKILL.md

In **Step 2 (Create directory structure)**, after the `mkdir -p` command block, add the living document template creation step.

**Insert location**: After existing Step 2 end (`mkdir -p .agents/runtime/tester/workspace/{test-cases,test-screenshots}`), before Step 3.

**Insert content**:

````markdown
### 2b. Create docs/ Living Document Templates

If `docs/` directory does not exist, create it:

```bash
mkdir -p docs
```

Create initial templates for the following 6 living documents (**only create if file does not exist; do not overwrite existing content**):

| File | Initial Content |
|------|----------------|
| `docs/requirement.md` | `# Requirements Document` + Acceptor maintenance note |
| `docs/design.md` | `# Design Document` + Designer maintenance note |
| `docs/test-spec.md` | `# Test Specification` + Tester maintenance note |
| `docs/implementation.md` | `# Implementation Document` + Implementer maintenance note |
| `docs/review.md` | `# Review Document` + Reviewer maintenance note |
| `docs/acceptance.md` | `# Acceptance Document` + Acceptor maintenance note |

Each file's initial content is two lines:
```markdown
# <Title>

> This document is automatically maintained by <Role>. A new section is appended after each task phase completes. Do not edit manually.
```

Creation logic:
```bash
# For each file, only create if it does not exist
[ ! -f docs/requirement.md ] && echo 'Creating docs/requirement.md'
[ ! -f docs/design.md ] && echo 'Creating docs/design.md'
# ... same for remaining 4 files
```
````

Also add a line in **Step 7 (Output summary)** output template:

```
Living documents: docs/ (6 living documents)
```

#### Step 3: Update skills/agent-acceptor/SKILL.md

**Change 1: Flow A append living document step**

In the existing Flow A step sequence, between step 5 (`Create task using agent-task-board skill`) and step 6 (`Update state.json`), insert new step:

```
5b. Append docs/requirement.md — append T-NNN requirements section to end of file
    - Read the just-created T-NNN-requirement.md and goals array from task-board.json
    - Extract summary content per Template Specs section 1 append template
    - Append to end of docs/requirement.md (start new section with `---`)
```

**Change 2: Flow B append living document step**

In existing Flow B, after step 7 (`If all goals are verified`) or step 8 (`If any goal is failed`), after FSM state transition, each append a step:

```
7b / 8b. Append docs/acceptance.md — append T-NNN acceptance section to end of file
    - Read acceptance report and goals verified/failed status from task-board.json
    - Generate acceptance section per Template Specs section 6 append template
    - Append to end of docs/acceptance.md
```

**Change 3: Add "Living Document Maintenance Rules" section**

Before the "Constraints" section, add the following complete section:

```markdown
## Living Document Maintenance Rules

This Agent is responsible for maintaining the following project-level living documents:
- `docs/requirement.md` — Append requirements section after Flow A completion
- `docs/acceptance.md` — Append acceptance section after Flow B completion

### Append Rules
1. Append to end of file, starting new section with `---` separator
2. Section title: `## T-NNN: <title from task-board.json>`
3. Content is a summary (not full-text copy), kept within 30-50 lines
4. Must include Changelog table
5. For revisions, append record to existing section's Changelog table; do not create new section
```

#### Step 4: Update skills/agent-designer/SKILL.md

**Change 1: Flow A append living document step**

In existing Flow A, between step 6 (`Output test spec`) and step 7 (`Use agent-fsm`), insert new step:

```
6b. Append docs/design.md — append T-NNN design section to end of file
    - Extract from just-completed design document: decision summary, architecture changes, file change list
    - Generate summary section per Template Specs section 2 append template
    - Append to end of docs/design.md
```

**Change 2: Flow B append revision record**

In existing Flow B, between step 4 (`Revise design document`) and step 5 (`Update test spec`), add:

```
4b. Update docs/design.md — append revision record to existing T-NNN section's Changelog table
    - For minor changes: append row to existing T-NNN section Changelog `| <date> | Revision | R2: <revision reason summary> |`
    - For major changes: append new section titled `## T-NNN: <title> (Revision R2)`
```

**Change 3: Add "Living Document Maintenance Rules" section**

Before the "Constraints" section, add:

```markdown
## Living Document Maintenance Rules

This Agent is responsible for maintaining the following project-level living documents:
- `docs/design.md` — Append design summary section after Flow A completion

### Append Rules
1. Append to end of file, starting new section with `---` separator
2. Section title: `## T-NNN: <title from task-board.json>`
3. Content is a design summary (not the full design document), retaining decisions and architecture changes
4. Must include file change list (downstream Agents need to know impact scope)
5. Must include Changelog table
6. For revisions, annotate revision version number (R2, R3...)
```

#### Step 5: Update skills/agent-tester/SKILL.md

**Change 1: Flow A add living document reading step**

Replace existing Flow A steps 2-3:

```
2. Read acceptance docs (acceptor/workspace/acceptance-docs/T-NNN-acceptance.md)
3. Read design docs + test specs
```

With:

```
2. Read project-level living documents as input:
   a. Read docs/requirement.md → find ## T-NNN section, extract functional goals and acceptance criteria
   b. Read docs/design.md → find ## T-NNN section, extract architecture changes and file change list
3. Supplementary reading of detailed docs (if living doc info insufficient):
   a. acceptor/workspace/acceptance-docs/T-NNN-acceptance.md
   b. designer/workspace/design-docs/T-NNN-*.md + test-specs/T-NNN-*.md
```

**Change 2: Flow A append living document step**

In existing Flow A, between step 5 (`Execute automated tests`) and step 6/7 (FSM transition), insert new step:

```
5b. Append docs/test-spec.md — append T-NNN test spec section to end of file
    - Note input sources: docs/requirement.md and docs/design.md corresponding sections
    - Generate test matrix, annotating each test scenario with covered Goal IDs
    - Generate section per Template Specs section 3 append template
    - Append to end of docs/test-spec.md
```

**Change 3: Add "Living Document Maintenance Rules" section**

Before the "Constraints" section, add:

```markdown
## Living Document Maintenance Rules

This Agent is responsible for maintaining the following project-level living documents:
- `docs/test-spec.md` — Append test spec section after Flow A test case generation

### Reading Rules (must execute before writing)
1. Read `docs/requirement.md` section `## T-NNN` → extract Goals and acceptance criteria
2. Read `docs/design.md` section `## T-NNN` → extract architecture changes and file list
3. Based on above information, design test matrix ensuring each Goal is covered by at least one test

### Append Rules
1. Append to end of file, starting new section with `---` separator
2. Section title: `## T-NNN: <title from task-board.json>`
3. Test matrix must include "Covers Goal" column
4. Must include Changelog table
5. For fix verification, append record to existing section's Changelog
```

#### Step 6: Update skills/agent-implementer/SKILL.md

**Change 1: Flow A append living document step**

In existing Flow A, between step 8 (`git commit + push`) and step 9 (`Use agent-fsm to transition to reviewing`), insert new step:

```
8b. Append docs/implementation.md — append T-NNN implementation section to end of file
    - Extract: goals completion status (from task-board.json) + git commit hashes + file change statistics (from git diff --stat)
    - Record technical debt and notes
    - Generate section per Template Specs section 4 append template
    - Append to end of docs/implementation.md
```

**Change 2: Flow B (Bug Fix) append record**

After Flow B fix completion and git commit, add:

```
Nb. Update docs/implementation.md — append fix record to existing T-NNN section's Changelog
    - Format: | <date> | Fix | Fixed issue #N: <summary>, commit `<hash>` |
```

**Change 3: Add "Living Document Maintenance Rules" section**

Before the "Constraints" section, add:

```markdown
## Living Document Maintenance Rules

This Agent is responsible for maintaining the following project-level living documents:
- `docs/implementation.md` — Append implementation section after Flow A completion

### Append Rules
1. Append to end of file, starting new section with `---` separator
2. Section title: `## T-NNN: <title from task-board.json>`
3. Goals completion table Commit column must contain actual git commit hash short codes
4. Must include Changelog table
5. For bug fixes, append fix record to existing section's Changelog
```

#### Step 7: Update skills/agent-reviewer/SKILL.md

**Change 1: Review process append living document step**

In existing review process, after step 6 (`Output review report to reviewer/workspace/review-reports/T-NNN-review.md`), before step 7 (`If passed: agent-fsm transition to testing`), insert new step:

```
6b. Append docs/review.md — append T-NNN review section to end of file
    - Extract: review verdict, issues list, quality assessment (build/test/lint results)
    - Generate summary section per Template Specs section 5 append template
    - Append to end of docs/review.md
```

**Change 2: Add "Living Document Maintenance Rules" section**

Before the "Constraints" section, add:

```markdown
## Living Document Maintenance Rules

This Agent is responsible for maintaining the following project-level living documents:
- `docs/review.md` — Append review section after review completion

### Append Rules
1. Append to end of file, starting new section with `---` separator
2. Section title: `## T-NNN: <title from task-board.json>`
3. When re-reviewing after rejection, append new record to existing section's Changelog and update issue status
4. Must include Changelog table
```

#### Step 8: Update scripts/verify-init.sh

After existing checks (recommended after "Configuration" check section), add living document check section:

```bash
# --- Living Documents ---
echo ""
echo "=== Living Documents ==="

for doc in requirement.md design.md test-spec.md implementation.md review.md acceptance.md; do
  if [ -f "docs/$doc" ]; then
    echo "  ✅ docs/$doc"
    ((pass++))
  else
    echo "  ❌ docs/$doc — missing"
    ((fail++))
  fi
done
```

Adds 6 check items (whether 6 living document files exist under docs/).

#### Step 9: Git Commit

```bash
git add docs/requirement.md docs/design.md docs/test-spec.md \
        docs/implementation.md docs/review.md docs/acceptance.md \
        skills/agent-acceptor/SKILL.md skills/agent-designer/SKILL.md \
        skills/agent-tester/SKILL.md skills/agent-implementer/SKILL.md \
        skills/agent-reviewer/SKILL.md skills/agent-init/SKILL.md \
        scripts/verify-init.sh
git commit -m "feat: T-015 project-level living documents system

- Add 6 living doc templates in docs/
- Update 5 agent SKILL.md files with append-after-stage rules
- Update agent-init to create templates during initialization
- Update verify-init.sh to check living doc files

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

## Test Spec

### Unit Tests

| # | Test Scenario | Expected Result |
|---|--------------|-----------------|
| 1 | `docs/requirement.md` initial template exists | File contains `# Requirements Document` title and "Acceptor" description |
| 2 | `docs/design.md` initial template exists | File contains `# Design Document` title and "Designer" description |
| 3 | `docs/test-spec.md` initial template exists | File contains `# Test Specification` title and "Tester" description |
| 4 | `docs/implementation.md` initial template exists | File contains `# Implementation Document` title and "Implementer" description |
| 5 | `docs/review.md` initial template exists | File contains `# Review Document` title and "Reviewer" description |
| 6 | `docs/acceptance.md` initial template exists | File contains `# Acceptance Document` title and "Acceptor" description |
| 7 | agent-acceptor SKILL.md has living doc append step | Flow A has requirement.md append step, Flow B has acceptance.md append step |
| 8 | agent-designer SKILL.md has living doc append step | Flow A has design.md append step, Flow B has revision record append |
| 9 | agent-tester SKILL.md has living doc read+append step | Flow A reads requirement.md + design.md first, then appends test-spec.md |
| 10 | agent-implementer SKILL.md has living doc append step | Flow A has implementation.md append step |
| 11 | agent-reviewer SKILL.md has living doc append step | Review process has review.md append step |
| 12 | agent-init SKILL.md has template creation step | After Step 2, has docs/ template creation step that does not overwrite existing files |
| 13 | verify-init.sh checks living docs | Contains existence checks for 6 docs/*.md files |

### Integration Tests

| # | Test Scenario | Expected Result |
|---|--------------|-----------------|
| 14 | Acceptor publishes task T-100 | docs/requirement.md has new `## T-100: <title>` section at end with functional goals table |
| 15 | Designer completes T-100 design | docs/design.md has new `## T-100: <title>` section at end with file change list |
| 16 | Tester generates T-100 test cases | Tester read T-100 sections from docs/requirement.md and docs/design.md |
| 17 | Tester completes T-100 test case generation | docs/test-spec.md has new `## T-100` section at end with "Covers Goal" column in test matrix |
| 18 | Implementer completes T-100 implementation | docs/implementation.md has new `## T-100` section at end with commit hash |
| 19 | Reviewer completes T-100 review | docs/review.md has new `## T-100` section at end with review verdict |
| 20 | Acceptor completes T-100 acceptance | docs/acceptance.md has new `## T-100` section at end with Goals acceptance results |
| 21 | T-100 and T-101 completed consecutively | Each living doc contains two `## T-NNN` sections separated by `---` in correct order |
| 22 | T-100 acceptance fails, redesign | docs/design.md T-100 section Changelog has revision record appended (or new revision section) |
| 23 | agent-init runs on new project | docs/ gets 6 living document initial templates + existing agent-rules.md unaffected |
| 24 | agent-init runs on already-initialized project | Existing docs/ living documents not overwritten |

### Acceptance Criteria

- [ ] G1: `docs/` contains 6 living document template files, each with standard structure (title, description, section template) and Changelog table
- [ ] G2: All 5 Agent SKILL.md files contain "Living Document Maintenance Rules" section and append steps in workflow
- [ ] G3: Living documents are cumulative — each task appends `## T-NNN: title` new section without overwriting existing content
- [ ] G4: Tester SKILL.md Flow A reads requirement.md + design.md before writing test-spec.md
- [ ] G5: agent-init SKILL.md creates docs/ living document templates during initialization (without overwriting existing files)

## Consequences

### Positive
- **Centralized global view**: Open any living document to overview all tasks' summaries for that phase, without navigating `.agents/runtime/` nested directories
- **Knowledge accumulation**: Subsequent tasks' Designers/Testers can reference prior tasks' design decisions and test strategies
- **Cross-Agent information chain**: Tester explicitly reads from requirement.md + design.md, making information sources traceable
- **Git-friendly**: Markdown format has good readability in Git diffs with clear change history
- **Compatible with existing system**: Living documents are incremental additions, not replacements for detailed docs in `.agents/runtime/*/workspace/`

### Negative/Risks
- **File size growth**: Each living document grows with task count (controlled via summaries rather than full-text copies, each section 30-50 lines)
- **Writing discipline dependency**: Agents must follow "append living document before FSM transition" workflow, lacking hard constraints
- **Concurrent append conflicts**: If two Agents append the same file simultaneously (theoretically impossible since only one Agent is active at a time), may cause Git conflicts

### Future Impact
- Existing tasks (T-001 ~ T-014) will have empty living document sections; no retroactive backfilling
- New tasks starting from T-015 will begin accumulating living document content
- Future considerations: auto-generate TOC index page for living documents, or provide `/docs status` command to view latest section in each document
- When files become too large, archive by year (e.g., `docs/archive/2024-design.md`)

## Goal Coverage Self-Check

| Goal ID | Goal Description | Corresponding Design Section | Coverage Status |
|---------|-----------------|----------------------------|-----------------|
| G1 | 6 living document template definitions | Template Specs — 6 templates fully defined | ✅ Covered |
| G2 | 5 Agent SKILL.md updates | Implementation Steps 3-7 — per-Agent update instructions | ✅ Covered |
| G3 | Cumulative append | Data Model > Accumulation rules + each template's append rules | ✅ Covered |
| G4 | Tester reads requirement + design | Implementation Step 5 + Tester Living Document Rules > Reading Rules | ✅ Covered |
| G5 | agent-init creates initial templates | Implementation Step 2 + Architecture > agent-init initialization | ✅ Covered |
