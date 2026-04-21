# hitl-adapter — Human-in-the-loop queue manipulation (terminal mode)

**Role**: Operator interface for resolving HITL gates written by
`orchestrator-tick`. Each invocation does exactly one thing.

## CLI

```bash
terminal.sh list  [--json] [--workspace <dir>]
terminal.sh show  --id <hitl-entry-id> [--workspace <dir>]
terminal.sh decide --id <id> --decision <approve|reject|needs_changes>
                   --reviewer <name> [--comment "..."] [--workspace <dir>]
```

## Exit codes

| code | meaning                                          |
|------|--------------------------------------------------|
| 0    | success                                          |
| 1    | precondition failure (already decided, no ctx)   |
| 2    | usage error (bad args, missing entry)            |

## Behaviour

* **list** — enumerates `.codenook/hitl-queue/*.json` and returns
  only entries with `decision == null`.
* **show** — prints the file at `entry.context_path` (relative to
  workspace root).
* **decide** — atomically updates the entry (via `_lib/atomic.py`),
  setting `decision`, `decided_at` (UTC ISO-8601), `reviewer`,
  `comment`. Refuses if `decision` is already non-null
  (immutable replay). Mirrors the resolved entry as one JSONL line
  to `.codenook/history/hitl.jsonl`.

## Scope

* M4: terminal/non-interactive mode only.
* M6+: interactive REPL (multi-entry triage, diff display,
  comment editor) is out of scope for M4.

→ Design basis: implementation.md M4.4
