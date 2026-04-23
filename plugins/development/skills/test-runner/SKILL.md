---
name: test-runner
title: test-runner skill (development plugin)
summary: Plugin-shipped skill that wraps the workspace test runner (pytest / jest / go test) so the tester role can issue a single command and parse a single exit code. Defines the CLI surface and exit-code contract.
tags:
  - development
  - testing
  - test-runner
  - skill
  - plugin-shipped
---
# test-runner — plugin-shipped skill (development plugin)

## Role

Wrap the workspace's actual test runner (pytest / jest / go test) so the
tester role can issue a single command and parse a single exit code.

## CLI

```
runner.sh --target-dir <dir> [--json]
```

## Detection

The script picks a runner based on the *first* match found under
`<target-dir>`:

| Marker file present                                | Runner invoked          |
|----------------------------------------------------|--------------------------|
| `pyproject.toml`, `setup.py`, `pytest.ini`, `tox.ini` | `pytest <target-dir>` |
| `package.json` (with a `test` script)              | `npm test --prefix <dir>` |
| `go.mod`                                           | `go test ./...`          |

If no marker is found, the script exits 0 with a `runner=none` note —
the tester is responsible for surfacing that as `verdict: blocked`.

## Exit codes / verdict mapping

| runner.sh exit | verdict suggestion |
|----------------|---------------------|
| 0              | `ok`                |
| 1              | `needs_revision`    |
| 2              | `blocked` (runner missing or crashed) |

## JSON envelope (`--json`)

```json
{
  "ok": true,
  "runner": "pytest",
  "exit_code": 0,
  "duration_ms": 1842
}
```

## Why a plugin-shipped skill (not a workspace skill)

This wrapper is specific to the development plugin's test phase. Per
the plugin.yaml `skills.consumes` declaration, it sits alongside other
plugin-shipped skills under `.codenook/plugins/development/skills/`
and never collides with a workspace-wide skill of the same name.
