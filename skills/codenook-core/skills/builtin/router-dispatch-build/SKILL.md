# router-dispatch-build (builtin skill)

## Role

Builds the canonical dispatch payload that the router sub-agent emits
when it decides to hand off to a plugin worker or a builtin skill.

Two responsibilities:

1. **Construct** a JSON payload conforming to architecture §3.1.7:
   `{role, target, task?, user_input, context: {plugins, active_phase?}}`
2. **Enforce** the 500-byte hard limit (decision #T-3) — truncating
   `user_input` to 200 chars + `"..."` if needed; failing if the
   envelope still doesn't fit after truncation. The limit is measured
   in UTF-8 bytes (CJK-safe).
3. **Audit** the dispatch by calling `dispatch-audit emit` with the
   final payload, so the architectural invariant "every handoff is
   logged" holds even when the router builds payloads inline.

## CLI

```
build.sh --target <plugin-id|skill-name>
         --user-input "<text>"
         [--task <T-NNN>]
         [--workspace <dir>]
         [--json]
```

- `--target` — required; either an installed plugin id or a builtin
  skill name. The presence of `<ws>/.codenook/plugins/<target>/plugin.yaml`
  determines `role` (plugin-worker vs builtin-skill).
- `--user-input` — required.
- `--task` — optional active task id.
- `--workspace` — defaults to upward `.codenook/` search.
- `--json` — output mode (currently the only mode).

## Exit codes

| code | meaning                                              |
|------|------------------------------------------------------|
| 0    | payload built + audited; envelope on stdout          |
| 1    | manifest missing OR payload still >500 bytes after truncate|
| 2    | usage error                                          |

## Output schema (also written to dispatch.jsonl preview)

```json
{
  "role":       "plugin-worker" | "builtin-skill",
  "target":     "writing-stub",
  "task":       "T-007"            // omitted if no --task
  "user_input": "...",             // ≤200 chars, ellipsis if truncated
  "context":    {"plugins": ["..."], "active_phase": "draft"}
}
```
