# router (builtin skill — self-bootstrap loader)

## Role

The **first sub-agent dispatched by the main session** on every user
turn that isn't pure chit-chat. It self-bootstraps from a fresh context
by reading its own profile + the main-session contract + the workspace
state, then hands off to `router-triage` for the actual decision.

## CLI

```
bootstrap.sh --user-input "<text>" [--workspace <dir>] [--task <T-NNN>] [--json]
```

- `--user-input` — required; the verbatim user utterance the router
  must triage. Truncated downstream by router-dispatch-build.
- `--workspace` — defaults to `$CODENOOK_WORKSPACE` then upward search
  for `.codenook/`.
- `--task` — optional active task id; surfaced verbatim in the
  envelope even if no `tasks/<id>/state.json` exists yet.
- `--json` — currently the only output mode.

## Files read (in order)

1. `<core>/agents/router.md`            — own profile (must exist)
2. `<core>/core/shell.md`               — main session contract (must exist)
3. `<ws>/.codenook/state.json`          — installed plugins + active tasks
4. `<ws>/.codenook/plugins/<id>/plugin.yaml` — for each installed plugin
5. `config-resolve --plugin __router__` — resolves model preference
   (`tier_strong` per decision #44)

`CN_CORE_ROOT` env var overrides the core directory location (used by
tests; defaults to the package root containing this skill).

## Exit codes

| code | meaning                                           |
|------|---------------------------------------------------|
| 0    | bootstrapped, ready (envelope on stdout)          |
| 1    | bootstrap failure (missing profile/shell/state)   |
| 2    | usage error                                       |

## Output schema

```json
{
  "role": "router",
  "context": {
    "active_tasks":      ["T-001", ...],
    "active_task":       "T-007",   // null if --task not passed
    "installed_plugins": [{"id": "...", "version": "...",
                           "intent_patterns": [...], "_error": "..."?}],
    "model":             "opus-4.7"
  },
  "ready": true
}
```
