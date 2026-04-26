---
id: test-runner
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
runner.py --target-dir <dir> [--config <path>] [--json]
```

`--config` is optional; when supplied, it overrides the marker
detection and runs whatever command the config file defines (see
*Memory-first lookup*, below).

## Three-tier resolution (memory-first, ask-second)

## Security / threat model

`--config <path>` is **executed as a Python module** (via
`runpy.run_path`); the module-level `TEST_CMD` is then executed via
`subprocess.run(..., shell=True)` inside the target directory. The
Python execution gives the config full host privileges (it can `import
os; os.system(...)` etc.) before any test even starts. This is
intentional — the memory-first pattern needs full flexibility to wrap
arbitrary test runners (pytest selectors, custom wrappers, env-var
preludes, SSH-into-DUT, etc.). Consequences:

* **The caller is responsible for trust.** Only point `--config` at:
  (a) a workspace-memory entry under `.codenook/memory/knowledge/`
      that a human author wrote / reviewed; OR
  (b) a snippet just pasted by the current user via HITL.
* Never load a `--config` file fetched over the network without
  human review first.
* The skill makes **no attempt to sandbox** the config or the test
  runner — anything Python (and `shell=True`) can do, the config can
  do.
* Memory entries shipped by plugins (under `.codenook/plugins/<id>/`)
  are not auto-trusted; they reach `--config` only after a human
  promotes the embedded snippet to a memory file.

This skill is **environment-agnostic**: it does not know about ADB,
QEMU, SSH-into-board, JTAG, etc. Instead, it follows a three-tier
resolution that lets the workspace's memory describe the target, with
the user as the ultimate fallback:

1. **Marker detection inside `<target-dir>`** (legacy v0.3 behaviour).
   If the directory contains `pyproject.toml` / `setup.py` /
   `pytest.ini` / `tox.ini` → run `pytest`. `package.json` → `npm
   test`. `go.mod` → `go test ./...`. This is the fast path for
   pure-software targets.

2. **`--config <path>`** loaded as a Python module. The calling role
   resolves this file by searching memory first:

   ```bash
   <codenook> knowledge search "test-runner-config target=$(basename target_dir)"
   ```

   A config file MUST set module-level `TEST_CMD: str` and MAY set
   `TEST_LABEL: str` and `PASS_CRITERION: str` (`"exit0"` or
   `"regex:<pattern>"`). Example for a device-attached test box:

   ```python
   # .codenook/memory/knowledge/test-runner-config-rfsw-hub-dut/index.md
   # (loaded as a Python module by runner.py after extraction)
   TEST_LABEL = "ssh-dut"
   TEST_CMD = "ssh hub-lab@10.0.31.42 'cd /opt/aphg && pytest -q tests/'"
   PASS_CRITERION = r"regex:^=+\s+\d+\s+passed"
   ```

3. **`needs_user_config: true` exit (code 3)**. When neither tier 1
   nor tier 2 yields a runnable command, the script emits a JSON
   envelope flagged `needs_user_config: true` and exits with code 3.
   The calling role (tester or test-planner) must then ask the user
   via HITL for the command line + pass criterion, optionally
   promoting the answer into a memory knowledge entry so future
   runs hit tier 2 without asking.

| Marker file present                                | Runner invoked          |
|----------------------------------------------------|--------------------------|
| `pyproject.toml`, `setup.py`, `pytest.ini`, `tox.ini` | `pytest <target-dir>` |
| `package.json` (with a `test` script)              | `npm test --prefix <dir>` |
| `go.mod`                                           | `go test ./...`          |
| (no marker, no `--config`)                         | `needs_user_config`      |

## Exit codes / verdict mapping

| runner.py exit | verdict suggestion |
|----------------|---------------------|
| 0              | `ok`                |
| 1              | `needs_revision`    |
| 2              | `blocked` (runner missing or crashed) |
| 3              | `blocked` + `needs_user_config: true` (caller must ask user) |

## JSON envelope (`--json`)

```json
{
  "ok": true,
  "runner": "pytest",
  "exit_code": 0,
  "duration_ms": 1842,
  "source": "marker"
}
```

`source` is one of `marker` (tier 1), `config` (tier 2), or `none`
(tier 3, with `needs_user_config: true`).

## Why a plugin-shipped skill (not a workspace skill)

This wrapper is specific to the development plugin's test phase. Per
the plugin.yaml `skills.consumes` declaration, it sits alongside other
plugin-shipped skills under `.codenook/plugins/development/skills/`
and never collides with a workspace-wide skill of the same name.
