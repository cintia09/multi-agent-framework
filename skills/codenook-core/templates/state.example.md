# CodeNook task state.json — annotated reference
#
# This file is shipped to .codenook/schemas/state.example.md by
# `bash install.sh` (E2E-P-006). Seed a real task state.json by copying
# the JSON block below into `.codenook/tasks/T-XXX/state.json` and
# editing values.
#
# Authoritative schema: `.codenook/schemas/task-state.schema.json`.
#
# Workspace-level state.json (different shape, lists installed plugins +
# kernel version) lives at `.codenook/state.json` and is governed by
# `.codenook/schemas/installed.schema.json`.

```json
{
  "schema_version": 1,
  "task_id": "T-100",
  "title": "Implement Fibonacci helper",
  "summary": "Add iterative + memoized fib() to src/fib.py with pytest coverage.",
  "plugin": "development",
  "plugin_version": "0.1.0",
  "target_dir": "src",
  "phase": null,
  "iteration": 0,
  "max_iterations": 3,
  "dual_mode": "serial",
  "status": "in_progress",
  "history": []
}
```

## Required fields

| Field | Type | Notes |
|---|---|---|
| `schema_version` | int | Always `1` for v0.11.x. |
| `task_id` | string | Pattern `T-[A-Za-z0-9_-]+`. |
| `plugin` | string | Installed plugin id (e.g. `development`). |
| `phase` | string\|null | `null` on creation; orchestrator advances. |
| `iteration` | int ≥ 0 | Per-phase retry counter. |
| `max_iterations` | int ≥ 0 | Hard cap before HITL block. |
| `status` | enum | `pending\|in_progress\|waiting\|blocked\|done\|cancelled\|error`. |
| `history` | array | Append-only audit, populated by orchestrator-tick. |

## Common optional fields

| Field | Type | Use |
|---|---|---|
| `title` / `summary` | string | Human display, used by parent_suggester. |
| `target_dir` | string | Directory where implementer should write files. |
| `dual_mode` | `"serial"` \| `"parallel"` | Required by `clarify` and `implement` phases. |
| `parent_id` | string\|null | M10 task-chain link to a parent task. |
| `chain_root` | string\|null | M10 cached terminal ancestor (set by `codenook chain link`). |
| `config_overrides` | object | Per-task config patches. |
| `decomposed` | bool | Triggers `seed_subtasks` during planner phase. |
| `subtasks` | array | Subtask units when `decomposed=true`. |

## Recommended workflow

```
codenook task new --title "Implement X" --dual-mode serial
codenook router --task T-100 --user-turn "…"
codenook tick --task T-100
codenook decide --task T-100 --phase design --decision approve
```
