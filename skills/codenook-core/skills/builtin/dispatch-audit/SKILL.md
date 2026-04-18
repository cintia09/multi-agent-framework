# dispatch-audit (builtin skill)

## Role

Redacted append-only logger for sub-agent dispatches. Every time the main
session (or orchestrator-tick) dispatches a helper/worker agent, it calls
this skill to log a one-line audit record AND enforce the 500-byte
payload hard limit (architecture §3.1.7 / v6 decision #T-3). The
limit is measured in UTF-8 bytes (CJK-safe).

## CLI

```
emit.sh --role <name> --payload <json-string> [--workspace <dir>]
```

- `--role` e.g. `planner`, `coder`, `reviewer` — the downstream role.
- `--payload` raw JSON string; must parse and be ≤ 500 bytes (UTF-8) total.
- `--workspace` defaults to `$CODENOOK_WORKSPACE`; if unset, upward search
  for a directory containing `.codenook/`.

## Exit codes

| code | meaning                                    |
|------|--------------------------------------------|
| 0    | logged                                     |
| 1    | payload > 500 bytes, or not valid JSON     |
| 2    | usage error / workspace not resolvable     |

## Log line shape

Appended to `<ws>/.codenook/history/dispatch.jsonl`:

```json
{
  "ts": "2026-04-18T12:34:56Z",
  "role": "planner",
  "payload_size": 187,
  "payload_sha256": "…",
  "payload_preview": "… first 80 chars …"
}
```

Note: full payload is **never** written — only sha256 + an 80-char
preview. Privacy by construction.

## Redaction

Before the 80-char preview is sliced, the payload is run through a
best-effort secret scrubber that masks common high-confidence patterns
(OpenAI `sk-` / `sk-proj-`, Anthropic `sk-ant-` / `sk-ant-api03-`, AWS
`AKIA…`, GitHub `ghp_` / `gho_` / `github_pat_`, and PEM private-key
headers) with the literal string `[REDACTED]`. This is best-effort
defence-in-depth, not a substitute for keeping secrets out of payloads
(callers SHOULD pass `${env:NAME}` placeholders, not resolved values).

## M1 notes

- Single-line append; no explicit flock (line sizes are far below
  `PIPE_BUF` so concurrent `write()` calls stay line-atomic on POSIX).
- `.codenook/history/` auto-created when missing.
