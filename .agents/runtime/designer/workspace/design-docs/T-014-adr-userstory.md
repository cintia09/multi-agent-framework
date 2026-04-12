# T-014: Add ADR Format to Designer, User Story Format to Acceptor

## Context

In the current framework:
1. **Designer's design document template** lacks ADR (Architecture Decision Record) format — no explicit "Decision", "Alternatives", and "Consequences" sections, making design decision rationale and trade-offs opaque
2. **Designer has no goal coverage self-check** — design documents may miss corresponding designs for some Goals
3. **Acceptor's requirement format** lacks user story template — Goal descriptions lean toward technical implementation, missing user perspective (who uses it, why, what value it brings)

## Decision

1. Upgrade design document template to ADR format in `agent-designer SKILL.md`
2. Add "Goal Coverage Self-Check" step in `agent-designer SKILL.md`
3. Add "User Story Format" guidance in `agent-acceptor SKILL.md`

## Alternatives Considered

| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| **A: SKILL.md template upgrade (selected)** | Consistent with existing framework, incremental improvement | Requires updating existing documentation habits | ✅ Selected |
| **B: Separate ADR directory** | Centralized ADR management | Separated from design docs, adds maintenance point | ❌ Fragmented management |
| **C: Only update template, no self-check** | Simpler | Goal omission problem persists | ❌ Incomplete |
| **D: Adopt JIRA-style tickets** | Industry standard | Too heavyweight for a lightweight framework | ❌ Over-engineering |

## Design

### Architecture

```
Change scope:

skills/agent-designer/SKILL.md
├── Existing: Design document template (8 sections)
│   └── Upgrade to ADR format (add Decision, Alternatives, Consequences)
├── New: Goal coverage self-check step
│   └── Verify each Goal has a corresponding design section before completion
└── Existing: Flow A / Flow B
    └── Reference new template and self-check step in workflows

skills/agent-acceptor/SKILL.md
├── Existing: Functional goal definition rules
│   └── New: User story format guidance
└── Existing: Flow A: Collect requirements
    └── Reference user story format in workflow
```

### Data Model

**ADR-enhanced design document template**:

```markdown
# T-NNN: <Title>

## Context
Describe problem background, current state, and pain points. Answer "Why is this change needed?"

## Decision
Clearly state the decision. Answer "What did we decide to do?"

## Alternatives Considered
| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| A: <Option name> (selected) | ... | ... | ✅ Selected |
| B: <Option name> | ... | ... | ❌ <reason> |
| C: <Option name> | ... | ... | ❌ <reason> |

## Design
### Architecture
System architecture or module relationship diagram (ASCII art preferred)

### Data Model (if applicable)
Data structure definitions, JSON Schema, database models

### API / Interface
External interface definitions, SKILL.md change descriptions

### Implementation Steps (numbered, specific enough for implementer to execute)
1. Specific step 1...
2. Specific step 2...

## Test Spec
| # | Test Scenario | Expected Result |
|---|--------------|-----------------|
| 1 | ... | ... |

### Acceptance Criteria
- [ ] G1: ...
- [ ] G2: ...

## Consequences
### Positive
- ...

### Negative/Risks
- ...

### Future Impact
- ...
```

**Goal coverage self-check table**:

```markdown
## Goal Coverage Self-Check

| Goal ID | Goal Description | Corresponding Design Section | Coverage Status |
|---------|-----------------|----------------------------|-----------------|
| G1 | ... | Design > Architecture | ✅ Covered |
| G2 | ... | Design > API / Interface | ✅ Covered |
| G3 | ... | (missing) | ❌ Not covered — needs supplement |
```

**User story format**:

```markdown
### Goal Definition Format

Each Goal uses user story format:

**As a** [role/user],
**I want** [desired feature/behavior],
**So that** [value/benefit].

#### Examples
- **As a** project manager,
  **I want** to see an ASCII pipeline diagram in `/agent status`,
  **So that** I can understand task progress without inspecting JSON files.

- **As a** downstream Agent,
  **I want** role-relevant memory summary loaded automatically on switch,
  **So that** I get sufficient context without reading full memory files.

#### Acceptance Condition Format
Each Goal has verifiable acceptance conditions:
**Given** [precondition], **When** [action], **Then** [expected result].
```

### API / Interface

**agent-designer SKILL.md changes**:

1. **Replace existing design document template**:
   - Original 8-section template → ADR format (Context, Decision, Alternatives, Design, Test Spec, Consequences)
   - Design sub-sections retained: Architecture, Data Model, API/Interface, Implementation Steps

2. **Add "Goal Coverage Self-Check" step**:
   - After "complete design document" step in Flow A, add "Goal Coverage Self-Check" step
   - Designer must fill in self-check table before submission, confirming each Goal has corresponding design

**agent-acceptor SKILL.md changes**:

1. **Add "User Story Format" section**:
   - Added after "Functional goal definition rules"
   - Define As a / I want / So that format
   - Define Given / When / Then acceptance condition format
   - Provide 2-3 examples

### Implementation Steps

1. **Update `skills/agent-designer/SKILL.md` — Design document template**:
   - Replace existing design document template with ADR-enhanced version
   - New template includes: Context, Decision, Alternatives Considered, Design (with sub-sections), Test Spec, Consequences
   - Each section includes fill-in guidance

2. **Add "Goal Coverage Self-Check" mechanism**:
   - In SKILL.md Flow A, add "Goal Coverage Self-Check" step after "complete design document"
   - Define self-check table format: Goal ID → corresponding design section → coverage status
   - All Goals must be "✅ Covered" before design submission

3. **Update `skills/agent-acceptor/SKILL.md` — User story format**:
   - Add "User Story Format" sub-section after "Functional goal definition rules"
   - Define As a / I want / So that template
   - Define Given / When / Then acceptance condition template
   - Provide project-relevant examples (Agent scenarios)

4. **Update template references in Flow A**:
   - Designer Flow A step 3 references new ADR template
   - Acceptor Flow A step 2 references user story format

5. **Ensure backward compatibility**:
   - Existing design documents do not need rewriting
   - New template is an incremental enhancement, does not change existing field semantics

## Test Spec

### Unit Tests

| # | Test Scenario | Expected Result |
|---|--------------|-----------------|
| 1 | agent-designer SKILL.md contains ADR template | Template includes Context, Decision, Alternatives, Consequences sections |
| 2 | agent-designer SKILL.md contains goal coverage self-check | Self-check table format defined with Goal ID/design section/coverage status |
| 3 | agent-acceptor SKILL.md contains user story format | Contains As a / I want / So that template |
| 4 | agent-acceptor SKILL.md contains acceptance condition format | Contains Given / When / Then template |
| 5 | ADR template backward compatible | All required fields from existing template preserved in new template |

### Integration Tests

| # | Test Scenario | Expected Result |
|---|--------------|-----------------|
| 6 | Designer creates design doc with new template | Document contains all ADR sections |
| 7 | Designer performs goal coverage self-check | Self-check table lists all Goals with corresponding design sections |
| 8 | Self-check finds uncovered Goal | Blocks submission, requires design supplement |
| 9 | Acceptor defines Goal using user story format | Goal description includes role, behavior, value |

### Acceptance Criteria

- [ ] G1: agent-designer SKILL.md design template includes ADR sections (Decision, Context, Alternatives, Consequences)
- [ ] G2: agent-designer adds goal coverage self-check step, verifying each Goal has corresponding design
- [ ] G3: agent-acceptor SKILL.md includes user story format guidance (As a / I want / So that)

## Consequences

**Positive**:
- Design decisions transparent; future maintainers can understand "why it was designed this way"
- Recorded alternatives aid future re-evaluation of decisions
- Goal coverage self-check reduces design omissions
- User story format keeps requirements focused on value rather than implementation details

**Negative/Risks**:
- ADR format increases design document writing time
- User story format may feel forced for purely technical tasks

**Future Impact**:
- This task (T-014) itself uses ADR format, serving as its own best practice validation
- All future T-008 ~ T-013 design documents should adopt this format
