# Acceptance Criteria — Implement Phase

Check each item against the implementer's output. Mark each as:
- ✅ pass — criterion fully satisfied
- ❌ fail — criterion violated
- ⚠️ partial — partially satisfied with caveats

## Critical Criteria (any fail → verdict: fail)

### C1. Syntactic correctness
The code is valid in the target language (parses without errors).

### C2. Files specified
Every code block has an explicit target file path (e.g. `# File: src/cli.py`).

### C3. Requirements coverage
Every goal/input/output listed in the clarify spec is addressed (or explicitly noted as out-of-scope).

### C4. No fabricated APIs
Imports, library calls, and function signatures refer only to real APIs in the target language/framework indicated by `project_env`.

### C5. Conventions compliance
Follows `project_conv` for naming, formatting, error handling.

## Advisory Criteria (any fail → verdict: needs_human, not automatic fail)

### A1. Test coverage
Includes at least one test per public function (if `project_env` indicates a test framework).

### A2. Error handling
Non-trivial operations handle obvious failure modes.

### A3. Size boundary
Output ≤ 500 lines of code. If exceeded, suggest split.

## Output Format (write to `validations/phase-N-validation.md`)

```markdown
# Validation Report — T-xxx phase-N

## Critical
- C1 ✅ / ❌ / ⚠️: <note>
- C2 ...
- C3 ...
- C4 ...
- C5 ...

## Advisory
- A1 ...
- A2 ...
- A3 ...

## Verdict
pass | fail | needs_human

## Reason
<≤ 50 chars>
```
