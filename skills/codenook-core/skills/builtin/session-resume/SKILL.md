# session-resume — Session state summary

**Role**: Generates ≤1KB summary of active tasks for session bootstrap.

**Exit codes**:
- 0: success
- 2: usage error (no workspace)

**CLI**:
```bash
resume.sh [--workspace <dir>] [--json]
```

**Output** (JSON when --json):
```json
{
  "active_task": "T-NNN",
  "phase": "implement",
  "iteration": 2,
  "total_iterations": 5,
  "last_action_ts": "2026-04-18T10:00:00Z",
  "hitl_pending": false,
  "next_suggested_action": "continue tick",
  "summary": "Task T-NNN at implement phase, iteration 2/5"
}
```

**Behavior**:
- Scans `.codenook/tasks/` for all task state.json files
- Returns most recent task by `updated_at` timestamp
- Checks for pending HITL queue entries
- Skips corrupt state.json with warning to stderr
- Output guaranteed ≤1KB

→ Design basis: architecture-v6.md §3.1.4 (session-resume)
