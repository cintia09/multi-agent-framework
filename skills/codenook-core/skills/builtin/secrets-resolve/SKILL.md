# secrets-resolve (builtin skill)

## Role

Resolves `${env:NAME}` and `${file:path}` placeholders inside a merged
config JSON. Emits a new JSON with secrets inlined. Never leaks resolved
values to stderr/logs — only placeholder *keys* (when missing).

Implements implementation-v6.md §M5.3 (simplified for M1: operates on the
already-merged config produced by `config-resolve`, rather than reading
`.codenook/secrets.yaml` directly).

## CLI

```
resolve.sh --config <merged.json> [--allow-missing]
```

- `--config` required.
- `--allow-missing`: env vars that are not set resolve to `""` with a
  stderr warning (keys only). Without this flag, missing env vars fail
  hard. File placeholders always fail hard on missing file.

## Exit codes

| code | meaning                                           |
|------|---------------------------------------------------|
| 0    | all placeholders resolved (or warnings only)      |
| 1    | at least one unresolvable placeholder / nested use|
| 2    | usage error                                       |

## Placeholder rules

- `${env:NAME}`  — reads `os.environ[NAME]`.
- `${file:path}` — reads file, strips surrounding whitespace. Supports
  relative and absolute paths.
- Multiple placeholders per string: all replaced.
- Walks into dicts and arrays recursively.
- **Nested placeholders** (e.g. `${env:${env:VAR_NAME}}`) are disallowed
  by design in M1 — they complicate audit/redaction and invite injection.

## Security contract

On success (exit 0) the stderr stream MUST NOT contain any resolved
value. Only placeholder *keys* appear in warnings/errors. Test
`m1-secrets-resolve.bats::SECURITY:` enforces this.

## ⚠️ SECURITY

stdout contains plaintext resolved secrets. Callers MUST NOT pipe stdout
into history/logs/dispatch-audit. Pipe directly to the consuming
sub-agent or to a file with mode 600 in workspace-private storage only.
