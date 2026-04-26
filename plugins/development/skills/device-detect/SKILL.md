---
id: device-detect
name: device-detect
title: device-detect skill (development plugin)
summary: Enumerate execution-environment hints under a target directory (markers, hidden config files, sibling scripts) so the test-planner can do a memory lookup and, if that misses, ask the user about the right environment. Plugin-shipped, called by test-planner step 2.
tags:
  - development
  - testing
  - device-detect
  - skill
  - plugin-shipped
---
# device-detect — plugin-shipped skill (development plugin)

## Role

Enumerate every file / directory under `<target-dir>` that *might* be
an execution-environment hint, classify each by a generic bucket, and
emit a JSON envelope. The skill is **deliberately liberal** — it does
not decide what kind of device or simulator the target is, only what
markers exist. Classification is the test-planner's job, and it does
that by:

1. Searching workspace memory for a matching environment record:
   `<codenook> knowledge search "test-environment target=<basename>"`.
2. If memory is silent, asking the user to identify the environment.

## CLI

```
detect.py --target-dir <dir> [--json]
```

## Detection (generic markers, no device-type hard-coding)

| Marker pattern under `<target>`                     | Bucket            |
|-----------------------------------------------------|-------------------|
| `pyproject.toml` / `setup.py` / `pytest.ini`        | `local-python`    |
| `package.json`                                      | `local-node`      |
| `go.mod`                                            | `local-go`        |
| Any `.codenook-test-env*` / `.test-env*` file       | `recorded-env`    |
| Any dot-config file matching `*.cfg` / `*.toml` / `*.yaml` at the root that does not match a known software runner | `unknown-config` |
| Any `scripts/run-*-tests.sh`                        | `custom-runner`   |
| (none of the above)                                 | `unknown`         |

The buckets are intentionally generic (`local-*`, `recorded-env`,
`unknown-config`, `custom-runner`, `unknown`) — the *specific* device
or simulator type (ADB / QEMU / SSH-into-board / JTAG / network
fixture / …) is **never** decided here. That decision belongs to the
calling role + memory + user.

## JSON envelope (`--json`)

```json
{
  "target": "src/",
  "buckets": ["local-python", "custom-runner"],
  "primary": "local-python",
  "markers": {
    "local-python": ["pyproject.toml"],
    "custom-runner": ["scripts/run-board-tests.sh"]
  },
  "memory_search_hint": "test-environment target=foo"
}
```

`primary` is the **first-seen non-`unknown` bucket** in detection
order (markers above are scanned roughly cheapest → broadest:
`local-*` → `recorded-env` → `custom-runner` → `unknown-config`).
The calling role should still ask the user to confirm when more than
one bucket is reported, OR when memory does not yield a matching
record.

`memory_search_hint` is a suggested query string — the calling role is
free to refine it (add tags, the repo name, etc.).

## Exit codes

| code | meaning |
|------|---------|
| 0    | scan completed (regardless of how many hits, including `unknown`) |
| 2    | invalid args / target dir missing |

