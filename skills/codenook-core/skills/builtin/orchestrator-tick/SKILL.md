# orchestrator-tick — Advance one task one phase

**Role**: Core builtin skill that drives the per-task state machine
defined in `implementation.md §3.3`.

## CLI

```bash
tick.sh --task <T-NNN> [--workspace <dir>] [--dry-run] [--json]
```

| flag         | meaning                                              |
|--------------|------------------------------------------------------|
| `--task`     | task id (required)                                   |
| `--workspace`| explicit workspace root; otherwise upward search     |
| `--dry-run`  | compute but do not persist or invoke dispatch        |
| `--json`     | emit ≤500-byte summary JSON to stdout                |

## Exit codes

| code | meaning                                                       |
|------|---------------------------------------------------------------|
| 0    | advanced / waiting / done (no operator action required)       |
| 1    | blocked (entry-questions, HITL, max_iterations, error)        |
| 2    | usage error (missing args, task/state not found)              |
| 3    | (legacy mode only) idle/terminal phase                        |

## Output (`--json`, ≤500 bytes UTF-8)

```json
{
  "status": "advanced|waiting|blocked|done|error",
  "next_action": "<human-readable>",
  "dispatched_agent_id": "ag_T-007_clarify_1",
  "message_for_user": "<optional, ≤200 chars>"
}
```

## Algorithm (M4 + v0.2.0 profiles)

Implements the §3.3 pseudocode in full. Reads
`.codenook/plugins/<plugin>/{phases,transitions,entry-questions}.yaml`,
mutates `tasks/<id>/state.json` atomically (`_lib/atomic.py`), and
appends to `history/dispatch.jsonl` via `dispatch-audit/emit.sh`.

### Profile resolution (v0.2.0+)

When `phases.yaml` declares both a `phases:` map (the catalogue) and a
`profiles:` map (chains over that catalogue), the orchestrator selects
the active chain on every tick via `_resolve_profile(...)`:

1. `state.profile` — the cached resolution from a previous tick wins.
2. The clarifier's output frontmatter `task_type` (if present) — read
   from the most recent `outputs/phase-1-clarifier.md`.
3. `state.task_type` — caller hint from entry-questions / seed.
4. Fallback default (`feature` if defined, else the first profile).

Sources 1–3 cache the resolved name into `state.profile` so the chain
stays stable across subsequent ticks. Source 4 is *provisional*: it
does not cache, so a clarifier output that arrives later still pins
the real profile.

`transitions.yaml` is profile-keyed (`{profile: {phase: {verdict: target}}}`).
A `default:` profile may be defined; profile-specific entries inherit
unspecified `(phase, verdict)` rows from `default`.

**Backward compatibility.** A plugin that ships a flat
`phases:` *list* (e.g. `generic`, `writing`) and a flat
`transitions:` table is treated as the single implicit `default`
profile and goes through the legacy code path unchanged.

Decision branches:

| condition                                       | action                                                  |
|------------------------------------------------|---------------------------------------------------------|
| `status ∈ {done,cancelled,error}`              | return `noop`, do not persist                           |
| `phase=null`                                   | dispatch first phase's role                             |
| in-flight agent, output not ready              | return `waiting`, do not persist                        |
| in-flight + output ready                       | record history, clear in-flight, post_validate, gate    |
| `phase.gate` or `cfg.hitl_required[phase.id]`  | write `hitl-queue/<task>-<gate>.json`, return waiting   |
| transition target = `complete`                 | `status=done`, write distiller pending marker           |
| transition target = same phase                 | `iteration++`; if > `max_iterations` → blocked          |
| `phase.allows_fanout` + `state.decomposed`     | seed child tasks `<parent>-c<n>` + queue entries        |
| `phase.dual_mode_compatible` + parallel cfg    | dispatch N agents; `in_flight_agent.agent_id` is array  |
| phase set, no in-flight                        | recovery — re-dispatch with `_warning` in history       |
| entry-questions required missing               | `blocked` + `message_for_user`                          |

`output_ready` requires the file at
`tasks/<tid>/<expected_output>` to exist AND to have YAML frontmatter
`verdict: ok|needs_revision|blocked`.

## M4 scope (what is stubbed for M5+)

* **Real Task() dispatch** — `dispatch_agent()` writes a marker file
  (`outputs/phase-<id>-<role>.dispatched`) containing the rendered
  manifest and returns a deterministic `agent_id`. The kernel that
  actually invokes the Task tool from main session is M5+ infra.
  See `_tick.py:dispatch_agent` (~line 130).
* **Distiller invocation** — `dispatch_distiller()` only writes
  `.codenook/memory/_pending/<tid>.json`; the actual distiller
  agent is invoked by a sweeper in M6+.
  See `_tick.py:dispatch_distiller`.
* **config-resolve four-layer merge** — current `cfg` is just
  `state.config_overrides`. Full merge with workspace + plugin
  defaults lands in M5 (`config-resolve`).
* **post_validate scripts** — invoked when present; missing scripts
  are recorded as `_warning` rather than blocking.

## Legacy mode

When `state.json` lacks the `plugin` field, `_tick.py` falls back to
the simpler M1 stub algorithm (preflight + iteration++ + tick_log) so
the M1 bats suite (29 tests) continues to pass without churn.

→ Design basis: implementation.md §3.3, architecture.md §3.1.3, §3.1.7
