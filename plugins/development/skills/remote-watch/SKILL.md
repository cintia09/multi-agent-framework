---
id: remote-watch
name: remote-watch
title: remote-watch skill (development plugin)
summary: Generic poller for any remote review / CI system (Gerrit, GitHub PR, Jenkins, custom HTTP). Memory-first → user-ask. Plugin-shipped, called by submitter step 6.
tags:
  - development
  - submit
  - remote-watch
  - skill
  - plugin-shipped
---
# remote-watch — plugin-shipped skill (development plugin)

## Role

Probe a remote review / CI endpoint for the status of a submission and
return one of `merged`, `pending`, `rejected`, or `unknown`. The skill
itself knows **nothing** about Gerrit / GitHub / Jenkins / etc. —
specifics live in workspace memory or are supplied per-call.

## Security / threat model

`--config <path>` is **executed as a Python module** (via
`runpy.run_path`); the module-level `PROBE_CMD` is then executed via
`subprocess.run(..., shell=True)`. The Python execution gives the
config full host privileges (it can `import os; os.system(...)` etc.)
before any probe even starts. This is intentional — the memory-first
pattern needs full flexibility to wrap arbitrary review backends
(custom CLIs, multi-step queries, env-var preludes). Consequences:

* **The caller is responsible for trust.** Only point `--config` at:
  (a) a workspace-memory entry under `.codenook/memory/knowledge/`
      that a human author wrote / reviewed; OR
  (b) a snippet just pasted by the current user via HITL.
* Never load a `--config` file fetched over the network without
  human review first.
* The skill makes **no attempt to sandbox** the config or the probe
  — anything Python (and `shell=True`) can do, the config can do.
* Memory entries shipped by plugins (under `.codenook/plugins/<id>/`)
  are not auto-trusted; they reach `--config` only after a human
  promotes the embedded snippet to a memory file.

## Three-tier resolution (memory-first → user-ask)

1. **Tier 1 — cheap probe.** If the target dir contains a `.github/`
   folder and `gh` is on PATH, run `gh pr view <ref> --json state`. If
   it contains a `.gerrit/` marker and `ssh` to the host succeeds, run
   the recorded `ssh gerrit query` command. These two probes ship as
   defaults so the most common cases just work.

2. **Tier 2 — `--config <path>`.** The caller (submitter role) does:
   ```
   <codenook> knowledge search "remote-watch-config target=<basename>"
   ```
   If a memory hit is found, the entry contains a Python snippet that
   defines (as module-level variables):
   - `PROBE_CMD: str` — command line to run; stdout becomes status text
   - `STATUS_REGEX_MERGED: str`   — regex matched against stdout
   - `STATUS_REGEX_REJECTED: str` — regex matched against stdout
   - `STATUS_REGEX_PENDING: str`  — regex matched against stdout (default `".*"`)

   The caller then invokes `watch.py --config <hit-path>`.

3. **Tier 3 — needs_user_config.** If neither tier 1 nor tier 2
   produces a result, exit code 3 with JSON
   `{"needs_user_config": true, "memory_search_hint": "remote-watch-config target=<basename>"}`
   so the conductor can ask the user (manual paste / abort / skip)
   and optionally promote the answer to a memory entry.

## CLI

```
watch.py --target-dir <dir> [--ref <pr-or-change-id>]
         [--config <path>] [--json]
```

## JSON envelope (`--json`)

```json
{
  "status": "pending|merged|rejected|unknown",
  "source": "tier1-github|tier1-gerrit|tier2-config|none",
  "raw": "<verbatim probe stdout>",
  "memory_search_hint": "remote-watch-config target=foo"
}
```

## Exit codes

| code | meaning |
|------|---------|
| 0    | probe ran cleanly, status classified (merged/pending/rejected) |
| 2    | invalid args, OR probe ran but exited non-zero (network / auth / missing CLI) — status reported as `unknown` |
| 3    | `needs_user_config` — no tier-1 probe, no `--config` supplied |

## Memory entry shape

`.codenook/memory/knowledge/remote-watch-config-<slug>/index.md`:

```yaml
---
id: remote-watch-config-<slug>
type: knowledge
title: Remote-watch config for <repo/board/...>
summary: PROBE_CMD + STATUS_REGEX_* for <project>'s review system.
tags: [remote-watch-config, target=<basename>]
---
```
…body contains the Python snippet (as a fenced `python` block) that
the caller will pass through `--config`. The conductor is responsible
for extracting the snippet to a temp `.py` file before invoking
`watch.py`.
