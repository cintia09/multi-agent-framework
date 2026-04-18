# config-validate (builtin skill)

## Role

Field-level validator for merged CodeNook configs (output of `config-resolve`).
Checks types, ranges, enums; emits warnings for deprecated keys. Separate
from `config-resolve`'s top-key whitelist (which is about routing only).

## CLI

```
validate.sh --config <merged.json> [--schema <config-schema.yaml>] [--json]
```

- `--config` required; must be valid JSON object.
- `--schema` defaults to the packaged `config-schema.yaml` shipped alongside
  this SKILL.
- `--json` switches stdout to `{ ok, errors, warnings }` (stderr still carries
  human-readable lines).

## Exit codes

| code | meaning                                         |
|------|-------------------------------------------------|
| 0    | no errors (warnings permitted)                  |
| 1    | at least one validation error                   |
| 2    | usage error (missing/bad flags, missing files)  |

## Error shape (--json)

```json
{
  "ok": false,
  "errors": [{ "path": "models.default", "msg": "must be at least 1 char(s)" }],
  "warnings": [{ "path": "legacy_router", "msg": "deprecated key" }]
}
```

## Schema DSL

See `config-schema.yaml` header comments. Supports `string|integer|object`,
`required`, `min_length`, `min`, `enum`, nested `fields`. Unknown top-level
keys are tolerated (routing-layer decides those); only entries in the
schema's `deprecated:` list emit warnings.

## Notes

- M1 scope: enough coverage for DoD fields (`models.default`, `hitl.mode`,
  `concurrency.max_parallel`). Grow the schema as subsystems land.
- M5 will layer plugin-specific schemas on top (see implementation-v6.md
  §M5.2).
