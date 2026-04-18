# Pytest conventions (development plugin — plugin-shipped knowledge)

This file is read by the tester role on demand. Conventions baked into
the development plugin's test-runner skill are listed here so the
implementer can target them up-front.

## Where tests live

- Library projects (`pyproject.toml` / `setup.py`): tests under
  `tests/` at the project root, mirroring the package layout.
- Single-file scripts: a sibling `test_<name>.py` is acceptable.

## Test naming

- Files: `test_*.py`.
- Functions: `test_<behaviour>_<expected_result>` (e.g.
  `test_filter_excludes_archived_tasks`).
- Classes: only when grouping ≥3 related tests; name `Test<Subject>`.

## Fixtures

- Shared fixtures in `tests/conftest.py`.
- Per-test fixtures inline (avoid magic action-at-a-distance).
- Use `tmp_path` (pytest builtin) for filesystem fixtures — never
  hard-code `/tmp/...`.

## Assertions

- Prefer `assert <expr>, <msg>` with a meaningful message on failure.
- Use `pytest.raises(<Exc>) as exc:` and assert on `exc.value`.

## Parametrization

- `@pytest.mark.parametrize` for ≥3 input variants of the same logic;
  inline if-branches for ≤2.

## Speed budget

- Unit test target: <100ms each.
- Mark slow tests with `@pytest.mark.slow`; the test-runner skill
  excludes them by default (`-m "not slow"`).

## What the tester role expects to see

After running the test-runner skill the tester writes a phase-5 report
with `verdict: ok` only when:

1. `pytest -q` returns 0.
2. No new `pytest.warns` regressions are introduced.
3. Coverage of changed lines is ≥80% (when `pytest-cov` is installed).
