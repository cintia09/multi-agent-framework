# plugin-path-normalize — Install gate G11

Stricter cousin of G01.  Rejects:

1. **Any** symlink under `<src>` (even ones whose target lies inside
   the tree). Plugins ship as plain files; symlinks are forbidden so
   that the on-disk shape is exactly what the schema declares.
2. Any YAML scalar string (in any `*.yaml` / `*.yml` under `<src>`)
   that names a path with one of:
   - leading `/`  (absolute)
   - leading `~`  (home-expansion)
   - any `..` segment (`../foo`, `foo/..`, `a/../b`)

A "path-shaped" string is defined heuristically: contains `/` OR
ends in `.sh`/`.py`/`.md`/`.yaml`/`.yml`/`.json`.

## CLI

```
path-normalize.sh --src <dir> [--json]
```
