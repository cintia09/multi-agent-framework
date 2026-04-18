# plugin-id-validate — Install gate G03

Validates the `id` field of a staged plugin.

## CLI

```
id-validate.sh --src <dir> [--workspace <dir>] [--upgrade] [--json]
```

## Checks

1. `id` matches `^[a-z][a-z0-9-]{2,30}$` (3..31 chars, lowercase
   letters, digits, hyphens; must start with a letter).
2. `id` is not in the reserved set: `core`, `builtin`, `generic`,
   `codenook`.
3. If `--workspace` is supplied: `id` is not already installed at
   `<workspace>/.codenook/plugins/<id>/`, **unless** `--upgrade` is
   also supplied.
