# router-context-scan (builtin skill)

## Role

Lightweight, fast workspace inventory consumed by the **router** sub-agent
at every triage call. Produces a ≤2KB JSON envelope summarising:

- which plugins are installed (`id` + `version`)
- which tasks are active (status != done/cancelled), capped by `--max-tasks`
- pending HITL queue size
- pending fan-out subtask count (sum of `subtasks[]` lengths across active tasks)
- workspace warnings (>100MB on disk OR >10K files)

The router uses this output to decide whether to dispatch, ask for
confirmation, or escalate to HITL — without needing to walk the
workspace itself.

## CLI

```
scan.sh [--workspace <dir>] [--max-tasks N] [--json]
```

- `--workspace` — defaults to upward search for a `.codenook/` ancestor;
  exit 2 if none found.
- `--max-tasks` — truncate `active_tasks` (default 20).
- `--json` — currently the only output format (reserved for future
  human-readable mode); accepting it is a no-op flag.

## Exit codes

| code | meaning                       |
|------|-------------------------------|
| 0    | scan complete                 |
| 2    | usage / workspace not located |

## Output schema

```json
{
  "installed_plugins":  [{"id": "...", "version": "..."}, ...],
  "active_tasks":       [{"task_id": "T-001", "plugin": "...",
                          "phase": "...", "last_tick_at": "..."}],
  "hitl_pending":       0,
  "fanout_pending":     0,
  "workspace_warnings": ["..."]
}
```

## Implementation notes

- O(n) scan of `.codenook/plugins/*/plugin.yaml` and
  `.codenook/tasks/*/state.json`; no shell-outs to git/find for size.
- File-count and byte-count walks are bounded — they short-circuit
  once they exceed the warning thresholds (10K files, 100MB).
- Output is shrunk to ≤2KB by truncating `workspace_warnings` first,
  then reasons in active_tasks; never the structural fields.
